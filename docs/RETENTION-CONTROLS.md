# Owner retention controls — WSP-05F

Plan saved before implementation on verified PR #53 main
`2f039caeac8a05db9ea42c03c9533b361e883efa`.

## Plan

- [x] Selected-workspace, bounded read-only policy/run/attempt inspection and history.
- [x] Session-bound, signed, expiring review/revoke previews. Explicit confirmation
  commits through the existing policy kernel with exact revision/run/policy binding;
  idempotent historical replay cannot restore revoked authority.
- [x] Task retention screen using the existing editorial ledger design: explain
  unavailable setup, show exact limits and cleanup consequences, require unchecked
  acknowledgments, preserve drafts and reject stale/cross-workspace responses.
- [x] Cached numeric/status assistant context and navigation only, with no policy
  actions, automatic inspections, notifications, controller or native effects.
- [x] Local HTTP/security/lifecycle/UI regressions, disposable two-workspace browser
  checks and full local suite. Update roadmap without claiming live activation.

## Boundaries

This exposes only WSP-05E retention review and revocation, not run authorization,
Play, maintenance release, packet approval, task archival or cleanup. Review still
requires paused setup and an already valid phase-delegated run. Ordinary legacy
workspaces show why review is unavailable; no setup is manufactured to enable it.
Revocation cannot cancel an already-consumed native send boundary. Native/archive
safety, preservation, accounting and safe-Pause rules remain unchanged.

Preserve local fonts, light/dark themes, keyboard focus and narrow-pane layout.
No new dependency, hosted asset, paid service or GitHub Actions workflow. Source
and disposable fixtures only; no live policy, installation, restart or schedule.

## Owner workflow

1. Select the workspace and open **Task retention** from the navigation or overview.
   The page does not inspect automatically. Click **Inspect retention policy** to
   read the current saved policy, the most recent 20 versions and per-run request
   counts. Extra versions remain in the ledger and are labeled as omitted.
2. If no current phase-delegated run is authorized, or its paused setup is no longer
   valid, read the blocker. This page cannot prepare that authority. Ordinary Pause
   fences an active run; it is not a shortcut to changing retention mid-run.
3. Enter explicit archive-request and minimum-age limits, then preview. Review the
   exact workspace, phase/run generation, limits, expiry and signed bindings. Both
   acknowledgments start unchecked, including the separate managed-worktree cleanup
   acknowledgment. Approve only this exact policy. Saving does not archive anything
   or unpause dispatch; the brain still uses the independently guarded lifecycle.
4. To stop further delegation, enter a non-secret reason, preview the exact policy,
   and confirm revocation. This remains available for an intact retained policy
   even if its run has expired, fenced or moved on. Revocation cannot undo a native
   archive call whose one-shot send check was already consumed.

Limits remain those of WSP-05E: 1 to `min(64, run.maxTasks)` requests and 0–86,400
seconds since accepted review. Attempts are charged per exact run and never reset
by revising or revoking the policy. A policy version is not evidence of complete
preservation, fresh inactivity or successful archival. Historical versions keep
their original timestamps and bindings; revocation does not erase them.

The UI keeps workspace-specific drafts only in tab memory. Switching workspaces
discards confirmation eligibility and late responses; it never carries checked
acknowledgments into another workspace. Policy display can become stale after
60 seconds or a revision change; inspect again before preparing a new preview.

## Authenticated protocol and recovery

Only explicit selected-workspace routes are added:

| Route | Effect |
| --- | --- |
| `GET /api/workspaces/{id}/retention` | Bounded read-only policy/run/attempt metadata; no native/proof inspection |
| `POST /api/workspaces/{id}/retention/preview` | Closed `review` or `revoke` request; returns an ephemeral signed preview without saving a policy |
| `POST /api/workspaces/{id}/retention/confirm` | Explicit owner confirmation through the existing policy kernel; returns a durable receipt |

Writes retain the dashboard's local session, host/origin and workspace-CSRF gates.
Duplicate JSON fields, non-finite numbers, unexpected fields and query parameters
are rejected. Preview binds the exact revision/context, policy, run generation,
workspace and ledger inode to the authenticated session. Its HMAC key belongs to
that workspace runtime; changing the document, browser session, ledger identity
or dashboard process invalidates the signature. Unused previews expire after
five minutes. The server derives the owner actor and request ID; browser/model
content cannot choose a different actor or archive target.

Confirmation, context validation, policy mutation and retained receipt share one
workspace transaction. Concurrent identical confirmations apply once. Retrying
the same signed confirmation after a lost response returns its original receipt,
even after expiry or later revocation, without reapplying or extending authority.
No automatic retry occurs. The UI retains the exact proposal on error and asks
for fresh explicit acknowledgments before a same-request retry. After a restart
or session change, inspect saved state and reconcile the retained request receipt
before preparing a different change; an invalid old signature cannot prove that
its earlier confirmation did not commit. Do not reset counters or remove history
to recover from a missing/corrupt receipt.

The inspector bounds policy and attempt inventory, decodes retained evidence using
the existing kernels, and shows unavailable rather than granting fallback authority.
Read-only inspection does not open/init shared admission or obtain a controller.
State polling and assistant chat see only the cached historical numeric/status
projection, with freshness/revision labels. Hashes, paths, reasons and proof bodies
are excluded; the assistant gets a navigation link, not a retention action.

## Verification and release boundary

Disposable fixtures cover read-only inspection, first opt-in, explicit cleanup
confirmation, scope/session/signature isolation, duplicate JSON and closed inputs,
expiry/revision races, concurrency, rollback, historical replay, revocation after
expiry, attempt continuity, corrupt/oversize evidence and no native/notification/
shared-accounting effects. UI tests cover unchecked acknowledgments, isolated
drafts, late responses, workspace generations, original-request retries and routes.

Verified 2026-09-21: **1,421 Python tests** and **11 JavaScript UI suites** passed,
along with syntax checks for every web JavaScript file, Python compilation and
`git diff --check`. The new coverage includes 16 owner-control and 6 HTTP tests.
Read-only pre-push GitHub inspection found zero workflows and zero Actions runs;
no workflow, runner or paid service was added or triggered.

Browser verification used the disposable two-workspace fixture, not the live
dashboard: policy v1 → v2, updated limits, separate checkbox gating, revocation,
an unconfigured second workspace with no inherited policy, retained first-workspace
drafts, 390×844 narrow layout, dark/light themes and keyboard focus. No browser
console warnings/errors were observed. Impeccable's interaction guidance preserved
the existing editorial design and made cleanup consent a separate explicit step.

Run the fixture locally with `PYTHONPATH=. python3 tests/manual_retention_fixture.py`;
its printed link is fixture-only and Ctrl-C cleans up its temporary ledger/repositories.
It has no inference configuration or usable notifier and never calls native tools.

Milestone 8 remains partial: complete descendant/non-Git output preservation,
qualified host evidence and observed safe archival still need separate work.
Before any separately authorized rollout, quiesce older writers and back up private
state. No mixed-writer/downgrade safety, live installation or acceptance is claimed.
