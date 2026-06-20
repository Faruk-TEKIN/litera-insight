# Local Bootstrap

The repository is designed to start from a clean clone with only two data files copied into `exports/retrieval`.

## Required files

Copy these files into:

`exports/retrieval/`

- `academic_platform.dump`
- `articles_bm25.sqlite`

## Expected flow

```bash
git clone <repo-url>
cp -r <your-data-folder>/* <repo-root>/exports/retrieval/
cd <repo-root>
docker compose up --build
```

## What happens automatically

- PostgreSQL restores `exports/retrieval/academic_platform.dump` on first initialization.
- The backend waits for PostgreSQL, applies Alembic migrations, and warms cached snapshots.
- The frontend reads the restored PostgreSQL data and the mounted BM25 SQLite index.

## Important note

If you start the stack once without the dump and later copy it in, the backend bootstrap will still attempt a restore when it sees an empty `articles` table. You only need `docker compose down -v` if you want to fully reset the local database volume.
