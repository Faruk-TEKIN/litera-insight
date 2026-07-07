# Oto Kurulum Adımları

The repository can now start from a clean clone without a dump file.

## Free data sources

The default bootstrap path uses free sources that do not require an API key:

- `arXiv`
- `OpenAlex`

Both endpoints were re-checked on `2026-07-07` and returned `HTTP 200`.

## Expected flow

The recommended way to set up the project automatically is to run the setup script:

```bash
git clone <repo-url>
cd <repo-root>
ollama pull qwen2.5:0.5b
./setup.sh
```

Alternatively, you can run the steps manually:

```bash
git clone <repo-url>
cd <repo-root>
cp .env.example .env
python3 -m venv .venv
.venv/bin/pip install --upgrade pip setuptools wheel
.venv/bin/pip install -r requirements.txt
mkdir -p exports/retrieval
ollama pull qwen2.5:0.5b
docker compose up -d --build
.venv/bin/python run_bulk_ingest.py --max-results 4000 --sources arxiv
.venv/bin/python ai_engine/embeddings/embeddings_to_db.py --total-articles 4000 --batch-size 250
.venv/bin/python scripts/build_bm25_index.py
.venv/bin/python ai_engine/clustering/ClusterFunctions.py --max-articles 4000
```

## What happens automatically

- PostgreSQL starts with an empty database if no dump exists.
- `pgvector` extension is enabled during PostgreSQL init.
- The backend waits for PostgreSQL, applies Alembic migrations, and warms cached snapshots.
- The configured small local RAG model is `qwen2.5:0.5b`.
- The local `.venv` is expected to be created during the first repo setup so ingestion and optional data jobs can run without extra manual environment work later.

## Seed a fresh local database with free data

After the stack is up, pull a small free dataset into the local database:

```bash
.venv/bin/python run_bulk_ingest.py --max-results 4000 --sources arxiv,openalex
```

Notes:

- `--max-results` default is already `4000`, so `run_bulk_ingest.py` is enough for the standard bootstrap.
- The script writes directly into the local PostgreSQL database.
- No API key is needed for `arxiv` or `openalex`.
- `semanticscholar` remains optional and is not part of the default bootstrap.
- This ingestion step is already included in the expected flow; run it separately only when refreshing the local dataset.

## Optional one-time indexing and clustering

These steps are already included in the expected flow. Run them separately only when rebuilding retrieval or topic clustering artifacts.

```bash
.venv/bin/python ai_engine/embeddings/embeddings_to_db.py --total-articles 4000 --batch-size 250
.venv/bin/python scripts/build_bm25_index.py
.venv/bin/python ai_engine/clustering/ClusterFunctions.py --max-articles 4000 --include-openalex
.venv/bin/python -c "from database.db import SessionLocal; from backend.app.services.report_snapshot_service import ReportSnapshotService; db=SessionLocal(); print(ReportSnapshotService(db).refresh_default_snapshots()); db.close()"
```

Recommended environment settings:

- `EMBEDDING_DEVICE=auto` (default)
- `CLUSTERING_HARDWARE_PROFILE=auto` (default)
- `RAG_RERANKER_MODEL_NAME=cross-encoder/ms-marco-TinyBERT-L2-v2` for lightweight reranking
- `RAG_BM25_INDEX_PATH=exports/retrieval/articles_bm25.sqlite` for BM25/hybrid retrieval

## Optional dump restore

If `exports/retrieval/academic_platform.dump` exists, PostgreSQL still restores it automatically on first initialization. The dump path is now optional, not required.
