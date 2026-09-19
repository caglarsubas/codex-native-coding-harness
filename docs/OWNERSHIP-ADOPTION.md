# Retained ownership adoption — WSP-04B2

Implemented scope: import the enrolled portfolio's retained worker and runner
identities into shared admission as **quarantined ownership**, not authorized
work. Do not activate missions, create native tasks, seed allocations, estimate
missing usage as zero, or remove enrollment fences.

## Scope and acceptance

- [x] Exact owner preview binds enrollment, all workspace observations, historical
  owner versions, explicit resource mappings and an immutable capacity policy.
- [x] Group historical versions by workspace/worker while preserving every
  version, native ID and pending client ID. A runner-only record is retained even
  when its worker record is missing. Conflicts and unknown mappings remain visible.
- [x] Commit a registry intent before a durable platform fence and atomic kernel
  import; recover by exact receipt after interruption, without replaying effects.
- [x] Reject new allocations, reservations, creation boundaries and runner
  acquisition under either platform fence signal, including cached kernel objects.
- [x] Keep imported ownership outside phase budgets until native inventory,
  account identity and usage baselines are independently reconciled. No zero-cost
  or free-capacity inference, even for an empty recorded legacy inventory.
- [x] Test stale/tampered reviews, identity drift, duplicate confirmation,
  conflicting owners, partial writes, hard process exits and CLI boundaries.

No live migration or runtime restart is part of this coding increment. Source,
local test, merge, installed runtime and live native acceptance remain separate.

## Owner workflow

**Maintenance only, no unfence operation.** Do not use this as a routine upgrade,
onboarding step or a way to make Play ready. All mutating clients must understand
the fences. Old binaries, copied private databases and unmanaged native tasks
are outside these application-level guarantees.

1. Complete the explicit [enrollment workflow](ENROLLMENT.md). All registered
   workspaces must remain paused with their controllers released. Keep both
   enrollment fence signals. Existing owners are not stopped or declared idle.
2. Prepare a private configuration containing an explicit immutable capacity
   policy and any operator-reviewed repository/runner mappings. The numeric
   values below are a **fixture example**, not a chosen live policy:

   ```json
   {
     "policy": {
       "maxParallelTasks": 2,
       "maxObservationAgeSeconds": 60,
       "minAccountRemainingPercent": 10
     },
     "repositories": [],
     "runners": []
   }
   ```

   Empty mapping arrays retain unknown ownership without inventing resource keys.
   A repository mapping contains `bindingHash` (from retained worker ownership),
   sorted unique `keys` (1–4 canonical repository keys) and an `evidenceHash`.
   A runner mapping contains `recordHash` (from retained runner ownership), one
   canonical `key` and an `evidenceHash`. Hash fields require SHA-256 hex strings.
   Unreferenced or duplicate mappings are refused. No local path, origin URL,
   secret, command or arbitrary observation text is accepted in these fields.

   Mappings are **owner assertions bound to evidence**, not independently verified
   facts. The read-only `platform-resources` audit can assist review, but its
   literal Git origin/common-directory observations do not prove host aliases,
   operator runner identity or native occupancy. Adoption never upgrades a
   supplied evidence hash into a verified native inventory or usage baseline.
3. Generate and inspect the exact private review document:

   ```sh
   python3 -m orchestrator.cli --platform /absolute/private/.platform platform-adoption-preview /absolute/private/configuration.json
   ```

   Save the returned JSON privately. The five-minute preview pins enrollment and
   registry identities, membership, current ledger state, historical owner
   versions, configuration and the existing kernel fingerprint (if any). Preview
   is read-only and does not create the kernel, import ownership or run Git/native
   tools. A changed source requires a new review.
4. Only for explicit owner authorization of this maintenance import:

   ```sh
   python3 -m orchestrator.cli --platform /absolute/private/.platform platform-adopt /absolute/private/review.json --id exact-adoption-id --confirm
   ```

   This is platform-wide; omit `--workspace` and `--state`. It requires an absent
   kernel or an empty one with the exact policy. Existing allocations, regular
   claims or resources require a separate migration; they are never overwritten.
   There is no HTTP/chat adoption route, native notification, policy escalation,
   automatic live import or mission activation.

## Ownership representation

The union of enrollment history and current owners is imported. Historical
versions are grouped by **enrollment + workspace + worker ID**, retaining every
repository-binding hash, worker status, native binding and pending client ID.
A later complete/missing worker row cannot erase retained ownership. Runner-only
records retain a conservative slot and an explicit missing-worker issue.

`legacy_claims` is a quarantined inventory in the shared admission database;
it is not an executable phase allocation. `retainedSlots` counts logical ledger
owners, not independently observed running native tasks. Multiple owners of the
same repository/runner or native task are all retained and conflicts are exposed.
Historical versions of one owner do not create extra slots. Missing host/task
IDs remain unresolved; a pending client ID is never treated as a native task ID.

Quarantined owners have `usageKnown: false`; they have no guessed estimate, zero
usage settlement or approved token budget. Even an empty recorded inventory
leaves new admission blocked because unmanaged work, actual native inventory,
account identity and token coverage have not yet been independently reconciled.
Account percentages are never converted into tokens or money here.

## Durable ordering and recovery

1. Commit the exact registry intent and review document (`prepared`).
2. Publish a durable private `adoption-fence.json` without overwrite.
3. Create or inspect the private kernel database, then durably pin its device/
   inode and the exact import hash in `adoption-kernel.json` **before** importing.
4. In one kernel transaction, initialize the exact policy if absent and import
   all quarantined claims, metadata binding and event, or roll back all of them.
5. Release workspace locks before reacquiring the registry lock; record the exact
   kernel identity and import receipt as `quarantined`.

The databases are not one atomic transaction. A hard process exit after file
creation, during the kernel transaction or after kernel commit can leave a
`prepared` registry receipt. Retrying the same submission reads its receipt only;
it never blindly replays staging. Recover explicitly:

```sh
python3 -m orchestrator.cli --platform /absolute/private/.platform platform-adoption-status
python3 -m orchestrator.cli --platform /absolute/private/.platform platform-adoption-recover exact-adoption-id --confirm
```

Recovery requires unchanged reviewed ownership/state, matching registry,
membership and pinned kernel identity, paused dispatch and released controllers.
It can initialize an owned empty file after rollback or recognize an exact
already-committed import. Changed ownership requires separately reviewed migration;
recovery cannot silently revise mappings or discard newly discovered owners.
Conflicting files, imported rows or identities are retained and refused, not
overwritten. Status labels the receipt historical; it does not refresh native
activity or claim current runtime acceptance.
`reviewedInventory` exposes the historical grouped claims, resource/native
conflicts and mapping issues for inspection; it is not a fresh kernel/native poll.

Either platform sidecar or the kernel metadata marker blocks new allocations,
reservations (including duplicate reserve calls), creation boundaries and runner
acquisition in updated clients, including objects opened before import. Existing
regular-claim reconciliation, observed runner release and settlement remain
possible if a fence interrupts a pre-existing kernel operation. Imported legacy
claims have no release/settlement API in this increment. Age, owner completion,
brain restart and observation updates cannot remove the fence or reset budgets.

## Remaining integration gates

This delivers ownership import and cross-database receipt recovery, **not all of
WSP-04 or autonomous Play**. Follow-up [WSP-04B3](ADMISSION-RECONCILIATION.md)
validates externally supplied identity, quiescence, runner, mapping and usage
assertions and retains versioned reviews/baselines. It does not independently
collect native observations or release imported ownership. Trusted observation
collection, exact authorized run/phase baselines and native-operation receipt
bridges remain required. Reviewed
mission configuration must not activate on merge, upgrade, enrollment or adoption.
New effect/continuation boundaries must recheck Pause, revocation, checkpoints,
scope, model/effort policy and budget headroom before native work is possible.

## Verification

Tests use disposable two-workspace ledgers and synthetic identities/mappings.
They cover malformed/stale reviews, pending/native conflicts, changed ownership,
unknown mappings, orphaned runners, empty inventory, cached kernel objects,
independent fence signals, rollback, hard child-process exits inside and after
the import transaction, pinned-inode recovery, idempotence and concurrent calls.
No live private state, native task, heartbeat, installed skill or running dashboard
was changed. Local checks are not CI, deployed-runtime or real-pilot acceptance.

Local verification on 2026-09-19 (Python 3.12): **338 Python tests passed**,
including 30 ownership-adoption tests. All four JavaScript regression suites
(mission, workspace, decision and panes), syntax checks for `web/app.js`,
`web/missions.js` and `web/workspaces.js`, and `git diff --check` passed.
