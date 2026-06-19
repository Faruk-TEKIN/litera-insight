# RAG Golden Set Evaluation Mechanism — Professional Prompt & Implementation Plan

## Purpose

This document provides a professional prompt and a step-by-step implementation plan for building a golden set evaluation mechanism for an academic publication intelligence and analysis platform.

The goal is not only to ask questions to the model and save answers, but to evaluate the full RAG pipeline in a controlled, repeatable, and debuggable way.

The evaluation mechanism should help answer these questions:

- Did the router correctly decide whether retrieval was needed?
- Did query rewriting improve or damage the original user question?
- Did the retriever return the expected papers?
- Did the reranker place the most relevant papers near the top?
- Did the LLM use the retrieved context correctly?
- Did the final answer cite the correct sources?
- Did the answer contain unsupported claims or hallucinations?
- Did the system behave consistently across repeated runs?

---

# 1. Master Prompt

Use the following prompt with an AI coding assistant, senior engineer, or yourself while designing the evaluation mechanism.

```text
You are a Senior AI Engineer specialized in Retrieval-Augmented Generation, LLM evaluation, information retrieval, academic search systems, and production-grade evaluation pipelines.

I am building an academic publication intelligence and analysis platform. The platform collects papers from sources such as arXiv, OpenAlex, and Semantic Scholar, stores them in PostgreSQL with pgvector, generates embeddings with a multilingual E5 model, clusters papers with BERTopic, and provides a RAG-based academic assistant through a FastAPI backend.

The current RAG flow includes:
- A router that decides whether a user query requires retrieval.
- Query rewriting for better semantic search.
- Metadata/filter extraction such as date, source, category, citation count, DOI, or PDF availability.
- Vector retrieval over PostgreSQL + pgvector.
- Lightweight reranking using metadata and relevance signals.
- Conversation memory for follow-up questions.
- A chat orchestrator that sends retrieved context to a local LLM.
- Final answers with citations such as [S1], [S2], etc.

I have prepared a golden set of evaluation questions. I want to build a professional evaluation runner that asks each golden question to the system, captures the output, stores intermediate RAG signals, calculates metrics, and generates a report.

Do not design this as a simple script that only sends questions to the model and saves the final answers. Design it as a reproducible RAG evaluation mechanism.

Your task:
1. Analyze the project architecture and identify which parts of the RAG pipeline must be observed during evaluation.
2. Design the golden set format.
3. Design the evaluation runner architecture.
4. Define the execution modes:
   - retrieval_only
   - rag_end_to_end
   - direct_llm_baseline
   - multi_turn_memory
5. Define the data that must be captured for each question.
6. Define the output file structure.
7. Define automatic metrics for retrieval and citation quality.
8. Define semi-automatic or manual metrics for answer quality.
9. Define failure categories.
10. Define how to compare multiple evaluation runs.
11. Define safeguards for reproducibility, determinism, retries, timeouts, and resume support.
12. Provide an implementation plan in phases.
13. Explain what mistakes must be avoided.
14. Produce a final Markdown plan that can guide implementation.

Important requirements:
- The evaluation must be reproducible.
- Each run must have a unique run_id.
- The model name, temperature, top_k, prompt version, database snapshot, embedding model, and retrieval configuration must be saved.
- The script must support resume mode.
- The script must store both raw outputs and summary metrics.
- The evaluation must separate router errors, retrieval errors, reranking errors, citation errors, and generation errors.
- The system must be tested with both independent single-turn questions and multi-turn follow-up scenarios.
- Do not hide intermediate failures behind a single answer score.
- Make the plan production-oriented, skeptical, and suitable for a senior engineering review.
```

---

# 2. Evaluation Philosophy

A RAG system should not be evaluated only by reading the final answer.

In a normal LLM application, the final answer may be the main artifact. In a RAG system, however, the final answer is the result of several dependent stages:

```text
question
  ↓
routing
  ↓
query rewriting
  ↓
filter extraction
  ↓
retrieval
  ↓
reranking
  ↓
context construction
  ↓
LLM generation
  ↓
citation formatting
  ↓
final answer
```

If the answer is wrong, the reason may be:

- The router skipped retrieval.
- The rewritten query lost the original meaning.
- Metadata filters became too restrictive.
- Vector search retrieved the wrong papers.
- Reranking pushed the correct paper down.
- The LLM ignored the relevant context.
- The final answer cited the wrong source.
- The answer included unsupported claims.

Therefore, the evaluation mechanism must be designed as a diagnostic system, not only as an answer collection script.

---

# 3. Golden Set Design

## 3.1 Recommended Golden Set Fields

Each golden question should be stored in a structured format such as CSV, JSON, or JSONL.

Recommended fields:

```text
question_id
question
question_type
expected_article_ids
expected_cluster_ids
expected_answer_keywords
expected_filters
requires_retrieval
difficulty
is_multi_turn
scenario_id
turn_index
notes
```

## 3.2 Field Explanations

### `question_id`

A stable unique identifier.

Example:

```text
Q001
Q002
Q003
```

This is required for resume support, debugging, and run comparison.

### `question`

The exact user question to send to the system.

The wording should not change between runs unless the golden set version changes.

### `question_type`

Used to analyze performance by category.

Recommended types:

```text
exact_paper_lookup
semantic_topic_search
comparative_question
metadata_filter_question
cluster_based_question
recent_or_trending_question
multi_turn_follow_up
out_of_domain
```

### `expected_article_ids`

The paper IDs that should ideally appear in the retrieved results or cited sources.

This is the most important field for retrieval evaluation.

### `expected_cluster_ids`

Useful if a question is about a topic or cluster rather than a specific paper.

### `expected_answer_keywords`

Important concepts that should appear in the final answer.

These should not be used as the only quality metric, but they are useful for lightweight answer coverage checks.

### `expected_filters`

The expected filters that the router or query analyzer should extract.

Example:

```json
{
  "year_min": 2023,
  "category": "cs.AI",
  "has_pdf": true
}
```

### `requires_retrieval`

Boolean value.

This is required to evaluate the routing decision.

### `difficulty`

Recommended values:

```text
easy
medium
hard
```

### `scenario_id` and `turn_index`

Required for multi-turn evaluation.

Example:

```text
scenario_id: S001
turn_index: 1
```

---

# 4. Golden Set Question Categories

## 4.1 Exact Paper Lookup

Purpose:

Test whether the system can retrieve a specific known paper.

Example:

```text
What is the main contribution of the paper titled "X"?
```

Expected behavior:

- The exact paper should appear in top-k retrieval.
- The answer should cite that paper.
- The answer should not invent details.

## 4.2 Semantic Topic Search

Purpose:

Test whether the system can retrieve relevant papers by meaning, not only keywords.

Example:

```text
Which studies discuss improving retrieval quality in RAG systems?
```

Expected behavior:

- Relevant papers should appear in top-k.
- The system should summarize shared themes.
- Citations should support the claims.

## 4.3 Metadata Filter Question

Purpose:

Test whether the router and retrieval service correctly extract and apply filters.

Example:

```text
Show recent papers after 2023 about retrieval augmented generation with available PDF links.
```

Expected behavior:

- The extracted filters should match the expected filters.
- Retrieved papers should satisfy the filters.
- The answer should not include papers outside the filter constraints.

## 4.4 Comparative Question

Purpose:

Test answer synthesis across multiple retrieved papers.

Example:

```text
Compare the main differences between dense retrieval and hybrid retrieval approaches in these papers.
```

Expected behavior:

- Multiple relevant sources should be retrieved.
- The final answer should compare, not only list.
- Citations should be attached to specific claims.

## 4.5 Cluster-Based Question

Purpose:

Test whether topic clustering metadata is useful in the RAG experience.

Example:

```text
What are the main themes in the cluster about graph neural networks?
```

Expected behavior:

- The correct cluster should be found.
- Representative papers should be included.
- The answer should reflect the cluster theme.

## 4.6 Multi-Turn Follow-Up

Purpose:

Test conversation memory.

Example:

```text
Turn 1: List three important papers about RAG evaluation.
Turn 2: Summarize the second one.
Turn 3: Which of these has a PDF link?
```

Expected behavior:

- The system should remember cited papers from the previous answer.
- Follow-up references such as "the second one" should resolve correctly.
- The answer should not perform an unrelated fresh search unless needed.

## 4.7 Out-of-Domain Question

Purpose:

Test assistant boundaries.

Example:

```text
Give me a dinner recipe.
```

Expected behavior:

- The assistant should refuse or redirect politely.
- It should explain that it is an academic publication assistant.
- It should not answer unrelated general-purpose questions.

---

# 5. Evaluation Runner Architecture

Recommended module structure:

```text
evaluation_runner/
  config_loader
  golden_set_loader
  session_manager
  rag_client
  retrieval_client
  direct_llm_client
  response_recorder
  metrics_engine
  failure_analyzer
  report_generator
```

## 5.1 `config_loader`

Responsible for loading evaluation settings.

Must capture:

```text
run_id
golden_set_path
mode
api_base_url
model_name
temperature
top_k
max_tokens
timeout_seconds
retry_count
database_snapshot
embedding_model
prompt_version
retrieval_config_version
output_dir
```

Why this matters:

Evaluation is only useful if the run is reproducible. If model, top_k, temperature, prompt, or database state changes silently, metrics cannot be compared reliably.

## 5.2 `golden_set_loader`

Responsible for:

- Loading the golden set.
- Validating required fields.
- Checking duplicate question IDs.
- Checking missing expected article IDs.
- Separating single-turn and multi-turn cases.
- Optionally checking whether expected article IDs exist in the database.

## 5.3 `session_manager`

Responsible for session isolation.

Recommended rule:

```text
Independent questions must use fresh sessions.
Multi-turn scenarios must reuse the same session within the scenario.
```

Reason:

Conversation memory can contaminate independent evaluation questions.

## 5.4 `rag_client`

Responsible for calling the actual backend RAG endpoint.

This should be the main evaluation target because the project is not only an LLM. The system includes routing, query rewriting, retrieval, reranking, memory, and citation formatting.

Recommended behavior:

- Send the question to the same endpoint used by the frontend.
- Capture final answer.
- Capture metadata if debug mode is enabled.
- Handle timeout and retry logic.
- Save errors without stopping the full run.

## 5.5 `retrieval_client`

Responsible for retrieval-only evaluation.

This mode should bypass final answer generation and directly test whether the expected papers are retrieved.

This is useful because retrieval quality must be measured before judging the LLM answer.

## 5.6 `direct_llm_client`

Responsible for baseline testing without RAG.

Purpose:

Compare:

```text
LLM alone
vs
LLM + RAG
```

This helps prove whether the RAG pipeline adds value.

## 5.7 `response_recorder`

Responsible for writing raw outputs safely.

Must support append-only writes.

Recommended raw format:

```text
raw_outputs.jsonl
```

Reason:

JSONL is robust for long-running evaluation. If the script fails midway, previously written lines remain valid.

## 5.8 `metrics_engine`

Responsible for calculating retrieval, citation, and answer-level metrics.

## 5.9 `failure_analyzer`

Responsible for classifying failures.

The goal is not only to say that a question failed, but to identify where it failed.

## 5.10 `report_generator`

Responsible for producing:

```text
summary_results.csv
retrieval_metrics.json
answer_metrics.json
failure_analysis.md
report.md
```

---

# 6. Execution Modes

## 6.1 `retrieval_only`

Purpose:

Evaluate retrieval without LLM generation.

Captures:

```text
question_id
question
rewritten_query
expected_article_ids
retrieved_article_ids
retrieval_scores
rank_of_expected_articles
filters_applied
latency_ms
```

Main metrics:

```text
Hit@1
Hit@3
Hit@5
Recall@K
MRR
NDCG@K
```

## 6.2 `rag_end_to_end`

Purpose:

Evaluate the full user-facing RAG experience.

Captures:

```text
question_id
question
router_decision
rewritten_query
extracted_filters
retrieved_article_ids
reranked_article_ids
context_article_ids
final_answer
cited_article_ids
latency_ms
error
```

Main metrics:

```text
citation_precision
citation_recall
answer_keyword_coverage
manual_answer_score
hallucination_flag
```

## 6.3 `direct_llm_baseline`

Purpose:

Evaluate the LLM without retrieval.

Captures:

```text
question_id
question
final_answer
latency_ms
model_name
```

Use this to compare RAG-supported answers against model-only answers.

## 6.4 `multi_turn_memory`

Purpose:

Evaluate conversation memory and follow-up resolution.

Captures:

```text
scenario_id
turn_index
question
previous_cited_articles
resolved_reference
final_answer
cited_article_ids
memory_state_summary
```

Important:

Do not mix multi-turn scenarios with independent single-turn questions.

---

# 7. Data to Capture Per Question

For each evaluated question, capture as much diagnostic information as possible.

Recommended raw record:

```json
{
  "run_id": "run_2026_06_12_gemma4_top5",
  "question_id": "Q001",
  "scenario_id": null,
  "turn_index": null,
  "question": "Which papers discuss hybrid retrieval for RAG?",
  "question_type": "semantic_topic_search",
  "expected_article_ids": ["A123", "A487"],
  "requires_retrieval_expected": true,
  "router_decision": "retrieval_required",
  "rewritten_query": "hybrid retrieval methods for retrieval augmented generation",
  "extracted_filters": {},
  "retrieved_articles": [
    {
      "article_id": "A123",
      "rank": 1,
      "score": 0.87
    }
  ],
  "reranked_articles": [],
  "context_article_ids": ["A123", "A222", "A487"],
  "final_answer": "...",
  "cited_article_ids": ["A123", "A487"],
  "metrics": {
    "hit_at_1": true,
    "hit_at_5": true,
    "mrr": 1.0,
    "citation_precision": 1.0,
    "citation_recall": 1.0
  },
  "latency_ms": 4200,
  "model_name": "gemma4:e4b",
  "temperature": 0,
  "top_k": 5,
  "created_at": "2026-06-12T12:00:00+03:00",
  "status": "completed",
  "error": null
}
```

---

# 8. Output Directory Structure

Recommended structure:

```text
evaluation/
  runs/
    run_2026_06_12_gemma4_top5/
      config.json
      raw_outputs.jsonl
      summary_results.csv
      errors.jsonl
      retrieval_metrics.json
      citation_metrics.json
      answer_review_sheet.csv
      failure_analysis.md
      report.md
```

## 8.1 `config.json`

Must store the full experimental configuration.

Include:

```text
model_name
temperature
top_k
prompt_version
database_snapshot
embedding_model
retrieval_mode
reranking_enabled
hybrid_search_enabled
golden_set_version
```

## 8.2 `raw_outputs.jsonl`

Stores full diagnostic records.

## 8.3 `summary_results.csv`

Stores one row per question with compact metrics.

Recommended columns:

```text
question_id
question_type
requires_retrieval_expected
requires_retrieval_actual
hit_at_1
hit_at_3
hit_at_5
recall_at_5
mrr
citation_precision
citation_recall
answer_keyword_coverage
manual_score
latency_ms
status
failure_category
```

## 8.4 `errors.jsonl`

Stores failed requests separately.

## 8.5 `report.md`

Human-readable final report.

---

# 9. Metrics

## 9.1 Retrieval Metrics

### Hit@K

Checks whether at least one expected article appears in the top K retrieved results.

Interpretation:

```text
High Hit@5:
The retriever usually finds at least one relevant paper.

Low Hit@5:
The retriever often fails before the LLM sees the right context.
```

### Recall@K

Measures how many expected articles appear in top K.

Useful when a question has multiple expected papers.

### MRR

Mean Reciprocal Rank.

If the expected paper appears at rank 1, reciprocal rank is 1.0. If it appears at rank 5, reciprocal rank is 0.2.

Interpretation:

```text
High Hit@5 but low MRR:
The retriever finds the correct paper but ranks it too low.
This suggests a reranking problem.
```

### NDCG@K

Useful if expected papers have graded relevance levels.

Use only if your golden set supports relevance grades.

---

## 9.2 Citation Metrics

### Citation Precision

```text
correctly cited expected sources / all cited sources
```

Measures whether the final answer cites relevant sources.

### Citation Recall

```text
correctly cited expected sources / all expected sources
```

Measures whether the answer cites the expected sources.

### Unsupported Citation Flag

True if the answer cites a source but the cited source does not support the claim.

This often requires manual or LLM-assisted review.

---

## 9.3 Answer Quality Metrics

Answer quality is harder to measure fully automatically.

Recommended approach:

Use a hybrid method:

```text
automatic lightweight checks
+
manual review
+
optional LLM-as-judge review
```

Recommended fields:

```text
answer_keyword_coverage
manual_completeness_score
manual_groundedness_score
manual_clarity_score
hallucination_flag
```

Suggested manual scale:

```text
1 = Incorrect or irrelevant
2 = Partially relevant but mostly weak
3 = Mostly correct but incomplete
4 = Correct, grounded, and useful
5 = Excellent, complete, well-cited, and faithful
```

---

# 10. Failure Taxonomy

The evaluation mechanism must classify failures.

Recommended categories:

```text
router_error
query_rewrite_error
filter_extraction_error
retrieval_miss
reranking_error
context_construction_error
citation_error
generation_error
memory_error
out_of_domain_policy_error
timeout_or_system_error
golden_set_error
```

## 10.1 Router Error

The router made the wrong decision.

Example:

```text
Expected retrieval, but router skipped retrieval.
```

## 10.2 Query Rewrite Error

The rewritten query lost important meaning.

Example:

```text
Original question asks about "hybrid retrieval", but rewritten query becomes only "retrieval".
```

## 10.3 Filter Extraction Error

The system extracted wrong metadata filters.

Example:

```text
Question asks for papers after 2023, but filter year_min is missing.
```

## 10.4 Retrieval Miss

Expected paper is not in top K.

## 10.5 Reranking Error

Expected paper was retrieved but pushed too low after reranking.

## 10.6 Citation Error

The answer cited irrelevant or wrong sources.

## 10.7 Generation Error

Correct context was provided, but the LLM produced an incomplete, incorrect, or unsupported answer.

## 10.8 Memory Error

The system failed to resolve a follow-up reference.

Example:

```text
"the second paper" refers to the wrong paper.
```

## 10.9 Out-of-Domain Policy Error

The assistant answered a question outside its academic publication assistant scope.

---

# 11. Reproducibility Rules

The following values must be saved for every run:

```text
run_id
timestamp
model_name
model_version
temperature
top_p
top_k
max_tokens
embedding_model
database_snapshot
prompt_version
retrieval_config_version
reranking_enabled
hybrid_search_enabled
golden_set_version
code_commit_hash
```

Important principle:

Only change one major variable per experiment.

Bad experiment:

```text
Changed model, top_k, prompt, and retrieval method at the same time.
```

Good experiment:

```text
Run A: top_k = 5
Run B: top_k = 10
Everything else unchanged.
```

This allows meaningful comparison.

---

# 12. Determinism and Stability

Recommended settings for evaluation:

```text
temperature = 0
fixed top_k
fixed prompt version
fixed database snapshot
fixed embedding model
fixed golden set version
```

Why:

Evaluation should measure system quality, not randomness.

Trade-off:

```text
Low temperature:
More stable, better for evaluation.

Higher temperature:
More natural answers, worse for reproducibility.
```

---

# 13. Resume and Retry Strategy

The evaluation runner must support resume mode.

Recommended behavior:

```text
If question_id already exists in raw_outputs.jsonl with status completed, skip it.
If status failed, retry only if retry_failed is enabled.
If script crashes, continue from the last incomplete question.
```

Retry policy:

```text
retry_count = 2 or 3
exponential backoff
timeout per request
log final failure to errors.jsonl
```

Do not let one failed question stop the full evaluation run.

---

# 14. Step-by-Step Implementation Plan

## Phase 1 — Define the Golden Set Schema

Tasks:

- Decide the golden set format.
- Add required fields.
- Add question types.
- Add expected article IDs.
- Add expected filters where relevant.
- Add scenario IDs for multi-turn tests.

Deliverable:

```text
golden_set.jsonl or golden_set.csv
```

Acceptance criteria:

- Every question has a stable `question_id`.
- Every retrieval question has at least one expected source.
- Every multi-turn question has `scenario_id` and `turn_index`.
- There are no duplicate IDs.

---

## Phase 2 — Add Evaluation-Friendly Backend Metadata

Tasks:

- Ensure the RAG endpoint can optionally return debug metadata.
- Add an evaluation/debug flag.
- Return router decision, rewritten query, filters, retrieved IDs, scores, and cited IDs.

Important:

This metadata should be available in evaluation mode, not necessarily exposed to normal users.

Deliverable:

```text
RAG response with optional evaluation metadata
```

Acceptance criteria:

- The final answer is still returned normally.
- Debug metadata can be enabled for evaluation.
- Retrieved article IDs are visible.
- Cited article IDs are visible.

---

## Phase 3 — Build the Evaluation Runner Skeleton

Tasks:

- Load config.
- Load golden set.
- Create run directory.
- Save config snapshot.
- Iterate through questions.
- Call selected evaluation mode.
- Write raw JSONL output.

Deliverable:

```text
evaluation_runner script
```

Acceptance criteria:

- Script can run on a small golden set.
- Output directory is created automatically.
- Raw outputs are saved incrementally.
- Errors are logged without crashing the full run.

---

## Phase 4 — Implement `retrieval_only` Mode

Tasks:

- Send the rewritten or original query to retrieval.
- Capture top-k retrieved articles.
- Compare with expected article IDs.
- Calculate Hit@K, Recall@K, and MRR.

Deliverable:

```text
retrieval_only evaluation mode
```

Acceptance criteria:

- Hit@1, Hit@3, Hit@5, Recall@5, and MRR are calculated.
- Retrieval failures are classified.
- Results are written to summary CSV.

---

## Phase 5 — Implement `rag_end_to_end` Mode

Tasks:

- Send each question to the actual RAG chat endpoint.
- Capture final answer.
- Capture router decision, rewritten query, filters, retrieved documents, and citations.
- Calculate citation precision and recall.
- Save answer text for manual review.

Deliverable:

```text
rag_end_to_end evaluation mode
```

Acceptance criteria:

- Final answers are saved.
- Cited article IDs are extracted.
- Citation metrics are calculated.
- Router and retrieval errors are distinguishable.

---

## Phase 6 — Implement `direct_llm_baseline` Mode

Tasks:

- Send the same question directly to the model without retrieval.
- Save answer.
- Compare qualitatively or manually with RAG answer.

Deliverable:

```text
direct_llm_baseline mode
```

Acceptance criteria:

- Baseline answers are saved separately.
- Report can compare RAG and non-RAG output.

---

## Phase 7 — Implement Multi-Turn Scenario Evaluation

Tasks:

- Group questions by `scenario_id`.
- Create one session per scenario.
- Send turns in order.
- Preserve session state.
- Evaluate whether follow-up references were resolved correctly.

Deliverable:

```text
multi_turn_memory evaluation mode
```

Acceptance criteria:

- Same session is reused within a scenario.
- Different scenarios use isolated sessions.
- Memory failures are classified.

---

## Phase 8 — Add Report Generation

Tasks:

- Aggregate metrics.
- Produce Markdown report.
- List worst-performing questions.
- Group results by question type.
- Summarize failure categories.
- Recommend improvement areas.

Deliverable:

```text
report.md
```

Acceptance criteria:

- Report includes retrieval metrics.
- Report includes citation metrics.
- Report includes failure analysis.
- Report includes actionable recommendations.

---

## Phase 9 — Run Controlled Experiments

Example experiment sequence:

```text
Run 1: Current baseline, top_k=5
Run 2: Same system, top_k=10
Run 3: Same system, improved query rewriting prompt
Run 4: Same system, hybrid retrieval enabled
Run 5: Same system, reranker enabled
```

Important:

Only change one major variable at a time.

Deliverable:

```text
comparison_report.md
```

Acceptance criteria:

- Metrics can be compared across runs.
- Changes are supported by evidence.
- Improvements are not based only on subjective feeling.

---

# 15. Common Mistakes to Avoid

## Mistake 1 — Saving Only the Final Answer

This hides the actual failure point.

Always save:

```text
router decision
rewritten query
filters
retrieved article IDs
scores
citations
final answer
```

## Mistake 2 — Running All Questions in the Same Chat Session

This contaminates independent questions with conversation memory.

Use fresh sessions for independent questions.

## Mistake 3 — Evaluating Only Answer Fluency

A fluent answer can still be wrong.

Evaluate retrieval and citation quality separately.

## Mistake 4 — Using High Temperature During Evaluation

High randomness makes results harder to compare.

Use temperature 0 for evaluation.

## Mistake 5 — Changing Many Variables at Once

If many things change, you cannot know what caused the improvement or regression.

## Mistake 6 — Weak Golden Set

A golden set without expected article IDs is not enough for RAG evaluation.

Expected sources are more important than expected prose.

## Mistake 7 — Ignoring Failed Questions

Failed requests should be logged and classified.

Timeouts and system errors are part of evaluation.

## Mistake 8 — Trusting LLM-as-Judge Blindly

LLM judges can be useful, but they should not be the only evaluation method.

Use them as support, not as the final truth.

---

# 16. Senior Engineering Review Checklist

Before considering the evaluation mechanism complete, verify:

```text
[ ] Golden set has stable IDs.
[ ] Expected article IDs are included.
[ ] Question types are labeled.
[ ] Independent questions use fresh sessions.
[ ] Multi-turn scenarios reuse session state correctly.
[ ] Router decisions are captured.
[ ] Rewritten queries are captured.
[ ] Extracted filters are captured.
[ ] Retrieved article IDs and scores are captured.
[ ] Final cited sources are captured.
[ ] Raw outputs are saved as JSONL.
[ ] Summary metrics are saved as CSV.
[ ] Run configuration is saved.
[ ] Resume mode is supported.
[ ] Retry and timeout behavior is implemented.
[ ] Retrieval metrics are calculated.
[ ] Citation metrics are calculated.
[ ] Failure categories are assigned.
[ ] Report generation is automated.
[ ] Runs can be compared.
[ ] Only one major variable changes per experiment.
```

---

# 17. Recommended First Version

Do not try to build everything at once.

The first useful version should include:

```text
golden_set_loader
rag_end_to_end mode
raw_outputs.jsonl
summary_results.csv
Hit@5
MRR
citation_precision
citation_recall
failure_category
report.md
resume support
```

After that, add:

```text
retrieval_only mode
direct_llm_baseline mode
multi_turn_memory mode
LLM-as-judge support
comparison reports
```

---

# 18. Final Principle

The goal of this mechanism is not to prove that the system works.

The goal is to discover where it fails.

A professional RAG evaluation setup should make failures visible, measurable, and comparable.

The final question should not be:

```text
Did the model answer?
```

It should be:

```text
Did the system retrieve the right evidence, use it correctly, cite it properly, and produce a grounded answer in a repeatable way?
```
