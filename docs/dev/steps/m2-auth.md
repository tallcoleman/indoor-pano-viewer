# M2 — Authentication and protected media

**Goal:** editors log in, viewers unlock with an access code, and `/media/*` only serves files to
a session allowed to see that tour, on both hosts.

**Plan sections:** §4 (entire), §5 (media serving and Caddyfile), §8 (public, editor auth, internal),
§10.2 (time, rate limiter, proxy header, Argon2 test approach), §12.

**Depends on:** M1 (tables and a real tour).  **Estimate:** 1.5–2 days.

## Decisions needed

| # | Decision | Recommendation |
|---|---|---|
| D1 | Serve media from FastAPI first, or go straight to Caddy `forward_auth`? | **Decided 2026-09-11: straight to `forward_auth`.** Caddy is already in the stack from M0; a `FileResponse` route would need 100% coverage now and deletion later. Plan §5 and §13 updated. |
| D2 | Which media a code can reach | A code with `tour_id` can only fetch `/media/tours/<that slug>/…`; a code with null `tour_id` gets every published tour; editors get everything. `media-auth` reads the original path from `X-Forwarded-Uri`. |
| D3 | CSRF token delivery | Double-submit: non-HttpOnly `csrf_token` cookie set at login; SPA echoes it in `X-CSRF-Token`. Compared in constant time. |
| D4 | Viewer session lifetime vs code expiry | `session.expires_at = min(now + code lifetime, code.expires_at)`. **Every** request also re-checks `revoked_at` and `expires_at` on the code, so revocation takes effect immediately. |
| D5 | `ip_prefix` | Store the /24 (IPv4) or /48 (IPv6) of the resolved client IP. It's useful for spotting shared codes and isn't a full address. |
| D6 | Rate limiter | Hand-rolled in-process token bucket (per IP + global) with an injectable clock. Values come from settings. No new dependency. |

## Slices

### M2.1 — Security primitives (`app/security.py`)

Scope: Argon2id hasher with parameters from settings; session token generation (`token_urlsafe(32)`) and
SHA-256 storage; access-code generation (prefix + ≥128-bit secret) and parsing; verification that
does a dummy Argon2 verify when the prefix doesn't exist; token-bucket limiter.

Acceptance:
- [ ] Code secret entropy ≥128 bits (asserted from length and alphabet)
- [ ] Malformed codes (no `-`, empty parts, extra dashes in prefix) are handled without exceptions
- [ ] Unknown prefix and wrong secret both run an Argon2 verify (assert the hasher is called in both paths)
- [ ] Limiter: burst allowed, then refused, then refills over (mocked) time; global ceiling trips independently of per-IP
- [ ] Production Argon2 parameters ≥ `argon2-cffi` defaults

As-built:
<!-- fill in on completion -->

### M2.2 — Editor auth

Scope: `cli editor create` (password via prompt or stdin, never as an argument); `POST /api/auth/login`,
`/logout`; `ed_session` cookie; session dependency; 12 h sliding expiry; `last_seen_at` throttled to
once a minute; rotate on login; `is_active` checked on every request; CSRF + JSON content-type
enforcement for editor mutations; `GET /api/session`.

Acceptance:
- [ ] Cookie attributes asserted exactly: `HttpOnly; Secure; SameSite=Lax; Path=/`
- [ ] Wrong password and unknown email give identical responses
- [ ] Session slides on use and expires after 12 h idle (time-machine)
- [ ] `last_seen_at` written at most once per minute across many requests
- [ ] Deactivating an editor rejects their next request
- [ ] Mutation without CSRF header → 403; mismatched → 403; non-JSON content type → 415 (or chosen code, asserted)
- [ ] Logout deletes the session row; the old cookie no longer works

As-built:
<!-- fill in on completion -->

### M2.3 — Access codes and unlock

Scope: `cli code create --label --expires [--tour]` (prints full code once), `code list`, `code revoke`;
`POST /api/unlock`; `vw_session`; `POST /api/session/logout`; rate limit on unlock; D4 and D5.

Acceptance:
- [ ] Created code unlocks; the stored row has no plaintext secret anywhere
- [ ] Unknown prefix, wrong secret, revoked and expired codes all return the same error body
- [ ] Revoking a code rejects an **existing** session on its next request
- [ ] Code expiring mid-session ends the session at that moment
- [ ] Unlock is rate limited: the (N+1)th attempt from one IP → 429; another IP is still allowed until the global ceiling
- [ ] `code list` never prints secrets or hashes

As-built:
<!-- fill in on completion -->

### M2.4 — Proxy headers and media auth

Scope: client IP resolution that trusts only the configured proxies; `GET /api/internal/media-auth`
implementing D2; add the `/media/*` `forward_auth` block to the Caddyfile (D1); `Cache-Control: private`.
The `internal` route must not be reachable from outside: Caddy must not proxy `/api/internal/*`
from the public site except through `forward_auth`. Decide how (e.g. `respond 404` for direct requests) and test it.

Acceptance:
- [ ] `test_proxy_headers.py`: spoofed `X-Forwarded-For` from an untrusted peer is ignored; from a trusted peer it's used
- [ ] media-auth: no cookie → 403; viewer on its tour → 204; viewer on another tour → 403; editor → 204; path traversal (`..`, encoded) → 403
- [ ] Through compose: `curl https://<host>/media/tours/<slug>/nodes/<node>/pano.jpg` → 403 without cookie, 200 with viewer cookie, `Cache-Control: private` present
- [ ] `curl https://<host>/api/internal/media-auth` directly → not 204
- [ ] The same curl checks pass on the Coolify deployment, and the rate limiter sees real client IPs there

As-built:
<!-- fill in on completion -->

## Out of scope

Tour payload and viewer (M3). Admin endpoints for access codes and activity (M5). Security headers/CSP (M5).
