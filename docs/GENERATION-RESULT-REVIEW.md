# WSP-03F — review settled results in a later generation

Plan saved before implementation against verified PR #55 merge
`5f7d7c43db3f8223629c289a128c38b9969600d7`.

## Plan

- [x] Add an explicit, exact-owner review-only authorization for one settled
  standard-policy result under a later current run, bounded by the current
  reviewed mission, original seed/contract, exact commit and previous outcome.
- [x] Permit existing result collectors and supplemental proof retention only
  through this current authorization; keep before/after I/O, maintenance, Pause,
  freshness, original evidence provenance and independent-review checks.
- [x] Record a new immutable result-review version without deleting earlier
  outcomes. Validate the bounded history on reads, settlement recovery and phase
  reports; historical retries never restore old projections or authority.
- [x] Integrate the existing designated-brain result handoff and CLI, test a
  checkpoint/new-generation/rereview cycle with temporary fixtures, and run the
  complete local regression suite.

## Scope and boundaries

This is review of existing bytes, not a correction send or a reopened attempt.
Previously accepted results are final in this increment. A changes-required
result may be reconsidered only at the same exact commit; changed source requires
a separately authorized new implementation task. No new task approval, native
call, runner, reservation, usage reset, ownership release or retry follows.

WSP-03F introduced an internal trusted owner seam. The subsequent
[WSP-03G dashboard adapter](REREVIEW-CONTROLS.md) now authenticates explicit owner
preview/confirmation; the brain still cannot mint permission. It may be revoked
before consumption.
There is no public Play, live installation, maintenance release, scheduler,
paid service or Actions execution. All verification uses disposable fixtures.
Harness review remains refused until its trusted adapter is qualified.

## Internal owner contract

`result_reauthorization.authorize(ledger, request, actor="dashboard_owner")`
accepts closed finite JSON, bounded to 16,000 bytes:

| Field | Binding |
| --- | --- |
| `id`, `expectedRevision` | Immutable 8–100 character request ID and exact current ledger revision |
| `runHash` | Current, unexpired, owner-authorized descendant of the original run |
| `workerId`, `intentHash`, `settlementHash` | Exact original task and attached confirmed-terminal result |
| `previousReviewHash` | Exact latest changes-required outcome, or `null` if not yet reviewed |
| `commit` | Full existing result commit; must equal the previous review commit when present |
| `reason`, `confirmed` | Bounded nonempty review rationale and literal `true` |

The actor argument is a trusted internal integration boundary, not authentication.
The subsequent [WSP-03G owner HTTP adapter](REREVIEW-CONTROLS.md) supplies signed
preview/confirmation, not a CLI shortcut or brain-authored permission. The later
run must already exist through the parked-checkpoint
and owner-reviewed phase-release contract. Authorization neither creates nor
resumes it, and it requires unpaused dispatch. The original seed, task contract and
approval remain unchanged; current reviewed mission paths, operations, repository
identity/policy and estimate limits must still cover the old declaration. This
conservative rule can refuse review after scope narrows, even if the old result
was once in scope. It never broadens the current phase to accommodate old work.

`revoke(ledger, request, actor="dashboard_owner")` takes `id`, `expectedRevision`,
`workerId`, exact current `authorityHash`, `reason`, and `confirmed: true`. It
retains a new denial version, even after Pause. Revoking consumed permission does
not undo an accepted result. Each permission binds one previous result version:
recording any new outcome consumes it, including another changes-required outcome.
Another review needs another exact owner permission. Historical request replay
returns the original receipt without restoring a superseded or revoked pointer.

## Brain handoff and immutable history

After owner authorization, use the existing result handoff collectors and proof
retention at the exact authorized commit. Current run, Pause, maintenance and
worker-control gates apply before and after collector I/O. There is no new native
transport or automatic inspection. Source/CI provenance, all required criteria,
preservation and independent-review checks are unchanged. An independent report
must be observed after the new permission, and all observations must still be
fresh at review; new report timestamps cannot refresh old proof bytes.

Add `reviewAuthorityHash` to the existing `result-handoff-review` request. The
hash is mandatory once this worker has a review-authority history. A successful
transaction records schema version 2 with `previousReviewHash`, updates only the
local result/worker/queue projection and retains every old version. It leaves
closed native attempts, original task approval, reservations, actual usage and
shared accounting unchanged. Unreviewed legacy results keep schema version 1
when reviewed under their original current run without this permission.

`result-handoff-state` includes newest-first `reviewHistory` receipts and a
historical `reviewAuthority` summary. The latter records approval/revocation,
expiry and consumption, not current eligibility. These explicit reads validate
the full bounded history; no polling, freshness update or live status is implied.
Result reads, settlement recovery and phase reports verify all previous outcome
proofs and each authorizing receipt. Old result-request replay can return an older
receipt but cannot restore that outcome over the current projection.

History is capped at 32 result versions per task and 128 authorization/revocation
records (2 MB serialized) per workspace. A final slot is reserved for withdrawal.
Bounds refuse and require an explicit migration; never prune history to reopen a
task. Before any separately authorized rollout, quiesce older writers and back up
private state. This source delivery provides no mixed-version or downgrade safety.

## Verification and remaining work

Regression coverage uses temporary ledgers, real temporary Git repositories and
stubbed GitHub responses. No live task or service is contacted. See the local
verification totals in [completion plan](COMPLETION-PLAN.md).

Local verification on 2026-09-21: all 1,467 Python tests passed (including 21 new
generation-review regressions), all twelve JavaScript UI suites passed, and
JavaScript syntax, Python compilation and diff whitespace checks passed. GitHub
reported zero configured Actions workflows and zero runs before publication;
no workflow was added or invoked. These are local results, not GitHub CI or live
acceptance evidence.

This advances only milestone 5's settled-result rereview component. Cross-generation
native correction/resume, changed-source tasks, phase-exit qualification and Play
remain separate. WSP-03G closes the owner UI gap only. Native host/counter evidence qualification
is still an external capability gate, not something these source tests establish.
