# WSP-03G — owner controls for settled-result rereview

Plan saved before implementation on verified PR #56 main
`ab2ec14caa4e14093483481df969d3f83eaa08f6`.

## Plan

- [x] Add explicit, bounded, selected-workspace/task inspection of original
  settlement, result versions, current review permission and later-run eligibility.
- [x] Add authenticated owner authorize/revoke previews with session, workspace,
  ledger, revision, exact commit and context binding; confirm atomically against
  WSP-03F. Historical retries recover receipts without reapplying permission.
- [x] Put the controls in Workers & evidence: choose a task, inspect, supply a
  non-secret reason and exact commit, preview, then explicitly confirm. Show
  blockers, immutable versions and original times without automatic proof reads.
- [x] Keep assistant/polling to cached closed metadata and navigation; verify
  API/kernel/UI races, disposable browser flows and the full local regression suite.

## Boundaries

Only permission to review unchanged settled bytes is granted. The brain still
must collect fresh evidence and independently review the exact result. No task
approval, result acceptance, native send, new attempt, budget reset, phase grant,
notification, public Play or maintenance release follows. Revocation cannot undo
an outcome already committed. Accepted results cannot reopen; changed source
requires a separately authorized implementation task. Harness remains gated.

Preserve the existing editorial design and locally available fonts, light/dark
themes, visible labels, keyboard focus and unchecked confirmations. No optimistic
authority state, inference-authored approval or automatic inspection/retry.

No live dashboard, ledger, task, skill installation, schedule, runner, paid service
or Actions workflow is changed. All tests use disposable fixtures. Quiesce older
writers before any separately authorized rollout; no downgrade safety is claimed.

## Owner workflow

1. Select the workspace and open **Workers & evidence**. Choose one admission-
   managed task; nothing is chosen or inspected automatically.
2. Select **Inspect result & permission**. Read the original settlement, latest
   outcome, original scope/criteria and current phase. A named blocker replaces
   authorization when the task or current reviewed run is ineligible.
3. Enter a non-secret reason. For a previously reviewed result the full commit is
   fixed; for an unreviewed settled result supply the existing result's full
   commit. A base commit or branch alias is refused; a previously reviewed commit
   cannot be changed.
   This form does not query Git or assert the supplied commit's existence.
4. Select **Preview review permission**, inspect the exact workspace, task,
   phase/generation, commit, previous outcome and expiry, then check the initially
   unchecked acknowledgment and select **Authorize this review**. The brain still
   needs fresh evidence and an independent review through the existing handoff.
   This action neither wakes the brain nor schedules a review.
5. To withdraw unused permission, supply a separate reason and preview/confirm
   **Revoke review permission**. Revocation is available after Pause and cannot
   undo a result already committed. A new grant requires a new explicit review.
6. Expand **Review versions & permission history** for newest-first outcomes and
   permissions with their original times. **Read saved independent review** opens
   the retained artifact as inert text through the existing authenticated reader.
   Inspection and artifact reading do not refresh proof timestamps.

Inputs and disclosure state are isolated by workspace/task. Changing workspace
invalidates pending previews, and late responses cannot appear under another
selection. Inspections older than 60 seconds or a changed revision require an
explicit refresh. Server-side current-context validation is authoritative.
If a response is lost, retry the same signed confirmation; never automatically
resend or prepare a replacement request. A committed original request can recover
its receipt even after the preview expires, without restoring revoked permission.
After a dashboard restart or browser-session change, inspect recorded history and
prepare a fresh preview if necessary; the old session signature is no longer usable.

## HTTP and transaction contract

All routes require the existing loopback Host validation and authenticated cookie.
Writes additionally require same-origin checks and selected-workspace CSRF.
No legacy unscoped route, assistant action or CLI owner-approval shortcut is added.

| Route under `/api/workspaces/{id}` | Behavior |
| --- | --- |
| `GET /result-review-controls?workerId=...` | One exact task, read-only SQLite snapshot; missing/duplicate/extra query fields refuse |
| `POST /result-review-controls/preview` | Closed authorize/revoke shape, fresh explicit inspection, session-bound signed five-minute preview; no write |
| `POST /result-review-controls/confirm` | Literal `confirmed: true`, intact signature/session/ledger, fresh context and WSP-03F write in one transaction |

An authorization preview accepts `operation`, `workerId`, `expectedRevision`,
`contextHash`, `reason` and `commit`. Revocation substitutes `authorityHash` for
`commit`. The server derives run, intent, settlement and previous-review bindings;
the client cannot override them. Confirmation accepts only `proposal` and
`confirmed`. JSON duplicates/nonfinite numbers, queries on writes and simultaneous
operations in one workspace refuse. Preview signatures are ephemeral per runtime.

An intact permission remains revocable when result proofs are damaged, but damaged
permission history fails closed. Confirmation revalidates in the same transaction
as the owner kernel write. Concurrent confirmation has one original receipt;
grant/revoke races have one winner. Historical replay verifies the original receipt
before bypassing freshness and never reapplies projections. Current run, task
scope, accepted-result, expiry and evidence checks still fence new work.

Existing bounds remain: 32 result versions per task, 128 permission records and
2 MB permission history per workspace; new grants retain the last slot for
revocation. Inspection is capped at 128,000 serialized bytes, signed preview at
28,000, HTTP body at 32,768 and underlying owner request at 16,000. Exhaustion
requires explicit operator migration, never silent truncation or pruning.

State/polling and assistant fact `F37` contain cached counts/status, original
inspection time/revision and explicit stale/changed indicators only. They do not
trigger proof inspection or disclose result identities, commits, hashes, reasons
or proof bodies to inference. The assistant may use the existing Workers & evidence
navigation, not authorize/revoke/accept/collect on the owner's behalf.

## Local verification

The focused backend/HTTP tests cover read-only inspection, exact commits (including
unreviewed results), accepted-result and narrowed-phase refusals, signatures,
session/CSRF/workspace binding, missing/corrupt evidence, Pause/expiry, concurrent
confirmations and rollback, revocation, historical retries and unchanged accounting.
The JavaScript suite covers explicit choices, unchecked confirmation, immutable
retry IDs, isolated drafts, stale task/workspace responses and inert artifact text.

Disposable two-workspace browser rehearsal on 2026-09-21 exercised inspection,
preview, authorization, revocation and reading the retained independent review.
The original changes-required outcome remained unchanged; the empty second
workspace inherited no task or permission. Light/dark rendering and the existing
narrow pane were checked. No live workspace or model service was used.

Reproduce with `PYTHONPATH=.:tests python3 tests/manual_rereview_fixture.py`, then
open its printed temporary loopback URL. Ctrl-C shuts down and cleans only its
temporary fixture. Its fixed bootstrap value is fixture-only, not a live secret.
See [completion plan](COMPLETION-PLAN.md) for final local regression totals.

All 1,490 Python tests and thirteen JavaScript UI suites passed locally, along with
JavaScript syntax, Python compilation and diff whitespace checks. GitHub's
read-only pre-publication inventory reported zero workflows and zero runs, and no
workflow file was added. These are local checks, not GitHub CI or live acceptance.

## Remaining gates

This closes WSP-03F's owner-surface gap, not the complete phase lifecycle. Native
changed-source correction/resume, phase-exit qualification, controlled rollout and
public Play remain separate. Qualified lifetime counters and whole-process-tree
cleanup evidence remain an external capability decision; more UI PRs cannot supply
that evidence. No live acceptance is claimed by a source test or a merged PR.
