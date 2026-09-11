# M5 — Hardening

**Goal:** safe to hand codes to real people. Security headers verified against real panorama loads,
editors can manage codes and see activity without a terminal, retention is enforced, and backups
have been restored at least once.

**Plan sections:** §4 (security headers), §3 (`access_event` retention and disclosure), §8 (admin
access-code and activity endpoints), §10.3 (backups), §12 (whole risk table).

**Depends on:** M2–M4.  **Estimate:** ~1 day.

## Decisions needed

| # | Decision | Recommendation |
|---|---|---|
| D1 | **Admin API scope for v1.** Plan §8 lists full CRUD for tours/floors/nodes/markers/links, but no milestone builds it, and JSON import is the authoring path. | v1 admin API = **access codes** (list/create/revoke), **activity** (per code, per node), and **placement** (M4). Move content CRUD to M6 with the GUI. Update plan §8. |
| D2 | `access_event` retention period (plan §14 open question 1) | Your call. 1 year is a reasonable default for a building survey; 90 days if the audience is external. |
| D3 | How prune runs on a schedule | Coolify **Scheduled Tasks** running `python -m app.cli events prune` in the `api` container; host cron with `docker compose exec` on vanilla. Both documented in `docs/dev/deploy.md`. No in-process scheduler. |
| D4 | Backup target | Your call (off-host is the point). Script produces `pg_dump -Fc` + media tarball with a date stamp; where it's copied depends on your storage. |

## Slices

### M5.1 — Security headers and CSP

Scope: headers from plan §4 in the Caddyfile. Extend the Playwright smoke test to fail on any CSP
violation (listen for `securitypolicyviolation` and console errors) while loading a panorama, switching
floors and opening the side panel. Custom error pages for 403/404/5xx served by Caddy.

Acceptance:
- [ ] `curl -I` shows all four headers on SPA, API and media responses
- [ ] Playwright: zero CSP violations across the smoke flow
- [ ] Manual: real pano loads on desktop and phone with the final CSP on both hosts

As-built:
<!-- fill in on completion -->

### M5.2 — Admin: access codes and activity

Scope: API from D1 (`/api/admin/access-codes`, `…/revoke`, `…/activity`, `/api/admin/tours/{slug}/activity`)
with pagination. `/admin` UI: code list with last-seen, create (shows code once, with copy-link button that
builds the `#code=` URL), revoke with confirmation, per-code activity timeline, per-node "who viewed this".

Acceptance:
- [ ] All endpoints: viewer → 403, missing CSRF on mutations → 403, pagination boundaries tested
- [ ] Created code appears once in the create response and never in list/activity responses
- [ ] Activity shows `node_slug` for pruned nodes
- [ ] Manual: create → open link in private window → walk tour → activity visible in admin → revoke → private window is locked out on next navigation

As-built:
<!-- fill in on completion -->

### M5.3 — Retention

Scope: `ACCESS_EVENT_RETENTION_DAYS` setting; `cli events prune [--older-than]` (defaults to the setting;
does nothing and says so when unset); D3 scheduling documented and configured on Coolify.

Acceptance:
- [ ] Prune removes exactly the rows older than the cutoff (boundary tested); unset setting → no deletion
- [ ] `--dry-run` reports count without deleting
- [ ] Scheduled task configured on Coolify and seen running once

As-built:
<!-- fill in on completion -->

### M5.4 — Backup and restore

Scope: `scripts/backup.sh` using `docker compose exec` (no hardcoded volume names); restore procedure in
`docs/dev/deploy.md`.

Acceptance:
- [ ] Backup taken on Coolify and restored into a fresh local stack; tour, codes and activity all present
- [ ] Runbook covers scheduling on both hosts

As-built:
<!-- fill in on completion -->

### M5.5 — Risk review

Scope: go through every row of plan §12 and record in As-built how it was verified (test name, curl
command, or manual check). Move resolved open questions into plan §14.

Acceptance:
- [ ] Every §12 row has a verification noted
- [ ] Plan §14 "Still open" is empty or each item has an owner

As-built:
<!-- fill in on completion -->

## Out of scope

Content CRUD API and GUI (M6).
