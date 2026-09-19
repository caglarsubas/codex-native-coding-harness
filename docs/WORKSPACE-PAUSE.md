# Workspace safe Pause — WSP-03B1

This increment makes cooperative workspace Pause visible and verifiable. It does
not enable autonomous Play, release ownership, activate a mission or change budgets.

## Implementation plan

- [x] Make Pause workspace the primary workspace control; retain dispatch-only
  controls separately and label brain resume as distinct from Play.
- [x] Bind each new workspace pause to its exact request and retained worker set.
  Fence packet preparation/approval while stopping; prevent early resume from
  discarding an unfinished checkpoint.
- [x] Retain bounded native inventory observations, including descendant tasks,
  with exact native IDs and fresh per-task checkpoint artifacts.
- [x] Expose stop blockers to the dashboard, compact brain inbox and assistant.
  A saved checkpoint and current native inactivity remain separate claims.
- [x] Require the complete evidence set before parking; preserve workers,
  runner ownership, requests and artifacts through retries and restarts.
- [x] Test isolated lifecycle, races, missing/stale evidence, workspace routing,
  browser rendering and regression behavior. Do not touch live workspace state.

The existing designated brain remains the only native coordinator. Supported
native tools supply observations; the helper validates their structure and
bindings, not their independent truth. No background observer or hard kill is added.

## Owner workflow

1. Select a workspace and press **Pause workspace**. This stores the exact intent,
   captures its current worker owners, fences new preparation/approval/dispatch
   and requests a brain notification through the existing opt-in bridge.
2. **Pausing safely** lists missing brain receipt, native inventory, worker or
   descendant checkpoint, runner cleanup, heartbeat or in-flight-control evidence.
   Running tools finish their bounded operation. Stop has no fixed deadline.
3. **Checkpoint saved · activity not confirmed** means the brain has parked the
   retained state. **Paused at checkpoint** additionally requires currently fresh
   worker/descendant/schedule evidence, no controller owner and a fresh native brain
   idle observation after the checkpoint. Reading the page never refreshes evidence.
4. **Resume brain from checkpoint** is available only after parking. It wakes the
   same brain to recover retained state. Worker dispatch stays paused; existing
   workers do not gain permission to continue, and autonomous Play remains absent.
   Pause remains available while a Resume request is pending and supersedes it.

Advanced dispatch-only controls remain distinct: holding new workers does not
stop the brain or checkpoint existing tasks. If delivery is unavailable, open
the existing brain to continue the saved stop; do not submit duplicate intent or
reset owners. Another workspace's controls and state are unaffected.

## Designated brain evidence procedure

Use the existing controller token environment mechanism and explicit routing:

```sh
python3 -m orchestrator.cli --platform /absolute/private/.platform --workspace example brain-stop-observe stop-request-id /absolute/private/pause-evidence.json
python3 -m orchestrator.cli --platform /absolute/private/.platform --workspace example brain-park stop-request-id /absolute/private/brain-checkpoint.json
```

First receive the stop with `process`, reconcile uncertain creation and active
acceptance without retry, and request cooperative task checkpoints. Observe every
retained native worker and descendant through supported native tools, including
review/helper tasks. Save each task's continuation artifact with its registered
repository and exact `references[].session` task ID. The artifact must be observed
after the stop and no later than that task's native idle observation. A common
artifact may reference several tasks if it truly retains each continuation.

Retain the underlying native evidence privately and supply its SHA-256 in
`evidenceHash`. The input is a closed object; this synthetic schema example is not
evidence and must never be submitted for live state:

```json
{
  "workspaceId": "example",
  "commandId": "stop-request-id",
  "observedAt": 1800000030,
  "evidenceHash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "complete": true,
  "includesDescendants": true,
  "brain": {"hostId": "local", "threadId": "brain-task-id"},
  "tasks": [{
    "hostId": "local",
    "threadId": "worker-task-id",
    "workerId": "owned-worker-id",
    "parent": null,
    "status": "idle",
    "observedAt": 1800000029,
    "checkpointArtifactId": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  }]
}
```

Descendants have `workerId: null` and an exact `{hostId, threadId}` parent whose
ancestry resolves to an owned worker or the designated brain. Status is `idle`,
`running` or `unknown`; a missing checkpoint uses null. Partial coverage is
retained for progress, never interpreted as an empty complete inventory. The
brain is not included in `tasks`: it must still finish its current turn after
parking. Input is bounded to 500 tasks / 512,000 UTF-8 bytes.

`brain-stop-observe` returns `documentHash`. Park using this closed shape:

```json
{
  "summary": "Bounded checkpoint summary with recovery instructions",
  "artifactIds": ["cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"],
  "pauseEvidenceHash": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
}
```

The hash must be the **latest returned documentHash**, not the underlying native
evidenceHash. Register 1–8 combined checkpoint artifacts first, with at least one
post-request version. Pause and observe the configured heartbeat through native
tools, retaining all other settings. Unconfigured scheduling is allowed. Recheck
intent and all evidence immediately before parking, release the controller after
the retained receipt, then end the turn. No worker owner is automatically released.

## Safety and recovery

- Inventory, each idle observation and configured heartbeat pause must be after
  the request, not future-dated and no older than 120 seconds. Task evidence cannot
  postdate the inventory. Missing native coverage remains a blocker.
- Captured workers cannot disappear by becoming complete or deleting a ledger row.
  Both old and new task bindings must be retained if a binding changes. Every task
  in an earlier observation must remain in the next report.
- Current worker/runner/processing-control state is hashed with the inventory.
  Changed ownership requires fresh evidence; owned acceptance runners, uncertain
  creation/acceptance and processing worker controls block parking.
- Duplicate observations return their original immutable receipt. New observations
  must advance time, preserve task coverage and point to the previous hash. An
  event failure rolls back the entire write. Restart never erases owners/evidence.
- Only the designated brain controller can submit observations or park. Browser
  and assistant expose status and existing confirmed controls, not evidence writes.
  Resume cannot discard an unfinished workspace checkpoint; a newer Pause can
  supersede queued Resume. Packet preparation and approval stay fenced until resume.

The brain's complete-coverage, parent, host, status and native evidence assertions
remain trusted inputs. The helper checks shape, identity, ancestry, freshness,
retained artifacts and ledger continuity; it does **not** query Codex independently,
authenticate the native evidence hash, terminate processes, enforce provider token
limits or prove that a worker cannot wake externally. Fresh diagnostics are not
execution authority. Saved checkpoint history remains readable after observations
expire, but current inactivity is no longer claimed.

## Compatibility and rollout

New `brain_stop` requests routed through a registered workspace use
`workspace_pause_v1`. Existing legacy stops/checkpoints are not rewritten and keep
their original recovery contract, without a workspace-wide inactivity claim. Once
a registered Pause has occurred, subsequent raw `--state` requests retain that
workspace protocol; switching CLI routing cannot remove it.

Delivery requires the upgraded helper, web assets **and matching source skill
instructions installed for the designated brain**. Merely merging this increment
does not update the running server or installed skill. No live stop, skill install,
heartbeat update, enrollment, ownership adoption or budget change is part of this
source delivery. Native collectors, mission/run activation, phase release and
integrated Play remain subsequent work.

## Local verification

The disposable UI fixture is `tests/manual_pause_fixture.py`; it contains synthetic
native assertions only. It can rehearse Pause, blocked checkpoint, retained
checkpoint and explicit brain Resume in two isolated workspaces. Tests cover
stale/missing/partial evidence, task ancestry, artifact/session binding, completed
and uncertain owners, resume races, retries, rollback and workspace HTTP isolation.
See the accompanying verification report for actual commands and observed results.
