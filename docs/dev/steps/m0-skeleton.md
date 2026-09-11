# M0 — Skeleton

**Goal:** an empty but real stack. Every later slice then only adds features, never infrastructure: the three services come up healthy on vanilla Compose and on Coolify, and CI enforces 100% branch coverage from the first commit.

**Plan sections:** §2 (architecture, stack), §2.2 (Postgres Docker gotcha), §5 (Caddyfile), §10 (layout, test strategy, compose rules), §12 (compose-related risks).

**Estimate:** ~1 day.

## Prerequisites (you)

- [ ] Access to the Coolify instance, plus a hostname you can point at it for a test app.
- [ ] Choose a vanilla HTTPS target: a spare VPS with DNS, **or** local `SITE_ADDRESS=localhost` (Caddy uses its internal CA; the browser needs to trust it once). Local is enough to prove the file works.
- [ ] GitHub Actions enabled on the repo.

## Decisions needed

Settle each one in M0.1 planning, then record it in CLAUDE.md "Locked decisions" or "Conventions".

| # | Decision | Status | Outcome |
|---|---|---|---|
| D1 | What to do with the `uv init` scaffold at the repo root (`pyproject.toml`, `src/indoor_pano_viewer/`, `.python-version`) | **Decided 2026-09-10** | Remove it. The Python project lives in `api/` (plan §10.1). Keep `.python-version` at the root or move it to `api/`. |
| D2 | Sync or async SQLAlchemy / endpoints | **Decided 2026-09-10** | **Sync.** A handful of concurrent viewers doesn't need async; FastAPI runs sync endpoints in a threadpool. Tests stay simpler (no event-loop fixtures, plain SAVEPOINT rollback). |
| D3 | Type checker | **Decided 2026-09-10** | **mypy `--strict`** with the Pydantic plugin. SQLAlchemy 2.0 `Mapped[]` types check natively; don't enable the deprecated `sqlalchemy.ext.mypy` plugin. |
| D4 | JS lint/format | **Decided 2026-09-10** | **ESLint (flat config) + Prettier.** Plugins: `typescript-eslint` type-checked configs, `eslint-plugin-react-hooks`, `@tanstack/eslint-plugin-query`, `@tanstack/eslint-plugin-router`. Chosen over Biome for the TanStack rules and full type-aware promise rules, which Biome lacks; lint speed doesn't matter at this frontend's size. Look at Oxlint again once its JS plugin support is stable. |
| D5 | Where `.env` lives and how `COMPOSE_FILE` is set for vanilla | **Decided 2026-09-10** | Root `.env` (gitignored) holding `COMPOSE_FILE=docker-compose.yml:docker-compose.selfhost.yml`; `.env.example` committed. |

## Slices

### M0.1 — API skeleton, test harness, CI

Scope:
- Apply D1. Create `api/` with `pyproject.toml` (Python 3.14, deps from plan §2), ruff, type checker config, `[tool.coverage.*]` and `[tool.pytest.ini_options]` exactly as plan §10.2.
- `app/main.py`, `app/config.py` (pydantic-settings; fail fast on missing or example secrets), `app/db.py` (engine and session dependency), `app/routers/health.py`.
- `GET /api/healthz`: 200 when the DB answers `SELECT 1`, 503 otherwise.
- Alembic initialised with a SQLAlchemy `MetaData(naming_convention=…)` so constraint names are deterministic (needed for `alembic check` and clean downgrades). First migration: `CREATE EXTENSION IF NOT EXISTS citext`.
- `tests/conftest.py`: Postgres 18 via testcontainers (or `TEST_DATABASE_URL`), `alembic upgrade head` once per session, per-test SAVEPOINT rollback, `httpx` client against the ASGI app.
- `tests/migrations/test_migrations.py`: up → down → up, and `alembic check`.
- `.github/workflows/ci.yml` `api` job: ruff, type check, pytest with the coverage gate, pragma count.
- Fill in the CLAUDE.md **Commands** section.

Acceptance:
- [ ] `uv run pytest` (in `api/`) passes, reports 100% line + branch, and fails if a branch is removed from a test
- [ ] Tests cover: healthz 200, healthz 503 (DB unreachable), config raises on missing secret, config raises on example secret
- [ ] Migration test passes; `alembic check` reports no drift
- [ ] CI is green on the PR

As-built:
<!-- fill in on completion -->

### M0.2 — Compose, Caddy, hello SPA

Scope:
- `web/`: Vite + React + TS "hello" page, pnpm, ESLint + Prettier (D4), Vitest with one test, `tsc --noEmit`. Configure all D4 plugins now, even the TanStack ones before TanStack is used, so the lint setup is final from the first commit.
- `caddy/Dockerfile` (multi-stage: pnpm build → `caddy:2` with `/srv/www`) and `caddy/Caddyfile` from plan §5, but without the `/media/*` block yet (M2). Use `SITE_ADDRESS` and `TRUSTED_PROXY_RANGES`. **Check** how Caddy handles an empty `TRUSTED_PROXY_RANGES`; if an empty `static` list is invalid, use a placeholder or split the global options in a way that still needs no file edits between hosts.
- `api/Dockerfile`: `python:3.14-slim` + uv; entrypoint runs `alembic upgrade head`, then `uvicorn --proxy-headers --forwarded-allow-ips=…`.
- `docker-compose.yml`, `docker-compose.selfhost.yml`, `docker-compose.dev.yml`, `.env.example`, following every rule in plan §10.3: `expose` only, healthchecks, `${VAR:?}`, db volume at `/var/lib/postgresql`, media named volume, `${IMPORT_HOST_PATH}` bind mount (read-only), `depends_on: service_healthy`.
- Dev override: Vite on 5173, proxying `/api` and `/media`; db port on localhost.
- Add `/data/` to `.gitignore`. It holds local import and media data; production tour data never goes in the repo (M1 D1).
- CI `web` job (lint, typecheck, Vitest) and `compose-smoke` job: `docker compose up --wait`, `curl` the SPA and `/api/healthz` through Caddy, then `down` + `up` and check a row written before the restart still exists.

Acceptance:
- [ ] `docker compose up --wait` from a clean clone (with `.env` copied from the example) → all services healthy
- [ ] `https://localhost/` serves the hello page; `https://localhost/api/healthz` → 200
- [ ] `docker compose -f docker-compose.yml config` shows no `ports:`
- [ ] Removing a required var from `.env` makes `docker compose up` refuse to start
- [ ] Data survives `docker compose down && docker compose up --wait` (not `down -v`)
- [ ] Dev override: editing the React page hot-reloads; `/api/healthz` works through the Vite proxy
- [ ] CI `web` and `compose-smoke` jobs green

As-built:
<!-- fill in on completion -->

### M0.3 — Deploy to both hosts (mostly you)

Scope:
- Vanilla: deploy to the chosen target with `SITE_ADDRESS=<host>`; confirm real HTTPS.
- Coolify: new Docker Compose resource from the repo; set env vars in the UI (`SITE_ADDRESS=:80`, etc.); assign `https://<test-domain>:80` to the `caddy` service.
- Run `docker network inspect coolify` (or whichever network Coolify attaches) on the server, then set `TRUSTED_PROXY_RANGES` → resolves build plan §14 open question 3.
- Claude writes `docs/dev/deploy.md`: a runbook for both hosts built from what actually worked, including the Coolify UI settings that aren't in the repo.

Acceptance:
- [ ] Both hosts serve the hello page and `/api/healthz` over HTTPS
- [ ] On Coolify, redeploying keeps DB data
- [ ] `docs/dev/deploy.md` exists and someone could follow it cold
- [ ] Plan §14 open question 3 answered and moved to the decisions table

As-built:
<!-- fill in on completion -->

## Out of scope

Models beyond the citext extension, auth, media serving, real frontend routes.
