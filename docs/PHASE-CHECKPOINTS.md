# WSP-03C — reviewed phase checkpoint reports

Plan saved before implementation, from verified PR #47 merge
`ecee2319de353a09120d77431d42d0d544c35ba0`.

## Plan

- [x] Retain a bounded, immutable report for the exact parked run/checkpoint,
  including phase goal, checkpoint destination, task outcomes, separate evidence
  axes, unresolved work and limits. Preserve it as a readable versioned artifact.
- [x] Bind owner review to that report and the exact next reviewed mission,
  settings policy and expiry. Require this review at every subsequent run intent;
  no direct-authorize bypass, stale report reuse or replay reactivation.
- [x] Expose scoped brain report prepare/read commands only. Owner review remains
  an internal trusted-caller seam until authenticated dashboard Play is qualified.
- [x] Test drift, tampering, replay, concurrency, rollback and multi-generation
  accounting continuity locally; retain full-suite verification.

## Limits

This report summarizes retained local claims; it does not collect new native,
GitHub, process, token or acceptance evidence. Safe parking is historical, not a
fresh assertion of inactivity. Phase completion is never inferred from an empty
queue or worker messages. Shared phase usage and admission must still be checked
at their existing effect boundaries; reported token limits are not measured usage.

Owner review is permission to retain the exact next run intent only. It does not
resume the brain, unpause dispatch, allocate capacity, settle ownership, approve
packets, grant a retry, accept results, merge or archive. Brain-stop reasons still
require a changed reviewed mission. Same-phase budgets and task attempts keep
their existing stable allocation; changing generations never resets them.

This advances milestone 5's report/release portion, not its separately bounded
new-generation task correction/rereview adapter. Native evidence milestone 3,
maintenance release, public Play, installed guidance and real acceptance remain
open. No live state, installation, schedules, paid services or Actions execution.

Older writers/prepared requests must be quiesced before a separately authorized
rollout. Subsequent generations now require the report review protocol; there is
no mixed-version writer or downgrade contract. Existing initial run and historical
request receipts remain readable; historical replay never restores authority.

## Report workflow and closed requests

The selected registered workspace and designated brain controller are mandatory.
The source CLI provides only `phase-checkpoint-prepare PRIVATE_REQUEST_JSON` and
`phase-checkpoint-read PRIVATE_REQUEST_JSON`, both following the normal
`--platform PRIVATE_PLATFORM --workspace WORKSPACE` selection. The controller token
comes from `ORCHESTRATOR_CONTROLLER_TOKEN`, never the file or output. There is no
automatic collection, report on every poll, owner-review CLI, HTTP control,
assistant control or native notification. No shared store is initialized/read
by this local report module, including when accounting has not been onboarded.

| Request | Exact fields |
| --- | --- |
| Brain prepare | `id`, `expectedRevision`, `runHash`, `checkpointHash`, `note` |
| Brain read | `reportHash`, `artifactId` |
| Internal owner review | `id`, `expectedRevision`, `reportHash`, `artifactId`, `missionHash`, `reviewReceiptHash`, `settingsPolicy`, `expiresAt`, `confirmed` |

Requests use bounded finite JSON (16,000 UTF-8 bytes) and explicit hashes, not
commands or file references to execute. Notes are inert, limited to 2,000
characters, and remain private. Reports are bounded to 256,000 bytes, 64 declared
phase tasks and 1,000 rows in each source table; oversized inventories refuse
rather than silently losing coverage. Larger histories need explicit migration.

Prepare requires the exact current parked checkpoint. It retains phase goal,
scope, checkpoint destination/criteria, stop reasons, configured limits, declared
tasks, original result commit and review times, per-axis/criterion statuses,
settlement references and recorded archival status. Report timestamps never renew
checkpoint or result observations. Accepted results are recorded independent
review outcomes, not a phase-completion claim; no review stays unreviewed even if
a worker's status claims complete. Retained result proofs are integrity-checked
using their existing historical validators. No new observation is made.

Unfinished task, unreviewed worker, other retained worker and pending-control
counts remain visible. Shared usage is explicitly unavailable in this local
report; use the separately qualified phase-usage interface before effect admission.
The report never converts configured limits, account percentages, estimates or
dashboard metrics into actual phase tokens. Empty work does not establish success.

The artifact uses the existing private versioned library, with a stable key per
run, original retention order, content hash and readable Markdown/JSON body.
Identical request replay returns the original artifact/receipt. A new prepare
creates another version and supersedes the release candidate, not old history.
Reads revalidate record hashes, receipt bindings, retained source proof bytes and
exact report artifact bytes without refreshing timestamps or rewriting state.

## Review and release

`phase_checkpoints.review(..., actor="dashboard_owner")` is an internal trusted
integration seam, not authentication. A future public caller must authenticate
the owner and bind its signed preview before invoking it. The brain cannot review
its report. Review requires the latest report and unchanged run, checkpoint,
worker/queue/repository state, pending controls and local runner. It also binds
the exact current owner-reviewed next mission, settings policy and expiry within
24 hours; prepare-only missions cannot authorize a release.

Every noninitial `run_authority.authorize` request must include the returned
`checkpointReviewHash` and those exact mission/review/settings/expiry values.
The grant transaction rechecks all report bindings and preserved evidence. No
missing-review legacy fallback exists. A later mission edit, report version,
changed task/control, expired intent or replaced checkpoint refuses. State change
and grant commit share one SQLite transaction; failures roll back. Concurrent
distinct requests at the same revision have one winner. Historical replay is
read-only even after a later stop; it cannot re-arm the old generation.

Review is not proof that the next phase is safe to execute. Current admission,
accounting, maintenance, native evidence and Pause checks remain mandatory at
every effect boundary. Old per-task approvals do not carry into the new run;
resuming existing tasks across generations still needs its future bounded adapter.

## Verification

Focused local checks cover report/CLI scoping, versioned preservation, unknown
usage, distinct result axes, proof tampering, report/mission/control drift,
read-only/replay semantics, expiry, rollback and concurrency. The existing
admission fixture releases a real fixture checkpoint through this protocol while
preserving its allocation, claim, 1,234 observed tokens and 11,500 held tokens.
Full local Python suite: **1,285 tests passed** in 180.792 seconds, including
30 new phase-report tests. The 117 focused report/run/admission tests also passed.
All eight JavaScript UI test files, both web-script syntax checks, Python module
compilation and `git diff --check` passed. No browser change was made. Read-only
GitHub inspection found zero Actions workflows and runs; no hosted CI was used.
