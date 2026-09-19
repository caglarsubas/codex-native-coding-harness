# WSP-04C3a — terminal ownership settlement

Plan saved before implementation, continuing merged PR #25 (`8318bf4`).

Implement one bounded internal coordinator for releasing a confirmed native
worker's repository/slot reservation after explicit terminal reconciliation.
Settlement is accounting and relinquishment, **not packet acceptance**, native
termination, archiving, runner execution or public Play.

## Implementation checklist

- [x] Require the exact latest native journal and dispatch/phase binding, a
  confirmed idle task, no unresolved continuation or worker control, and no local
  or shared runner ownership. Preserve maintenance/adoption fences.
- [x] Require bounded complete idle descendant inventory, retained task-scoped
  handoff bytes, resource cleanup observations and complete per-task cumulative
  usage; refuse missing, stale, foreign and contradictory evidence.
- [x] Atomically journal shared settlement, replace held estimates with actual
  tokens and release only this claim's exact repository keys. Retain task-attempt
  counts, native identity and all prior history; overruns remain truth.
- [x] Attach the committed receipt locally. Recover after a crash without another
  release, native send, counter reset, approval reuse or packet completion claim.
- [x] Test replay, concurrent requests, partial writes/process exit, two-workspace
  resource reuse, evidence corruption, Pause and budget continuity.

## Boundaries

Only trusted designated-brain internal Python calls and isolated tests. No CLI,
HTTP, assistant or installed-skill entry point; no live setup or transport.
Native activity, coverage, terminal intent, cleanup and token samples are supplied
external assertions, not independently authenticated native evidence. The future
adapter must obtain and independently verify them; a final worker message or
empty queue is not evidence. This increment cannot qualify live dispatch.

Confirmed terminal workers only. Unknown/pending creation, reconciled not-created
attempts, active or uncertain correction sends, runner ownership, quarantined
legacy owners, maintenance release and continuation across new run generations
remain separate work. Idle alone never releases anything.

The local worker becomes `settled`, not `complete`; its queue is held for separate
result review. Existing source/CI/merge/artifact/deployment/runtime/assurance/tenant
axes, pilot state and preserved/archived flags are not upgraded. The old task,
seed, approval and native IDs cannot be reused for another dispatch.
Portfolio metadata counts settled tasks separately from active and completed
tasks. Safe-Pause and legacy maintenance inventory remain conservative and still
retain these unaccepted task records; settlement does not delete their native
supervision history or silently change enrollment migration behavior.

No dashboard process, installed skill, live ledger, schedule, native task, product
repository, inference service, credential or model setting is changed by delivery.

## Internal contract

Construct `OwnershipSettlement` from the existing `DispatchAdmission`. Construction
and recovery never create policy, allocations or a settlement table. Only
`settle(controller_token, worker_id, request)` can record a new settlement. The
token must identify that workspace's current designated-brain controller.

The request is closed and limited to 16,000 UTF-8 bytes:

| Field | Required content |
| --- | --- |
| `id` | Bounded request identifier; one immutable settlement per worker |
| `expectedHash` | Exact latest attached native journal hash; not an execution permit |
| `inventory` | `observedAt`, `evidenceHash`, explicit true `complete`, `includesDescendants`, `pendingResolved`, `effectsComplete`, and 1–16 `tasks` |
| `inventory.tasks[]` | `hostId`, `threadId`, `parent` (null only for the exact root, otherwise host/task pair), `status: idle`, `observedAt`, `evidenceHash`, `checkpointArtifactId` |
| `resources[]` | Exactly the claim's 1–4 canonical repository keys, each with `key`, true `processesExited`, true `cleanupObserved`, `observedAt`, `evidenceHash` |
| `usage` | `observedAt`, `evidenceHash`, true `complete`, and `sessions` covering exactly the inventory |
| `usage.sessions[]` | `hostId`, `threadId`, `counterEpoch`, complete `counters`, true `complete`, `observedAt`, `evidenceHash` |

Counter fields retain the admission contract: `inputTokens`, `cachedInputTokens`,
`outputTokens`, `reasoningOutputTokens`. Aggregate actual usage is input + output;
cached input and reasoning are subsets, not extra tokens or monetary discounts.
The final per-session counter epochs and source hashes are preserved. This module
does not derive samples from historical dashboard totals or authenticate their
completeness. Missing counters are never converted to zero.

Coverage and `effectsComplete` mean that the trusted coordinator has independently
reconciled the entire task tree, pending IDs, native sends and external effects,
and intends to end this claim permanently. They are not commands to stop anything.
The only null parent is the confirmed worker. Every other parent chain must reach
that worker; cycles, other claims, registered brains and retained pending client
IDs refuse. Previously observed descendants from retained workspace-Pause history
must remain covered, including descendants of a root missing from a partial report.
Pause-history inspection is bounded to 1,000 records / 2 MB; larger history needs
an explicit archival migration, not silently truncated coverage.

Every task needs immutable handoff bytes of at most 16,000 bytes, verified against
the retained artifact version/hash and same-repository, exact-session references.
The artifact must be retained after the latest native journal entry and before
the supplied task idle observation. Artifact text remains data; no commands are
parsed or executed. Evidence timestamps must be fresh under admission policy and
not future-dated. Task observations follow the journal and artifacts, inventory
follows task observations, cleanup follows inactivity, and final usage follows the
inventory. Polling or reading never refreshes those timestamps.

No local runner may be owned, and this claim may not own any shared runner. Queued
or processing checkpoint/archive controls for the worker must be reconciled first.
Continuation intent, uncertain/acknowledged delivery or an unmatched local marker
blocks release; a finished correction permits reconciliation but does not release
anything on its own. Native receipt drift requires explicit native recovery first.

## Transaction and recovery

The lock order remains registry -> workspace -> admission. Settlement verifies
the exact dispatch intent, immutable phase allocation, native journal and local
receipt. It then atomically commits the shared immutable settlement record, final
claim/counters, repository-key removal and audit event. Shared records are capped
at 32,768 bytes. Only the reconciled claim's exact resources are removed; runner
resources never pass the release gate.

The local attachment happens **after** that shared commit. Cross-database writes
are recoverable, not atomic. A failed attachment leaves a conservative local
`running` owner. The shared `settled` claim prevents every old creation or
correction path from operating. Another workspace may reserve the released keys
after the commit; receipt recovery checks only the old claim's absence of ownership
and must not disturb that newer owner.

`recover(controller_token, worker_id)` attaches only an existing hash-verified
settlement, including after Pause, expiry or a later maintenance fence. It never
settles an uncommitted request, releases resources again, increments usage, sends
a message, changes model settings or resumes a task. Missing or changed shared
history/local identity refuses rather than silently repairing ownership. Exact
request replay returns the original receipt without re-evaluating expired evidence
or refreshing its time; conflicting settlement content refuses. New settlement
requests preserve enrollment/adoption fences even while paused. A dedicated
recovery call is required if an enrollment fence now blocks request replay.

The receipt reports `ownershipReleased: true`, `packetAccepted: false`,
`executionAuthorized: false`, `nativeCallMade: false`, and explicitly identifies
the caller-supplied evidence boundary. The module does not claim that no external
native work ever happened, or that an externally awakened task cannot run later.
Any such later activity is a separate incident requiring explicit reconciliation.

## Accounting and remaining work

The original claim, native/client/descendant identities, attempts, estimates,
correction totals and no-progress history remain retained. Held estimates stop
consuming capacity, but actual tokens remain conservatively charged as
unincorporated settled usage until a later complete cumulative allocation sample
explicitly includes this claim. Existing overlap is intentionally over-counted
until that incorporation. Overruns are recorded even when the budget is exhausted;
negative headroom blocks later admission. Pause, expiry or revoked work approval
cannot conceal actual usage or prevent safe terminal accounting.

Settlement changes workspace-Pause's ownership binding, invalidating old inventory;
it never parks or resumes the brain. Both worker and queue still require separate
packet-result/acceptance review before any `complete` or pilot claim. No worktree
is deleted, no task archived and no source committed/pushed/merged by this module.

WSP-04C3b now adds [standard-policy runner coordination](RUNNER-COORDINATION.md).
It releases only the runner after explicit cleanup; this settlement coordinator
still requires complete terminal reconciliation to release repository/slot/token
ownership. It retains runner history and cumulative estimates in the terminal
record without changing historical no-runner receipt shapes.

Next increments retain independently verified destination/resource observations,
trusted Harness runner integration, not-created recovery, separate
acceptance/result coordination, new-generation continuation approval, native
transport, maintenance migration and exact owner Play activation. A separately
authorized real pilot remains required. See [verification](OWNERSHIP-SETTLEMENT-VERIFICATION.md).
