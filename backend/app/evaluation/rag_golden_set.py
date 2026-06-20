from __future__ import annotations

import asyncio
import csv
import json
import re
import subprocess
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.evaluation.retrieval_metrics import load_golden_questions, score_retrieval
from backend.app.evaluation.schemas import GoldenQuestion
from backend.app.services.assistant_prompts import ACADEMIC_ASSISTANT_SYSTEM_PROMPT
from backend.app.schemas.retrieval import RetrievedArticle, RetrievalFilters, RouteDecision
from backend.app.services.chat_orchestrator import ChatOrchestrator
from backend.app.services.conversation_memory_service import ConversationMemory
from backend.app.services.ollama_service import OllamaService, OllamaServiceError
from backend.app.services.rag_router_service import RagRouterService
from backend.app.services.retrieval_service import RetrievalService, build_rag_context


SUPPORTED_MODES = {"retrieval_only", "rag_end_to_end", "direct_llm_baseline", "multi_turn_memory"}
FAILURE_NONE = "none"


class RagGoldenSetConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: str
    mode: str = "rag_end_to_end"
    golden_set_path: Path
    output_dir: Path
    model_name: str = settings.MODEL_NAME
    temperature: float = 0.0
    top_k: int = settings.RAG_TOP_K
    max_tokens: int | None = None
    timeout_seconds: int = 120
    retry_count: int = 0
    prompt_version: str = "chat_orchestrator_v1"
    database_snapshot: str | None = None
    embedding_model: str = settings.EMBEDDING_MODEL_NAME
    retrieval_config_version: str = "rag_retrieval_v1"
    retrieval_mode: str = settings.RAG_RETRIEVAL_MODE
    fusion_method: str = settings.RAG_FUSION_METHOD
    vector_top_k: int | None = None
    bm25_top_k: int | None = None
    final_top_k: int | None = None
    force_rag: bool = False
    use_llm_router: bool = False
    use_keyword: bool = True
    apply_golden_filters: bool = True
    resume: bool = False
    retry_failed: bool = False
    code_commit_hash: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    def validate_runtime(self) -> None:
        if self.mode not in SUPPORTED_MODES:
            raise ValueError(f"Unsupported mode {self.mode!r}. Expected one of {sorted(SUPPORTED_MODES)}.")
        if self.top_k < 1:
            raise ValueError("top_k must be greater than zero.")
        if self.timeout_seconds < 1:
            raise ValueError("timeout_seconds must be greater than zero.")
        if self.retry_count < 0:
            raise ValueError("retry_count cannot be negative.")


class RagGoldenSetEvaluator:
    def __init__(
        self,
        db: Session,
        config: RagGoldenSetConfig,
        embedding_service,
        ollama_service: OllamaService | None = None,
        retrieval_service: RetrievalService | None = None,
        orchestrator: ChatOrchestrator | None = None,
    ):
        config.validate_runtime()
        self.db = db
        self.config = config
        self.embedding_service = embedding_service
        self.ollama_service = ollama_service or OllamaService(model=config.model_name)
        self.retrieval_service = retrieval_service or RetrievalService(
            db,
            retrieval_mode=config.retrieval_mode,
            fusion_method=config.fusion_method,
            vector_top_k=config.vector_top_k,
            bm25_top_k=config.bm25_top_k,
            final_top_k=config.final_top_k,
        )
        self.orchestrator = orchestrator or ChatOrchestrator()
        self.orchestrator.ollama_service = self.ollama_service
        self.router = (
            RagRouterService(self.ollama_service)
            if config.use_llm_router
            else RagRouterService.__new__(RagRouterService)
        )

    def run(self, questions: list[GoldenQuestion]) -> Path:
        run_dir = self.config.output_dir / self.config.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        _write_json(run_dir / "config.json", self.config.model_dump(mode="json"))

        raw_path = run_dir / "raw_outputs.jsonl"
        errors_path = run_dir / "errors.jsonl"
        completed = _completed_question_ids(raw_path, retry_failed=self.config.retry_failed) if self.config.resume else set()

        records: list[dict[str, Any]] = []
        for question, memory in self._iter_questions_with_memory(questions):
            if question.id in completed:
                continue
            record = self._run_with_retries(question, memory)
            _append_jsonl(raw_path, record)
            records.append(record)
            if record["status"] == "failed":
                _append_jsonl(errors_path, record)
            self._update_memory(memory, record)

        all_records = _latest_records_by_question(_read_jsonl(raw_path))
        write_summary_csv(run_dir / "summary_results.csv", all_records)
        _write_json(run_dir / "retrieval_metrics.json", summarize_retrieval(all_records))
        _write_json(run_dir / "citation_metrics.json", summarize_citations(all_records))
        write_answer_review_sheet(run_dir / "answer_review_sheet.csv", all_records)
        write_failure_analysis(run_dir / "failure_analysis.md", all_records)
        write_report(run_dir / "report.md", self.config, all_records)
        return run_dir

    def _iter_questions_with_memory(
        self,
        questions: list[GoldenQuestion],
    ) -> list[tuple[GoldenQuestion, ConversationMemory]]:
        if self.config.mode == "multi_turn_memory":
            grouped: dict[str, list[GoldenQuestion]] = defaultdict(list)
            for question in questions:
                if question.scenario_id:
                    grouped[question.scenario_id].append(question)
            ordered: list[tuple[GoldenQuestion, ConversationMemory]] = []
            for scenario_id in sorted(grouped):
                memory = ConversationMemory(summary=None, recent_messages=[], previous_sources=[])
                for question in sorted(grouped[scenario_id], key=lambda item: item.turn_index or 0):
                    ordered.append((question, memory))
            return ordered

        return [
            (question, ConversationMemory(summary=None, recent_messages=[], previous_sources=[]))
            for question in questions
            if not question.is_multi_turn
        ]

    def _run_with_retries(self, question: GoldenQuestion, memory: ConversationMemory) -> dict[str, Any]:
        attempts = self.config.retry_count + 1
        last_record: dict[str, Any] | None = None
        for attempt in range(1, attempts + 1):
            record = self._run_one(question, memory, attempt=attempt)
            last_record = record
            if record["status"] == "completed":
                return record
            if attempt < attempts:
                time.sleep(min(2 ** (attempt - 1), 8))
        return last_record or self._failed_record(question, "No evaluation attempt ran.", attempt=0)

    def _run_one(self, question: GoldenQuestion, memory: ConversationMemory, attempt: int) -> dict[str, Any]:
        start = time.perf_counter()
        try:
            if self.config.mode == "direct_llm_baseline":
                answer = self.ollama_service.chat_generate(_direct_llm_messages(question.question, memory))
                latency_ms = (time.perf_counter() - start) * 1000
                return self._record(
                    question=question,
                    memory=memory,
                    attempt=attempt,
                    latency_ms=latency_ms,
                    final_answer=answer,
                    status="completed",
                )

            route_decision = self._route(question, memory)
            route_decision.top_k = question.top_k or self.config.top_k
            router_filters = route_decision.filters
            applied_filters = _applied_filters(router_filters, question, self.config.apply_golden_filters)
            route_decision.filters = applied_filters

            retrieved = self._retrieve_if_needed(question, route_decision)
            final_answer = ""
            if self.config.mode in {"rag_end_to_end", "multi_turn_memory"}:
                rag_context = build_rag_context(retrieved) if route_decision.use_rag else ""
                messages = self.orchestrator._build_answer_messages(
                    question.question,
                    memory,
                    route_decision,
                    rag_context,
                    retrieved,
                )
                final_answer = self.ollama_service.chat_generate(messages)

            latency_ms = (time.perf_counter() - start) * 1000
            return self._record(
                question=question,
                memory=memory,
                attempt=attempt,
                latency_ms=latency_ms,
                route_decision=route_decision,
                router_filters=router_filters,
                retrieved=retrieved,
                final_answer=final_answer,
                status="completed",
            )
        except (OllamaServiceError, Exception) as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            return self._record(
                question=question,
                memory=memory,
                attempt=attempt,
                latency_ms=latency_ms,
                final_answer="",
                status="failed",
                error=str(exc),
            )

    def _route(self, question: GoldenQuestion, memory: ConversationMemory) -> RouteDecision:
        if self.config.use_llm_router:
            route_decision = asyncio.run(self.router.route(question.question, memory))
        else:
            route_decision = self.router.fallback_route(question.question, memory.previous_sources)
        if self.config.force_rag:
            route_decision.use_rag = True
            route_decision.reason = f"{route_decision.reason} Forced RAG for golden-set evaluation.".strip()
        return route_decision

    def _retrieve_if_needed(self, question: GoldenQuestion, route_decision: RouteDecision) -> list[RetrievedArticle]:
        should_retrieve = (
            route_decision.use_rag
            or self.config.force_rag
            or self.config.mode == "retrieval_only"
        )
        if not should_retrieve:
            return []

        query_embedding = None
        if route_decision.sort_by == "relevance" and self.config.retrieval_mode != "bm25":
            query_embedding = self.embedding_service.embed_query(route_decision.rewritten_query)
        return self.retrieval_service.retrieve(
            query_embedding=query_embedding,
            filters=route_decision.filters,
            top_k=question.top_k or self.config.top_k,
            sort_by=route_decision.sort_by,
            query_text=route_decision.rewritten_query if self.config.use_keyword else None,
        )

    def _record(
        self,
        question: GoldenQuestion,
        memory: ConversationMemory,
        attempt: int,
        latency_ms: float,
        final_answer: str,
        status: str,
        route_decision: RouteDecision | None = None,
        router_filters: RetrievalFilters | None = None,
        retrieved: list[RetrievedArticle] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        retrieved = retrieved or []
        retrieved_ids = [item.source.article_id for item in retrieved]
        effective_top_k = question.top_k or self.config.top_k
        cited_article_ids = extract_cited_article_ids(final_answer, retrieved)
        metrics = calculate_metrics(question, retrieved_ids, cited_article_ids, final_answer, effective_top_k)
        router_filter_data = router_filters.model_dump(mode="json") if router_filters else {}
        applied_filter_data = route_decision.filters.model_dump(mode="json") if route_decision else {}
        failure_category = classify_failure(
            question=question,
            status=status,
            error=error,
            route_decision=route_decision,
            retrieved_ids=retrieved_ids,
            cited_article_ids=cited_article_ids,
            answer=final_answer,
            router_filters=router_filter_data,
            metrics=metrics,
        )

        return {
            "run_id": self.config.run_id,
            "mode": self.config.mode,
            "question_id": question.id,
            "scenario_id": question.scenario_id,
            "turn_index": question.turn_index,
            "question": question.question,
            "question_type": question.question_type or question.query_type,
            "difficulty": question.difficulty,
            "expected_article_ids": question.expected_article_ids,
            "expected_cluster_ids": question.expected_cluster_ids,
            "expected_answer_keywords": question.expected_answer_keywords,
            "expected_filters": _expected_filters(question),
            "requires_retrieval_expected": question.requires_retrieval,
            "router_decision": route_decision.model_dump(mode="json") if route_decision else None,
            "requires_retrieval_actual": bool(route_decision.use_rag) if route_decision else None,
            "rewritten_query": route_decision.rewritten_query if route_decision else None,
            "router_filters": router_filter_data,
            "applied_filters": applied_filter_data,
            "retrieved_articles": retrieved_articles_payload(retrieved),
            "retrieved_article_ids": retrieved_ids,
            "context_article_ids": retrieved_ids,
            "final_answer": final_answer,
            "cited_article_ids": cited_article_ids,
            "previous_cited_articles": [source.get("article_id") for source in memory.previous_sources],
            "metrics": metrics,
            "latency_ms": latency_ms,
            "model_name": self.config.model_name,
            "temperature": self.config.temperature,
            "top_k": effective_top_k,
            "attempt": attempt,
            "created_at": datetime.now(UTC).isoformat(),
            "status": status,
            "error": error,
            "failure_category": failure_category,
        }

    def _failed_record(self, question: GoldenQuestion, error: str, attempt: int) -> dict[str, Any]:
        return self._record(
            question=question,
            memory=ConversationMemory(summary=None, recent_messages=[], previous_sources=[]),
            attempt=attempt,
            latency_ms=0.0,
            final_answer="",
            status="failed",
            error=error,
        )

    def _update_memory(self, memory: ConversationMemory, record: dict[str, Any]) -> None:
        if self.config.mode != "multi_turn_memory" or record["status"] != "completed":
            return
        memory.recent_messages.append(SimpleNamespace(role="user", content=record["question"]))
        memory.recent_messages.append(SimpleNamespace(role="agent", content=record["final_answer"]))
        for source in record.get("retrieved_articles") or []:
            if source.get("article_id") is not None:
                memory.previous_sources.append(source)
        memory.previous_sources = _dedupe_memory_sources(memory.previous_sources)


def load_validated_golden_set(path: Path) -> list[GoldenQuestion]:
    questions = load_golden_questions(path)
    seen: set[str] = set()
    duplicates: list[str] = []
    for question in questions:
        if question.id in seen:
            duplicates.append(question.id)
        seen.add(question.id)
    if duplicates:
        raise ValueError(f"Duplicate golden question ids: {', '.join(sorted(set(duplicates)))}")
    return questions


def calculate_metrics(
    question: GoldenQuestion,
    retrieved_article_ids: list[int],
    cited_article_ids: list[int],
    answer: str,
    top_k: int,
) -> dict[str, Any]:
    if question.expected_article_ids:
        retrieval_at_k = score_retrieval(question.expected_article_ids, retrieved_article_ids, top_k)
        hit_at_1 = bool(score_retrieval(question.expected_article_ids, retrieved_article_ids, 1)["hit_at_k"])
        hit_at_3 = bool(score_retrieval(question.expected_article_ids, retrieved_article_ids, min(3, top_k))["hit_at_k"])
        hit_at_5 = bool(score_retrieval(question.expected_article_ids, retrieved_article_ids, min(5, top_k))["hit_at_k"])
    else:
        retrieval_at_k = {
            "hit_at_k": None,
            "recall_at_k": None,
            "precision_at_k": None,
            "mrr": None,
            "ndcg_at_k": None,
        }
        hit_at_1 = hit_at_3 = hit_at_5 = None

    expected = set(question.expected_article_ids)
    cited = _dedupe(cited_article_ids)
    correct_citations = [article_id for article_id in cited if article_id in expected]
    citation_precision = len(correct_citations) / len(cited) if cited else 0.0
    citation_recall = len(correct_citations) / len(expected) if expected else None
    keyword_hits = [
        keyword
        for keyword in question.expected_answer_keywords
        if keyword.lower() in (answer or "").lower()
    ]

    return {
        "hit_at_1": hit_at_1,
        "hit_at_3": hit_at_3,
        "hit_at_5": hit_at_5,
        "hit_at_k": retrieval_at_k["hit_at_k"],
        "recall_at_k": retrieval_at_k["recall_at_k"],
        "precision_at_k": retrieval_at_k["precision_at_k"],
        "mrr": retrieval_at_k["mrr"],
        "ndcg_at_k": retrieval_at_k["ndcg_at_k"],
        "citation_precision": citation_precision,
        "citation_recall": citation_recall,
        "citation_count": len(cited),
        "answer_keyword_hits": keyword_hits,
        "answer_keyword_coverage": len(keyword_hits) / len(question.expected_answer_keywords)
        if question.expected_answer_keywords else None,
    }


def classify_failure(
    question: GoldenQuestion,
    status: str,
    error: str | None,
    route_decision: RouteDecision | None,
    retrieved_ids: list[int],
    cited_article_ids: list[int],
    answer: str,
    router_filters: dict[str, Any],
    metrics: dict[str, Any],
) -> str:
    if status != "completed" or error:
        return "timeout_or_system_error"
    if question.requires_retrieval and route_decision and not route_decision.use_rag:
        return "router_error"
    if _filter_mismatches(_expected_filters(question), router_filters):
        return "filter_extraction_error"
    if question.expected_article_ids and not set(question.expected_article_ids).intersection(retrieved_ids):
        return "retrieval_miss"
    if question.expected_article_ids and retrieved_ids:
        expected_positions = [
            retrieved_ids.index(article_id) + 1
            for article_id in question.expected_article_ids
            if article_id in retrieved_ids
        ]
        if expected_positions and min(expected_positions) > min(3, len(retrieved_ids)):
            return "reranking_error"
    if answer and question.expected_article_ids and metrics.get("citation_recall") is not None:
        if metrics["citation_recall"] < 1.0:
            return "citation_error"
    if answer and question.expected_answer_keywords and metrics.get("answer_keyword_coverage") == 0:
        return "generation_error"
    return FAILURE_NONE


def extract_cited_article_ids(answer: str, retrieved: list[RetrievedArticle]) -> list[int]:
    source_to_article = {item.source.source_id.upper(): item.source.article_id for item in retrieved}
    cited: list[int] = []
    for match in re.finditer(r"\[(S\d+)\]", answer or "", flags=re.IGNORECASE):
        source_id = match.group(1).upper()
        article_id = source_to_article.get(source_id)
        if article_id is not None and article_id not in cited:
            cited.append(article_id)
    return cited


def retrieved_articles_payload(retrieved: list[RetrievedArticle]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for rank, item in enumerate(retrieved, start=1):
        source = item.source
        payload.append(
            {
                "rank": rank,
                "source_id": source.source_id,
                "article_id": source.article_id,
                "title": source.title,
                "score": source.score,
                "vector_score": source.vector_score,
                "bm25_score": source.bm25_score,
                "fusion_score": source.fusion_score,
                "reranker_score": source.reranker_score,
                "retrieval_source": source.retrieval_source,
                "cluster_id": source.cluster_id,
                "url": source.url,
                "doi": source.doi,
                "publish_date": source.publish_date.isoformat() if source.publish_date else None,
            }
        )
    return payload


def write_summary_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fieldnames = [
        "question_id",
        "scenario_id",
        "turn_index",
        "question_type",
        "difficulty",
        "requires_retrieval_expected",
        "requires_retrieval_actual",
        "hit_at_1",
        "hit_at_3",
        "hit_at_5",
        "recall_at_k",
        "mrr",
        "citation_precision",
        "citation_recall",
        "answer_keyword_coverage",
        "latency_ms",
        "status",
        "failure_category",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            metrics = record.get("metrics") or {}
            writer.writerow(
                {
                    "question_id": record.get("question_id"),
                    "scenario_id": record.get("scenario_id"),
                    "turn_index": record.get("turn_index"),
                    "question_type": record.get("question_type"),
                    "difficulty": record.get("difficulty"),
                    "requires_retrieval_expected": record.get("requires_retrieval_expected"),
                    "requires_retrieval_actual": record.get("requires_retrieval_actual"),
                    "hit_at_1": metrics.get("hit_at_1"),
                    "hit_at_3": metrics.get("hit_at_3"),
                    "hit_at_5": metrics.get("hit_at_5"),
                    "recall_at_k": metrics.get("recall_at_k"),
                    "mrr": metrics.get("mrr"),
                    "citation_precision": metrics.get("citation_precision"),
                    "citation_recall": metrics.get("citation_recall"),
                    "answer_keyword_coverage": metrics.get("answer_keyword_coverage"),
                    "latency_ms": record.get("latency_ms"),
                    "status": record.get("status"),
                    "failure_category": record.get("failure_category"),
                }
            )


def write_answer_review_sheet(path: Path, records: list[dict[str, Any]]) -> None:
    fieldnames = [
        "question_id",
        "question",
        "expected_article_ids",
        "retrieved_article_ids",
        "cited_article_ids",
        "answer_keyword_coverage",
        "manual_completeness_score",
        "manual_groundedness_score",
        "manual_clarity_score",
        "hallucination_flag",
        "failure_category",
        "final_answer",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            metrics = record.get("metrics") or {}
            writer.writerow(
                {
                    "question_id": record.get("question_id"),
                    "question": record.get("question"),
                    "expected_article_ids": json.dumps(record.get("expected_article_ids") or []),
                    "retrieved_article_ids": json.dumps(record.get("retrieved_article_ids") or []),
                    "cited_article_ids": json.dumps(record.get("cited_article_ids") or []),
                    "answer_keyword_coverage": metrics.get("answer_keyword_coverage"),
                    "manual_completeness_score": "",
                    "manual_groundedness_score": "",
                    "manual_clarity_score": "",
                    "hallucination_flag": "",
                    "failure_category": record.get("failure_category"),
                    "final_answer": record.get("final_answer"),
                }
            )


def summarize_retrieval(records: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [record for record in records if record.get("status") == "completed"]
    return {
        "question_count": len(records),
        "completed_count": len(completed),
        "hit_rate_at_1": _mean_bool(_metric_values(completed, "hit_at_1")),
        "hit_rate_at_3": _mean_bool(_metric_values(completed, "hit_at_3")),
        "hit_rate_at_5": _mean_bool(_metric_values(completed, "hit_at_5")),
        "mean_recall_at_k": _mean_number(_metric_values(completed, "recall_at_k")),
        "mean_precision_at_k": _mean_number(_metric_values(completed, "precision_at_k")),
        "mean_mrr": _mean_number(_metric_values(completed, "mrr")),
        "mean_ndcg_at_k": _mean_number(_metric_values(completed, "ndcg_at_k")),
        "mean_latency_ms": _mean_number([record.get("latency_ms") for record in completed]),
    }


def summarize_citations(records: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [
        record for record in records
        if record.get("status") == "completed" and record.get("mode") != "retrieval_only"
    ]
    return {
        "answer_count": len(completed),
        "mean_citation_precision": _mean_number(_metric_values(completed, "citation_precision")),
        "mean_citation_recall": _mean_number(_metric_values(completed, "citation_recall")),
        "mean_citation_count": _mean_number(_metric_values(completed, "citation_count")),
    }


def write_failure_analysis(path: Path, records: list[dict[str, Any]]) -> None:
    counts = Counter(record.get("failure_category") or FAILURE_NONE for record in records)
    lines = ["# Failure Analysis", "", "## Counts", ""]
    for category, count in sorted(counts.items()):
        lines.append(f"- {category}: {count}")
    lines.extend(["", "## Failed Questions", ""])
    for record in records:
        if record.get("failure_category") in (None, FAILURE_NONE):
            continue
        error = record.get("error")
        error_text = f", error={str(error)[:180]}" if error else ""
        lines.append(
            f"- {record.get('question_id')}: {record.get('failure_category')} "
            f"(status={record.get('status')}, latency_ms={record.get('latency_ms'):.2f}{error_text})"
        )
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def write_report(path: Path, config: RagGoldenSetConfig, records: list[dict[str, Any]]) -> None:
    retrieval = summarize_retrieval(records)
    citations = summarize_citations(records)
    failures = Counter(record.get("failure_category") or FAILURE_NONE for record in records)
    lines = [
        "# RAG Golden Set Evaluation Report",
        "",
        f"- run_id: {config.run_id}",
        f"- mode: {config.mode}",
        f"- model_name: {config.model_name}",
        f"- top_k: {config.top_k}",
        f"- golden_set_path: {config.golden_set_path}",
        f"- generated_at: {datetime.now(UTC).isoformat()}",
        "",
        "## Retrieval Metrics",
        "",
        f"- question_count: {retrieval['question_count']}",
        f"- hit_rate_at_1: {_fmt(retrieval['hit_rate_at_1'])}",
        f"- hit_rate_at_3: {_fmt(retrieval['hit_rate_at_3'])}",
        f"- hit_rate_at_5: {_fmt(retrieval['hit_rate_at_5'])}",
        f"- mean_recall_at_k: {_fmt(retrieval['mean_recall_at_k'])}",
        f"- mean_mrr: {_fmt(retrieval['mean_mrr'])}",
        "",
        "## Citation Metrics",
        "",
        f"- answer_count: {citations['answer_count']}",
        f"- mean_citation_precision: {_fmt(citations['mean_citation_precision'])}",
        f"- mean_citation_recall: {_fmt(citations['mean_citation_recall'])}",
        "",
        "## Failure Categories",
        "",
    ]
    for category, count in sorted(failures.items()):
        lines.append(f"- {category}: {count}")
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def current_git_commit(project_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def new_run_id(mode: str) -> str:
    return f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{mode}"


def _direct_llm_messages(question: str, memory: ConversationMemory) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": ACADEMIC_ASSISTANT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"""
Conversation memory:
{memory.as_prompt_block() or "No prior context."}

Instructions:
Answer directly without using local database retrieval. Do not invent stored paper titles, article IDs, DOI values, or database statistics.

User message:
{question}

Assistant:
""".strip(),
        },
    ]


def _applied_filters(
    router_filters: RetrievalFilters,
    question: GoldenQuestion,
    apply_golden_filters: bool,
) -> RetrievalFilters:
    if not apply_golden_filters:
        return router_filters
    constraints = {}
    constraints.update(question.filters)
    constraints.update(question.expected_filters)
    if not constraints:
        return router_filters
    data = router_filters.model_dump()
    data.update(constraints)
    return RetrievalFilters.model_validate(data)


def _expected_filters(question: GoldenQuestion) -> dict[str, Any]:
    return question.expected_filters or {}


def _filter_mismatches(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    if not expected:
        return False
    for key, expected_value in expected.items():
        actual_value = actual.get(key)
        if actual_value != expected_value:
            return True
    return False


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def _latest_records_by_question(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for record in records:
        question_id = record.get("question_id")
        if not question_id:
            continue
        if question_id not in latest_by_id:
            order.append(question_id)
        latest_by_id[question_id] = record
    return [latest_by_id[question_id] for question_id in order]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _completed_question_ids(raw_path: Path, retry_failed: bool) -> set[str]:
    completed: set[str] = set()
    for record in _read_jsonl(raw_path):
        if record.get("status") == "completed" or (record.get("status") == "failed" and not retry_failed):
            completed.add(record["question_id"])
    return completed


def _dedupe(values: list[int]) -> list[int]:
    seen: set[int] = set()
    deduped: list[int] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _dedupe_memory_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[int] = set()
    for source in reversed(sources):
        article_id = source.get("article_id")
        if article_id in seen:
            continue
        if article_id is not None:
            seen.add(article_id)
        deduped.append(source)
    return list(reversed(deduped))[-10:]


def _metric_values(records: list[dict[str, Any]], metric_name: str) -> list[Any]:
    return [(record.get("metrics") or {}).get(metric_name) for record in records]


def _mean_bool(values: list[Any]) -> float:
    concrete = [value for value in values if value is not None]
    return sum(1 for value in concrete if value) / len(concrete) if concrete else 0.0


def _mean_number(values: list[Any]) -> float:
    concrete = [float(value) for value in values if value is not None]
    return sum(concrete) / len(concrete) if concrete else 0.0


def _fmt(value: float) -> str:
    return f"{value:.4f}"
