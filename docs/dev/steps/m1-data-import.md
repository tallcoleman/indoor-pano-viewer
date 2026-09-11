# M1 — Data model and import

**Goal:** a committed, non-confidential sample tour (two floors, 4–6 nodes) lives in Postgres and
the media volume. It gets there through an idempotent import CLI, and its images are metadata-free
and correctly sized. The same CLI imports production tours from a folder outside the repo.

**Plan sections:** §3 (data model), §5 (media layout), §6 (tour.json, CLI, import behaviour,
image processing), §10.2 (image/CLI test approach), §12.

**Depends on:** M0 complete.  **Estimate:** 1.5–2 days.

## Prerequisites (you)

- [ ] 4–6 **non-confidential** Max 2 JPGs across **two floors**, of a place you're happy to have in the
      repo permanently. These become the committed sample tour (D1).
- [ ] Simple floorplans for those two floors (hand-drawn and scanned is fine).
- [ ] `exiftool` installed locally.
- [ ] Rough `map` coordinates for each node (read from the floorplan in any image editor). They get corrected in M4.

## Decisions needed

| # | Decision | Recommendation |
|---|---|---|
| D1 | What tour data lives in the repo | **Decided 2026-09-11.** Two kinds of test data are committed: (1) tiny synthetic images and test JSON generated or stored under `api/tests/fixtures/`, for unit tests; (2) a **sample tour** in `samples/sample-tour/` (full-size real Max 2 JPGs, ~3 MB each, in plain git, no LFS; floorplans; `tour.json`) for local dev, the Playwright smoke test, and checks against real Max 2 files. **Production `tour.json`, photos and floorplans are never required in the repo**; they reach the server through `IMPORT_HOST_PATH`. `/data/` is gitignored. |
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

### M1.5 — Sample tour and real data check (you + Claude)

Scope:
1. Run `exiftool -G1 -a -xmp:all -exif:all` on the **original** JPGs, which stay local and uncommitted.
   Decide D4 and record it in plan §14. Record the real dimensions and typical file size.
2. Prepare copies for the repo. Remove real location data (`exiftool -gps:all= -overwrite_original`),
   then check with `exiftool -a -G1 "-*gps*" "-*location*"` that no location tags remain in EXIF **or XMP**.
   Write **fake** GPS (e.g. 0°N 0°E) into one sample so the stripping test runs on a real Max 2 file layout.
3. Commit `samples/sample-tour/` (JPGs, floorplans, `tour.json`). Set `.env.example`
   `IMPORT_HOST_PATH=./samples` so a fresh clone can import it immediately.
4. Import on local compose and run `exiftool` on the **output** panoramas.
5. Import once more from a folder **outside the repo** (absolute `IMPORT_HOST_PATH`) to prove production data needs no repo.

Acceptance:
- [ ] Sample tour committed: two floors, 4–6 nodes; no real location data in any committed file
- [ ] Fresh clone → `docker compose up --wait` → import sample tour works with no extra files
- [ ] Integration test imports one sample JPG through the pipeline and asserts the fake GPS is gone
- [ ] `exiftool` on output panoramas shows no GPS or other location data
- [ ] Import from a directory outside the repo works
- [ ] Real Max 2 dimensions confirmed; if they aren't 7680×3840, plan §1/§6 and CLAUDE.md updated
- [ ] D4 recorded in plan §14 (and §6 step 4 updated)

As-built:
<!-- fill in on completion -->

## Out of scope

Auth and access-code CLI (M2). Any HTTP endpoint for tour data (M3). Markdown rendering (M3).
Computing link yaw from geometry (M3).
