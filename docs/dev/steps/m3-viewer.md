# M3 — Viewer

**Goal:** the first demo-able build. A viewer unlocks with a code, walks the real two-floor tour
using map hotspots, arrows, gallery and floor switcher, and every node view is logged.

**Plan sections:** §3 (`link`, `access_event` rules), §8 (viewer endpoints), §9 (entire), §10.2
(frontend testing), §4 (fragment handling).

**Depends on:** M1, M2.  **Estimate:** 1.5–2 days.

## Decisions needed

| # | Decision | Recommendation |
|---|---|---|
| D1 | API client | Generate TypeScript types from FastAPI's OpenAPI schema (`openapi-typescript`) with a thin fetch wrapper. CI fails if the generated file is stale. |
| D2 | Link yaw from geometry: convention | Floorplan "up" (−y) is north. Bearing = `atan2(dx, −dy)`. Arrow yaw = bearing − `sphere_pan`, normalised to [−π, π). **One pure, tested function**; sign confirmed against a real node in M4.3. |
| D3 | Who sees unpublished tours | Editors only. Viewers get 404 (not 403), so slugs don't leak. |
| D4 | PSV version | Pin an exact `@photo-sphere-viewer/*` version across all plugins. |

## Slices

### M3.1 — Markdown and tour payload

Scope: `app/markdown.py` (markdown-it-py with HTML disabled → `nh3`), the link-yaw function (D2),
`GET /api/tours/{slug}` returning a payload shaped for `VirtualTourPlugin.setNodes()`: floors (image URL,
dimensions, default node), nodes (pano and thumb URLs, map position, `sphere_pan`, default view,
`description_html`, markers with rendered content, links with yaw), and the tour's default node.
Access rules: D3, plus code `tour_id` scoping from M2.

Acceptance:
- [ ] Hostile Markdown table (plan §10.2) produces safe output; ordinary Markdown (emphasis, lists, links) survives
- [ ] Link yaw: computed for same-floor links, `yaw_override` wins when set, links between floors always use the override; tested at the four compass points
- [ ] Viewer with a code for tour A → 404 for tour B; viewer → 404 for an unpublished tour; editor → 200
- [ ] Response contains no hash columns or internal paths (asserted against the full JSON)
- [ ] Query count for the payload is constant, not growing with the number of nodes (assert with an SQL event counter)

As-built:
<!-- fill in on completion -->

### M3.2 — Node view logging

Scope: `POST /api/tours/{slug}/nodes/{node}/viewed` following plan §3 `access_event` rules.

Acceptance:
- [ ] Viewer view → one row with code, session, tour, node, `node_slug`, server `occurred_at`
- [ ] Same session and node within 60 s → no new row; at 60 s+ → new row (time-machine, boundary tested)
- [ ] Different node within 60 s → new row
- [ ] Editor → 204, no row
- [ ] Node not in that tour, or tour outside the code's scope → 404, no row

As-built:
<!-- fill in on completion -->

### M3.3 — Web shell: routing, unlock, login

Scope: TanStack Router routes from plan §9; API client (D1); session query; `/unlock` with
`#code=` handling (POST, then `history.replaceState`), plus the "access is logged" notice; `/login`;
redirects based on `GET /api/session`.

Acceptance:
- [ ] Vitest: fragment is read, POSTed, and stripped from the URL even when unlock fails
- [ ] Vitest: unauthenticated visit to `/t/:slug` → `/unlock`
- [ ] Manual: one-click link `https://<host>/t/<slug>#code=…` lands in the viewer with a clean URL bar

As-built:
<!-- fill in on completion -->

### M3.4 — Viewer

Scope: PSV with Virtual Tour (manual mode), Map, Markers, Gallery, and optional Compass; custom floor
switcher; `withCredentials`; per-node `sphereCorrection`; Map `setImage()` and hotspot replacement
on floor change; description in the side panel; `keepalive` fetch to `…/viewed` on `node-changed`;
neighbour preloading on idle.

Acceptance:
- [ ] Vitest: payload → PSV node transform; floor change detection; hotspots limited to the current floor
- [ ] Manual on real tour: hotspot, arrow, gallery and floor switcher all navigate; a link between floors switches the map
- [ ] Manual on a phone: a 6144×3072 pano loads without the tab crashing
- [ ] `access_event` rows appear as you walk the tour

As-built:
<!-- fill in on completion -->

### M3.5 — Playwright smoke in CI

Scope: CI builds the compose stack, imports a **synthetic** two-floor tour (generated images, no real
imagery), creates a code with the CLI, then runs Playwright: unlock → pano renders (canvas present,
no failed media requests) → floor switch → logout → `/media/*` 403.

Acceptance:
- [ ] Smoke job green in CI and runnable locally with one documented command (added to CLAUDE.md Commands)

As-built:
<!-- fill in on completion -->

## Out of scope

Align mode (M4). Admin UI, activity views, security headers/CSP (M5).
