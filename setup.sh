#!/bin/sh
set -eu

SEED_DEMO=0
TELEGRAM_PROFILE=0

for arg in "$@"; do
    case "$arg" in
        --seed)
            SEED_DEMO=1
            ;;
        --telegram)
            TELEGRAM_PROFILE=1
            ;;
        --help|-h)
            cat <<'EOF'
Usage: ./setup.sh [--seed] [--telegram]

Without arguments, starts the Docker stack and waits for the application to become ready.
With --seed, also runs the one-time demo data bootstrap inside Docker:
  - ingestion
  - embeddings
  - BM25 index build
  - clustering
  - snapshot refresh
With --telegram, also starts the optional ngrok webhook profile for Telegram PDF delivery.
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

env_value() {
    key="$1"
    grep -E "^${key}=" .env | tail -n 1 | cut -d= -f2-
}

if [ "$TELEGRAM_PROFILE" -eq 1 ]; then
    for key in TELEGRAM_BOT_TOKEN TELEGRAM_BOT_USERNAME NGROK_AUTHTOKEN; do
        if [ -z "$(env_value "$key")" ]; then
            echo "$key must be set in .env before running ./setup.sh --telegram" >&2
            echo "Use: TELEGRAM_BOT_TOKEN=... TELEGRAM_BOT_USERNAME=... NGROK_AUTHTOKEN=... bash scripts/setup_local_telegram_env.sh" >&2
            exit 1
        fi
    done
    if [ -z "$(env_value TELEGRAM_WEBHOOK_SECRET)" ]; then
        secret="$(openssl rand -hex 32)"
        if grep -q "^TELEGRAM_WEBHOOK_SECRET=" .env; then
            python - .env TELEGRAM_WEBHOOK_SECRET "$secret" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
lines = path.read_text().splitlines()
path.write_text("\n".join(f"{key}={value}" if line.startswith(f"{key}=") else line for line in lines) + "\n")
PY
        else
            printf 'TELEGRAM_WEBHOOK_SECRET=%s\n' "$secret" >> .env
        fi
        echo "Generated TELEGRAM_WEBHOOK_SECRET in .env."
    fi
    docker compose --profile telegram down --remove-orphans
    docker compose --profile telegram up -d --build
else
    docker compose down --remove-orphans
    docker compose up -d --build
fi

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
