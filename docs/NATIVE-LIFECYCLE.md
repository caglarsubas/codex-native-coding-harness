# WSP-04C2 — native results and correction continuation

Plan saved before implementation, continuing merged PR #24 (`9b76707`).

Extend the internal admission coordinator with durable native-result observations
and a one-shot correction-continuation journal. This is not a native transport,
public Play control, ownership-release migration or live rollout.

## Implementation checklist

- [x] Preserve pending client IDs separately from confirmed host/task identities;
  enforce immutable bindings and platform-wide uniqueness.
- [x] Retain bounded, hash-linked, versioned observations with exact replay and
  optimistic concurrency. Unknown outcomes keep ownership and token reserves.
- [x] Accept safety observations/recovery after Pause or expired authority without
  authorizing further work. Bindings and activity remain caller-supplied evidence,
  not authenticated native attestation or proof of task completion.
- [x] Journal correction-only continuation in the existing confirmed idle task,
  with current run/task authority, fresh preflight/account/usage, an exact retained
  scoped instruction artifact, and additional work/review/handoff reservation.
- [x] Commit a local in-flight marker before shared continuation intent; retain
  both sides on interrupted writes and prohibit blind resends.
- [x] Separate delivery acknowledgment from finished-turn evidence. Count two
  consecutive no-progress corrections once each and block further corrections.
- [x] Verify cross-workspace isolation, freshness, conflicts, races, process exit,
  receipt recovery, Pause, cumulative budgets and legacy bypass fences.

## Boundary

Internal trusted designated-brain methods only. No CLI/HTTP/assistant write route,
native API call, generated native argv, scheduler or public activation. No public
or private Codex API is introduced. All returned receipts are explicitly
non-executable. Native transport and independent destination/resource observations
must be integrated before Play. Do not use this module on live state during a
source upgrade or reinstall the skill to activate it.

This increment supports only correction of an already approved `edit` scope in
the same task. It does not grant acceptance, runner acquisition, merge, archive,
new model/effort/speed settings, a new task or a new run generation. Other operations
still require their own checked coordinator. Phase policy and per-repository
rules cannot be widened by an instruction artifact or result observation.

Creation-result evidence is required before continuation. A pending client ID is
never a task ID. A confirmed ID cannot be replaced or erased by a later unknown
observation. Activity is observed separately from lifecycle/ownership: an idle
task remains owned. Neither a finished turn nor a checkpoint releases repository
claims or proves source, CI, merge, runtime or tenant acceptance.

## Durable protocol

Lock order remains registry -> workspace -> admission. Immutable journal records
live in the admission store with local receipt copies. Request IDs are bound to
one worker and exact content; replay returns historical evidence and cannot reapply
an effect or roll back current state. Changed requests/previous hashes refuse.

Result recording commits the shared observation before its local attachment.
The prior local starting/pending owner remains conservative if attachment fails.
For continuation, first commit a local `starting` marker, then recheck authority
and admission and commit additional held tokens plus a shared one-shot intent.
Any durable local intent prohibits automatic retry, even if shared advancement
never committed. Recovery only attaches committed state; it cannot create a claim,
rewind an intent, resend, release capacity or unpause dispatch.

Continuation receipt states are intent, acknowledged, uncertain and finished.
Acknowledgment is not turn completion. Finishing requires exact confirmed task
identity, explicit acknowledged delivery, fresh idle/turn evidence after the
intent and a progress result. An uncertain send cannot be retried; reconcile its
delivery first. Two consecutive finished no-progress corrections block another
begin. Counts survive replay/restart and are not cleared by activity polling.

Additional correction estimates remain conservatively held until future explicit
settlement/complete usage incorporation. They are never reclaimed on an idle
observation, failed send or Pause. Cached/reasoning subsets retain the existing
accounting semantics. All maintenance enrollment/adoption fences still block new
continuation; observations may retain ownership behind a fence.

An unmatched local continuation intent remains in-flight and requires a future
explicit reconciled-not-sent recovery; neither an absent shared record nor a
timeout proves that sending is safe. Shared ownership release and this recovery
are deliberately not implemented here.

## Internal contract

Construct `NativeLifecycle` from the existing `DispatchAdmission` coordinator.
Construction/read/recovery never initializes policy, allocates a phase budget or
releases an owner. The `native_records` table is created transactionally on the
first explicit observation, not during a source upgrade. Records are bounded to
32 KiB and 1,000 per claim pending explicit archival; requests are at most 16 KiB.

Every write request has an exact `id` and `expectedHash` (null before the first
native observation). The hash is the current journal record, not a run permit.
IDs are scoped to one claim but cannot be reused for different request content or
event types. Native and client IDs are checked against other shared owners and
registered brains; retained bindings cannot be replaced or erased.

| Method | Additional closed request fields |
| --- | --- |
| `observe` | `outcome` (pending/confirmed/uncertain), `hostId`, nullable `threadId` and `clientThreadId`, `activity` (idle/running/unknown), `observedAt`, `evidenceHash` |
| `begin_continuation` | `operation: edit`, `instructionArtifactId`, positive `estimates` for work/review/handoff tokens |
| `delivery` | Exact `continuationHash`, `hostId`, `threadId`, `outcome` (acknowledged/uncertain/finished), `observedAt`, `evidenceHash`, `progress` and `activity` |
| `recover` | Exact retained worker ID only; no new observation or effect request |

Pending and uncertain creation observations require unknown activity. A pending
client cannot be used as a confirmed task. Observations must be newer than the
creation boundary and retained evidence, and within the admission policy's age
limit. Finished delivery requires a prior acknowledgment, explicit idle activity
and boolean progress; other delivery states require unknown activity and null
progress. These fields assert observed facts; they do not authenticate them.

The correction artifact must retain exact bytes (at most 16 KiB), version and
content hash in the same repository. Its contents are never parsed/executed by
this module, and scope correctness remains a designated-brain judgment under the
existing exact contract. No artifact can expand operations or policy.

Receipts separate historical `recordHash`, latest shared `currentHash` and local
`attachedHash`. The returned `nativeCallMade: false` describes this module only;
it does not assert absence of externally created work. Every receipt also says
`executionAuthorized: false`, `ownershipReleased: false`, and identifies the
caller-supplied evidence boundary. The shared claim's native binding, extra held
tokens and local receipt must be reconciled together, never through legacy kernel
bind/block/runner/settlement methods.

New native lifecycle hashes are part of workspace Pause's source binding. A later
observation invalidates an older pause inventory even if the task ID and worker
status stay the same. A finished turn still needs the independent retained
checkpoint/descendant/idle evidence required by workspace Pause.

Only the original current run may start a correction. A new generation cannot
reuse old task approval; explicit reauthorization of an already-owned task is
still future work. Next: independently verified destination/resource evidence,
unresolved-creation recovery, separate result review, new-generation continuation approval,
native transport, then exact owner-facing Play and a separately authorized pilot.

See [verification evidence](NATIVE-LIFECYCLE-VERIFICATION.md). No live installation,
native task, schedule, product scope, credentials or private state was changed.

WSP-04C3a now adds [confirmed-terminal settlement](OWNERSHIP-SETTLEMENT.md) as a
separate internal coordinator. Once its shared settlement commits, native writes
and lifecycle recovery refuse rather than reopening the claim. Use settlement
receipt recovery instead. Pending/uncertain/not-created claims and unresolved
correction sends still cannot release through this native coordinator; no native transport or Play is added.

WSP-04C3b extends the same journal with [standard-policy runner coordination](RUNNER-COORDINATION.md).
An owned runner blocks generic native observations/corrections and settlement;
use the runner-specific process/cleanup observations until its resource is released.
Runner launch markers also bind Pause inventory. After release, correction and
terminal settlement retain runner history and cumulative tokens. Recovery attaches
the exact local runner receipt without releasing shared resources again or
clearing another worker's newer ownership. No commands or automatic retries run.

WSP-04C3c adds [reconciled non-creation closure](CREATION-RECOVERY.md) for explicit
final failed-creation evidence, not a missing-ID inference. It seals the original
attempt with zero task usage and preserves all pending IDs/history. Confirmed
tasks, continuations and runner sends cannot use this path. After closure these
native methods refuse; receipt-only recovery belongs to the outcome coordinator.
