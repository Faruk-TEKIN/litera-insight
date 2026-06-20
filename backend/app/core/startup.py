from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine.url import make_url

from backend.app.core.database import engine, SessionLocal
from backend.app.services.report_snapshot_service import ReportSnapshotService


PROJECT_ROOT = Path(__file__).resolve().parents[3]
RETRIEVAL_DUMP_PATH = PROJECT_ROOT / "exports" / "retrieval" / "academic_platform.dump"
DEFAULT_DB_WAIT_SECONDS = 300
DB_POLL_INTERVAL_SECONDS = 3


def wait_for_database(timeout_seconds: int = DEFAULT_DB_WAIT_SECONDS) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return
        except Exception as exc:  # pragma: no cover - startup guard
            last_error = exc
            print(f"[startup] Waiting for database: {exc}", file=sys.stderr)
            time.sleep(DB_POLL_INTERVAL_SECONDS)

    raise RuntimeError("Database did not become ready in time.") from last_error


def run_migrations() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{PROJECT_ROOT}:{env.get('PYTHONPATH', '')}".rstrip(":")
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(PROJECT_ROOT / "database/alembic.ini"), "upgrade", "head"],
        cwd=str(PROJECT_ROOT),
        env=env,
        check=True,
    )


def restore_database_dump_if_needed() -> None:
    if not RETRIEVAL_DUMP_PATH.exists():
        print(f"[startup] No dump found at {RETRIEVAL_DUMP_PATH}; skipping restore.")
        return

    with engine.connect() as connection:
        table_exists = connection.execute(text("SELECT to_regclass('public.articles') IS NOT NULL")).scalar()
        if table_exists:
            article_count = int(connection.execute(text("SELECT count(*) FROM articles")).scalar() or 0)
            if article_count > 0:
                print(f"[startup] Existing articles detected ({article_count}); skipping dump restore.")
                return

    url = make_url(os.environ["DATABASE_URL"])
    cmd = [
        "pg_restore",
        "--verbose",
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        "--host",
        url.host or "localhost",
        "--port",
        str(url.port or 5432),
        "--username",
        url.username or "postgres",
        "--dbname",
        url.database or "academic_platform",
        str(RETRIEVAL_DUMP_PATH),
    ]
    env = os.environ.copy()
    if url.password:
        env["PGPASSWORD"] = url.password

    print(f"[startup] Restoring database dump from {RETRIEVAL_DUMP_PATH}.")
    subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env, check=True)


def warm_report_snapshots() -> None:
    db = SessionLocal()
    try:
        ReportSnapshotService(db).refresh_default_snapshots()
    finally:
        db.close()


def main() -> None:
    wait_for_database()
    restore_database_dump_if_needed()
    run_migrations()
    warm_report_snapshots()


if __name__ == "__main__":
    main()
