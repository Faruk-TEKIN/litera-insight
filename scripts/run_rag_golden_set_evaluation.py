from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.database import SessionLocal
from backend.app.evaluation.rag_golden_set import (
    RagGoldenSetConfig,
    RagGoldenSetEvaluator,
    current_git_commit,
    load_validated_golden_set,
    new_run_id,
)
from backend.app.services.embedding_service import get_embedding_service
from backend.app.services.ollama_service import OllamaService


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run diagnostic RAG golden-set evaluation.")
    parser.add_argument(
        "--golden-file",
        type=Path,
        default=PROJECT_ROOT / "evaluation/rag_golden_set_10_questions.json",
    )
    parser.add_argument(
        "--mode",
        choices=("retrieval_only", "rag_end_to_end", "direct_llm_baseline", "multi_turn_memory"),
        default="rag_end_to_end",
    )
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "evaluation/runs")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--retry-count", type=int, default=0)
    parser.add_argument("--prompt-version", default="chat_orchestrator_v1")
    parser.add_argument("--database-snapshot", default=None)
    parser.add_argument("--retrieval-config-version", default="rag_retrieval_v1")
    parser.add_argument("--retrieval-mode", choices=("hybrid", "vector", "bm25"), default="hybrid")
    parser.add_argument("--fusion-method", choices=("rrf", "weighted"), default="rrf")
    parser.add_argument("--vector-top-k", type=int, default=None)
    parser.add_argument("--bm25-top-k", type=int, default=None)
    parser.add_argument("--final-top-k", type=int, default=None)
    parser.add_argument("--force-rag", action="store_true")
    parser.add_argument("--use-llm-router", action="store_true")
    parser.add_argument("--disable-keyword", action="store_true")
    parser.add_argument(
        "--no-apply-golden-filters",
        action="store_true",
        help="Do not merge golden expected filters into retrieval filters.",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.top_k < 1:
        print("--top-k must be greater than zero.", file=sys.stderr)
        return 2
    if args.timeout_seconds < 1:
        print("--timeout-seconds must be greater than zero.", file=sys.stderr)
        return 2
    if args.retry_count < 0:
        print("--retry-count cannot be negative.", file=sys.stderr)
        return 2

    try:
        questions = load_validated_golden_set(args.golden_file)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    run_id = args.run_id or new_run_id(args.mode)
    llm_service = OllamaService(model=args.model)
    config = RagGoldenSetConfig(
        run_id=run_id,
        mode=args.mode,
        golden_set_path=args.golden_file,
        output_dir=args.output_dir,
        model_name=llm_service.model,
        temperature=args.temperature,
        top_k=args.top_k,
        max_tokens=args.max_tokens,
        timeout_seconds=args.timeout_seconds,
        retry_count=args.retry_count,
        prompt_version=args.prompt_version,
        database_snapshot=args.database_snapshot,
        retrieval_config_version=args.retrieval_config_version,
        retrieval_mode=args.retrieval_mode,
        fusion_method=args.fusion_method,
        vector_top_k=args.vector_top_k,
        bm25_top_k=args.bm25_top_k,
        final_top_k=args.final_top_k,
        force_rag=args.force_rag,
        use_llm_router=args.use_llm_router,
        use_keyword=not args.disable_keyword,
        apply_golden_filters=not args.no_apply_golden_filters,
        resume=args.resume,
        retry_failed=args.retry_failed,
        code_commit_hash=current_git_commit(PROJECT_ROOT),
    )

    db = SessionLocal()
    try:
        evaluator = RagGoldenSetEvaluator(
            db=db,
            config=config,
            embedding_service=get_embedding_service(),
            ollama_service=llm_service,
        )
        run_dir = evaluator.run(questions)
    finally:
        db.close()

    print(f"RAG golden-set evaluation written to {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
