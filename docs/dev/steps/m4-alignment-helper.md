# M4 — Alignment helper

**Goal:** setting `map_x`, `map_y` and `sphere_pan` takes ~20 s per node, and the results end up
in `tour.json` so git stays the source of truth.

**Plan sections:** §7 (entire), §8 (placement endpoint), §11 (why the helper and not a GUI).

**Depends on:** M3.  **Estimate:** 0.5 day, plus the time to align every real node.

## Decisions needed

| # | Decision | Recommendation |
|---|---|---|
| D1 | How values get back into `tour.json` | The plan has a per-node **Copy JSON patch** button. Consider also adding `cli export-placements --tour <slug>`, which writes every node's `map` and `sphere_pan` back into `tour.json` in one go. That's less clipboard work over 100 nodes and only a few dozen lines to test. |
| D2 | Re-import after aligning | A re-import overwrites DB placement with whatever `tour.json` says. The helper UI shows a warning while DB values differ from the last import, until they've been exported. Needs a "last imported values" comparison (or just a documented rule; decide during planning). |

## Slices

### M4.1 — Placement endpoint

Scope: `POST /api/admin/nodes/{id}/placement` with `{map_x, map_y, sphere_pan}`. Editor only, CSRF,
bounds checked against the node's floor dimensions, `sphere_pan` normalised. Plus D1's CLI if adopted.

Acceptance:
- [ ] Viewer → 403; missing CSRF → 403; out-of-bounds → 422; valid → 200 and DB updated
- [ ] `sphere_pan` outside [−π, π) normalised (tested at the edges)
- [ ] (If D1) export produces a `tour.json` that imports back to identical placements

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
Export or paste the values into `tour.json`, re-import, walk the tour.

Acceptance:
- [ ] Link-yaw convention confirmed (or fixed) and noted in As-built
- [ ] All nodes aligned; arrows and map cone agree with reality
- [ ] `tour.json` in git holds the aligned values; a fresh import reproduces them

As-built:
<!-- fill in on completion -->

## Out of scope

Drag-and-drop pins, marker placement, uploads: that's the M6 GUI.
