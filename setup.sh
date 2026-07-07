#!/bin/sh
set -eu

SEED_DEMO=0

for arg in "$@"; do
    case "$arg" in
        --seed)
            SEED_DEMO=1
            ;;
        --help|-h)
            cat <<'EOF'
Usage: ./setup.sh [--seed]

Without arguments, starts the Docker stack and waits for the application to become ready.
With --seed, also runs the one-time demo data bootstrap inside Docker:
  - ingestion
  - embeddings
  - BM25 index build
  - clustering
  - snapshot refresh
EOF
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            exit 1
            ;;
    esac
done

if [ ! -f .env ]; then
    cp .env.example .env
fi

docker compose down --remove-orphans
docker compose up -d --build

echo "Waiting for backend readiness..."
until curl -fsS http://127.0.0.1:8000/health/ready >/dev/null 2>&1; do
    sleep 5
done
echo "Backend is ready."

if [ "$SEED_DEMO" -eq 1 ]; then
    echo "Running one-time data bootstrap inside Docker..."
    docker compose run --rm --no-deps --entrypoint python backend /app/run_bulk_ingest.py --max-results 4000 --sources arxiv,openalex
    docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/embeddings/embeddings_to_db.py --total-articles 4000 --batch-size 250
    docker compose run --rm --no-deps --entrypoint python backend /app/scripts/build_bm25_index.py
    docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/clustering/ClusterFunctions.py --max-articles 4000 --include-openalex
    docker compose run --rm --no-deps --entrypoint python backend -c "from database.db import SessionLocal; from backend.app.services.report_snapshot_service import ReportSnapshotService; db=SessionLocal(); print(ReportSnapshotService(db).refresh_default_snapshots()); db.close()"
    echo "Demo bootstrap complete."
fi

echo "=== Kurulum başarıyla tamamlandı ==="
