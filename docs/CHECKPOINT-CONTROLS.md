# Owner phase-checkpoint decisions — WSP-03E

Plan saved before implementation on verified PR #54 main
`dfb8962d24056e666c49b4bb010ab278dae9fdcb`.

## Plan

- [x] Expose explicit selected-workspace decision inspection: latest retained
  report, exact next reviewed mission, available settings policy and review history.
- [x] Add signed, session-bound, five-minute preview/confirm controls for review
  and withdrawal. Preserve exact revision, report, mission, settings and expiry.
- [x] Add durable owner withdrawal of an exact review; check it atomically before
  a subsequent run grant. Historical retries never reapply withdrawn permission.
- [x] Extend Phase checkpoints with explicit next-intent confirmation and separate
  withdrawal. Preserve scoped drafts, stale-response guards and honest blockers.
- [x] Keep polling/chat to cached numeric/status metadata and navigation only;
  verify kernel/HTTP/UI regressions, disposable browser flows and full local suite.

## Boundaries

Review permits only a separately gated exact next run intent. This is not public
Play, phase acceptance, report preparation, fresh native evidence, capacity
allocation, task approval, retry, budget reset, maintenance release or notification.
Withdrawal prevents an unused review from authorizing a new grant; it cannot stop
an already-authorized run. That requires the existing safe-Pause control.

No live ledger, dashboard process, skill installation, schedule, native task,
paid service, workflow or GitHub Actions job is changed. Preserve the existing
editorial design, explicit unchecked confirmations, keyboard focus and both themes.

## Owner workflow

1. Select the workspace and open **Phase checkpoints → Inspect checkpoint decisions**.
   Opening the page alone performs no proof inspection. An unavailable report,
   unreviewed mission, changed evidence or unparked run produces a blocker, not
   default permission. Existing readable reviews remain withdrawable even when
   the report is no longer a valid candidate.
2. Inspect the bound saved report and expand the next mission's exact scope.
   The headline shows its objective, required checkpoint and configured limits;
   full mission and authority detail remains available. These are not measured
   usage or phase acceptance.
3. Explicitly select native defaults or an available current owner-reviewed
   adaptive policy, then a validity of 1–1,440 minutes. Neither choice is prefilled.
   Preview the review and check the exact report, mission, settings and expiry.
   The preview is valid for five minutes; the next-intent expiry starts at preview
   creation, not confirmation. Confirm through the initially unchecked acknowledgment.
4. Review is recorded locally. It does not grant a run, wake the brain or send a
   notification. Admission, qualified native evidence, maintenance and safe-Pause
   checks still apply before any later authorized effect.
5. Expand **Recorded owner reviews** to withdraw one exact review. Enter a
   non-secret reason, preview, then explicitly confirm. A new review does **not**
   supersede earlier reviews; withdraw each unwanted review. Withdrawal cannot
   cancel a grant that already committed, so use safe Pause for an authorized run.

History is newest first with original review/expiry and withdrawal times. An
inspection never renews those times. Missing review/withdrawal proof refuses
instead of silently showing an empty history. Details stay open across polling;
drafts are workspace-local, late responses are discarded even after switching
away and back, and focus moves to previews or explicitly inspected reports.

An uncertain confirmation retains the identical signed request for explicit retry.
Its historical receipt never reactivates a withdrawn review. If the dashboard
restarts, signatures no longer work: inspect saved decisions before preparing
another request. No automatic retry or retry-as-new-request is performed.

## Closed protocol and limits

Only authenticated selected-workspace routes exist:

| Route | Behavior |
| --- | --- |
| `GET /api/workspaces/{id}/checkpoint-decisions` | Explicit read-only inspection; no query parameters |
| `POST /api/workspaces/{id}/checkpoint-decisions/preview` | Signed five-minute review or withdrawal proposal; no ledger mutation |
| `POST /api/workspaces/{id}/checkpoint-decisions/confirm` | Exact proposal plus `confirmed: true`; atomic owner receipt and state |

Previews require `operation`, `expectedRevision`, and `contextHash`. Review also
requires exact `reportHash`, `artifactId`, `missionHash`, `reviewReceiptHash`,
`settingsPolicy`, and integer `expiresInSeconds` (60–86,400). Withdrawal requires
`checkpointReviewHash` and a nonempty reason capped at 2,000 characters. Unknown,
duplicate, nonfinite, extra or ambiguous input is rejected. No raw review, withdraw,
release, prepare, Play or owner CLI shortcut is added.

The server requires the normal loopback host/origin, authenticated browser session
and workspace-scoped CSRF checks. HMAC previews bind the session, ledger inode,
workspace, revision, full inspected context and decision. New confirmations check
fresh context inside the same SQLite write transaction as the existing review or
new withdrawal receipt. Historical confirmations recover only the original receipt;
review proof and withdrawal projection validation still apply. Per-workspace HTTP
operation locks refuse overlapping reads/previews/confirmations rather than blocking
dashboard threads indefinitely; SQLite revision checks protect other writers.

Inspection caps review history at 128 records / 2 MB before decoding. Signed
preview documents are capped at 28,000 UTF-8 bytes to fit the 32,768-byte HTTP
request bound; oversized missions refuse with a named next action. Durable
withdrawal inventories are bounded to 128 exact reviews and checked against
retained hash-bound documents and owner receipts. Missing projection/history
fails closed. Both authorization and withdrawal serialize through the same ledger
transaction: at the same revision only one may win. Other unused, nonwithdrawn
reviews remain eligible only if every existing scope/report/expiry gate still holds.

Dashboard polling and assistant F36 receive cached closed status/count metadata,
with inspection time, revision, staleness and historical labels. No report body,
mission, settings profile, review hash, reason, proof scan or assistant action is
included. The existing Phase checkpoints link is reused.

## Rollout and remaining work

Quiesce old writers before any separately approved installation. Older code does
not honor withdrawal, so no mixed-version writer or downgrade safety is claimed.
Live installation/restart, maintenance release and native acceptance are separate
owner-scoped work. New-generation correction/rereview, complete phase-exit
qualification and public Play remain open; this source increment does not remove
the external native-evidence qualification blocker. See [completion plan](COMPLETION-PLAN.md).

## Verification — 2026-09-21

- 1,446 Python tests passed, including 25 new adapter/kernel/HTTP tests covering
  owner/session/workspace/CSRF scope, tampering, expiry, concurrent confirmation,
  withdrawal versus grant, rollback, corrupt proof, historical retry, adaptive
  selection, empty workspaces, read-only polling and denied activation shortcuts.
- All 12 JavaScript UI suites, all web syntax checks, Python compilation and
  `git diff --check` passed. New UI checks cover empty explicit choices, stable
  policy selection, scope-isolated drafts, disclosure retention and immutable retries.
- Disposable browser fixture verified review then withdrawal receipts, keyboard
  confirmation, direct bound-report reading, focus, dark/narrow-middle and
  light/expanded-middle layouts, second-workspace blockers and no console errors.
  Fixture command: `PYTHONPATH=.:tests python3 tests/manual_checkpoint_controls_fixture.py`.
  Its fixed test-only bootstrap belongs solely to a temporary server and ledger;
  native notification and inference are unavailable.
- GitHub's read-only workflow/run inventory showed zero configured workflows and
  zero Actions runs. No jobs were dispatched and no runner/service was provisioned.

These are source and disposable-fixture results, not installed-runtime, native
execution, phase acceptance or autonomous-development qualification.
