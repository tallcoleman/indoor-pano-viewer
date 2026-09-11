# Indoor 360° Tour App

Self-hosted viewer for GoPro Max 2 panoramas placed on multi-floor floorplans, behind
access-code and editor authentication. FastAPI + Postgres 18 + Vite/React + Photo Sphere
Viewer + Caddy, deployed with one compose file to Coolify and to plain Docker Compose.

## Where things are written down

| Doc | Role | When to read it |
|---|---|---|
| `CLAUDE.md` (this file) | Rules and context that apply to **every** step | Always loaded |
| `docs/dev/360-tour-app-build-plan.md` | Design and rationale ("why"); decisions log in §14 | Read the sections the step doc points to |
| `docs/dev/steps/mN-*.md` | One per milestone: slices, acceptance criteria, as-built notes | The step you're working on |

If these disagree: step doc as-built notes > this file > build plan. Never resolve a
disagreement silently; raise it, then update the losing doc in the same PR.

## Workflow for a slice

Each milestone is split into **slices** (M1.2, M1.3, …). One slice = one branch = one PR.

1. **Start**: read this file, the step doc, and every plan section the slice references.
   Check the previous slices' as-built notes.
2. **Plan first**: use plan mode. The plan lists files to add or change, the tests that will
   cover each branch, and any **Decision needed** items from the step doc that block the slice.
   Wait for approval; don't pick a decision on the user's behalf.
3. **Build**: stay inside the slice. If something outside it is needed, stop and say so; don't
   quietly grow the slice.
4. **Finish**: meet the definition of done below, then fill in the slice's **As-built** notes
   in the step doc (deviations, decisions made, anything the next slice needs to know).
   If a new convention was set, add it to this file.
5. **PR**: branch `mN/<slice-number>-<short-name>` (e.g. `m1/2-import-schema`), PR against `main`.

### Definition of done (every slice)

- [ ] All acceptance criteria in the step doc pass, and the PR says how each was checked
- [ ] `api`: tests pass at **100% line + branch coverage**; ruff and the type checker are clean
- [ ] `web` (once it exists): lint, typecheck and Vitest pass
- [ ] `docker compose up --wait` still comes up healthy
- [ ] No new `# pragma: no cover` without a reason on the same line
- [ ] As-built notes written; build plan §14 updated if a decision changed

## Locked decisions

Change these only through the decisions log in build plan §14.

- **Python 3.14**, `uv`. The Python project lives in `api/` (no root `pyproject.toml`).
- **SQLAlchemy 2.0** typed models (pin `<2.1`) + **separate Pydantic v2 schemas**. psycopg 3.
  Alembic. **Sync** engine, sessions and endpoints; no async DB code.
- **mypy `--strict`** with the Pydantic plugin (no SQLAlchemy mypy plugin). ruff for lint + format.
- Root `.env` (gitignored) is the vanilla Compose config, including `COMPOSE_FILE`; `.env.example` is committed.
- **Postgres 18**, volume mounted at `/var/lib/postgresql` (not `/data`).
- IDs: UUIDv7 (`uuid.uuid7()` in Python, `server_default uuidv7()` fallback).
- Multiple floors from day one. Markdown descriptions, rendered and sanitised on the server.
- `access_event` node-level logging is in scope for v1.
- **Repo data:** only synthetic test fixtures and the non-confidential sample tour in
  `samples/sample-tour/` are committed. Production `tour.json`, photos and floorplans are never
  required in the repo; they reach the server through `IMPORT_HOST_PATH`.
- Media is served only through Caddy `forward_auth` → `/api/internal/media-auth`. No FastAPI file-serving route.
- v1 admin API = access codes, activity, placement (plus `cli export-placements`). Content CRUD endpoints belong to M6.
- Input panoramas are **GoPro Max 2 JPG, 7680×3840**; anything else is rejected.
- Opaque DB-backed session cookies. No JWTs.
- `pnpm` for JS. Vite + React + TypeScript, TanStack Router + Query.
- **ESLint (flat config) + Prettier** for JS: `typescript-eslint` type-checked, `react-hooks`,
  `@tanstack/eslint-plugin-query`, `@tanstack/eslint-plugin-router`. Not Biome.

## Conventions

<!-- Add to this list as slices set new conventions. -->

### API (Python)

- Layout: `api/app/…`, tests in `api/tests/{unit,api,cli,migrations}` (plan §10.1).
- **Never return ORM objects from endpoints.** Response schemas list fields explicitly, so
  `password_hash`, `secret_hash` and `token_hash` can never be serialised.
- Settings come only from `app/config.py` (pydantic-settings). It fails at startup on missing
  secrets or values left at `.env.example` defaults.
- Time: always timezone-aware UTC. Anything with a time window takes an injectable clock
  or is tested with `time-machine`.

### Testing

- **Real Postgres 18** (testcontainers, or `TEST_DATABASE_URL`). Never SQLite.
- Each test runs in a SAVEPOINT that is rolled back; build data with `tests/factories.py`.
- **Coverage is the floor, not the goal.** Security branches get tests that assert behaviour
  (status, body, DB state, cookie attributes), not just tests that run the line.
- **Unit-test images are synthetic and tiny** (generated with Pillow). The only real photos in
  the repo are the sample tour in `samples/sample-tour/`: non-confidential, with real location
  data removed. Never commit production tour data.

### Security invariants (never break these)

- Media is only reachable with a valid session; responses carry `Cache-Control: private`.
- Access codes are never accepted in query strings. They're shown once, stored as prefix + Argon2id hash.
- Revoking a code or deactivating an editor takes effect on the **next request**, not at session expiry.
- Every imported image has all EXIF/XMP stripped (GPS in particular).
- Markdown never passes raw HTML through; output goes through `nh3`.
- Editor mutations require a CSRF token and `Content-Type: application/json`.

### Compose portability (plan §10.3)

- `docker-compose.yml` publishes **no ports** and uses no Coolify-specific keys.
- No one-shot containers: migrations run in the `api` entrypoint; the SPA is baked into the Caddy image.
- Every service has a healthcheck. Required env vars use `${VAR:?}`.
- Differences between Coolify and vanilla come **only** from env vars.

## Commands

<!-- Filled in by M0. Keep this list accurate; later slices rely on it. -->

_Not yet created. M0 adds commands for tests, lint, typecheck, migrations, compose up, and CLI._
