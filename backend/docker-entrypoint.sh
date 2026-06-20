#!/usr/bin/env sh
set -eu

python -m backend.app.core.startup
exec uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
