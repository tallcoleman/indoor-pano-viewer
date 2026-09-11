# M6 — Admin GUI (deferred)

**Status:** not started, on purpose. Don't plan slices until a trigger below is met. By then
M0–M5 as-built notes will have changed enough that detail written now would be wrong.

**Plan sections:** §11 (effort analysis and verdict).

## Start when any of these is true

- A second building
- A non-technical person needs to author content
- The same space is re-shot often
- `tour.json` is being edited more than once a month

## Known inputs when it starts

- Content CRUD API for tours/floors/nodes/markers/links (moved here from plan §8 by M5 D1).
- The M4 alignment helper is the core of the floorplan canvas; wrap it rather than rewrite it.
- Export back to `tour.json` is mandatory, so `tour.json` stays the source of truth. Extend M4's
  `export-placements` merge approach to all fields rather than writing a second exporter.
- Upload path must reuse the M1 image pipeline, including EXIF stripping.
- Budget: ~5–6.5 days + ~30–40% for tests at 100% API coverage.
