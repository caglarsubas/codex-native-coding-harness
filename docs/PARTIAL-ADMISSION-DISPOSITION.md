# Partial successor admission — unqualified disposition only

This operator-only contract records a failed, uncommitted admission without
completing it. Source delivery installs nothing, restarts nothing and applies no
live disposition. Preparation is read-only. No native transport is imported.

## Registry validation repair

The original successor validator treated `platform.sqlite3` as a runtime record
through `host_lifecycle.private_file`, whose 64 KiB JSON/manifest bound is correct
for its callers but not for SQLite databases. A valid registry can grow beyond
that bound through ordinary project/profile history. Preview passed, exclusive
claims were flushed, then transaction-exit validation refused the larger file,
rolling back SQLite while correctly preserving both filesystem claims.

`workspaces.private_database` now checks canonical paths and ancestors, private
owner permissions, regular-file/no-hardlink identity, the fixed SQLite header,
and replacement races without reading the entire database or imposing a small
record limit. Successor preparation and retained-lineage validation use that
same helper. Runtime-record limits remain unchanged. This does not repair,
checkpoint, truncate or initialize a database. Invalid identities refuse before
either admission claim is written. Changes to this validator invalidate future
successor reviews through their source hash; old issued claims are not replayed.

## What the disposition can record

`partial_admission_disposition_v1` accepts only both matching original claims,
the exact original private request anchored by its claim review hash, and an
unchanged schema-v1 empty paused target. There must be no committed successor
snapshot/pointer/run, controller or private credential, runner, workers, commands,
queue, decisions, continuations, Brain Stop or strict enrollment. The exact
owner-reviewed target mission, both project identities, catalog mapping, binding
bytes/file epoch, standalone repository proofs and all original database inodes
must still match. Missing evidence, a changed target or any committed/ambiguous
admission refuses. An old source hash is historical data anchored by the original
claims, not permission to reuse its approval for this new contract.

Revalidate the source's original quarantine, run, usage/high-water, gaps, expiry,
held identities and immutable history. Pin bounded complete schema/row
fingerprints of source, target and registry, plus both immutable claim-file
epochs. The review has no timer: only scope changes invalidate it. It inspects
saved binding/catalog bytes, never an old or current native endpoint, loaded
policy, terminal list or process cleanup.

## Explicit operator steps

Use the compatible source, exact platform, and **source** workspace for preview,
backup and confirmation. Status selects the target workspace instead.

```text
partial-admission-preview PRIVATE_ORIGINAL_SUCCESSOR_REQUEST
partial-admission-backup PRIVATE_DISPOSITION_REQUEST NEW_PRIVATE_BACKUP --writers-stopped
partial-admission-confirm PRIVATE_DISPOSITION_REQUEST --confirm-hash EXACT_NEW_HASH --writers-stopped --backup VERIFIED_PRIVATE_BACKUP
partial-admission-status
```

Save the preview's **request object**, not its wrapper, privately. These CLI
routes use read-only registry/ledger handles; preview/status do not instantiate
writers. Before separately approved confirmation, quiesce all older writers and
verify compatible launchers. `--writers-stopped` is an explicit operator assertion,
not process attestation or a mechanism that stops processes. The backup command
requires it separately. It retains complete integrity-checked SQLite backups,
both claims, original request and unchanged binding, with exact schema/row and
byte agreement. Existing directories, aliases, missing/changed backup data or
request drift refuse. No backup is implicit in preview or confirmation.

Confirmation revalidates under registry-then-target locks and exclusively fsyncs
`standard-partial-admission-disposition.json`. It writes **no database row** and
does not alter either original claim. The outcome is
`partial_admission_disposed_unqualified`, not admitted or successfully closed.
There is no reconstructed missing receipt or original recording time. An exact
receipt reread preserves its original time and makes no write. A partial/corrupt
new file stays fenced: no retry, deletion, overwrite or automatic repair exists.

Normal writes and Play remain blocked by the original partial marker and the new
disposition fence independently. UI/status report the unqualified failure or an
unavailable/corrupt record, never available Play. Keep the existing source hold
and outgoing claim; no new target or successor is implicitly authorized. Older
helpers do not validate the new record, so rollout still requires quiesced
writers and verified private backups; no mixed-version safety is promised.

## Boundaries and qualification

No admission retry, ownership/resource release, native connection/load/turn,
brain reload, host/binding change, Play/recovery replay, usage reset, expiry
extension, cleanup assertion or pilot acceptance follows. Current and historical
terminal safety remain unknown. Recording a failed admission does not qualify
its target to execute or solve unrelated readiness/catalog/usage gaps.

Disposable tests cover grown registries, unchanged small-record bounds, path and
permission/alias/replacement checks, exact review and backup requirements,
original claim/scope/mission/source/usage drift, committed snapshots, interrupted
disposition, corrupted status, receipt rereads, read-only CLI routing and retained
fences. Full Python/JavaScript checks remain local; no Actions or paid service is
added. A live preview is preparation only, not installation or application.
