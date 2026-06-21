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
cd <repo-root>
mkdir exports && mkdir exports/retrieval/
cp -r /path/to/database/* exports/retrieval/
docker compose up --build
```

`/path/to/database` folder, contains `academic_platform.dump` and `articles_bm25.sqlite` files.

## What happens automatically

- PostgreSQL restores `exports/retrieval/academic_platform.dump` on first initialization.
- The backend waits for PostgreSQL, applies Alembic migrations, and warms cached snapshots.
- Ollama starts automatically and pulls the configured model.
- The frontend reads the restored PostgreSQL data and the mounted BM25 SQLite index.

## Important note

If you start the stack once without the dump and later copy it in, the backend bootstrap will still attempt a restore when it sees an empty `articles` table. You only need `docker compose down -v` if you want to fully reset the local database volume.
