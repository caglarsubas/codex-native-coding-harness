# WSP-05D — event-bound brain waits and operating-loop guidance

Plan saved against verified PR #49 merge
`178e545ded40d1ad21c67668e1884eb62f1ec274` before implementation.

## Scope and acceptance

- [x] Bind new brain `wait` decisions to bounded recorded lifecycle inputs.
  Store category hashes, not command bodies, artifacts or credentials.
- [x] Add read-only `brain-cycle-wait-state DECISION_HASH`: distinguish unchanged,
  changed, superseded and older unbound waits. Repeated reads do not renew evidence,
  append decisions/checkpoints, reset counters or produce native arguments.
- [x] Prevent duplicate unchanged wait decisions. Ignore controller/checkpoint
  bookkeeping, but notice owner input, policy/run changes, ownership, shared
  budget/capacity and eligibility changes. Refuse incomplete/oversized inventories.
- [x] Keep stop, pending receipts, owned tasks/runners, unfinished result review,
  eligible work and explicit idle-listener preference above quiet waiting.
- [x] Route the reusable skill to the integrated managed lifecycle, not legacy
  reserve/begin/complete shortcuts. Explain one-shot recovery and named wake events.
- [x] Verify local fixtures, CLI, repeated wake behavior and existing regressions.

This advances milestone 7 in source only. It does not install the skill, change a
heartbeat, suppress a native wake, prove native inactivity, release maintenance,
initialize an allocation or enable Play. The missing qualified host evidence and
real two-workspace operating-loop acceptance remain separate gates. No Actions or
new billable services are used.

## Recorded event contract

New `brain-cycle-decide` requests with `choice: wait` retain `waitBoundary` inside
the existing immutable decision and request receipt, in the same transaction.
It contains protocol `brain_event_wait_v1`, category SHA-256 values and recorded
supervision reason codes. The request schema is unchanged. Historical exact
replay returns the original receipt without comparing or refreshing it. A new
wait ID against an identical boundary is refused without writes.

Categories cover policy/run metadata, eligibility, queue, workers, control
requests, decision answers, follow-up planning, repositories, shared admission,
quarantined ownership, artifact metadata and recorded observations. No raw
command/answer body, artifact BLOB, source file or token is copied into a wait
boundary. Artifact metadata changes are events, not proof validation. Shared
changes can matter across workspaces because capacity/account headroom is shared.

Routine controller acquisition/release, ledger revision, inbox-check time,
checkpoint text and heartbeat observation time are ignored. Actual heartbeat
identity/status, owner input, policy changes and retained facts remain significant.
Elapsed time can change existing eligibility (for example expired account/run
evidence); it never refreshes the evidence. Comparisons are bounded to 500 rows
and 2 MB of metadata per scanned table, plus existing coordinator limits. Excess
refuses rather than reporting unchanged from a partial inventory.

Use the existing private controller token and explicit workspace:

```text
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace EXACT_WORKSPACE brain-cycle-wait-state DECISION_HASH
```

| State | Meaning / next action |
| --- | --- |
| `unchanged` | Recorded categories match and no local supervision reason is present. End the idle turn without another decision or evidence artifact. |
| `changed` | Inspect the named changed categories, then make a fresh decision. This is not approval or a permit. |
| `supervision_required` | Retained ownership/runner, pending receipts/answers/review, planning, eligible work or explicit idle listening still needs handling. |
| `stopped` | Safe-stop procedure takes precedence, including when the queried wait was superseded. |
| `superseded` | A later decision exists; use the current lifecycle instead of restoring the old wait. |
| `unbound` | Old-format wait has no event coverage; inspect and retain a bound wait once. No automatic migration. |

Every result says `executionAuthorized: false`, `nativeCallMade: false`,
`scheduleChangeAuthorized: false` and native activity `not_observed`.
`quietEligible` is a point-in-time scheduling advisory, not independent native
inactivity, a host subscription or proof that the named external event occurred.
An unrecorded external change cannot be discovered by this comparison. It must
arrive through an owner input or separately authorized observation/reconciliation.
Stop and normal inbox checks still precede every effect; recheck for racing input
before ending a turn or changing an already authorized schedule.

## Integrated guidance and rollout boundary

The source skill routes managed scope to `references/managed-cycle.md`, covering
selection, delegated authority, adaptive policy, creation/correction/runner
handoffs, evidence review, phase checkpoints and quiet waits. Legacy effect
commands are not fallback paths. Missing terminal/native adapters remain explicit;
the guide does not invent a complete end-to-end live loop.

No installed skill, running process, private ledger, heartbeat, native task,
admission allocation or fence is changed here. Stop and upgrade compatible
writers/prepared handoffs only under a separate owner rollout; no mixed-version
or downgrade guarantee is made. Old wait documents remain readable and unbound.
This does not save usage from an already-triggered model wake: actual idle-usage
reduction depends on later authorized installation and quiet schedule operation.

## Local verification

On 2026-09-21, **1,331 Python tests passed**, including 31 wait tests. All nine
JavaScript UI suites, `node --check web/app.js`, Python compilation and
`git diff --check` passed. The skill validator passed using an already-installed
Python environment; no dependency was downloaded. A temporary-directory install
copied the new guide exactly and its wrapper exposed the new command's help.
The real installed skill was untouched.

Fixtures cover unchanged read/replay, duplicate waits, concurrent receipts,
transaction rollback, controller handoff, stale context/clock aging, owner input,
Pause precedence, listener policy, shared budget changes, orphan/quarantined
ownership, conclusively reconciled non-creation, missing stores, evidence metadata,
corrupt/missing receipts and inventory bounds. One flow resumes from a recorded
event into delegated selection/reservation without replaying the prior wait.
Proof bytes and native tools are not polled by wait-state.

Read-only GitHub checks found zero Actions workflows and zero runs before push.
No CI success, deployment, native inactivity or real-loop acceptance is claimed.
