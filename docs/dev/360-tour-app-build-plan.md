# Indoor 360° Tour App — Build Plan

A self-hosted web app for displaying 360° panoramas positioned on a building floorplan,
behind authentication. FastAPI + Postgres + Vite/React SPA + Caddy, deployable with a
single `docker compose up`.

---

## 1. Scope

### In scope (v1)

- Display equirectangular 360° panoramas using [Photo Sphere Viewer](https://photo-sphere-viewer.js.org/) (MIT).
- Position panoramas on a **non-georeferenced** floorplan image via the Map plugin.
- Navigate between panoramas via floorplan hotspots, arrow links, and a thumbnail gallery.
- Per-panorama text descriptions and in-panorama markers.
- **Editors**: real accounts (email + password) for anyone who administers the tour.
- **Viewers**: unique, revocable, individually-attributable access codes. No accounts.
- Media served only to authenticated sessions; no public URLs.
- Tour content authored as a JSON file + image directory, loaded via an import CLI.

### Out of scope (v1)

- 360° video (host separately, e.g. unlisted YouTube; optionally embed a link as a marker).
- Multi-building / multi-tenant management (schema allows it; UI does not).
- Image blurring/redaction (done externally in GIMP before import).
- Placement GUI (see §11 for the effort analysis and the recommended interim tool).

### Non-negotiables

- Everything runs from one `docker-compose.yml`. No external SaaS dependency for auth.
- The app is the auth layer. Media is never publicly reachable.
- Tour definition is reproducible and diffable (lives in git, re-importable).

---

## 2. Architecture

```
                        ┌──────────────────────────────────────┐
   browser ──── 443 ───▶│ Caddy                                │
                        │  /            → SPA static files     │
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
                        │ Postgres 16 │
                        └─────────────┘
```

**Single origin.** Caddy serves the SPA, the API and the media from the same hostname.
No CORS, cookies work without `SameSite=None`, and Photo Sphere Viewer only needs
`withCredentials: true` rather than injecting bearer tokens into the texture loader.

### Stack choices

| Layer | Choice | Notes |
|---|---|---|
| Reverse proxy | Caddy 2 | Automatic HTTPS; `forward_auth` replaces nginx's `auth_request` + `X-Accel-Redirect`. |
| API | FastAPI + Uvicorn, Python 3.12 | |
| ORM | SQLAlchemy 2.0 (typed) or SQLModel | Either is fine; SQLAlchemy 2.0 has cleaner typing for non-trivial relationships. |
| Migrations | Alembic | Autogenerate + hand-review every migration. |
| DB | Postgres 16 | |
| Password/secret hashing | Argon2id (`argon2-cffi`) | |
| Image processing | Pillow (+ `pillow-heif` if needed) | |
| Frontend | Vite + React + TypeScript | |
| Routing / data | TanStack Router + TanStack Query | |
| Viewer | `@photo-sphere-viewer/core` + plugins | Map, Virtual Tour, Markers, Gallery, Compass. |
| Package manager | `uv` (Python), `pnpm` (JS) | |

---

## 3. Data model

All tables have `id` (UUID v7 or bigint identity), `created_at`, `updated_at`.

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
| `title`, `description` | text | |
| `default_node_id` | fk node, nullable | Entry point |
| `is_published` | bool | |

### `floor`
| Column | Type | Notes |
|---|---|---|
| `tour_id` | fk | |
| `slug`, `name` | text | unique per tour |
| `ordering` | int | |
| `image_path` | text | floorplan image, relative to media root |
| `image_width`, `image_height` | int | pixels; Map plugin coordinates are in this space |

### `node` — one panorama
| Column | Type | Notes |
|---|---|---|
| `tour_id`, `floor_id` | fk | |
| `slug` | text | unique per tour |
| `title` | text | shown in gallery + caption |
| `description` | text | rendered in the PSV side panel; sanitised HTML or Markdown |
| `pano_path`, `thumb_path` | text | relative to media root |
| `pano_width`, `pano_height` | int | |
| `map_x`, `map_y` | float | **pixel coordinates on the floorplan image** |
| `sphere_pan` | float | **north-alignment offset, radians.** See §7 |
| `default_yaw`, `default_pitch`, `default_zoom` | float | initial view |
| `ordering` | int | gallery order |
| `captured_at` | timestamptz nullable | |

### `link` — navigation arrows between nodes
| Column | Type | Notes |
|---|---|---|
| `from_node_id`, `to_node_id` | fk | |
| `yaw_override` | float nullable | usually null; derive from map geometry |

> Arrow positions can be **computed** from `map_x/map_y` + `sphere_pan` rather than
> authored. Only override where the computed direction is wrong (e.g. through a wall).
> This removes most of the tedium of hand-authoring links.

### `marker` — in-panorama annotations
| Column | Type | Notes |
|---|---|---|
| `node_id` | fk | |
| `yaw`, `pitch` | float | |
| `kind` | enum | `note`, `image`, `link` |
| `label`, `content` | text | |
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

### `access_session`
| Column | Type | Notes |
|---|---|---|
| `access_code_id` | fk | |
| `token_hash` | text unique indexed | SHA-256 of the opaque cookie token |
| `expires_at` | timestamptz | |
| `last_seen_at` | timestamptz | answers "has Jane opened this yet?" |
| `user_agent` | text | |
| `ip_prefix` | text nullable | store /24 or /48 only, or omit entirely |

### `access_event` (optional but cheap)
`access_code_id`, `node_id`, `occurred_at`. One row per node view, for
"which parts of the building did they actually look at". Skip if you don't want the audit trail.

### `editor_session`
Same shape as `access_session` but keyed to `editor_id`.

---

## 4. Authentication design

### Two principals, one mechanism

Both editors and viewers get an **opaque, DB-backed session token** in an HttpOnly cookie.
No JWTs. Rationale: single server, tiny table, and a DB row gives instant revocation plus
`last_seen_at` for free. Stateless tokens would buy nothing and cost you revocation.

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

- **Rate limit `/api/unlock`** — per-IP token bucket plus a global ceiling. A revocable code
  that can be brute-forced is not revocable. In-process limiter is fine (single instance);
  reach for Redis only if you scale out.
- **Constant-time comparison** on the prefix lookup result; return an identical error and
  a similar response time for "no such prefix" and "wrong secret".
- **Cookies**: `HttpOnly; Secure; SameSite=Lax; Path=/`.
- **CSRF**: `SameSite=Lax` covers the common cases, but add a double-submit CSRF token for
  all editor mutations. Reject state-changing requests without `Content-Type: application/json`.
- **Argon2id params**: use `argon2-cffi` defaults or stronger; unlock is rare so cost is free.
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
example.com {
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

**Watch the subrequest volume.** Every media request triggers an auth call. Fine for
whole-JPEG panoramas; if you later tile for multi-resolution, one node view becomes dozens
of tile fetches and therefore dozens of auth calls. Mitigate by authorising per-node prefix
and caching the decision in-process for a short TTL. (nginx's `auth_request` has the same
characteristic — this isn't a Caddy limitation.)

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
    {
      "slug": "level-1",
      "name": "Level 1",
      "image": "floors/level-1.png",
      "ordering": 1
    }
  ],
  "nodes": [
    {
      "slug": "lobby-main",
      "floor": "level-1",
      "title": "Main Lobby",
      "description": "Looking north toward the reception desk. The mezzanine above was added in the 2011 retrofit.",
      "pano": "nodes/lobby-main/pano.jpg",
      "map": { "x": 412, "y": 388 },
      "sphere_pan": 1.221,
      "default_yaw": 0,
      "links": ["corridor-east", "stair-a-l1"],
      "markers": [
        { "yaw": 0.42, "pitch": -0.1, "kind": "note",
          "label": "Original 1962 terrazzo", "content": "Retained during the retrofit." }
      ]
    }
  ]
}
```

### CLI

```bash
docker compose run --rm api python -m app.cli import /data/import/tour.json
docker compose run --rm api python -m app.cli import /data/import/tour.json --dry-run
docker compose run --rm api python -m app.cli reprocess-images --tour building-a
docker compose run --rm api python -m app.cli code create --label "Jane Smith — Acme" --expires 30d
docker compose run --rm api python -m app.cli code list
docker compose run --rm api python -m app.cli code revoke k7f3q2xa
docker compose run --rm api python -m app.cli editor create --email you@example.com
```

**Import behaviour**

- Validate the whole file with Pydantic before touching the DB; fail with all errors at once.
- Upsert by slug — re-running must be safe and idempotent.
- Nodes absent from the file are *reported*, not deleted, unless `--prune`.
- Wrap the whole import in one transaction.

**Image processing on import**

1. Verify the panorama is 2:1 equirectangular; warn otherwise.
2. **Strip EXIF/XMP, especially GPS.** Consumer 360 cameras embed location by default.
   Given that the whole point is confidentiality, this matters.
3. Read XMP `PoseHeadingDegrees` if present — it can seed `sphere_pan` and save manual work.
4. Generate a ~400px thumbnail for the gallery.
5. Optionally downscale to a max dimension (8192 or 6144) — see §12.
6. Set `Image.MAX_IMAGE_PIXELS` deliberately rather than letting Pillow's decompression-bomb
   guard fire on legitimate 11K panoramas.

---

## 7. The alignment problem (build this on day one)

Every node needs three hand-set numbers:

| Field | How you get it | Automatable? |
|---|---|---|
| `map_x`, `map_y` | click the right spot on the floorplan | No — you know where you stood |
| `sphere_pan` | rotate until the panorama's north matches the floorplan | **No — must be eyeballed** |

`sphere_pan` is the expensive one. It cannot be computed (there's no GPS, no compass you can
trust indoors), and if it's wrong every navigation arrow and the map's viewing-direction cone
point the wrong way. Getting it wrong is immediately obvious and deeply annoying.

### Alignment helper — ~150 lines, half a day

A dev-only mode in the viewer, gated behind an editor session:

- `?align=1` enables it.
- Arrow keys nudge `sphereCorrection.pan` for the current node (Shift = coarse, plain = fine),
  live, with the map's direction cone visible so you can see when it's right.
- Clicking the floorplan sets `map_x/map_y` for the current node.
- A floating panel shows the current values and a **Copy JSON patch** button.
- `n` / `p` step to the next/previous node.

This turns a ~3-minute-per-node chore into a ~20-second one. Over 100 nodes that is the
difference between a lost weekend and an afternoon. It is also, not coincidentally, the core
interaction of the eventual placement GUI — build it once, reuse it.

---

## 8. API surface

### Public
- `POST /api/unlock` → set viewer session
- `POST /api/session/logout`
- `GET  /api/session` → current principal + capabilities

### Viewer (session required)
- `GET /api/tours/{slug}` → PSV-ready payload: floors, nodes, links, markers, media URLs
- `POST /api/tours/{slug}/nodes/{node}/viewed` → fire-and-forget access event

### Editor
- `POST /api/auth/login`, `POST /api/auth/logout`
- `GET/POST/PATCH/DELETE /api/admin/tours|floors|nodes|markers|links`
- `GET/POST /api/admin/access-codes`, `POST /api/admin/access-codes/{id}/revoke`
- `GET /api/admin/access-codes/{id}/activity` → who accessed what, when
- `POST /api/admin/nodes/{id}/placement` → `{map_x, map_y, sphere_pan}` (used by the alignment helper)

### Internal
- `GET /api/internal/media-auth` → 204/403 for Caddy `forward_auth`

Design `GET /api/tours/{slug}` to return something the frontend can hand almost directly to
the Virtual Tour plugin's `setNodes()`. Keep the shape-shifting on the server.

---

## 9. Frontend

### Routes

| Route | Purpose |
|---|---|
| `/unlock` | code entry; also handles `#code=` fragment |
| `/t/:slug` | the viewer |
| `/login` | editor login |
| `/admin` | tours, nodes, access codes, activity |

### Viewer composition

```
Viewer (core)
├── VirtualTourPlugin   (manual mode, client-side, nodes from /api/tours/{slug})
├── MapPlugin           (floorplan image; center = node.map_x/map_y; hotspots = all nodes)
├── MarkersPlugin       (per-node annotations)
├── GalleryPlugin       (thumbnails, ordered)
└── CompassPlugin       (optional; only meaningful once sphere_pan is correct)
```

Key configuration points:

- `withCredentials: true` on the Viewer so media requests carry the session cookie.
- `sphereCorrection: { pan: node.sphere_pan }` per node.
- Multi-floor: call the Map plugin's `setImage()` when the active node's floor changes, and
  recompute hotspots for that floor only.
- Floorplan hotspots are the **primary** navigation; arrow links are a convenience. This means
  you don't need a dense link graph.
- Node descriptions go in the PSV side panel; sanitise server-side if you allow HTML.

### Performance

- Preload the panoramas of linked neighbours on idle.
- Cap concurrent decodes; an 8K JPEG decode is ~200MB of RAM as a texture.
- Consider the tiled adapter only if load times prove unacceptable (§12).

---

## 10. Repo layout & compose

```
.
├── docker-compose.yml
├── docker-compose.dev.yml
├── Caddyfile
├── .env.example
├── api/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic/
│   └── app/
│       ├── main.py
│       ├── config.py          # pydantic-settings
│       ├── db.py
│       ├── models/
│       ├── schemas/
│       ├── routers/
│       │   ├── auth.py  unlock.py  tours.py  admin.py  internal.py
│       ├── security.py        # argon2, tokens, session deps, rate limit
│       ├── media.py           # image processing
│       └── cli.py
├── web/
│   ├── Dockerfile             # multi-stage; outputs static to a volume
│   ├── vite.config.ts
│   └── src/
│       ├── routes/
│       ├── viewer/            # PSV setup, plugins, alignment helper
│       └── api/               # generated or hand-written client
└── data/
    ├── import/                # tour.json + source images (bind mount, git-tracked)
    └── media/                 # processed output (named volume)
```

### Services

| Service | Notes |
|---|---|
| `caddy` | ports 80/443; mounts built SPA + media (read-only) |
| `api` | no published ports; depends_on db healthy |
| `db` | Postgres 16; named volume; no published ports in prod |
| `web` | build-only stage in prod; Vite dev server in dev override |

**Dev override**: Vite dev server on 5173 with `server.proxy` pointing `/api` and `/media` at
the API container, so cookies stay same-origin during development.

**Secrets**: `.env` for `POSTGRES_PASSWORD`, `SESSION_SECRET`, `DOMAIN`. Never bake into the
image. Fail fast at startup if any are missing or still at their example values.

**Backups**: `pg_dump` on a cron plus a tar of the media volume. The `data/import` directory
is your real source of truth — keep it in git (or git-annex / LFS for the images).

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
| **Total** | **~5–6.5 days** | |

### Verdict

**Build the alignment helper (0.5 d), skip the GUI (5–6.5 d), for now.**

The helper captures roughly 80% of the manual pain for roughly 8% of the GUI's cost. The
crossover point where the GUI pays for itself is somewhere around 4–5 buildings of this size,
or the first time someone other than you has to author content.

Three further arguments for the JSON-first approach in your specific situation:

1. **It's diffable and reproducible.** A GUI mutating rows directly *removes* that property
   unless you also build the export path — which is why "export back to `tour.json`" is in the
   table above. JSON-first gets it free.
2. **The forms aren't the hard part; the canvas is.** Upload widgets and description fields are
   commodity work. The floorplan canvas with draggable pins and the in-panorama marker placer
   are real interaction design, and they're where the estimate could double if you're
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
| **EXIF GPS in panoramas** leaks the building location | Strip all EXIF/XMP on import; verify with `exiftool` on a sample |
| `sphere_pan` cannot be automated | Accept it; the helper makes it cheap; check XMP `PoseHeadingDegrees` first |
| 8K panoramas exhaust mobile browser memory | Downscale to 6144×3072 for v1; measure before reaching for tiling |
| Pillow decompression-bomb guard rejects large panoramas | Set `MAX_IMAGE_PIXELS` explicitly and deliberately |
| Access codes brute-forced | ≥128-bit secrets + rate limiting + expiry |
| Codes shared between people | Inherent to code-based auth; mitigate with per-recipient codes, short expiry, and the `last_seen`/activity view to spot anomalies |
| Media cached by an intermediary | `Cache-Control: private`; TLS everywhere |
| Blurred regions re-imported over the top | Keep redacted originals in `data/import`, never edit in `data/media` |
| Description HTML → XSS | Sanitise server-side (`nh3`/`bleach`) or restrict to Markdown |

---

## 13. Execution order

Suited to incremental work in Claude Code; each milestone ends somewhere runnable.

**M0 — Skeleton (0.5 d)**
Compose file with all four services, Caddyfile, health endpoint, Alembic initialised,
"hello" SPA served through Caddy over HTTPS.

**M1 — Data + import (1–1.5 d)**
All models and migrations. `tour.json` schema + Pydantic validation. Import CLI with
`--dry-run`. Image processing: EXIF strip, thumbnail, dimension capture. Import a real tour
with 3–5 nodes.

**M2 — Auth (1–1.5 d)**
Argon2 hashing, session tables, editor login, access-code create/list/revoke CLI, unlock
endpoint, cookie handling, rate limiting, `/api/internal/media-auth`, media served behind the
session. Verify with curl that media 403s without a cookie.

**M3 — Viewer (1–1.5 d)**
`GET /api/tours/{slug}` returning a PSV-ready payload. React viewer with Virtual Tour + Map +
Markers + Gallery. Unlock page including `#code=` fragment handling. This is the first
demo-able build.

**M4 — Alignment helper (0.5 d)**
`?align=1` mode, nudge + click-to-place, JSON patch copy, `POST /placement`.
**Then align all your real nodes.**

**M5 — Hardening (0.5–1 d)**
Caddy `forward_auth` handoff, security headers, CSP verified against a real panorama load,
access activity view, `access_event` logging, backup script, error pages.

**M6 — Admin GUI (later, 5–6.5 d)**
Only when §11's crossover conditions are met.

**Realistic total to a usable, secured tour: 4.5–6 days of focused work**, or a few weekends.

---

## 14. Open questions to settle early

1. **One floor or several?** Multi-floor is cheap if the `floor` table exists from day one and
   expensive to retrofit into hardcoded map handling.
2. **Do you want `access_event` node-level logging**, or is session-level `last_seen_at`
   sufficient? The former tells you what they looked at; the latter only that they showed up.
3. **Markdown or HTML for descriptions?** Markdown is safer and easier to author in JSON.
4. **Where does this get hosted**, and does that host give you a domain for Caddy's automatic
   HTTPS? (Internal-only deployment means you'll want a DNS challenge or an internal CA instead.)
