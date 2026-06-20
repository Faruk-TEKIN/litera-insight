#!/usr/bin/env sh
set -eu

SEED_DIR="/seed/retrieval"
DUMP_PATH="${SEED_DIR}/academic_platform.dump"

if [ ! -f "$DUMP_PATH" ]; then
  echo "[postgres-init] No dump found at $DUMP_PATH, skipping restore."
  exit 0
fi

export PGPASSWORD="${POSTGRES_PASSWORD}"

echo "[postgres-init] Enabling pgvector extension."
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE EXTENSION IF NOT EXISTS vector;"

echo "[postgres-init] Restoring database dump from $DUMP_PATH."
pg_restore \
  --verbose \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  "$DUMP_PATH"

echo "[postgres-init] Database restore completed."
