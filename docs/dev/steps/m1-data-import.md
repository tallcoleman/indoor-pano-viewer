# M1 — Data model and import

**Goal:** a real two-floor tour with 3–5 nodes lives in Postgres and the media volume. It gets
there through an idempotent import CLI, and its images are metadata-free and correctly sized.

**Plan sections:** §3 (data model), §5 (media layout), §6 (tour.json, CLI, import behaviour,
image processing), §10.2 (image/CLI test approach), §12.

**Depends on:** M0 complete.  **Estimate:** 1.5–2 days.

## Prerequisites (you)

- [ ] 3–5 real Max 2 JPGs across **two floors**, with GPS **on** for at least one (to prove stripping works).
- [ ] Floorplan images for those two floors.
- [ ] `exiftool` installed locally.
- [ ] Rough `map` coordinates for each node (read from the floorplan in any image editor). They get corrected in M4.

## Decisions needed

| # | Decision | Recommendation |
|---|---|---|
| D1 | **Do real images go in git?** The plan says `data/import` is git-tracked (§10.3). The repo is private, but the imagery is confidential: once committed, it's in every clone, every CI checkout, and GitHub's storage for good, and ~10 MB × 100 JPGs will soon hit LFS quotas. | Commit `tour.json` only. Keep source JPGs and floorplans **out of this repo**: gitignore the image files under `data/import/`, and store originals in a private backup. Update plan §10.3 "Backups" to match. |
| D2 | CLI framework | **Typer**: subcommands (`import`, `code`, `events`, `editor`) and in-process `CliRunner` tests, so CLI code counts toward coverage. |
| D3 | Floorplan processing | Strip metadata, keep format and size, record dimensions. No downscale unless a plan is larger than ~8192 px on a side. |
| D4 | Does the Max 2 write usable heading metadata? (plan §6 step 4) | Decide in M1.5 from real `exiftool` output. Until then, no code for it. |
| D5 | Order of image writes and DB transaction | Process images to a temp path, commit the DB, then move files into place. If the DB fails, no files are published. Re-running is safe either way because outputs are deterministic. |

## Slices

### M1.1 — Models and migrations

Scope: every table in plan §3, including `access_event`, `access_session` and `editor_session`
(auth *logic* comes in M2; the tables arrive now so there's a single schema migration history).
Enums, citext, UUIDv7 defaults, circular FKs with `use_alter`, the `(tour_id, floor_id)` composite FK,
check constraints, unique constraints, indexes, `ON DELETE SET NULL` on `access_event`.
`tests/factories.py` for every model.

Acceptance:
- [ ] Migration up → down → up passes; `alembic check` clean
- [ ] DB-level tests prove each constraint rejects bad data: node on another tour's floor, duplicate slug
      within a tour (and the same slug allowed across tours), link to itself, duplicate link, negative `map_x`
- [ ] Deleting a node sets `access_event.node_id` to null and keeps `node_slug`; deleting a session sets `access_session_id` to null
- [ ] `citext`: `editor.email` uniqueness ignores case
- [ ] Python `uuid7` default and DB `uuidv7()` default both produce v7 UUIDs

As-built:
<!-- fill in on completion -->

### M1.2 — `tour.json` schema and validation

Scope: Pydantic models for the file in plan §6, including links written either as a slug or as
`{to, yaw}`. Validation across records, reporting **all** errors at once: unknown floor, unknown
link target, link between floors without `yaw`, `default_node` missing or on the wrong floor,
duplicate slugs. Pure code, no DB and no image I/O. Map bounds need image dimensions, so the
check that uses them takes the dimensions as input and runs in M1.4.

Acceptance:
- [ ] `tests/fixtures/tours/valid-multi-floor.json` validates
- [ ] One fixture per error type, each asserting the exact error location and message
- [ ] A file with several errors reports all of them in one exception

As-built:
<!-- fill in on completion -->

### M1.3 — Image pipeline (`app/media.py`)

Scope: plan §6 steps 1–7 for panoramas, D3 for floorplans. Synthetic fixtures are generated in
test setup: a tiny 2:1 JPEG with GPS EXIF and `DateTimeOriginal`, a non-2:1 JPEG, a PNG renamed to
`.jpg`, a truncated JPEG, and an image over the pixel limit (use a small patched
`MAX_IMAGE_PIXELS` rather than a huge file).

Acceptance:
- [ ] Output has **no** EXIF/XMP/GPS (asserted by reading the output back)
- [ ] `captured_at` extracted before stripping; missing `DateTimeOriginal` → `None`
- [ ] Magic-byte check rejects PNG-as-JPG; non-2:1 rejected; non-7680×3840 2:1 image warns but proceeds
- [ ] Downscale honours `max_width`; images already smaller aren't upscaled; thumbnail is ~400 px wide
- [ ] Truncated file and pixel-limit breach raise a clear import error, not a Pillow traceback

As-built:
<!-- fill in on completion -->

### M1.4 — Import CLI

Scope: `python -m app.cli import <tour.json> [--dry-run] [--prune]` and `reprocess-images --tour`.
Resolve paths relative to the JSON file, check image existence and map bounds (using floorplan
dimensions), run the pipeline, upsert by slug in one transaction, and report nodes present in the
DB but missing from the file. Links are stored with `yaw_override` only where the file gives `yaw`.

Acceptance:
- [ ] Importing the valid fixture creates the expected rows and media files at the §5 paths
- [ ] Running the import twice is a no-op the second time (no row changes, same files)
- [ ] Changing one node's title and re-importing updates only that node
- [ ] `--dry-run` writes nothing to the DB or media volume, and still reports every error
- [ ] Without `--prune`, a removed node is reported but kept; with `--prune` it's deleted and its events keep `node_slug`
- [ ] A failure midway leaves DB and media unchanged (D5)
- [ ] Out-of-bounds `map` coordinates fail validation

As-built:
<!-- fill in on completion -->

### M1.5 — Real data check (you + Claude)

Scope: `exiftool -G1 -a -xmp:all -exif:all` on a real Max 2 JPG, then decide D4 and record it in plan §14.
Write the real `tour.json`, import it on local compose, and run `exiftool` on the **output** pano to confirm
it's clean. Note file sizes and import time in As-built.

Acceptance:
- [ ] Real tour imported: two floors, 3–5 nodes
- [ ] `exiftool` on the output shows no GPS or other location data
- [ ] D4 recorded in plan §14 (and §6 step 4 updated)

As-built:
<!-- fill in on completion -->

## Out of scope

Auth and access-code CLI (M2). Any HTTP endpoint for tour data (M3). Markdown rendering (M3).
Computing link yaw from geometry (M3).
