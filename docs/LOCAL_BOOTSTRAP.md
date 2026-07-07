# Automatic Setup Steps

The delivery flow for this repository is Docker Compose. All services, including the model runtime, run inside containers.

## Expected Flow

```bash
cp .env.example .env
./setup.sh
```

## What Happens

- If no PostgreSQL dump is present, the system starts with an empty database.
- The `pgvector` extension is enabled during PostgreSQL initialization.
- `ollama-pull` downloads and warms the configured model.
- The backend applies migrations and refreshes cached report snapshots.
- The backend and worker use the same in-network `ollama` service.
- The reranker is disabled in the delivery profile for faster RAG responses.

## First-Time Data Bootstrap

If you are not using a dump and want demo data loaded during initial setup:

```bash
./setup.sh --seed
```

This mode runs the following one-time tasks inside containers:

- `run_bulk_ingest.py`
- `ai_engine/embeddings/embeddings_to_db.py`
- `scripts/build_bm25_index.py`
- `ai_engine/clustering/ClusterFunctions.py`
- `ReportSnapshotService.refresh_default_snapshots()`

To run the same steps manually:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/run_bulk_ingest.py --max-results 4000 --sources arxiv,openalex
docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/embeddings/embeddings_to_db.py --total-articles 4000 --batch-size 250
docker compose run --rm --no-deps --entrypoint python backend /app/scripts/build_bm25_index.py
docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/clustering/ClusterFunctions.py --max-articles 4000 --include-openalex
docker compose run --rm --no-deps --entrypoint python backend -c "from database.db import SessionLocal; from backend.app.services.report_snapshot_service import ReportSnapshotService; db=SessionLocal(); print(ReportSnapshotService(db).refresh_default_snapshots()); db.close()"
```

## Verification

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/ready
docker compose logs -f ollama-pull backend frontend
```

## Optional Full Rebuild

If you want to remove the stack and rebuild it from scratch:

```bash
docker compose down --remove-orphans
docker compose up -d --build --force-recreate
```
