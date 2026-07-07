# AGENT.md

Guidance for coding agents working in this repository.

## Project Overview

This repository contains an academic literature intelligence platform. It ingests papers from external academic sources, stores article metadata and embeddings in PostgreSQL with pgvector, clusters papers with BERTopic, exposes analytics and RAG chat features through a FastAPI backend, and provides a Vite/React frontend.

Primary domains:

- Data ingestion from arXiv, OpenAlex, Semantic Scholar, and Kaggle arXiv snapshots.
- Data hygiene and text preparation for embeddings and topic modeling.
- Embedding generation with sentence-transformers.
- Topic clustering with BERTopic, UMAP, and HDBSCAN.
- RAG retrieval with pgvector, optional BM25 sidecar index, routing, reranking, and Ollama-backed answer generation.
- Dashboard, bulletin, authentication, and chat UI.

## Main Modules

- `backend/`: FastAPI application, API routes, service layer, schemas, configuration, and worker stubs.
- `backend/app/api/routes/`: HTTP endpoints for health, auth, chat, analytics, and bulletin.
- `backend/app/services/`: business logic for RAG, retrieval, embeddings, snapshots, bulletins, memory, and Ollama.
- `ai_engine/`: ingestion, data hygiene, embeddings, and clustering pipeline.
- `database/`: SQLAlchemy models and Alembic migrations.
- `frontend/`: Vite React TypeScript frontend.
- `scripts/`: operational and evaluation scripts, including BM25 index generation and RAG evaluation.
- `evaluation/`: golden questions and evaluation fixtures.
- `tests/`: Python pytest tests.
- `docs/` and `LATEX/`: project documentation and report artifacts.

## Entry Points

Backend:

```bash
uvicorn backend.app.main:app --reload
```

Frontend:

```bash
cd frontend
npm run dev
```

Docker Compose:

```bash
./setup.sh
```

Database migrations:

```bash
docker compose run --rm --no-deps --entrypoint python backend -m alembic -c /app/database/alembic.ini upgrade head
```

Bulk ingestion:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/run_bulk_ingest.py --max-results 10000 --sources arxiv,openalex
```

Kaggle arXiv ingestion:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/run_kaggle_arxiv_ingest.py --input /app/data/arxiv-metadata-oai-snapshot.json --dry-run
```

Data hygiene:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/data_hygiene/export_clean_papers.py --output-dir exports/data_hygiene
```

Embedding generation:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/embeddings/embeddings_to_db.py --total-articles 3500 --batch-size 250
```

Clustering:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/clustering/ClusterFunctions.py
```

BM25 sidecar index:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/scripts/build_bm25_index.py
```

RAG golden-set evaluation:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/scripts/run_rag_golden_set_evaluation.py --golden-file evaluation/rag_golden_set_10_questions.json --mode retrieval_only --top-k 5 --force-rag
```

## Local Development

Expected local dependencies:

- Python 3.11+
- Node.js 20+
- PostgreSQL with `pgvector`
- Redis, if worker functionality is used
- Ollama, if LLM-backed chat, routing, digest generation, or end-to-end RAG evaluation is used

Python setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

Frontend setup:

```bash
cd frontend
npm install
npm run dev
```

Environment:

- Start from `.env.example`.
- For local non-Docker backend runs, `DATABASE_URL` should point to localhost PostgreSQL.
- For Docker Compose, the provided compose file points backend database access at the `postgres` service and Ollama at the in-network `ollama` service.
- Backend health check: `http://127.0.0.1:8000/health`.
- Frontend default URL: `http://localhost:5173`.

Ollama runs inside Docker Compose through the `ollama` service. The `ollama-pull` service pulls and warms the configured `MODEL_NAME`.

## Tests

Run the Python tests with:

```bash
pytest tests
```

The test suite is organized as lightweight unit and contract tests. It covers ingestion normalization, routing heuristics, retrieval filters and ranking helpers, conversation memory, analytics response shape, report snapshots, and evaluation metrics.

Most tests are designed not to require live Ollama or PostgreSQL. Before adding integration tests that require live services, keep them clearly separated or mark them so default local test runs stay lightweight.

There is no visible frontend test suite. Use `npm run build` and `npm run lint` for frontend verification when changing UI code.

## Development Rules

- Prefer existing service boundaries and schemas over introducing parallel abstractions.
- Keep backend API changes synchronized with frontend TypeScript types and API client usage.
- Keep database model changes synchronized with Alembic migrations.
- Do not run `reset_database.py --yes` unless the user explicitly requests a destructive database reset.
- Docker startup applies migrations through the backend entrypoint; run Alembic explicitly only for manual schema verification or one-off maintenance.
- Treat `exports/`, BM25 indexes, model outputs, dumps, caches, and generated reports as local artifacts unless the user explicitly asks to version them.
- Avoid committing `__pycache__`, test caches, local dumps, generated ML artifacts, or scratch files.
- For retrieval changes, consider vector retrieval, BM25 retrieval, fusion, reranking, source formatting, and RAG prompt behavior together.
- For auth changes, remember current authentication is local and header-based; do not treat it as production-grade security.

## Risk Areas

- Authentication currently uses unsalted SHA-256 password hashing and trusts `X-User-Id`; it is not production-safe.
- Docker Compose starts PostgreSQL, Redis, Ollama, backend, worker, beat, and frontend.
- Worker configuration uses Redis through `redis://redis:6379/0` in Docker Compose.
- Python dependencies are mostly unpinned, so fresh installs may drift.
- AI dependencies are heavy and hardware-sensitive: Torch, sentence-transformers, BERTopic, UMAP, HDBSCAN, and cross-encoder reranking.
- Hybrid retrieval depends on a SQLite BM25 sidecar index at `exports/retrieval/articles_bm25.sqlite`; missing or stale indexes can change behavior.
- Alembic migrations form a single chain but include several init-style migrations; validate schema carefully before assuming a clean bootstrap.
- The frontend Dockerfile runs a Vite dev server, not a production static build.
- Root `main.py` is empty and should not be treated as the application entrypoint.
- Documentation and LaTeX files contain TODO placeholders for metrics and environment details.

## Missing Context To Clarify Before Major Changes

- Production deployment target and runtime model.
- Authentication and authorization requirements.
- Expected data volume and hardware profile.
- Whether Redis/Celery is intended to be active or legacy.
- Canonical seed/demo database flow.
- CI expectations and required test gates.
- Whether generated research artifacts should remain in the repo.
- Frontend testing strategy.
- Required LLM/model alternatives if the default Docker model is too small for a target demo.

## Useful Files

- `README.md`: high-level English delivery overview.
- `README_DEV.md`: detailed developer runbook.
- `.env.example`: expected configuration variables.
- `docker-compose.yml`: local container orchestration.
- `backend/app/main.py`: FastAPI app wiring.
- `frontend/src/App.tsx`: frontend route layout.
- `backend/app/core/config.py`: settings and environment variables.
- `database/alembic/env.py`: migration configuration.
- `tests/conftest.py`: pytest path setup.
