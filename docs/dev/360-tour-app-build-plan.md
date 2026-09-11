# Indoor 360° Tour App — Build Plan

A self-hosted web app for displaying 360° panoramas positioned on a building floorplan,
behind authentication. FastAPI + Postgres + Vite/React SPA + Caddy. The same
`docker-compose.yml` deploys to a self-hosted Coolify instance (Docker Compose build pack)
and to any plain Docker host with `docker compose up`.

---

## 1. Scope

### In scope (v1)

- Display equirectangular 360° panoramas using [Photo Sphere Viewer](https://photo-sphere-viewer.js.org/) (MIT).
- Position panoramas on **non-georeferenced** floorplan images via the Map plugin.
- **Multi-floor from day one**: every node belongs to a floor; the map changes when you move
  between floors.
- Navigate between panoramas via floorplan hotspots, arrow links (including between floors),
  and a thumbnail gallery.
- Per-panorama **Markdown** descriptions and in-panorama markers.
- **Editors**: real accounts (email + password) for anyone who administers the tour.
- **Viewers**: unique, revocable, individually-attributable access codes. No accounts.
- **Node-level activity logging** (`access_event`): which nodes each access code viewed, and when.
- Media served only to authenticated sessions; no public URLs.
- Tour content authored as a JSON file + image directory, loaded via an import CLI.

### Input assumptions (v1)

- All panoramas are **JPG files from a GoPro Max 2**: 29 MP, 7680×3840, 2:1 equirectangular.
  The import pipeline is built for exactly this and rejects anything else (see §6).
- Floorplans are PNG (or JPG) raster images.

### Out of scope (v1)

- 360° video (host separately, e.g. unlisted YouTube; optionally embed a link as a marker).
- Other cameras and formats (HEIC, raw, dual-fisheye). The input check is one function, so
  adding them later is easy.
- Multi-building / multi-tenant management (schema allows it; UI does not).
- Image blurring/redaction (done externally in GIMP before import).
- Placement GUI (see §11 for the effort analysis and the recommended interim tool).

### Non-negotiables

- One `docker-compose.yml` that works **unchanged** on Coolify's Docker Compose build pack
  and on vanilla Docker Compose (see §10.3). No external SaaS dependency for auth.
- The app is the auth layer. Media is never publicly reachable.
- Tour definition is reproducible and diffable (lives in git, re-importable).
- **The API has 100% line and branch coverage**, enforced in CI (see §10.2).

---

## 2. Architecture

```
                   ┌───────────────────────────────┐
   browser ─ 443 ─▶│ Coolify proxy (Coolify only)  │  TLS terminates here on Coolify
                   └───────────────┬───────────────┘
                                   │ http :80
                        ┌──────────▼───────────────────────────┐
   (vanilla: 443 ──────▶│ Caddy                                │  TLS terminates here on vanilla
    straight to Caddy)  │  /            → SPA (baked into image)│
                        │  /api/*       → reverse_proxy api    │
                        │  /media/*     → forward_auth api     │
                        │                 then file_server     │
                        └──────┬────────────────────┬──────────┘
                               │                    │
                        ┌──────▼──────┐      ┌──────▼───────┐
                        │ api         │      │ media volume │
                        │ FastAPI     │      │ (read-only   │
                        │ uvicorn     │      │  to Caddy)   │
                        └──────┬──────┘      └──────────────┘
                               │
                        ┌──────▼──────┐
                        │ db          │
                        │ Postgres 18 │
                        └─────────────┘
```

**Single origin.** Caddy serves the SPA, the API and the media from the same hostname.
No CORS, cookies work without `SameSite=None`, and Photo Sphere Viewer only needs
`withCredentials: true` rather than injecting bearer tokens into the texture loader.

**Why keep Caddy on Coolify?** Coolify's own proxy could do the routing and forward-auth
through labels, but those labels mean nothing on a plain Docker host. Keeping Caddy inside
the stack puts all routing and auth in one portable file. Coolify's proxy only terminates TLS
and forwards to `caddy:80`.

### Stack choices

| Layer | Choice | Notes |
|---|---|---|
| Reverse proxy | Caddy 2 | Automatic HTTPS on vanilla; plain HTTP behind Coolify's proxy. `forward_auth` replaces nginx's `auth_request` + `X-Accel-Redirect`. |
| API | FastAPI + Uvicorn, **Python 3.14** | 3.14 has `uuid.uuid7()` built in, and coverage.py can measure branches cheaply on it (§10.2). |
| ORM | **SQLAlchemy 2.0** (typed `Mapped[]`) + separate Pydantic v2 schemas | See §2.1. Pin `<2.1` until 2.1 is released as final, then upgrade. |
| DB driver | psycopg 3 | |
| Migrations | Alembic | Autogenerate + hand-review every migration; `alembic check` in CI. |
| DB | **Postgres 18** | See §2.2. |
| Password/secret hashing | Argon2id (`argon2-cffi`) | |
| Image processing | Pillow | JPG only; no `pillow-heif` needed. |
| Markdown | `markdown-it-py` (raw HTML off) + `nh3` sanitiser | Rendered on the server; see §3 and §9. |
| API testing | pytest, coverage.py, httpx, testcontainers, time-machine | See §10.2. |
| Frontend | Vite + React + TypeScript | |
| Routing / data | TanStack Router + TanStack Query | |
| Viewer | `@photo-sphere-viewer/core` + plugins | Map, Virtual Tour, Markers, Gallery, Compass. |
| Frontend testing | Vitest; Playwright smoke tests | No coverage target. |
| Package manager | `uv` (Python), `pnpm` (JS) | |

### 2.1 ORM: SQLAlchemy 2.0 vs SQLModel

SQLModel is a layer on top of SQLAlchemy and Pydantic. One class is both the table and the
Pydantic model. So the real question is whether that merging helps this schema or gets in
its way.

| Concern | SQLAlchemy 2.0 | SQLModel |
|---|---|---|
| Maturity | Stable 2.0 line; 2.1 is at release candidate. | Still `0.0.x` and marked "Beta" on PyPI. Releases are frequent but make no stability promise. |
| Boilerplate | Model and API schema are separate classes, so some fields are written twice. | One class can serve as table, input and output for simple CRUD. **This is its main selling point.** |
| Secret columns | API schemas list exactly what gets exposed; `password_hash`, `secret_hash` and `token_hash` can't leak by accident. | Returning a table model from an endpoint returns every column. The docs' fix is separate `Base`/`Create`/`Public` classes, which removes most of the boilerplate savings. |
| Postgres-specific types | `citext`, native enums, `uuidv7()` server defaults, check constraints and composite FKs are all first-class. | Anything beyond basic types needs `sa_column=Column(...)`, and then you're writing SQLAlchemy anyway. |
| Relationships | Fully typed. `use_alter` / `post_update` handle the circular `tour.default_node_id` ↔ `node.tour_id` FK. | Relationship typing is weaker; circular or self-referencing cases need SQLAlchemy arguments passed through `sa_relationship_kwargs`. |
| Alembic | Works directly. | Works, but autogenerated migrations reference `sqlmodel.sql.sqltypes.AutoString`, so you have to add an import to `script.py.mako`. |
| Keeping up | Gets new features (2.1: better typing, free-threading work) first. | Trails SQLAlchemy and Pydantic releases. |
| Docs | Big and dense, but covers everything. | Friendly tutorials; for anything advanced it sends you to the SQLAlchemy docs. |
| Effect on 100% coverage | Neutral. Coverage measures your code, and neither library adds branches you'd have to test. | Neutral. |

**Decision: SQLAlchemy 2.0.** This schema has most of what SQLModel handles poorly: three hash
columns that must never be serialised, `citext`, enums, UUIDv7 defaults, per-tour composite
uniqueness, and a circular FK. SQLModel would win on a flat CRUD app where each table is
basically the API response. This project isn't that.

### 2.2 Postgres version

Postgres has **no LTS release**. Every major version gets 5 years of fixes. As of
September 2026:

| Version | Released | End of life |
|---|---|---|
| 19 | beta 3 (Aug 2026); final expected ~Sept/Oct 2026 | — |
| **18** | Sept 2025 | **Nov 2030** |
| 17 | Sept 2024 | Nov 2029 |
| 16 | Sept 2023 | Nov 2028 |

**Use 18** (`postgres:18`, which tracks the latest minor release). It's the newest production
release, gives the longest support window you can get today, and has a native `uuidv7()`
function that matches the ID strategy in §3. Plan a move to 19 after its first couple of
minor releases. At this data size a `pg_dump`/restore upgrade takes minutes.

> **Docker gotcha for 18+:** the official image now mounts its volume at
> `/var/lib/postgresql`, not `/var/lib/postgresql/data` (`PGDATA` is
> `/var/lib/postgresql/18/docker`). If you mount the old path, data silently goes into an
> anonymous volume and is lost when the container is recreated.

---

## 3. Data model

Unless noted otherwise, every table has `id uuid` (UUIDv7: generated in Python with
`uuid.uuid7()` so IDs exist before flush, with a `server_default uuidv7()` fallback),
`created_at`, and `updated_at`.

### `editor`
| Column | Type | Notes |
|---|---|---|
| `email` | citext unique | |
| `password_hash` | text | Argon2id |
| `is_active` | bool | |
| `last_login_at` | timestamptz | |

### `tour`
| Column | Type | Notes |
|---|---|---|
| `slug` | text unique | URL key, e.g. `building-a` |
| `title` | text | |
| `description` | text | Markdown source |
| `default_node_id` | fk node, nullable | Entry point. Circular with `node.tour_id`, so create it with `use_alter=True` |
| `is_published` | bool | |

### `floor`
| Column | Type | Notes |
|---|---|---|
| `tour_id` | fk | |
| `slug`, `name` | text | unique per tour |
| `ordering` | int | bottom-to-top; drives the floor switcher order |
| `image_path` | text | floorplan image, relative to media root |
| `image_width`, `image_height` | int | pixels; Map plugin coordinates are in this space |
| `default_node_id` | fk node, nullable | where the floor switcher lands; `use_alter=True` |

Unique `(tour_id, id)` so `node` can reference it with a composite FK (below).

### `node` — one panorama
| Column | Type | Notes |
|---|---|---|
| `tour_id`, `floor_id` | fk | composite FK `(tour_id, floor_id) → floor(tour_id, id)`; a node can't sit on another tour's floor |
| `slug` | text | unique per tour |
| `title` | text | shown in gallery + caption |
| `description` | text | **Markdown source**; rendered to sanitised HTML by the API (§9) |
| `pano_path`, `thumb_path` | text | relative to media root |
| `pano_width`, `pano_height` | int | processed dimensions (after any downscale) |
| `map_x`, `map_y` | float | **pixel coordinates on this node's floor image**; check constraint ≥ 0 |
| `sphere_pan` | float | **north-alignment offset, radians.** See §7 |
| `default_yaw`, `default_pitch`, `default_zoom` | float | initial view |
| `ordering` | int | gallery order |
| `captured_at` | timestamptz nullable | read from EXIF before stripping |

### `link` — navigation arrows between nodes
| Column | Type | Notes |
|---|---|---|
| `from_node_id`, `to_node_id` | fk | unique pair; check `from <> to` |
| `yaw_override` | float nullable | usually null; derive from map geometry |

> Arrow positions can be **computed** from `map_x/map_y` + `sphere_pan` rather than
> authored. Only override where the computed direction is wrong (e.g. through a wall).
> This removes most of the tedium of hand-authoring links.
>
> **Links between floors** (stairs, elevators) can't be computed, because the two nodes are on
> different floorplan images. The import requires `yaw_override` whenever `from` and `to` are
> on different floors.

### `marker` — in-panorama annotations
| Column | Type | Notes |
|---|---|---|
| `node_id` | fk | |
| `yaw`, `pitch` | float | |
| `kind` | enum | `note`, `image`, `link` |
| `label` | text | plain text |
| `content` | text | Markdown source |
| `size` | int nullable | |

### `access_code` — viewer credentials
| Column | Type | Notes |
|---|---|---|
| `tour_id` | fk nullable | null = all tours |
| `label` | text | **"Jane Smith — Acme Consulting"**; this is your attribution |
| `prefix` | text unique indexed | lookup key, see §4 |
| `secret_hash` | text | Argon2id |
| `expires_at` | timestamptz nullable | |
| `revoked_at` | timestamptz nullable | |
| `note` | text | free-form |
| `created_by` | fk editor | |

Codes are never deleted, only revoked, so `access_event` rows always keep their attribution.

### `access_session`
| Column | Type | Notes |
|---|---|---|
| `access_code_id` | fk | |
| `token_hash` | text unique indexed | SHA-256 of the opaque cookie token |
| `expires_at` | timestamptz | |
| `last_seen_at` | timestamptz | answers "has Jane opened this yet?" |
| `user_agent` | text | |
| `ip_prefix` | text nullable | store /24 or /48 only, or omit entirely |

### `access_event` — node-level activity log

Append-only, so it has no `updated_at`. One row per node view by a viewer session.

| Column | Type | Notes |
|---|---|---|
| `access_code_id` | fk, not null | attribution; codes are never deleted |
| `access_session_id` | fk nullable, `ON DELETE SET NULL` | sessions are deleted on logout/expiry; the event outlives them |
| `tour_id` | fk | |
| `node_id` | fk nullable, `ON DELETE SET NULL` | `import --prune` can delete nodes |
| `node_slug` | text | copied at write time, so history still reads correctly after a prune |
| `occurred_at` | timestamptz | server time, not client time |

Indexes: `(access_code_id, occurred_at DESC)` for the activity view; `(tour_id, node_id)` for
"who looked at this room".

Rules:

- **Viewers only.** Editor sessions never create events.
- **Deduplicate on the server**: skip the insert if the same session logged the same node
  within the last 60 s. Flicking back and forth between nodes shouldn't create dozens of rows.
- **Retention**: `ACCESS_EVENT_RETENTION_DAYS` (unset = keep forever) plus
  `cli events prune`. This is personal, attributable browsing data, so pick a period on
  purpose rather than defaulting to forever by accident.
- **Disclosure**: the unlock page says that access is logged per code.

### `editor_session`
Same shape as `access_session` but keyed to `editor_id`.

---

## 4. Authentication design

### Two principals, one mechanism

Both editors and viewers get an **opaque, DB-backed session token** in an HttpOnly cookie.
No JWTs. With one server and a small table, a DB row gives instant revocation plus
`last_seen_at` for free. Stateless tokens would add nothing here and would cost you revocation.

| | Editor | Viewer |
|---|---|---|
| Credential | email + password | access code |
| Cookie | `ed_session` | `vw_session` |
| Path scope | `/` | `/` |
| Lifetime | 12h, sliding | configurable per code, default 30d |
| Can call | `/api/admin/*`, `/api/tour/*`, `/media/*` | `/api/tour/*`, `/media/*` |

### Access code format

```
k7f3q2xa-9BqR2xLmWvN8dY4pKt3s
└──────┘ └────────────────────┘
 prefix        secret
 (indexed)     (Argon2id hashed)
```

- Generate with `secrets.token_urlsafe`; secret must carry ≥128 bits of entropy.
- **The prefix exists so you can look the row up.** If you hash the whole code you cannot
  find it without scanning and hashing every row in the table. Same pattern as GitHub /
  Stripe tokens.
- Display the full code **once**, at creation time. Store only the hash.

### Unlock flow

1. `POST /api/unlock` with `{"code": "..."}`.
2. Split on the first `-`, look up by prefix, verify with Argon2id.
3. Check `revoked_at IS NULL` and `expires_at`.
4. Create `access_session`, set HttpOnly cookie, return the tour slug.

**Never accept the code as a query parameter.** It leaks into Referer headers, proxy logs
and browser history. If you want one-click links, put it in the URL *fragment*
(`https://host/t/building-a#code=k7f3q2xa-...`), which is never sent to the server; the SPA
reads `location.hash`, POSTs it, then immediately calls
`history.replaceState` to strip it.

### Hardening checklist

- **Rate limit `/api/unlock`**: per-IP token bucket plus a global ceiling. A revocable code
  that can be brute-forced is not revocable. An in-process limiter is fine (single instance);
  reach for Redis only if you scale out.
- **Find the real client IP.** On Coolify, requests pass through two proxies
  (Coolify proxy → Caddy → api). If you get this wrong, every request seems to come from the
  proxy and the per-IP limit turns into one global limit. Configure Caddy
  `servers { trusted_proxies static <range> }`, with the range set by an env var
  (`TRUSTED_PROXY_RANGES`, empty on vanilla), and run uvicorn with
  `--proxy-headers --forwarded-allow-ips=<caddy's network>`. Write a test that sends a spoofed
  `X-Forwarded-For` and checks it is ignored when it doesn't come from a trusted proxy.
- **Constant-time comparison** on the prefix lookup result; return an identical error and
  a similar response time for "no such prefix" and "wrong secret".
- **Cookies**: `HttpOnly; Secure; SameSite=Lax; Path=/`.
- **CSRF**: `SameSite=Lax` covers the common cases, but add a double-submit CSRF token for
  all editor mutations. Reject state-changing requests without `Content-Type: application/json`.
- **Argon2id params**: use `argon2-cffi` defaults or stronger; unlock is rare so cost is free.
  (Tests use cheap parameters through settings; one test asserts the production defaults.)
- **Session rotation**: issue a fresh token on privilege change; delete on logout.
- **`last_seen_at` throttling**: update at most once per minute per session, otherwise a
  single tour visit writes hundreds of times.
- **Security headers** (set in Caddy):
  ```
  Strict-Transport-Security "max-age=31536000; includeSubDomains"
  X-Content-Type-Options "nosniff"
  Referrer-Policy "no-referrer"
  Content-Security-Policy "default-src 'self'; img-src 'self' data: blob:; worker-src 'self' blob:; style-src 'self' 'unsafe-inline'"
  ```
  `img-src` needs `blob:` and `data:` because three.js builds textures from blobs.
  Verify the CSP against a real panorama load before locking it down.

---

## 5. Media serving

### Layout

```
/data/media/
  tours/<tour-slug>/
    floors/<floor-slug>.png
    nodes/<node-slug>/
      pano.jpg
      thumb.jpg
```

### MVP: serve from FastAPI

`FileResponse` behind the session dependency. With a handful of concurrent viewers this is
completely adequate. Check your Starlette version's Range-request support if you later serve
anything seekable.

### Production: hand off to Caddy

```caddyfile
{
    servers {
        trusted_proxies static {$TRUSTED_PROXY_RANGES}
    }
}

# vanilla: SITE_ADDRESS=tour.example.com  (Caddy fetches certificates)
# Coolify: SITE_ADDRESS=:80               (Coolify's proxy terminates TLS)
{$SITE_ADDRESS} {
    encode zstd gzip

    handle /api/* {
        reverse_proxy api:8000
    }

    handle /media/* {
        forward_auth api:8000 {
            uri /api/internal/media-auth
        }
        root * /data/media
        header Cache-Control "private, max-age=3600"
        file_server
    }

    handle {
        root * /srv/www
        try_files {path} /index.html
        file_server
    }
}
```

`forward_auth` reissues the request to your endpoint with the original cookies, so the
existing session dependency works unchanged. Return `204` to allow, `403` to deny.

**Watch the subrequest volume.** Every media request triggers an auth call. That's fine for
whole-JPEG panoramas. If you later tile for multi-resolution, one node view becomes dozens
of tile fetches and therefore dozens of auth calls. To mitigate, authorise per node prefix
and cache the decision in-process for a short TTL. (nginx's `auth_request` behaves the same
way; this isn't a Caddy limitation.)

Always set `Cache-Control: private` so no shared cache retains confidential imagery.

---

## 6. Tour authoring via import CLI

### `tour.json`

```json
{
  "tour": {
    "slug": "building-a",
    "title": "Building A — Interior Survey",
    "default_node": "lobby-main"
  },
  "floors": [
    { "slug": "level-1", "name": "Level 1", "image": "floors/level-1.png", "ordering": 1,
      "default_node": "lobby-main" },
    { "slug": "level-2", "name": "Level 2", "image": "floors/level-2.png", "ordering": 2,
      "default_node": "stair-a-l2" }
  ],
  "nodes": [
    {
      "slug": "lobby-main",
      "floor": "level-1",
      "title": "Main Lobby",
      "description": "Looking north toward the reception desk.\n\nThe **mezzanine** above was added in the 2011 retrofit.",
      "pano": "nodes/lobby-main/pano.jpg",
      "map": { "x": 412, "y": 388 },
      "sphere_pan": 1.221,
      "default_yaw": 0,
      "links": ["corridor-east", "stair-a-l1"],
      "markers": [
        { "yaw": 0.42, "pitch": -0.1, "kind": "note",
          "label": "Original 1962 terrazzo", "content": "Retained during the retrofit." }
      ]
    },
    {
      "slug": "stair-a-l1",
      "floor": "level-1",
      "title": "Stair A — Level 1",
      "pano": "nodes/stair-a-l1/pano.jpg",
      "map": { "x": 640, "y": 210 },
      "sphere_pan": 0.35,
      "links": [
        "lobby-main",
        { "to": "stair-a-l2", "yaw": 2.9 }
      ]
    }
  ]
}
```

A link is either a slug (direction computed from the map) or `{ "to", "yaw" }`. The object
form is required when the target is on a different floor.

### CLI

`exec` into the running `api` container. This works the same on both hosts; on Coolify, use
the `api` service's **Terminal** tab and drop the `docker compose exec api` prefix.

```bash
docker compose exec api python -m app.cli import /data/import/tour.json
docker compose exec api python -m app.cli import /data/import/tour.json --dry-run
docker compose exec api python -m app.cli reprocess-images --tour building-a
docker compose exec api python -m app.cli code create --label "Jane Smith — Acme" --expires 30d
docker compose exec api python -m app.cli code list
docker compose exec api python -m app.cli code revoke k7f3q2xa
docker compose exec api python -m app.cli code activity k7f3q2xa
docker compose exec api python -m app.cli events prune --older-than 365d
docker compose exec api python -m app.cli editor create --email you@example.com
```

**Import behaviour**

- Validate the whole file with Pydantic before touching the DB, and report every error at once.
  Beyond field types, validate across records: every `node.floor` exists, `map.x/y` fall
  inside that floor's image dimensions, link targets exist, links between floors have a
  `yaw`, and `default_node`s exist and sit on the right floor.
- Upsert by slug. Re-running must be safe and idempotent.
- Nodes absent from the file are *reported*, not deleted, unless `--prune`. Pruning keeps the
  `access_event` history (FK set to null; `node_slug` stays).
- Wrap the whole import in one transaction.

**Image processing on import (GoPro Max 2 JPG)**

1. **Check the input.** Accept only JPEG (check the file's magic bytes, not just the
   extension). Reject anything that isn't 2:1. Warn if a 2:1 image isn't 7680×3840, since that
   usually means a different camera mode or an image that was already processed.
2. **Read what you need from EXIF first**: `DateTimeOriginal` → `captured_at`.
3. **Strip all EXIF/XMP, especially GPS.** The Max 2 has GPS and embeds location when it's
   enabled. Given that the whole point is confidentiality, this matters. Add a test that runs a
   fixture JPG with fake GPS through the pipeline and asserts no GPS tags remain.
4. **Heading metadata: check before relying on it.** Some 360 cameras write XMP
   `PoseHeadingDegrees`, which could seed `sphere_pan`. It isn't confirmed that the Max 2 does.
   Run `exiftool -G1 -a -xmp:all -exif:all pano.jpg` on a real sample in M1 and decide then.
   Until then, `sphere_pan` comes from the alignment helper (§7).
5. Generate a ~400px-wide thumbnail for the gallery.
6. **Downscale 7680×3840 → 6144×3072 by default** (`--max-width`), re-encoding at quality ~90.
   A full-size Max 2 frame is a ~118 MB RGBA texture, which is a lot for mobile browsers
   (see §12).
7. Set `Image.MAX_IMAGE_PIXELS` explicitly (e.g. 40 M). A Max 2 frame is 29.5 M pixels, which
   is already under Pillow's default guard. The explicit lower limit is a guardrail: an
   unexpectedly huge file fails loudly instead of being processed.

---

## 7. The alignment problem (build this on day one)

Every node needs three hand-set numbers:

| Field | How you get it | Automatable? |
|---|---|---|
| `map_x`, `map_y` | click the right spot on the floorplan | No — you know where you stood |
| `sphere_pan` | rotate until the panorama's north matches the floorplan | **No — must be eyeballed** (unless §6 step 4 finds usable heading metadata) |

`sphere_pan` is the expensive one. It can't be computed (no GPS indoors, and no compass you
can trust there). If it's wrong, every navigation arrow and the map's viewing-direction cone
point the wrong way. That's immediately obvious and deeply annoying.

### Alignment helper — ~150 lines, half a day

A dev-only mode in the viewer, gated behind an editor session:

- `?align=1` enables it.
- Arrow keys nudge `sphereCorrection.pan` for the current node (Shift = coarse, plain = fine),
  live, with the map's direction cone visible so you can see when it's right.
- Clicking the floorplan sets `map_x/map_y` for the current node (on the current node's floor).
- A floating panel shows the current values and a **Copy JSON patch** button.
- `n` / `p` step to the next/previous node (in floor order, then gallery order).

This turns a ~3-minute-per-node chore into a ~20-second one. Over 100 nodes that's the
difference between a lost weekend and an afternoon. It is also the core interaction of the
eventual placement GUI, so you build it once and reuse it.

---

## 8. API surface

### Public
- `GET  /api/healthz` → 200 when the DB is reachable (used by the compose healthcheck)
- `POST /api/unlock` → set viewer session
- `POST /api/session/logout`
- `GET  /api/session` → current principal + capabilities

### Viewer (session required)
- `GET  /api/tours/{slug}` → PSV-ready payload: floors, nodes, links, markers, media URLs,
  descriptions as sanitised `description_html`
- `POST /api/tours/{slug}/nodes/{node}/viewed` → `204`; records an `access_event` (deduplicated,
  viewer sessions only; editors get `204` and nothing is written)

### Editor
- `POST /api/auth/login`, `POST /api/auth/logout`
- `GET/POST/PATCH/DELETE /api/admin/tours|floors|nodes|markers|links`
- `GET/POST /api/admin/access-codes`, `POST /api/admin/access-codes/{id}/revoke`
- `GET /api/admin/access-codes/{id}/activity` → sessions + node-level events, paginated
- `GET /api/admin/tours/{slug}/activity?node=` → who viewed which nodes, when
- `POST /api/admin/nodes/{id}/placement` → `{map_x, map_y, sphere_pan}` (used by the alignment helper)

### Internal
- `GET /api/internal/media-auth` → 204/403 for Caddy `forward_auth`

Design `GET /api/tours/{slug}` to return something the frontend can hand almost directly to
the Virtual Tour plugin's `setNodes()`. Keep the shape-shifting on the server; it's also where
the 100% coverage requirement makes it cheapest to test.

---

## 9. Frontend

### Routes

| Route | Purpose |
|---|---|
| `/unlock` | code entry; also handles `#code=` fragment; states that access is logged |
| `/t/:slug` | the viewer |
| `/login` | editor login |
| `/admin` | tours, nodes, access codes, activity |

### Viewer composition

```
Viewer (core)
├── VirtualTourPlugin   (manual mode, client-side, nodes from /api/tours/{slug})
├── MapPlugin           (current floor's image; center = node.map_x/map_y; hotspots = nodes on this floor)
├── MarkersPlugin       (per-node annotations)
├── GalleryPlugin       (thumbnails, ordered)
├── CompassPlugin       (optional; only meaningful once sphere_pan is correct)
└── FloorSwitcher       (custom navbar button/menu; ours, not a PSV plugin)
```

Key configuration points:

- `withCredentials: true` on the Viewer so media requests carry the session cookie.
- `sphereCorrection: { pan: node.sphere_pan }` per node.
- **Multi-floor**: on `node-changed`, if the floor changed, call the Map plugin's `setImage()`
  and replace hotspots with that floor's nodes. The floor switcher jumps to
  `floor.default_node`. Build this in M3; don't add it later.
- Floorplan hotspots are the **primary** navigation and arrow links are a convenience, so
  you don't need a dense link graph. Links between floors are the exception: they're the only
  way to change floors without the switcher.
- **Descriptions**: the API renders Markdown to HTML (raw HTML disabled, then `nh3` as a second
  layer of defence) and returns `description_html`. The frontend puts it in the PSV side panel.
  The frontend never parses Markdown, so the sanitiser runs, and is tested, in one place.
- **Activity**: on `node-changed`, `fetch(POST …/viewed, { keepalive: true })`, fire-and-forget
  so a slow or failed request never blocks navigation.

### Performance

- Preload the panoramas of linked neighbours on idle.
- Cap concurrent decodes; a 6144×3072 JPEG is ~75 MB as a texture, and a full 7680×3840 is ~118 MB.
- Consider the tiled adapter only if load times prove unacceptable (§12).

---

## 10. Repo layout, tests & compose

### 10.1 Layout

```
.
├── docker-compose.yml             # the only file Coolify reads; no published ports
├── docker-compose.selfhost.yml    # vanilla-only: publishes 80/443
├── docker-compose.dev.yml         # Vite dev server, db port exposed
├── .env.example
├── .github/workflows/ci.yml       # lint, api tests + coverage gate, web tests, compose smoke
├── caddy/
│   ├── Dockerfile                 # multi-stage: pnpm build web/ → caddy:2 image with /srv/www
│   └── Caddyfile
├── api/
│   ├── Dockerfile                 # python:3.14-slim; entrypoint runs migrations then uvicorn
│   ├── pyproject.toml             # includes [tool.coverage.*] and [tool.pytest.ini_options]
│   ├── alembic/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py              # pydantic-settings; fail fast on missing/example secrets
│   │   ├── db.py
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── routers/
│   │   │   ├── auth.py  unlock.py  tours.py  activity.py  admin.py  internal.py  health.py
│   │   ├── security.py            # argon2, tokens, session deps, rate limit
│   │   ├── media.py               # image processing
│   │   ├── markdown.py            # markdown-it-py + nh3
│   │   ├── importer.py            # tour.json schema + upsert
│   │   └── cli.py
│   └── tests/
│       ├── conftest.py            # Postgres container, per-test SAVEPOINT rollback, app client, clock
│       ├── factories.py           # editor/tour/floor/node/code/session builders
│       ├── fixtures/
│       │   ├── images/            # tiny 2:1 JPG with fake GPS EXIF, non-2:1 JPG, PNG, truncated JPG
│       │   └── tours/             # valid multi-floor tour.json + one file per validation error
│       ├── unit/
│       │   ├── test_security.py   test_rate_limit.py   test_markdown.py
│       │   ├── test_media.py      test_import_schema.py   test_config.py
│       ├── api/
│       │   ├── test_health.py     test_unlock.py   test_auth.py   test_session.py
│       │   ├── test_tours.py      test_access_events.py   test_activity.py
│       │   ├── test_admin_*.py    test_internal_media_auth.py   test_proxy_headers.py
│       ├── cli/
│       │   └── test_import.py     test_codes.py   test_events.py   test_editor.py
│       └── migrations/
│           └── test_migrations.py # upgrade head → downgrade base → upgrade head; alembic check
├── web/
│   ├── vite.config.ts             # also configures Vitest
│   ├── src/
│   │   ├── routes/
│   │   ├── viewer/                # PSV setup, plugins, floor switcher, alignment helper
│   │   └── api/                   # generated or hand-written client
│   │   (tests live next to the code as *.test.ts[x])
│   └── e2e/                       # Playwright smoke tests against the compose stack
└── data/
    ├── import/                    # tour.json + source JPGs (git / git-annex / LFS)
    └── media/                     # processed output (named volume in compose)
```

### 10.2 API test strategy — 100% line + branch coverage

**Enforcement** (`api/pyproject.toml`):

```toml
[tool.coverage.run]
branch = true
source = ["app"]
omit = ["app/__main__.py"]  # a one-line entrypoint, if you add one

[tool.coverage.report]
fail_under = 100
show_missing = true
skip_covered = true
exclude_also = [
    "if TYPE_CHECKING:",
    "@overload",
]
```

CI runs `uv run pytest --cov --cov-report=term-missing` and fails below 100%. On Python 3.14,
coverage.py defaults to the `sys.monitoring` core, which supports branch measurement and has
much lower overhead than the old trace-function approach. So the gate doesn't have to make
the suite slow.

**Rules that keep 100% honest**

- `# pragma: no cover` needs a comment on the same line explaining why, and CI shows the count
  (`grep -rc "pragma: no cover" app/`) so any increase is visible in review. The
  `exclude_also` list stays short and gets reviewed like code.
- Coverage is the floor, not the goal. Security branches (expired vs revoked vs wrong secret,
  CSRF missing vs mismatched, dedupe window edges) each get a test that **asserts the
  behaviour**, not one that just runs the line.
- Migration files live in `alembic/`, outside `app/`, so they don't count toward coverage.
  `tests/migrations/` still runs every one of them (up, down, up) and runs `alembic check`
  so models and migrations can't drift apart.

**How the hard parts get tested**

| Area | Approach |
|---|---|
| Database | **Real Postgres 18** via `testcontainers` (session-scoped). `citext`, enums, `uuidv7()` and composite FKs don't exist in SQLite, so no SQLite. `TEST_DATABASE_URL` overrides this to use an existing DB (e.g. a CI service container). |
| Isolation | Schema built once with `alembic upgrade head`; each test runs inside a transaction using SQLAlchemy's `join_transaction_mode="create_savepoint"` and is rolled back. |
| HTTP | `httpx` client against the ASGI app (no network); cookies persist per client so login → call → logout flows read naturally. |
| Time | `time-machine` for session expiry, sliding lifetimes, `last_seen_at` throttling, code expiry and the 60 s `access_event` dedupe window. |
| Rate limiter | The limiter takes an injectable clock and is reset per test; test both the per-IP and the global ceiling. |
| Proxy headers | Spoofed `X-Forwarded-For` from an untrusted address is ignored; the same header from a trusted range is used. |
| Argon2 | Cheap parameters in tests via settings; one test asserts production parameters are at least the `argon2-cffi` defaults. |
| Images | Tiny generated JPGs (e.g. 64×32) keep the suite fast; assert GPS stripped, thumbnail size, downscale maths, rejection of PNG / non-2:1 / truncated files, `MAX_IMAGE_PIXELS` guard. |
| Markdown | Table of hostile inputs (`<script>`, `javascript:` links, `onerror=` attributes, raw HTML blocks) → asserted safe output. |
| CLI | Invoked in-process (e.g. Typer's `CliRunner` or calling `main(argv)`) so its lines count toward coverage. Covers `--dry-run`, `--prune`, and aggregated validation errors. |
| Config | Missing secrets and secrets left at `.env.example` values each raise at startup. |

**Frontend**: Vitest for the logic that has branches (payload → PSV node transform, floor
switching, `#code=` fragment handling). A Playwright smoke suite runs against
`docker compose up`: unlock → panorama renders → floor switch → `/media/*` returns 403 without
a cookie. No coverage target.

### 10.3 Compose: one file for Coolify and vanilla Docker

| Service | Notes |
|---|---|
| `caddy` | Built from `caddy/Dockerfile`, so the SPA is inside the image (no separate `web` container that builds and exits). `expose: 80`. Mounts media read-only. Healthcheck. |
| `api` | Entrypoint runs `alembic upgrade head`, then uvicorn. `expose: 8000`. Mounts media read-write and the import dir read-only. `depends_on: db: condition: service_healthy`. Healthcheck hits `/api/healthz`. |
| `db` | `postgres:18`. Named volume mounted at **`/var/lib/postgresql`** (§2.2). `pg_isready` healthcheck. Never publishes ports. |

**Rules for keeping one file portable**

- **No published ports in `docker-compose.yml`.** Coolify's docs say publishing ports bypasses
  its proxy. Vanilla adds them in `docker-compose.selfhost.yml` (`80:80`, `443:443`, `443:443/udp`,
  plus a `caddy_data` volume for certificates). Set
  `COMPOSE_FILE=docker-compose.yml:docker-compose.selfhost.yml` in the vanilla `.env`, so plain
  `docker compose up -d` still works.
- **No Coolify-specific keys** (`exclude_from_hc`, `is_directory`, `content:`). They aren't part
  of the Compose spec.
- **No one-shot containers.** Migrations run in the `api` entrypoint and the SPA is baked into the
  Caddy image. This avoids Coolify health-status problems with containers that exit, and
  avoids `exclude_from_hc`.
- **Healthchecks on every service.** Coolify uses them for status; Compose uses them for
  `depends_on`. Use tools that exist in each image (`pg_isready`; `python -c "urllib…"` in the
  slim image; `wget` in Caddy's Alpine image).
- **Required variables use `${VAR:?}`.** Both Coolify and Compose refuse to deploy when they're
  missing. Don't rely on Coolify's `SERVICE_PASSWORD_*` magic variables, which do nothing on
  vanilla. Set the values explicitly in Coolify's environment UI instead.
- **Behaviour that differs between hosts comes from env vars only**:

| Variable | Vanilla | Coolify |
|---|---|---|
| `SITE_ADDRESS` | `tour.example.com` | `:80` |
| `TRUSTED_PROXY_RANGES` | *(empty)* | Coolify's Docker network range, or `private_ranges` |
| `IMPORT_HOST_PATH` | `./data/import` | absolute host path, e.g. `/srv/pano/import` |
| Domain | DNS A record → host; Caddy gets the cert | set `https://tour.example.com:80` on the `caddy` service in Coolify |

- **Import directory.** On Coolify, relative bind mounts resolve under
  `/data/coolify/applications/<uuid>/`, and repository files are only there if "Preserve
  Repository During Deployment" is on. Rather than depend on that, bind-mount
  `${IMPORT_HOST_PATH}` and rsync `data/import` to that path on the server. That also keeps
  multi-GB JPGs out of every build context.
- **Named volumes** get a resource prefix on Coolify, so scripts must never hardcode volume
  names. Backups go through `docker compose exec db pg_dump` and through the running `api`
  container's media mount.

**Dev override**: Vite dev server on 5173 with `server.proxy` pointing `/api` and `/media` at
the API container, so cookies stay same-origin during development. Postgres published on
localhost for inspection.

**Secrets**: `POSTGRES_PASSWORD`, `SESSION_SECRET`, plus the env vars in the table above. Never
bake them into an image. `config.py` fails fast at startup if any are missing or still at
their `.env.example` values (and a test proves it).

**Backups**: `pg_dump` on a cron plus a tar of the media volume. The `data/import` directory
is your real source of truth — keep it in git (or git-annex / LFS for the images).
`access_event` exists **only** in the database, so if you want activity history to survive,
the DB backup isn't optional.

---

## 11. Placement GUI vs. manual authoring — effort analysis

You asked for a real estimate, so here it is.

### Cost of the manual path (100 nodes)

| Task | With alignment helper | Without |
|---|---|---|
| Write node stanza in JSON | ~20s | ~20s |
| Determine `map_x/map_y` | ~5s (click) | ~90s (open in GIMP, read cursor coords, transcribe) |
| Determine `sphere_pan` | ~15s (arrow keys, live) | ~120s (guess, re-import, reload, repeat) |
| **Per node** | **~40s** | **~3.8 min** |
| **100 nodes** | **~1.2 h** | **~6.5 h** |

Add iteration: you will redo perhaps 20% of nodes after seeing them in context. Call it
**~1.5 hours with the helper**, ~8 hours without.

### Cost of building the full GUI

| Component | Estimate | Notes |
|---|---|---|
| Admin shell: auth-gated routes, layout, list views | 0.5–1 d | Mostly boilerplate |
| Upload: multipart endpoint, progress, background processing, retry | 1–1.5 d | Large files make this fiddly |
| Floorplan canvas: pan/zoom, draggable pins, selection | 1–1.5 d | **The expensive part** |
| Inline `sphere_pan` alignment with live preview | 0.5 d | Reuses the helper |
| Description/marker editing forms | 0.5–1 d | Marker placement = click-in-panorama, another canvas interaction |
| Link editing + reordering | 0.5 d | |
| Export back to `tour.json` | 0.5 d | Needed to keep git as source of truth |
| **Total** | **~5–6.5 days** | Add ~30–40% for tests to hold 100% API coverage |

### Verdict

**Build the alignment helper (0.5 d), skip the GUI (5–6.5 d), for now.**

The helper removes roughly 80% of the manual pain for roughly 8% of the GUI's cost. The GUI
starts paying for itself somewhere around 4–5 buildings of this size, or the first time
someone other than you has to author content.

Three further arguments for the JSON-first approach in your specific situation:

1. **It's diffable and reproducible.** A GUI that edits rows directly *loses* that property
   unless you also build the export path. That's why "export back to `tour.json`" is in the
   table above. JSON-first gets it for free.
2. **The forms aren't the hard part; the canvas is.** Upload widgets and description fields are
   commodity work. The floorplan canvas with draggable pins and the in-panorama marker placer
   are real interaction design, and they're where the estimate could double if you're a
   perfectionist about it.
3. **The helper is the GUI's seed.** Its click-to-place and nudge-to-align interactions are
   exactly what the canvas needs. When you do build the GUI, you'll be wrapping working code in
   an admin shell rather than starting cold.

**Revisit the GUI when** any of these becomes true: a second building, a non-technical author,
frequent re-shoots of the same space, or you find yourself editing `tour.json` more than once
a month.

---

## 12. Risks and gotchas

| Risk | Mitigation |
|---|---|
| **EXIF GPS in panoramas** leaks the building location (Max 2 has GPS) | Strip all EXIF/XMP on import; a test asserts it; verify a real sample with `exiftool` |
| `sphere_pan` cannot be automated | Accept it; the helper makes it cheap; check the Max 2 XMP for heading data in M1 |
| 7680×3840 panoramas exhaust mobile browser memory | Downscale to 6144×3072 for v1; measure before reaching for tiling |
| Unexpectedly huge image processed silently | Set `MAX_IMAGE_PIXELS` explicitly below Pillow's default |
| Access codes brute-forced | ≥128-bit secrets + rate limiting + expiry |
| **Rate limiter keyed on the proxy's IP** behind Coolify | Configure trusted proxies in Caddy and uvicorn; covered by `test_proxy_headers.py` |
| Codes shared between people | Inherent to code-based auth; mitigate with per-recipient codes, short expiry, and the `access_event` activity view to spot anomalies |
| `access_event` is attributable personal data | Disclosure on the unlock page; explicit retention period + `events prune` |
| Media cached by an intermediary | `Cache-Control: private`; TLS everywhere |
| Blurred regions re-imported over the top | Keep redacted originals in `data/import`, never edit in `data/media` |
| Description XSS | Markdown only, raw HTML disabled, `nh3` on output, hostile-input test table |
| **Postgres 18 volume path** mounted at old `/data` location | Mount at `/var/lib/postgresql`; M0 checks that data survives `docker compose down && up` |
| Coolify relative bind mounts resolve somewhere unexpected | `IMPORT_HOST_PATH` as an absolute path on Coolify |
| Compose file drifts to work on only one host | CI runs the compose smoke test on vanilla; M0 includes a real Coolify deploy |
| Coverage gate pressures low-value tests or pragma creep | Behaviour assertions for security branches; pragma count shown in CI |

---

## 13. Execution order

Suited to incremental work in Claude Code; each milestone ends somewhere runnable, **with the
API at 100% coverage**. Holding the gate from the first commit costs much less than
retrofitting it.

**M0 — Skeleton (1 d)**
Compose file (caddy, api, db) + selfhost/dev overrides, Caddyfile with `SITE_ADDRESS`,
`/api/healthz`, Alembic initialised, "hello" SPA baked into the Caddy image. pytest +
testcontainers + coverage gate running in CI. **Deploy to both**: vanilla over HTTPS, and a
Coolify test app. Confirm Postgres data survives a container recreate on both.

**M1 — Data + import (1.5–2 d)**
All models (including `access_event`) and migrations, plus migration tests. `tour.json` schema
with checks across records for multiple floors. Import CLI with `--dry-run`/`--prune`. Image
pipeline: JPEG/2:1 check, EXIF read-then-strip, thumbnail, downscale. Inspect a real Max 2 JPG
with `exiftool`. Import a real tour with 3–5 nodes across **two floors**.

**M2 — Auth (1.5–2 d)**
Argon2 hashing, session tables, editor login, access-code create/list/revoke CLI, unlock
endpoint, cookie handling, CSRF, rate limiting with trusted-proxy handling,
`/api/internal/media-auth`, media served behind the session. Verify with curl that media 403s
without a cookie, both directly and through Coolify's proxy.

**M3 — Viewer (1.5–2 d)**
`GET /api/tours/{slug}` returning a PSV-ready payload with rendered Markdown. React viewer with
Virtual Tour + Map + Markers + Gallery + floor switcher. Unlock page including `#code=`
fragment handling and the logging notice. `POST …/viewed` recording deduplicated `access_event`s.
Playwright smoke test. This is the first demo-able build.

**M4 — Alignment helper (0.5 d)**
`?align=1` mode, nudge + click-to-place, JSON patch copy, `POST /placement`.
**Then align all your real nodes.**

**M5 — Hardening (1 d)**
Caddy `forward_auth` handoff, security headers, CSP verified against a real panorama load,
activity views (per code and per node), `events prune` + retention setting, backup script,
error pages.

**M6 — Admin GUI (later, 5–6.5 d + tests)**
Only when §11's crossover conditions are met.

**Realistic total to a usable, secured tour: 7–8.5 days of focused work**, or a few weekends.
That's about 2 days more than the first draft, spent on the 100% coverage gate, multi-floor
navigation, activity logging, and checking deploys on both hosts.

---

## 14. Decisions

Settled 2026-09-10:

| # | Question | Decision |
|---|---|---|
| 1 | One floor or several? | **Multiple floors from day one.** `floor` table, per-floor map switching, links between floors (§3, §9). |
| 2 | Node-level `access_event` logging? | **Yes.** In scope for v1 with dedupe, retention and disclosure (§3). |
| 3 | Markdown or HTML descriptions? | **Markdown**, rendered and sanitised on the server (§9). |
| 4 | Hosting | **Self-hosted Coolify, Docker Compose build pack**; the same file must also run on vanilla Docker Compose (§10.3). |
| — | Python version | **3.14** |
| — | ORM | **SQLAlchemy 2.0** (§2.1) |
| — | Postgres version | **18**; revisit 19 after its first minor releases (§2.2) |
| — | Input images | **GoPro Max 2 JPG only**, 7680×3840 (§1, §6) |
| — | Test coverage | **100% line + branch on the API**, enforced in CI (§10.2) |

### Still open

1. **Retention period for `access_event`**: 90 days, 1 year, or keep forever?
2. **Does the Max 2 write usable heading metadata?** Answer by inspecting a real JPG in M1 (§6 step 4).
3. **Coolify's Docker network range** for `TRUSTED_PROXY_RANGES`: read it from the server in M0
   (`docker network inspect coolify`), or accept `private_ranges` if Caddy is never reachable
   from other hosts on the private network.
