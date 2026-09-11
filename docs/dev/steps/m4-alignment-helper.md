# M4 — Alignment helper

**Goal:** setting `map_x`, `map_y` and `sphere_pan` takes ~20 s per node, and the results end up
in `tour.json`, which stays the source of truth.

**Plan sections:** §7 (entire), §8 (placement endpoint), §11 (why the helper and not a GUI).

**Depends on:** M3.  **Estimate:** 0.5 day, plus the time to align every real node.

## Decisions needed

| # | Decision | Recommendation |
|---|---|---|
| D1 | How values get back into `tour.json` | **Decided 2026-09-11: add `cli export-placements`.** It reads the existing `tour.json`, replaces only each node's `map` and `sphere_pan` with the DB values, and writes the merged file to stdout or `--output`. The import mount is read-only, so it never writes in place. All other fields and key order are kept. Values are rounded (`map` to 0.1 px, `sphere_pan` to 4 decimals) so diffs stay readable. The per-node **Copy JSON patch** button stays for one-off fixes. |
| D2 | Re-import after aligning | A re-import overwrites DB placement with whatever `tour.json` says. Simplest guard: `export-placements --check` exits non-zero and lists nodes whose DB placement differs from the file, and `import` refuses to overwrite differing placements without `--overwrite-placements`. Decide during planning. |

## Slices

### M4.1 — Placement endpoint

Scope: `POST /api/admin/nodes/{id}/placement` with `{map_x, map_y, sphere_pan}`. Editor only, CSRF,
bounds checked against the node's floor dimensions, `sphere_pan` normalised. Plus `cli export-placements` (D1),
and D2's guard if adopted.

Acceptance:
- [ ] Viewer → 403; missing CSRF → 403; out-of-bounds → 422; valid → 200 and DB updated
- [ ] `sphere_pan` outside [−π, π) normalised (tested at the edges)
- [ ] Export → re-import round-trips to identical placements
- [ ] Only `map` and `sphere_pan` change; every other field and the key order are untouched (compared against a fixture)
- [ ] Nodes in the file but not the DB, and vice versa, are reported, not silently dropped
- [ ] Output works both to `--output <path>` and to stdout via `docker compose exec -T api … > tour.json`

As-built:
<!-- fill in on completion -->

### M4.2 — Align mode UI

Scope: `?align=1`, only for editor sessions (ignored for viewers). Arrow keys nudge pan (Shift = coarse)
with the direction cone live; clicking the floorplan sets the map position; the floating panel shows the
values with Copy JSON patch and Save (calls M4.1); `n`/`p` step through nodes in floor order, then gallery order.

Acceptance:
- [ ] Vitest: key handling (fine vs coarse step, wrap-around), patch generation, node ordering across floors
- [ ] Viewer session with `?align=1` sees the normal viewer
- [ ] Manual: aligning one node takes under ~30 s and survives a reload after Save

As-built:
<!-- fill in on completion -->

### M4.3 — Align the real tour (you)

Scope: align every node. **First, confirm the link-yaw sign convention (M3 D2)** on a node where you
know the true direction; if arrows point the mirror-image way, fix the M3 function and its tests before going further.
Run `export-placements`, save the output over your `tour.json` (the sample tour's in the repo, or
production's wherever you keep it), re-import, walk the tour.

Acceptance:
- [ ] Link-yaw convention confirmed (or fixed) and noted in As-built
- [ ] All nodes aligned; arrows and map cone agree with reality
- [ ] The saved `tour.json` holds the aligned values; a fresh import reproduces them

As-built:
<!-- fill in on completion -->

## Out of scope

Drag-and-drop pins, marker placement, uploads: that's the M6 GUI.
