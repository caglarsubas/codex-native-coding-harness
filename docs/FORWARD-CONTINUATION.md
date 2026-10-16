# Forward-only continuation after an uncommitted admission

`standard_forward_continuation_v1` is **new prospective lineage**, never a retry,
completion or receipt repair of `standard_successor_v1`. It applies only to that
exact unchanged, empty, paused target after its two original claims were issued
without a committed admission. It sends no native request and starts no Play.
Source/disposable delivery installs nothing and confirms no live control.

## One exact review, distinct historical and prospective facts

The owner reviews a new, until-scope-changes request. It includes the exact
original attempted request and both matching claim bytes/file epochs, immutable
quarantined source/run/usage/gap/expiry evidence, the empty target's schema/rows
and reviewed mission, both native project identities, repository disjointness,
catalog mapping and unchanged binding. No old admission or disposition approval
confirms this new contract. No timer refresh or renewed old approval is involved.

If the unqualified partial-admission disposition is not yet recorded, this new
review explicitly includes recording it. If it already exists, preserve its
exact file epoch and bytes. Its source hash is historical; only the unchanged
non-source scope may match the newly reviewed context. The new review does not
reinterpret that failure as successful admission, cleanup or safe terminals.
The standalone disposition remains non-executable. This explicit combined
review avoids a redundant disposition confirmation before the lineage review.

Require unchanged original claim routing and an uncommitted schema-v1 target:
no prior run, successor snapshot, native tasks, pending commands/queue/decisions,
continuations, controller/private credential, runner, Brain Stop or strict
enrollment. Missing, corrupt, committed, ambiguous or changed state refuses.
Repeat held-resource disjointness before the new claim. Unknown identity never
means unused capacity. Preserve the source outgoing claim; another target cannot
reuse it. All source repositories stay held.

## Explicit operator preparation and application

Route preview/backup/confirmation through the **source** workspace, status through
the target. These routes use read-only registry/ledger handles, not constructors
that might initialize or migrate state:

```text
forward-continuation-preview PRIVATE_ORIGINAL_ADMISSION_REQUEST
forward-continuation-backup PRIVATE_NEW_REQUEST NEW_PRIVATE_BACKUP --writers-stopped
forward-continuation-confirm PRIVATE_NEW_REQUEST --confirm-hash EXACT_NEW_HASH --writers-stopped --backup VERIFIED_BACKUP
forward-continuation-status
```

Save the preview's request object privately, not its wrapper. The review has no
wall-clock countdown; any pinned scope/source change invalidates it. Quiesce all
writers, verify compatible launchers and retain complete integrity-checked private
SQLite backups plus both old claims, the original request, unchanged binding and
any existing disposition. No backup or writer shutdown is implicit. The explicit
stopped-writers flag is an operator assertion, not native cleanup evidence.

Confirmation revalidates everything under registry-then-target locks. It flushes
a **new** exclusive `standard-forward-continuation.json` intent, retains or records
the unqualified disposition, and commits exactly one new forward snapshot and
prospective metadata pointer. The original `standard-successor.json` and registry
outgoing claim are never deleted, overwritten, reissued or redirected. Their
missing original snapshot/receipt and timestamp are never fabricated. No source
or registry row is changed. The target remains paused with no run or workers.

Schema-v7's existing standard control envelope carries a *different* forward
record kind, explicit `forwardContinuationVersion`, and new lineage hash. It is
not the original marker's record hash. Prior writers reject the partial-disposition
file or original-marker mismatch; no mixed-version safety is promised. Preserve
all original target history rows and schema, apart from the explicitly reviewed
prospective metadata change. Normal future events may advance `sqlite_sequence`;
they cannot remove or rewrite original events. Native/mission/checkout/binding
identity, old source state, both claims and the unqualified disposition are
revalidated at existing writes and effect boundaries. Registry growth is not a
release: current foreign owners still fence effects while local Pause remains.

An interrupted new intent, disposition write or target commit stays blocked.
There is no automatic replay, second claim, rollback deletion or reconstruction.
Only an already complete, exact snapshot can return its original local receipt,
without writes or timestamp renewal. A malformed or missing component blocks
ordinary controls and execution even if another fence was adversarially removed.

## Execution is a later, fresh authority boundary

The new lineage grants **no Play**. The target requires the same separately
signed fresh Play for its unchanged owner-reviewed mission, fresh catalog/usage
checks, exact limits/reserve and normal cooperative fences. It has one new run,
not a replay, extension or usage reset of the source's old run or failed admission.
The old usage is displayed separately, with gaps preserved. New counters begin
as `not_observed`, not verified zero global usage.

Existing schema-v7 loaded-only delivery handles this lineage. It must repeat
exact loaded-idle/project/policy and complete known-empty current tracker reads
on the unchanged reviewed binding. `notLoaded`, unsupported or changing metadata,
unknown policy or terminal coverage refuses before `turn/start`; there is no
`thread/resume`, subscription adoption or recovery fallback. Pause and budget/
expiry guards stay at the original native boundary. Task/inspection/checkpoint
operations use the existing brain/observer path, not a second dispatcher.

Current empty trackers are not historical cleanup or whole-terminal safety.
No native safety assertion, host/binding change, brain reload, Play/recovery replay,
usage reset, source ownership release, expiry extension or pilot acceptance is
included. An unloaded live brain remains blocked under the no-reload constraint.

## Qualification

Disposable tests cover new review/backup requirements, combined and existing
dispositions, full claim epochs, immutable original history, interrupted commits,
missing/corrupt fences, wrong/aliased backups, downgrade, old-approval refusal,
one fresh Play, loaded-only delivery, unknown trackers, Pause/expiry races and a
new task-to-checkpoint journey with original source usage preserved. The UI labels
forward lineage separately and rendering submits nothing. Full Python/JavaScript
qualification is local; no Actions or paid service is added. Live source upgrade,
exact owner application and any fresh Play remain separate rollout steps.
