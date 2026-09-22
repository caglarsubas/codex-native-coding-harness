# Remembered browser access

The dashboard supports explicit **Remember this browser** for 7, 30 (the default
selection), or 90 days. It remains loopback-only. This changes browser sign-in,
not any workspace's approval, controller, pause, notification or dispatch policy.

## Owner workflow

1. Open the current private URL from `dashboard-session.json` in the ledger root
   (`--state`) or registry root (`--platform`). Pair each browser separately.
   Never share or publish this URL. The fragment is removed immediately.
2. In the top bar choose **Remember this browser**, choose the duration, and
   confirm with **Remember this browser**. Opt-in is explicit, not automatic.
3. Bookmark the normal workspace URL, without a token. Remembered sign-in survives
   browser and dashboard restarts until the displayed absolute expiry. Polling
   does not extend it indefinitely. Renew explicitly in **Browser access**.
4. **Use temporary sign-in** returns to eight hours, lost on server restart.
   **Sign out** revokes this browser's session. **Revoke all browser access**
   requires an unchecked confirmation and signs out all paired browsers, including
   temporary sessions. Neither operation pauses or stops development.

Existing in-memory sessions cannot be migrated. After installing this version,
one last private-link sign-in and explicit Remember action are required per browser.
Cleared cookies, private-browsing cleanup, expiry or revocation require pairing
again. Changing the listening port or private state root also requires pairing.
Renewing changes the cookie and CSRF; reload other open tabs before using controls.
If an action was already submitted before sign-out, it is not cancelled.

## Implementation and boundaries

- Browser cookies are HttpOnly, SameSite=Strict, Path=/, with a bounded Max-Age.
  This remains HTTP on `127.0.0.1`; do not expose it through a network proxy.
- Cookie names bind the canonical private root and origin, preventing accidental
  main/pilot collisions. Cookies are still host-wide, not port-isolated security.
  This does not protect against malicious same-host services or the same OS user.
- Only SHA-256 hashes of random 256-bit session credentials are stored, together
  with CSRF material and fixed creation/expiry/duration. No raw cookie, bootstrap
  token, browser fingerprint or conversation is stored in this auth database.
- Remembered sessions live in `<private-root>/browser-auth/`: directory mode 0700,
  files 0600. File locking, bounded reads, ownership/link/permission checks and
  fsynced atomic replacement protect normal persistence. Invalid or unsafe storage
  refuses access; it is never silently repaired to grant access.
- Ordinary sessions remain in memory. Up to 32 live sessions are permitted per
  dashboard origin. Expired entries are pruned when issuing a session.
- Authentication changes require exact Host, Origin, JSON, and **global** browser
  CSRF. Workspace CSRF cannot revoke platform browser access. Existing scoped
  controls still require their original workspace-bound CSRF and authority gates.
- The private bootstrap link still rotates on server restart. Remembered browser
  sessions do not depend on that token. Revocation removes sessions, not the local
  owner's possession of the current bootstrap link.
- No credential goes into localStorage, sessionStorage, Git, exports or inference.
  Backups of the auth store contain sensitive authorization state; restoring an
  old store can restore revoked sessions until their original expiry. Exclude it
  from routine ledger restores or deliberately reset/re-pair after restoration.

The auth store is independent of ledger schema. Rolling source back preserves
ledger data but does not provide remembered sign-in in old code. No live ledger
migration, native task operation, schedule change or paid service is required.

## Verification

`python3.12 -m unittest discover -s tests -p test_browser_auth.py -v` tests restart
survival, hard expiry, temporary sessions, logout, all-browser revocation, session
rotation, namespace separation, file permissions/corruption/link safety, failed
writes, caps and input validation, HTTP security gates and untouched workspaces.
`node tests/test_browser_auth_ui.js` tests the explicit UI choices and global CSRF.
Use disposable state for browser QA; never revoke live sessions as a test.
