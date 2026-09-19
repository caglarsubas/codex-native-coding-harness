# Platform enrollment and legacy dispatch fences — WSP-04B1

This increment closes the **upgraded legacy-client bypass** before shared
admission can be enabled. It implements owner-reviewed, maintenance-only
enrollment: a durable journal, per-workspace dispatch fences, retained ownership
and interrupted-enrollment recovery. It does **not** activate a run, enable Play,
grant a budget, or connect the capacity kernel to native task creation.

**Do not enroll a working portfolio as a routine upgrade.** Enrollment deliberately
blocks new dispatch and acceptance acquisition. This version has no unfence
command; reopening requires the later explicit activation/migration protocol.
Use disposable fixtures for qualification unless the owner specifically requests
this maintenance fence and understands that boundary. Installing or merging this
code does not enroll anything. No live enrollment was performed for this release.

## Exact owner workflow

There is no browser/chat enrollment action, automatic migration or new native
notification. The trusted local owner can inspect and explicitly confirm through
the CLI. Use the registry's absolute path; these commands cover **all** registered
workspaces and reject `--workspace`/`--state` combinations.

1. Stop older controller/dashboard processes from making mutations. All mutating
   clients must run code that understands the fence. A Python protocol cannot
   constrain an old binary that ignores it, arbitrary SQL or native tasks outside
   the controller. Do not infer deployed/runtime version from a merge.
2. Pause dispatch and safely release every controller through existing supported
   controls. Enrollment refuses to clear a controller or assume its owner died.
   Existing workers and acceptance processes remain owned; they are not killed
   or declared idle. Plan their supervision while new acceptance is fenced.
3. Generate and inspect the private review document:

   ```sh
   python3 -m orchestrator.cli --platform /absolute/private/.platform platform-enrollment-preview
   ```

   Save the returned JSON privately. It pins registry/database identity, exact
   membership, ledger revisions/state hashes, recorded worker/native identities,
   runner references and the maintenance-only effect. It omits checkout paths,
   controller tokens, prompts and arbitrary observation text. Preview expires
   after five minutes; changed state or membership requires a fresh review.
4. Only for explicit owner authorization of that reviewed fence:

   ```sh
   python3 -m orchestrator.cli --platform /absolute/private/.platform platform-enroll /absolute/private/review.json --id owner-enrollment-id --confirm
   ```

   Confirmation does not approve packets, activate reviewed mission configuration,
   spend an allocation, change pilot/concurrency limits or invoke native tools.
   A request ID cannot be reused for a different review. Retrying identical input
   returns the current receipt, including `prepared` after interruption; it does
   **not** silently replay unfinished staging.

## Durable stages and recovery

The registry journal commits **before** workspace effects. Workspaces are then
fenced separately, in stable ID order:

1. Atomically publish and sync a private `admission-fence.json` in that ledger's
   state directory, without overwriting an existing fence.
2. Commit the matching `meta.admissionBinding` marker and an enrollment event.
   Reject queued/processing worker-dispatch Resume requests as superseded; retain
   other requests and all approval/worker/runner records.
3. After all workspace stages, record `fenced` and current ownership observations
   in the registry journal. This is not an atomic cross-database transaction,
   proof of native inactivity or proof of admission readiness.

The file and SQLite marker are independent fail-closed signals. Either one blocks
new dispatch in updated clients, including direct `--state` callers and runtime
objects opened before enrollment. A surviving sidecar also blocks an older
database snapshot restored in place. Missing, malformed or dangling-link fence
files do not override a surviving marker; an existing malformed or foreign file
does not mean free capacity and is never overwritten by recovery.

On interruption:

```sh
python3 -m orchestrator.cli --platform /absolute/private/.platform platform-enrollment-status
python3 -m orchestrator.cli --platform /absolute/private/.platform platform-enrollment-recover owner-enrollment-id --confirm
```

`prepared` can mean zero, some or all workspace fences are present. Status exposes
the current per-workspace state; no elapsed-time expiry releases a fence. Recovery
requires the same registry/database, workspace membership, brain identities,
paused dispatch and released controllers. It completes matching missing stages
and records new observations. It never resumes dispatch, clears a controller,
releases a runner, deletes a fence or reconstructs native effects by guessing.
Identity drift or a conflicting fence requires separately scoped operator recovery.

Every worker binding and runner record observed at preparation/recovery is retained
in `retainedOwnership`. Repeated observations of the same worker can contain
different status/binding versions; this is an evidence inventory, not a task-count
or token-allocation calculation. A later complete or missing ledger row does not
erase a previously retained owner. Native terminal reconciliation and canonical
resource adoption remain required before future admission can release it.

The append-only `admission_enrollment_events` journal retains the exact preview
and observed ownership records in the existing private registry database. Current
and historical observations are not native observations; unknowns remain unknown.
The admission-capacity database is not created, seeded or populated by enrollment.

## Enforced boundaries

- Updated legacy and registered routes refuse new reservations, native creation
  boundaries, acceptance-runner acquisition, dispatch Resume and repository-map
  reinitialization when either fence signal exists. A queued old Resume is rejected
  again at processing, so restoring an old command cannot reopen dispatch.
- Workspace membership is closed as soon as the journal is prepared; registration
  rechecks this inside its write transaction. A fenced ledger cannot be registered
  into another registry to evade the boundary. Future membership changes require
  a deliberate migration, not a restart or implicit fresh registry.
- Read-only inspection, brain coordination, exact existing packet review, binding
  an already-created/pending task, recording evidence, observed runner release and
  ordinary completion validation remain possible. Ownership and approval limits
  are not relaxed. The brain must restrict native activity to existing safe-stop
  supervision and reconciliation, not new implementation, retries or merges.
- Readiness includes the fence reason and marks proposed launches ineligible.
  The compact brain inbox includes `admission`. The assistant receives only bounded
  fence status/reason; dispatch Resume is unavailable in its catalog. Old signed
  Resume previews still encounter ledger enforcement before queueing or notification.
- Fenced queued work is not a reason for idle polling. Active owners, runner
  supervision and unresolved receipts still are; no schedule is changed here.

These are application-level guarantees for upgraded clients and the registered
scope, not an OS sandbox against the owner, old binaries, copied pre-enrollment
ledgers elsewhere or unmanaged native work. Never delete both fence signals or
edit private tables to make the UI look ready.

## What follows

WSP-04B2 must verify/adopt retained canonical resource identities, actual native
inventory, account/baseline coverage and budget claims; bridge creation/binding/
runner/settlement receipts without cross-database replay. WSP-03B/C then adds exact
owner-bound run activation, packet/phase authority and composite Play/Pause fences.
Model/effort/speed policy and real two-workspace qualification remain separate
roadmap requirements. Reviewed missions must not activate automatically.

## Verification boundary

Disposable tests cover reviewed-state/hash/freshness checks, controller conflicts,
membership races, concurrent confirmation, partial staging, a real child-process
exit after the file fence but before its SQLite marker, retry/recovery, retained
owners, pending bindings, runner release, direct legacy CLI bypass attempts and
authenticated HTTP/assistant Resume rejection before notification. No live Codex
task, heartbeat, runtime process, approval or private state was changed.

Local verification on 2026-09-19 (Python 3.12): **308 Python tests passed**,
including 23 enrollment tests and the authenticated HTTP fence regression.
The mission, workspace, decision and pane JavaScript suites passed; syntax checks
for `web/app.js`, `web/missions.js` and `web/workspaces.js`, the source skill
validator and `git diff --check` also passed. These are disposable local test
results, not CI, merged-source, deployed-runtime or autonomous-pilot acceptance.
