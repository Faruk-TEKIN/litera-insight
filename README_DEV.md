# Developer Runbook

This document clarifies the project entrypoints, Docker-only delivery flow, and operational commands used during development and testing.

## Requirements

- Docker
- Docker Compose
- Python 3.11+ only if you want to run lightweight local tests outside Docker

## Environment Variables

Create a `.env` file at the repository root:

```bash
cp .env.example .env
```

Docker Compose overrides `DATABASE_URL`, `OLLAMA_BASE_URL`, and Redis addresses inside containers.

## Optional Local Python Dependencies

If you want to run lightweight tests outside Docker:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

## Tests

To run lightweight unit tests locally:

```bash
pytest tests
```

These tests do not require live Ollama or PostgreSQL. They cover router fallbacks, retrieval filter SQL behavior, conversation memory, and analytics response contracts.

## RAG Golden Set Evaluation

To run a quick retrieval-only evaluation with `evaluation/rag_golden_set_10_questions.json`:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/scripts/run_rag_golden_set_evaluation.py --golden-file evaluation/rag_golden_set_10_questions.json --mode retrieval_only --top-k 5 --force-rag
```

To run end-to-end RAG answers, citation scoring, and answer evaluation with the same golden set while Ollama and PostgreSQL are running:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/scripts/run_rag_golden_set_evaluation.py --golden-file evaluation/rag_golden_set_10_questions.json --mode rag_end_to_end --top-k 5 --force-rag --temperature 0
```

Output is written to `evaluation/runs/<run-id>`. Each run produces `summary_results.csv`, `retrieval_metrics.json`, `citation_metrics.json`, `answer_review_sheet.csv`, `failure_analysis.md`, `report.md`, and `raw_outputs.jsonl`.

## Docker-Only Delivery Flow

Docker Compose is the only supported delivery path. The model and all services run inside containers.

```bash
cp .env.example .env
./setup.sh
```

This flow:

- starts with an empty database if no PostgreSQL dump is present,
- pulls and warms the configured model through `ollama-pull`,
- waits until the database is ready before backend startup,
- uses `MODEL_NAME` from `.env` for RAG and cluster labeling,
- applies Alembic migrations,
- refreshes cached report snapshots,
- exposes the frontend on `5173` and the backend on `8000`.

To load demo data during first-time setup:

```bash
./setup.sh --seed
```

`--seed` runs ingestion, embedding generation, BM25 index build, clustering, and snapshot refresh inside Docker.

If needed, the same steps can be run manually:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/run_bulk_ingest.py --max-results 4000 --sources arxiv,openalex
docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/embeddings/embeddings_to_db.py --total-articles 4000 --batch-size 250
docker compose run --rm --no-deps --entrypoint python backend /app/scripts/build_bm25_index.py
docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/clustering/ClusterFunctions.py --max-articles 4000 --include-openalex
docker compose run --rm --no-deps --entrypoint python backend -c "from database.db import SessionLocal; from backend.app.services.report_snapshot_service import ReportSnapshotService; db=SessionLocal(); print(ReportSnapshotService(db).refresh_default_snapshots()); db.close()"
```

To rerun free ingestion without API keys:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/run_bulk_ingest.py --max-results 4000 --sources arxiv,openalex
```

Default RAG demo profile:

- `RAG_RERANKER_ENABLED=false`
- If reranking is re-enabled, use `RAG_RERANKER_MODEL_NAME=cross-encoder/ms-marco-TinyBERT-L2-v2`

Optional one-off embedding and clustering steps:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/embeddings/embeddings_to_db.py --total-articles 4000 --batch-size 250
docker compose run --rm --no-deps --entrypoint python backend /app/scripts/build_bm25_index.py
docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/clustering/ClusterFunctions.py --max-articles 4000 --include-openalex
```

If `exports/retrieval/academic_platform.dump` exists, it is still restored on first startup, but it is no longer required.

## Ollama

Ollama is not run separately on the host. The project uses the `ollama` service inside Docker Compose.

To switch models, change `MODEL_NAME` in `.env`.

## Backend

Primary backend entrypoint:

```bash
uvicorn backend.app.main:app --reload
```

Health endpoint:

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{ "status": "ok" }
```

Readiness endpoint:

```bash
curl http://127.0.0.1:8000/health/ready
```

Chat endpoint:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Hello"}'
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Default frontend URL:

```text
http://localhost:5173
```

## Ingestion

Default sources are `arxiv,openalex` with Computer Science filtering.

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/run_bulk_ingest.py --max-results 10000 --sources arxiv,openalex
```

arXiv ingestion rules:

- API queries are limited to `cat:cs.*`.
- A single month can advance up to `start_offset=3000`; when that limit is reached, ingestion moves to the previous month.
- Only arXiv records with at least one `cs.` category in `primary_category` or `categories` are written to the database.
- Records without `abstract_text` are skipped.
- arXiv legacy API terms require a single connection and at most one request every 3 seconds; the extractor respects this delay before each HTTP request.
- On `429`, the system logs `Retry-After` and any available `X-RateLimit-*` or `RateLimit-*` headers.

To import from a Kaggle arXiv snapshot without using the API:

```bash
docker compose run --rm --no-deps -v "$PWD/data:/data:ro" --entrypoint python backend /app/run_kaggle_arxiv_ingest.py --input /data/arxiv-metadata-oai-snapshot.json --samples-per-month 2500 --start-year 2016 --end-year 2026 --target-max-records 300000 --dry-run
docker compose run --rm --no-deps -v "$PWD/data:/data:ro" --entrypoint python backend /app/run_kaggle_arxiv_ingest.py --input /data/arxiv-metadata-oai-snapshot.json --samples-per-month 2500 --start-year 2016 --end-year 2026 --target-max-records 300000 --batch-size 1000
```

The script reads the file line by line, converts records into the current `RawArticleSchema`, and passes them through the same loader filters. That means `cs.` category filtering, empty abstract removal, empty title removal, DOI/PDF checks, metadata normalization, and `external_id`-based upserts are applied consistently. With the `2016-2026` range and `2500` samples per month, the theoretical total is about `330000` records; `--target-max-records 300000` caps the run at `300000`.

Semantic Scholar must be queried with an explicit search query:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/run_bulk_ingest.py --max-results 1000 --sources semanticscholar --query "machine learning"
```

`ai_engine/ingestion/ingestion_state.json` is kept in the repository so the team can continue from the same cursor and offset state.

## Data Hygiene And Text Preparation

To export cleaned arXiv CS records for embeddings and BERTopic:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/data_hygiene/export_clean_papers.py --output-dir exports/data_hygiene
```

This command generates `clean_papers.csv`, `clean_papers_for_bertopic.csv`, `data_hygiene_metrics.csv`, `removed_records.csv`, `duplicate_records.csv`, and `data_hygiene_report.md`. The pipeline uses `embedding_text` for embeddings and `representation_text` for BERTopic input.

## Embedding

To generate embeddings for records that do not have them yet:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/embeddings/embeddings_to_db.py --total-articles 3500 --batch-size 250
```

The script prefers `exports/data_hygiene/clean_papers.csv` and `exports/data_hygiene_openalex/clean_papers.csv` when present and reads `embedding_text` from them. If those CSV files are missing, it falls back to scanning the database. It fills `articles.embedding`, `embedding_model`, `embedding_text_hash`, and `embedding_created_at`. On reruns, it skips articles whose model and text hash are unchanged.

`EMBEDDING_DEVICE=auto` selects `cuda` when available, `mps` on Apple Silicon, otherwise `cpu`. For a MacBook M4 Pro with 24 GB RAM, `auto` and `EMBEDDING_ENCODE_BATCH_SIZE=64` are reasonable defaults. If memory pressure stays low, batch size can be increased to `128`.

## Clustering

To cluster arXiv Computer Science papers that already have embeddings:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/clustering/ClusterFunctions.py
```

By default, this command clusters embedded articles where `source='arxiv'` and `primary_category` or `categories` contains a `cs.*` category. BERTopic outlier articles are automatically reassigned to the nearest cluster centroid in the original embedding space when cosine similarity is high enough; otherwise they remain with `articles.cluster_id = NULL`. The default UMAP parameters are `n_neighbors=50`, `n_components=10`, and `min_dist=0.05`, which reduce the overly compressed local islands produced by the older `n_neighbors=10` and `min_dist=0.0` configuration. HDBSCAN `min_samples` is chosen automatically from `min_topic_size`.

`CLUSTERING_HARDWARE_PROFILE=auto` selects the `m4-pro-24gb` profile when macOS Apple Silicon with about 24 GB RAM is detected. That profile limits CPU threads, enables UMAP low-memory mode, and keeps HDBSCAN job count at a practical level. To set the same configuration explicitly:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/clustering/ClusterFunctions.py --hardware-profile m4-pro-24gb --threads 8
```

To run a smaller or faster experiment:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/clustering/ClusterFunctions.py --max-articles 3500
```

To force larger minimum topic sizes on larger datasets:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/clustering/ClusterFunctions.py --min-topic-size 50
```

To disable high-confidence outlier reassignment or change the threshold:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/clustering/ClusterFunctions.py --no-reassign-outliers
docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/clustering/ClusterFunctions.py --outlier-reassignment-threshold 0.90
```

To run BERTopic improvement experiments and write CSV/model artifacts:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/clustering/ClusterFunctions.py --run-experiments --output-dir exports/bertopic
```

This produces `topic_info.csv`, `paper_topic_assignments.csv`, `topic_keywords.csv`, `bertopic_experiment_results.csv`, `bertopic_cluster_iyilestirme_raporu.md`, and `bertopic_model`. To generate reports and model artifacts without updating the database cluster tables:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/clustering/ClusterFunctions.py --skip-database-save --run-experiments --output-dir exports/bertopic
```

In the latest run on 20,000 cleaned embeddings, `--min-topic-size 5` reduced the largest topic ratio compared with the baseline while keeping the outlier ratio closest to the target range.

To include OpenAlex data in clustering, use explicit opt-in:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/clustering/ClusterFunctions.py --include-openalex
```

By default, the script uses `representation_text` from cleaned CSV files as BERTopic document input and only clusters precomputed embeddings whose `embedding_text_hash` still matches the cleaned CSV version. It refreshes the `clusters` table, updates `articles.cluster_id`, and saves cluster metadata and representative article information. Keyword lists dominated by stop words are not written to the database.

## Analytics And Bulletin Snapshots

Analytics and bulletin endpoints do not recompute expensive database aggregations and centroid calculations on every page load. Prepared payloads are stored in the `report_snapshots` table. `/analytics` and the frontend bulletin call `/bulletin?limit=10&include_digests=true` both read from these snapshots.

To create the snapshot table, migrations must be applied:

```bash
docker compose run --rm --no-deps --entrypoint python backend -m alembic -c /app/database/alembic.ini upgrade head
```

Normal refresh flow:

1. Ingestion writes new articles to the database.
2. Data hygiene generates cleaned CSV files.
3. Embedding generation writes embeddings for new or changed articles.
4. Clustering updates `clusters` and `articles.cluster_id`.
5. After the clustering transaction commits, analytics and bulletin snapshots are regenerated automatically.

To refresh snapshots manually through endpoints:

```bash
curl "http://127.0.0.1:8000/analytics?force_refresh=true"
curl "http://127.0.0.1:8000/bulletin?limit=10&include_digests=true&force_refresh=true"
```

To trigger the same refresh in Python while the backend is not running:

```bash
docker compose run --rm --no-deps --entrypoint python backend -c "from database.db import SessionLocal; from backend.app.services.report_snapshot_service import ReportSnapshotService; db=SessionLocal(); print(ReportSnapshotService(db).refresh_default_snapshots()); db.close()"
```

To inspect snapshot status:

```bash
psql "$DATABASE_URL" -c "select snapshot_key, generated_at from report_snapshots order by snapshot_key;"
```

Notes:

- If no snapshot exists, the normal endpoint returns an empty but fast response; clustering or manual `force_refresh=true` is required to populate the payload.
- `force_refresh=true` is intended for manual operations only and should not be sent by normal frontend traffic.
- Filtered bulletin requests such as `category`, `source`, `period_start`, and `period_end` are stored under their own snapshot keys. The default pipeline refresh updates the main frontend bulletin snapshot.
- The bulletin UI shows the available cluster topic pool from the snapshot as a checkbox list. Clusters outside the selected set are hidden on the frontend.
- Bulletin cards use shortened abstracts for fast loading. When an article card is opened, full abstracts and PDF/source links are fetched from `/bulletin/articles/{article_id}`.

To inspect an article manually:

```bash
curl "http://127.0.0.1:8000/bulletin/articles/254424"
```

To generate a cluster digest:

```bash
curl "http://127.0.0.1:8000/bulletin/clusters/3/digest?max_articles=5"
```

`/bulletin?include_digests=true` adds deterministic digests based on real articles to the cluster list.

## Worker

To run the Celery worker while Redis is available:

```bash
celery -A backend.worker.scheduler.app worker --loglevel=info
```

The current worker structure is still MVP-level. The chat and RAG request path does not run through Celery yet.

## MVP Manual Verification Flow

Start all services:

```bash
./setup.sh
```

Pull a small RAG sample dataset:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/run_bulk_ingest.py --max-results 100 --sources arxiv --query "retrieval augmented generation"
```

Run embeddings and clustering:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/embeddings/embeddings_to_db.py --total-articles 100 --batch-size 50
docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/clustering/ClusterFunctions.py --max-articles 100
```

Check the main endpoints:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/analytics
curl http://localhost:8000/bulletin
```

If a manual snapshot rebuild is needed:

```bash
curl "http://localhost:8000/analytics?force_refresh=true"
curl "http://localhost:8000/bulletin?limit=10&include_digests=true&force_refresh=true"
```

Check sessions and chat:

```bash
curl -X POST http://localhost:8000/chat/sessions -H "Content-Type: application/json"

curl -X POST http://localhost:8000/chat/sessions/1/message \
  -H "Content-Type: application/json" \
  -d '{"message":"What is RAG?"}'

curl -X POST http://localhost:8000/chat/sessions/1/message \
  -H "Content-Type: application/json" \
  -d '{"message":"Summarize arXiv RAG papers from the last 30 days"}'

curl -X POST http://localhost:8000/chat/sessions/1/message \
  -H "Content-Type: application/json" \
  -d '{"message":"Expand on the second paper from the previous answer"}'
```

Expected behavior:

- `What is RAG?` is answered as a general question without retrieval.
- The last-30-days arXiv request uses retrieval and returns `[S1]` style citations.
- The follow-up question uses `metadata_json.sources` from the previous assistant message.
- On an empty database, the system does not invent sources and instead states that there is not enough evidence.
- If Ollama is unavailable, the API returns a usable error message instead of a raw stack trace.
