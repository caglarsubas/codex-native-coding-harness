# WSP-04C3b — shared runner coordination

Plan saved before implementation, continuing merged PR #26 (`9f5aa46`).

Implement internal runner reservation, one-shot launch-intent recording, process
observations and explicit cleanup release for an already confirmed worker. No
commands, native messages or acceptance processes run in this module.

## Checklist

- [x] Reserve one allocation-pinned runner after current `test` authority,
  preflight, native idle, retained instruction/execution binding and fresh budget
  checks; retain additional work/review/handoff tokens without another task slot.
- [x] Persist a local launch marker before shared launch intent; recheck gates
  between commits. Either marker blocks retries, corrections and settlement.
- [x] Retain unknown/running/exited process observations without timeout release
  or treating worker prose as independent evidence.
- [x] Release only the exact runner after fresh process-tree exit, cleanup and
  task-idle evidence, or cancel an unlaunched reservation. Repository ownership
  and held tokens remain until separate terminal settlement.
- [x] Recover shared receipts after crashes without another reservation, launch
  or release; preserve Pause, maintenance fences and newer owners.
- [x] Verify two-workspace contention, authority/budget drift, uncertain outcomes,
  process termination, evidence integrity, Pause and all regression suites.

## Deliberate scope

Standard-policy repositories only in this increment. Harness acceptance remains
blocked until its trusted external launcher, OS isolation, packet-specific attempt
budget and evidence adapter are integrated. A hash match or `test` declaration
cannot substitute for those constraints. Do not execute product acceptance here.

Only one runner reservation/attempt per worker is supported. Repeated acceptance
runs need a later explicit bounded retry contract; changing a request ID, process
identity or run generation must not reset attempts. An unlaunched cancellation
does not replenish this allowance. No process kill, blind resend or runner lease
expiry is provided.

All external activity/cleanup observations are trusted coordinator assertions,
not independently authenticated native/operator evidence. This internal source
increment has no CLI/HTTP/assistant write route, scheduler, transport, native argv,
public Play or live migration. No live ledger, dashboard process, installed skill,
schedule, credentials, inference service or product repository changes.

## Internal contract

Construct `RunnerCoordination` from an existing `DispatchAdmission`. Every call
requires the selected workspace's current designated-brain controller token and
exact worker ID. Constructor and reads do not initialize policy or allocations.
The existing shared native journal is extended; there is no separate runner
database or second owner of lifecycle history. Requests are closed, finite JSON
of at most 16,000 UTF-8 bytes, always including `id` and `expectedHash` (latest
attached native journal hash). Receipts are non-executable.

| Method | Additional request fields |
| --- | --- |
| `acquire` | `runnerKey`, `executionHash`, `instructionArtifactId`, `estimates`, `observation` |
| `begin` | `runnerKey`, `reservationId`, `observation` |
| `observe_process` | `runnerKey`, `reservationId`, exact `hostId`/`threadId`, `outcome`, `processIdentityHash`, `exitCode`, `processTreeExited`, `observedAt`, `evidenceHash` |
| `release` | `runnerKey`, `reservationId`, `outcome`, `observedAt`, `evidenceHash`, `nativeEvidenceHash`, true `nativeIdle`, `runnerIdle`, `cleanupObserved`, `processesExited`, `complete` |

`observation` contains `state: idle`, true `complete` and `cleanupObserved`,
`observedAt` and `evidenceHash`. It is a fresh external observation of the runner,
not a database query for its owner. `runnerKey` is an allocation-pinned canonical
`runner:<sha256>` identity. Its actual host identity must be independently
verified by a future trusted adapter; a correctly shaped hash is not proof.

`executionHash` binds the approved seed's exact execution contract. The retained
instruction artifact must be at most 16,000 bytes, have unchanged bytes, matching
ID/version/hash and the same repository. Artifact text stays inert; no shell,
argv, model message or execution approval is derived from its contents. The
future adapter must independently enforce the approved execution contract.

Each estimate (`workTokens`, `reviewTokens`, `handoffTokens`) is a positive integer.
Reservation increases the same claim's cumulative extra-token hold but does not
open a new task slot. The legacy journal field `reservedTokens` / claim field
`continuationReservedTokens` now includes both correction and runner overhead.
Release never refunds these estimates; full final actual usage is reconciled by
the separate terminal settlement coordinator. Attempt/task counts never reset.

Reservation and launch both recheck the current exact `test` approval, mission/run
generation, phase allocation fingerprint, preflight, account/phase budget,
checkpoint reserve, global/workspace/local capacity and immutable dispatch seed.
Pending checkpoint/archive controls, unfinished corrections, two no-progress
corrections, stale native idle, held queues and maintenance fences refuse new work.
A task approved only for `edit` cannot reserve acceptance capacity.

## State transitions and ownership

`reserved` -> `launch_intent` -> `uncertain` / `running` -> `exited` -> `released`.
A fresh exact exit observation can also reconcile `launch_intent` or `uncertain`
directly to `exited`. A reservation can become `released` with outcome `unlaunched`
only if no local or shared launch intent exists. Cancellation consumes the single
reservation allowance. No transition itself executes or stops a process.

The launch is journaled local-first. Its immutable local marker is committed
before shared advancement; both phases recheck authority, budget and evidence.
The second phase also verifies the unchanged local worker/marker bytes and owner.
Any local-only marker remains `runner_launch_pending` and blocks retries,
corrections, cancellation and terminal settlement. Receipt recovery does not
erase this ambiguity. Resolving a local-only launch needs a later explicit
reconciliation contract; there is no automatic retry or guessed not-launched path.

Process observations must identify the exact native task and retained reservation.
`uncertain` can initially have a null process identity. `running` and `exited`
require an exact identity hash; once known it cannot change or disappear. Only
`exited` accepts an integer exit code and true `processTreeExited`. A nonzero exit
is retained truth, not a failed journal operation. Exit is not cleanup, a passing
acceptance run or packet completion.

Every new observation must be fresh, non-future and later than the retained
journal/launch/evidence. Cleanup requires all flags true and the exact exited
process (or unlaunched reservation), with a fresh task-idle evidence hash. The
coordinator validates consistency, not the authenticity/completeness of these
external assertions. A future native/operator adapter must independently verify
the full process tree, runner cleanup and native inactivity before supplying them.

Local worker states are `awaiting_acceptance` while reserved and `accepting` from
launch through exit; both retain runner ownership. Release returns the worker to
`running` as an ownership state with last-observed idle activity, not a claim of
active execution. Repository ownership and tokens remain held. A later correction
or terminal settlement is possible under its own gates; another runner attempt
is not. No packet, pilot, CI, source, merge, runtime or tenant acceptance axis is
promoted by these records.

## Transactions, Pause and recovery

Lock order remains registry -> workspace -> admission. Reservation, runner-key
changes, cumulative budget holds and native journal append commit together in
the shared store; the local worker/runner receipt attaches afterward. A rollback
before shared commit changes none of those shared facts. A crash after shared
commit leaves a conservative local owner/marker until `recover(token, workerId)`
attaches the latest hash-verified journal receipt.

Exact request replay returns the historical record hash and current state without
repeating an effect or refreshing evidence. Changed content under the same ID
refuses. Shared release removes only that claim's runner key; recovery never
deletes shared resources. Another workspace can therefore acquire after the
release commit without an old receipt removing its new ownership. Attaching a
historical released-runner record also preserves another local worker's runner.

Pause/expired work authority do not suppress safety observations or cleanup.
Maintenance fences allow observations and receipt recovery, but block new
ownership changes including cleanup release. Replay of an already committed
release is receipt-only and may cross a later fence. None of these calls resumes
the brain, clears a fence or changes its schedule. Runner journal hashes and local
launch markers bind Pause inventory; in-flight/owned runners remain blockers.

Receipts keep `executionAuthorized: false`, `nativeCallMade: false` and
`ownershipReleased: false` (the whole claim still belongs to the worker).
`runnerStatus` and `runnerResourceReleased` describe only the runner's journal
and resource-key accounting. No independent native/host attestation is implied.

See [verification](RUNNER-COORDINATION-VERIFICATION.md). WSP-04C3c separately adds
[non-creation recovery](CREATION-RECOVERY.md), which cannot settle any runner send.
Next gates remain independent result review, trusted host/native adapters,
new-generation continuation approval, migration and exact owner Play activation.
