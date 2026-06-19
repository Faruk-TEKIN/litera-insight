# MVP Readiness Review

This review looks at the project as an MVP deliverable, not as a high-scale production system. The question is: can a reviewer or demo user reliably run it, understand what works, and use the core AI/RAG features without hidden local assumptions?

## Verification Performed

- Python tests: `.venv/bin/pytest tests` passed, 92 tests.
- Frontend build: `npm run build` passed.
- Frontend lint: `npm run lint` passed.
- Alembic heads: single head, `a1b2c3d4e5f6`.

These checks are positive, but they mostly validate isolated helper logic and TypeScript correctness. They do not prove that a fresh clone, Docker Compose setup, empty database, Ollama runtime, ingestion pipeline, BM25 index, and frontend work together end to end.

## Executive Summary

The project has a strong amount of implemented surface area for an academic RAG MVP: ingestion, cleaning, embeddings, clustering, analytics, chat, citations, bulletin views, and evaluation scripts. The biggest MVP risk is not missing ambition. The risk is that too many parts depend on local state and manual sequencing.

The highest-priority problems are:

1. The documented Docker path does not fully prepare a runnable MVP database and AI runtime.
2. Authentication looks real in the UI but is only an `X-User-Id` convention with localStorage.
3. RAG quality depends on several fragile runtime artifacts: Ollama model, embedding model, reranker model, and a sidecar SQLite BM25 index.
4. The project lacks one reliable "demo seed" path that creates a known-good dataset, embeddings, clusters, snapshots, and BM25 index.
5. Tests pass, but they avoid the riskiest integration paths.

## Critical MVP Blockers

### 1. Fresh Setup Is Not One Reliable Flow

Relevant files:

- `docker-compose.yml`
- `backend/Dockerfile`
- `README.md`
- `README_DEV.md`
- `database/alembic.ini`
- `scripts/build_bm25_index.py`

`docker compose up --build` starts Postgres, backend, and frontend, but it does not run migrations, restore a dataset, build embeddings, run clustering, generate snapshots, build the BM25 index, or pull/start the Ollama model. The README documents those as separate manual steps.

For an MVP handoff, this is fragile. A reviewer can easily start the containers and see a frontend, but the main features may silently fail or show empty data because the database is not prepared.

Minimum MVP fix:

- Add a single documented setup command or script, for example `scripts/bootstrap_demo.py` or `make demo`.
- It should run migrations, load a small known dataset, generate or load embeddings, create clusters, build snapshots, build the BM25 index, and print the frontend/backend URLs.
- Keep the current full ingestion pipeline as an advanced path, not the default MVP path.

### 2. Authentication Is Not Actually Authentication

Relevant files:

- `backend/app/api/routes/auth.py`
- `backend/app/api/routes/chat.py`
- `backend/app/api/routes/bulletin.py`
- `frontend/src/lib/auth.ts`
- `frontend/src/components/RequireAuth.tsx`

The frontend stores the returned user object in localStorage and sends `X-User-Id`. The backend trusts that header. Any user can impersonate any other user by changing the localStorage value or request header.

Passwords are stored as unsalted SHA-256 hashes. There is no session token, JWT, server-side session, token expiry, logout invalidation, CSRF protection, or ownership guarantee beyond the trusted integer ID.

There is also inconsistent behavior:

- Chat falls back to a shared `default_user` if no valid `X-User-Id` is present.
- Bulletin endpoints reject missing `X-User-Id`.
- The UI requires login, but the backend chat route can still silently use the default user.

For an MVP, this does not need enterprise auth, but it must not pretend to provide account isolation if it cannot.

Minimum MVP fix:

- Either simplify to a single-user local demo mode and remove the account promise, or implement real bearer tokens.
- Replace SHA-256 password hashing with `passlib`/bcrypt or Argon2.
- Remove the chat `default_user` fallback when the UI requires login.
- Apply one consistent auth dependency across chat and bulletin endpoints.

### 3. RAG Runtime Depends On Hidden Local Artifacts

Relevant files:

- `backend/app/services/chat_orchestrator.py`
- `backend/app/services/retrieval_service.py`
- `backend/app/services/embedding_service.py`
- `backend/app/services/ollama_service.py`
- `scripts/build_bm25_index.py`
- `.env.example`

The RAG path depends on all of these being available:

- Ollama running on `OLLAMA_BASE_URL`.
- The configured chat model being pulled locally.
- `intfloat/multilingual-e5-base` available for query embeddings.
- `cross-encoder/ms-marco-MiniLM-L-6-v2` available for reranking if enabled.
- A current `exports/retrieval/articles_bm25.sqlite` index mounted into the backend container.
- Articles already embedded in Postgres.

If query embedding fails, the orchestrator falls back to lexical retrieval. If BM25 is missing or stale, retrieval logs warnings and may degrade. If the reranker model is missing, it logs and falls back. These fallbacks are useful, but for an MVP they can produce confusing behavior: the app may appear to work while returning weak or empty answers.

Minimum MVP fix:

- Add a startup health endpoint that checks database schema, article count, embedded article count, BM25 status, Ollama availability, and configured model availability.
- Surface those checks in README and optionally the UI.
- For demo mode, consider disabling the reranker by default unless the model is preloaded.
- Make stale or missing BM25 visible in API responses or an admin/debug endpoint, not only logs.

### 4. No Small, Known-Good Demo Dataset Path

Relevant files:

- `academic_platform.dump`
- `exports/`
- `docker-compose.yml`
- `scripts/create_sample_db.py`
- `README_DEV.md`

The local workspace contains a large `academic_platform.dump` and about 4.9 GB of exports, but these are ignored by Git. That is good for repository size, but it means another machine will not have the data needed to reproduce the current state.

The project needs a small deterministic dataset for MVP delivery. Without it, reviewers must run external ingestion APIs, download models, generate embeddings, cluster papers, and build snapshots before they can evaluate the product.

Minimum MVP fix:

- Create a small fixture dataset, for example 50 to 300 articles, committed as JSON/CSV or generated by `scripts/create_sample_db.py`.
- Include precomputed demo embeddings only if licensing and size are acceptable. Otherwise provide a tiny fallback model path or clear generation step.
- Add `scripts/bootstrap_demo.py --sample` that produces a complete working DB state.
- Treat the large local dump and exports as private artifacts, not the MVP path.

### 5. Health Check Is Too Shallow

Relevant file:

- `backend/app/api/routes/health.py`

`/health` returns `{"status": "ok"}` regardless of database connectivity, schema readiness, model availability, BM25 status, or whether any articles exist.

For this project, a shallow health check is actively misleading because most failures are dependency or data-preparation failures.

Minimum MVP fix:

- Keep `/health` for process liveness.
- Add `/health/ready` or `/diagnostics` that checks:
  - DB connection.
  - Alembic/schema expected tables.
  - `pgvector` extension.
  - article count.
  - embedding count.
  - cluster count.
  - snapshot count.
  - BM25 index status.
  - Ollama reachability.

## High-Priority Problems

### 6. Tests Avoid The Highest-Risk Integration Paths

Relevant files:

- `tests/`
- `tests/conftest.py`

The current tests are valuable and fast, but they mostly test pure functions, fake services, and SQL compilation. They do not cover:

- Fresh Alembic migration against Postgres.
- Backend startup from an empty database.
- Auth flow from signup/login to protected API calls.
- Chat streaming endpoint with a stubbed Ollama service.
- Retrieval against a real pgvector-enabled database.
- BM25 index build and stale-index handling.
- Frontend/backend contract tests.
- Docker Compose smoke test.

Minimum MVP fix:

- Add one integration smoke suite that runs against a temporary Postgres with pgvector.
- Stub Ollama responses for deterministic chat tests.
- Add a single happy-path test: signup, create chat session, send message, receive streamed response, save assistant message.
- Add a setup smoke test that applies Alembic migrations from scratch.

### 7. AI Answer Grounding Is Prompt-Based, Not Enforced

Relevant files:

- `backend/app/services/chat_orchestrator.py`
- `backend/app/services/rag_router_service.py`
- `backend/app/services/retrieval_service.py`
- `evaluation/`
- `scripts/run_rag_golden_set_evaluation.py`

The answer prompt instructs the LLM to cite sources and use only retrieved context. If the model omits a source section, the code appends one. That ensures source lines appear, but it does not prove the answer's claims are grounded in those sources.

There is no runtime check that every cited source was retrieved, every source in the answer exists, or that the answer avoids unsupported claims. Golden-set evaluation scripts exist, which is good, but they are not part of a required MVP verification flow.

Minimum MVP fix:

- Add a post-generation validator for source IDs: reject or repair citations not in the retrieved set.
- Return structured metadata with retrieved sources in the chat API, not only plain text.
- Define a tiny golden set for MVP and make it part of the demo checklist.
- For weak retrieval, prefer a refusal/insufficient-evidence answer over a general answer.

### 8. BM25 Index Is A Separate Consistency Boundary

Relevant files:

- `scripts/build_bm25_index.py`
- `backend/app/services/retrieval_service.py`
- `docker-compose.yml`

BM25 is stored in SQLite outside Postgres. The service can detect missing, unknown, or stale status, but the index is not automatically rebuilt by ingestion, migrations, or Docker startup. Compose mounts `./exports/retrieval` read-only into the backend container.

This is acceptable for an MVP if explicitly managed, but currently it is another hidden step.

Minimum MVP fix:

- Add BM25 build to the demo bootstrap flow.
- Add a visible diagnostic for BM25 status.
- Decide whether stale BM25 should fall back silently or disable hybrid retrieval with a clear warning.

### 9. Worker And Notification Scope Is Misleading

Relevant files:

- `backend/worker/scheduler.py`
- `backend/worker/tasks.py`
- `backend/app/services/user_bulletin_service.py`
- `docker-compose.yml`

The app has bulletin preferences with `notifications_enabled`, `notification_frequency`, and Celery/Redis dependencies. But Compose does not include Redis or a worker, and the only Celery task is a placeholder print.

For MVP, this is not a problem if notifications are out of scope. It is a problem if the UI or documentation implies that notifications actually work.

Minimum MVP fix:

- Hide notification controls or label them as inactive.
- Remove Celery/Redis from MVP requirements unless a real scheduled job exists.
- If scheduled bulletin generation is required, add Redis and worker services to Compose and implement one real task.

### 10. Repository Hygiene Can Cause Handoff Mistakes

Relevant files:

- `.gitignore`
- `frontend/TEMPLATE/`
- `ai_engine/ingestion/ingestion_state.json`

Problems:

- `frontend/TEMPLATE/` contains a zipped and extracted starter project that is tracked. This adds noise and can confuse maintainers.
- `ai_engine/ingestion/ingestion_state.json` is tracked, which means cursor/offset state may leak one developer's ingestion progress into another environment.
- `.gitignore` ignores `database/models/*` except one file, while the existing model files are already tracked. Future new model files may be silently ignored unless force-added.

Minimum MVP fix:

- Remove `frontend/TEMPLATE/` from the deliverable unless it has a documented purpose.
- Stop tracking ingestion state; keep a `.example` state file if needed.
- Fix `.gitignore` so future model files are not ignored.

## Medium-Priority Problems

### 11. Dependency Versions Are Mostly Unpinned

Relevant files:

- `requirements.txt`
- `backend/requirements.txt`
- `frontend/package.json`

Python dependencies are unpinned. This is risky for AI projects because `sentence-transformers`, `torch`, `transformers`, `bertopic`, `hdbscan`, and `umap-learn` can break behavior or installation across versions.

The local tests ran under Python 3.13.5, while the backend Dockerfile uses Python 3.11. That split may be fine, but it should be deliberate.

Minimum MVP fix:

- Freeze Python dependencies for the MVP.
- Remove `asyncio` from requirements because it is part of the standard library.
- Document the supported Python version.
- Prefer one lockfile or constraints file for reproducible setup.

### 12. Database Schema Has MVP-Level Integrity Gaps

Relevant files:

- `database/models/UserBulletinPreference.py`
- `database/models/ArticleData.py`
- `database/alembic/versions/`

Examples:

- `user_bulletin_preferences.user_id` has no foreign key to `users.id`.
- `articles.external_id` is globally unique, while source-specific external IDs are usually better represented by a composite uniqueness rule on `(source, external_id)`.
- Several migration files are empty or named generically as `init`, which makes audit/debug harder.

These are not necessarily demo blockers, but they increase the chance of confusing data problems.

Minimum MVP fix:

- Add the missing foreign key for bulletin preferences.
- Decide whether `external_id` should be globally unique or unique per source.
- Clean up migration naming or add a schema history note.

### 13. Frontend Uses A Dev Server Container

Relevant files:

- `frontend/Dockerfile`
- `docker-compose.yml`

The frontend container runs `npm run dev -- --host 0.0.0.0`. This is fine for local development, but an MVP deliverable often benefits from a production build served by a static server or backend reverse proxy.

Minimum MVP fix:

- Either document that Docker Compose is a development/demo setup, or create a production-like frontend Dockerfile using `npm run build` and static serving.

### 14. API Contract Is Partly Plain Text Where Structure Would Help

Relevant files:

- `backend/app/api/routes/chat.py`
- `frontend/src/pages/ChatPage.tsx`

The streaming chat endpoint returns `text/plain`. This keeps implementation simple, but the frontend cannot reliably distinguish answer text, citations, source metadata, route decisions, retrieval warnings, or errors.

Minimum MVP fix:

- Keep streaming text if needed, but add a final metadata endpoint or structured SSE events.
- At minimum, persist and expose message metadata consistently so the UI can render sources as actual source cards.

## What Is Already In Good Shape

- The codebase has a real layered structure: routes, schemas, services, database models, scripts, tests.
- The RAG path has useful deterministic fallbacks when routing or embeddings fail.
- The retrieval service supports vector, BM25, hybrid fusion, filters, and reranking.
- Analytics and bulletin snapshots avoid recomputing expensive payloads on every request.
- Existing Python tests are fast and currently passing.
- Frontend TypeScript build and ESLint pass.
- `.env` is ignored and `.env.example` exists.

## Recommended MVP Cut Line

For a reliable MVP, narrow the promise to:

1. Local single-machine demo.
2. One prepared sample academic dataset.
3. Working dashboard, bulletin, and chat over that dataset.
4. Source-grounded RAG answers with visible source metadata.
5. Manual account creation only if real token auth is added; otherwise single-user demo mode.

Defer or hide:

- Notifications.
- Celery/Redis worker.
- Full live multi-source ingestion in the default demo path.
- Large dump/export artifacts.
- Production-grade deployment claims.

## Suggested Priority Order

1. Create a one-command demo bootstrap path.
2. Add readiness diagnostics.
3. Fix or simplify authentication.
4. Add a small demo dataset and deterministic smoke test.
5. Make BM25 and model availability explicit.
6. Add one backend integration test with Postgres and stubbed Ollama.
7. Clean repository noise and ignored tracked-state issues.
8. Freeze dependencies for the MVP.

## MVP Acceptance Checklist

Before presenting the project as MVP-ready, the following should pass on a clean machine:

- `docker compose up --build` or `make demo` starts all required services.
- Migrations apply from an empty database.
- A sample dataset is loaded.
- At least one article has an embedding.
- At least one cluster exists.
- Dashboard shows non-empty analytics.
- Bulletin shows non-empty content or a clear empty-state explanation.
- Chat signup/login works, or the app clearly runs in single-user mode.
- A RAG question returns an answer with valid retrieved sources.
- `/health/ready` reports database, model, and retrieval readiness.
- Python tests pass.
- Frontend build and lint pass.

