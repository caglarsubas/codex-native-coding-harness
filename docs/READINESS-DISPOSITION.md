# Forward-only canceled-readiness disposition

## What this resolves

An original pre-Play capability turn can end after the owner cancels its native
permission, without the designated brain recording a catalog or error receipt.
PR #163's prospective checkout-local mailbox must not be backfilled onto that
old turn. Nor should the UI keep promising a reply from an observer that ended.

`standard_readiness_disposition_v1` is a **local, unqualified owner disposition**
of that one attempt. It leaves the complete original command JSON, notification,
Cancel decision, observer, missing brain receipt, metadata, mission, usage and
bindings unchanged. A distinct immutable snapshot records the owner review;
it is not a brain receipt, catalog, checkpoint, native effect reconciliation,
cleanup, ownership release, Play approval or pilot acceptance. Current and
historical terminal safety remain unknown.

## Narrow eligibility

Only a registered schema-1, all-standard, paused first-phase project with its
unchanged reviewed phase-delegated mission qualifies. There must be no run,
controller (including its private file), runner, task, packet, decision,
continuation, Brain Stop, handoff or strict enrollment. Exactly one command must
exist: the original queued `standard_catalog_refresh`, without a catalog/error
receipt, retry history, recovery or prospective mailbox.

Require its accepted original owned `turn/start`, exact brain/turn/wake identity,
restricted resume acknowledgement and original binding hash; one **resolved
owner Cancel** correlated by request hash and turn; the saved interrupted turn;
and a closed exact original observer. Cancel claim, resolution and observer
closure timestamps must agree in order. An open/unconfirmed observer, sending
decision, changed native identity or missing record refuses. These saved facts
prove the disposition's context, not present native inactivity or historical
non-execution. The adapter has no native client or current observation authority.

## Exact review, backup and application

Operator-only commands route before any Registry/Ledger writer constructor.
Use the same qualified source for all steps and explicit `--platform` and
`--workspace`; omit `--state`. Private files must be canonical, owner-only,
single-link regular files. Keep them in ignored private state.

1. `readiness-disposition-preview BINDING COMMAND_ID` reads only local metadata.
   Save the returned `request` as a private JSON file. The review binds complete
   original command bytes, mission/review, source, registry and ledger logical
   fingerprints/identities, both native project IDs, checkout, catalog mapping,
   binding bytes and file epoch. It has no timer expiry: scope changes invalidate
   it. Preparing or polling confirms nothing and contacts no host.
2. Separately quiesce every older writer. This command does not stop processes;
   `--writers-stopped` is an operator assertion, not process-exit evidence.
   `readiness-disposition-backup REVIEW DESTINATION --writers-stopped` creates a
   new private, integrity-checked target/registry SQLite backup plus the exact
   binding and review. It verifies all original rows before and after copying.
   It preserves rather than exports or edits any old run or claim.
3. After **exact owner review**, use
   `readiness-disposition-confirm REVIEW --confirm-hash HASH --writers-stopped --backup DESTINATION`.
   Registry-then-ledger locks revalidate the entire scope and backup. A permanent
   exclusive claim precedes the single atomic snapshot insertion. No command,
   metadata, registry row or binding is rewritten. A matching committed receipt
   can be read again after a lost response without reapplication or time renewal.
4. `readiness-disposition-status` only reads. A partial/corrupt/missing claim or
   changed original command stays fenced; it never reapplies an interrupted
   transaction, deletes the claim or reconstructs a receipt. Investigate that
   exact local journal rather than retrying a native effect.

Do not run an older helper against this new protocol. Installation requires a
quiescent boundary and the verified private backup; no mixed-version/downgrade
compatibility is claimed. The core transaction guard validates the immutable
record both before and after every ordinary write. Original-request catalog/error
writes, ID reuse, handoff backfill and notification are permanently refused.

## Prospective continuation, not replay

The dashboard shows **Readiness check ended without a result**, retains raw
`queued` as the original saved status, and separately displays the unqualified
disposition and missing brain receipt. The old attempt no longer counts as a
live receipt wait. Rendering, polling, Help and installation submit nothing.

Only a separately explicit owner request can create a genuinely **new** capability
check with a distinct ID and the new context hash. It uses PR #163's prospective
mailbox on its own original observer. No old handoff, claim, turn, receipt or
authority migrates. Even a current catalog without that distinct new completed
catalog receipt cannot enable Play. Actual native policy/readiness and separate
exact Play confirmation remain mandatory. A prohibition on readiness replay is
not permission to send this new request automatically.

## Delivery boundary

Source and disposable fixtures install/apply nothing on the live pilot, confirm
no owner review, load no brain and send no native turn or recovery. Preserve old
runs, cumulative usage/gaps/expiry, both historical claims and all bindings. Local
test passes, a recorded disposition, a new capability receipt, Play, native worker
results and pilot acceptance remain separate evidence states.
