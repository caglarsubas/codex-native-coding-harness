# Device-only review with a consumed ended recovery

Source-only operator adapter. Not installation, live identity repair, native
runtime repair, historical cleanup, terminal closeout or pilot acceptance.

A reboot can change the filesystem device number while the ledger inode, brain
and every saved record remain unchanged. Ordinary identity repair correctly
refuses pending requests. The pending-Play exception also refuses a stopping run
with an already consumed Pause receipt recovery. Requiring those requests to
settle before restoring read access creates a deadlock.

This **separate exact review** repairs only registry device metadata, while
preserving the unresolved requests. It does not make any request received or safe.
Default and pending-Play recovery gates are unchanged.

## Explicit operator interface

```sh
python3 -m orchestrator.cli --platform PRIVATE_REGISTRY --workspace EXACT_WORKSPACE workspace-identity-preview RETAINED_LEDGER_BACKUP --preserve-ended-recovery PRIVATE_ORIGINAL_BINDING
python3 -m orchestrator.cli --platform PRIVATE_REGISTRY --workspace EXACT_WORKSPACE workspace-identity-recover PRIVATE_PREVIEW --confirm-hash EXACT_DOCUMENT_HASH --confirm --writers-stopped
```

The preview flag takes the preserved **original Pause/recovery binding**, not a
current or proposed replacement endpoint. It is mutually exclusive with
`--preserve-pending-play`. No ordinary read, model response, old review or source
merge selects the mode. Confirmation needs the exact displayed hash and explicit
owner approval; installation and vague assent cannot confirm it.

Use a separately retained, owner-only canonical reference whose full SQLite
schema and logical contents match the unchanged ledger. A verified copy of an
earlier retained backup may be used with its original provenance preserved; a
new current-state copy cannot be presented as earlier evidence. This remains
operator-supplied provenance, not authenticated native attestation.

The private preview has no countdown. Revision, usage, expiry, command, database,
catalog, reference or original-binding changes invalidate it. It renews no native
observation. CLI JSON preserves integer identity epochs losslessly; no browser
or model inference is used to transform them.

## Narrow retained eligibility

- Schema-4 cooperative standard run, paused and stopping, with no controller,
  private controller credential, runner, task, queue, merge or managed/enrolled
  ownership. Strict Harness, Brain Stop/handoff, decisions awaiting receipt and
  other pending/uncertain controls remain refused.
- Exact original accepted owned Play, accepted completed Pause and consumed
  completed Pause receipt recovery. The recovery remains queued without its
  ledger receipt/checkpoint. Preserve its original permit and all request hashes.
  Pause/recovery keep closed observers and their exact restricted resume profiles.
  Play may retain its unconfirmed observer; it is never backfilled as closed.
- No recorded native approval intent or descendant event. A malformed empty
  task/merge/approval value is not an empty ownership list. Absence of recorded
  native events does not prove historical effect absence.
- Only device-number drift, with unchanged ledger inode and brain, matching full
  reference data/schema and unchanged registry/project mapping. No ledger
  replacement, relocation, schema downgrade or guessed project match.
- One preserved binding naming the same brain/workspace/canonical registered
  checkout and both explicit native project IDs. The app-server project must
  match the original recovery observation; the app catalog must retain the exact
  local project/location mapping. Workspace-write/on-request and Code Mode
  disabled remain exact. Names and checkout similarity substitute for neither ID.

The original binding is read as private immutable bytes only. Its full hash must
match the original Pause/recovery, and its file epoch is pinned. No executable,
socket, host PID, native thread, process tree or terminal is inspected. The reader
does not connect even when the old endpoint exists. Saved completed-turn claims
are labelled `retained_only`, not current native evidence. Current and historical
terminal coverage, and historical effect outcome, remain **unknown**.

## Transaction and replay

The new `workspace_device_ended_recovery_v1` document pins the unchanged complete
run, all three command/turn/binding hashes, original binding file/mapping, full
registry/ledger/reference checksums and exact catalog/location records.

Confirmation reuses registry-before-ledger locking, the exclusive dashboard lock,
stopped-writer acknowledgment, fresh private SQLite backups and final unchanged
scope check. It journals a registry-only receipt and changes only the selected
workspace device pin and corresponding unchanged project pin. The local ledger
transaction makes no writes and is rolled back; its lock lasts through registry
commit. Failed backup/drift retains partial backups and rolls back the registry.

Every original command, missing receipt, observer, consumed permit, checkpoint,
usage/gap, expiry, controller/resource state and evidence record remains intact.
No native receipt, effect settlement, ownership release, safe checkpoint, clock
extension or phase authority follows. The report's corresponding boundary flags
are false. Historical receipt replay validates its immutable record and returns
only that receipt; it never repins a later device or migrates a native claim.

The already accepted notifications cannot be resent after device repair. The
phase stays stopping and unqualified. Native runtime launch/binding needs its
own review; historical inspection/cleanup and terminal closeout keep all existing
requirements. Repairing read access cannot supply missing historical facts.

## Qualification and rollout

The source preview was explicitly checked against the unchanged retained pilot,
using a verified copy of its earlier backup and original recovery binding. Full
before/after record/database checks matched revision 218 and usage 719,893. The
preview retained unknown current/historical terminals and effects, with zero
native calls, control submissions or applied device changes. Private evidence,
native IDs and review hashes are not committed. This qualifies local preview
construction, not a live confirmation, runtime or pilot.

Disposable tests cover exact confirmation/mode isolation, full ledger and request
preservation, both IDs, private file epochs, stale usage/expiry/revision/reference,
unknown/open/received recovery, approval/descendant/ownership/strict fences,
dashboard locking, failed backup/rollback, delayed reviews, concurrent receipt
retention, immutable replay and continued notification/closeout fences. No native
transport is available on this route. Run full local Python/JavaScript, syntax,
compilation and diff checks; add no Actions or paid service.

Final local verification passed 2,376 Python tests (one skipped), including the
21 new ended-recovery identity tests, all 35 JavaScript suites, 31 web-script
syntax checks, Python compilation and diff checks. Remote workflow configuration
was inspected read-only: zero workflows. Missing hosted CI is not passing CI.
No rendered/live dashboard qualification is claimed for this CLI-only increment.

Source merge, installation and exact live owner review remain separate. Quiesce
older writers and back up private state before installation. This source delivery
applies no review, starts/rebinds no host and does not continue native development.
