# Same-project continuation after a recorded preflight refusal

This is a distinct, bounded successor to the original version-2 planning attempt,
not another pilot project, host, binding or renamed retry. It preserves the
original request and its `incomplete_unknown` result. Neither missing markers nor
an ended process proves native non-execution or terminal cleanup.

## Lifecycle and invariants

The operation separates immutable history, diagnostic observation, original
foreground connection ownership, native subscription, usage collection, turn
start, explicit new receipt, proposal and connection closure. They are not one
generic "running" flag. A host process remaining alive is not a loaded brain.

Only an exact original version-2 failure with the recorded
`Already-loaded idle brain required; never reload` refusal is eligible for a
successor review. Require the original complete local disposition; identical
brain, dual project IDs, checkout, original/candidate binding bytes/epochs,
package/interpreter, source pins and accounting configuration; the complete
closed predecessor inventory; its retained cumulative usage; and no subscription,
turn, receipt, permission, stop, unexpected or partial records.

New senders retain a typed, pinned positive `metadata_preflight` stage and closed
connection record. Historical PR-176 senders lack that instrumentation. The only
legacy compatibility case additionally requires their complete, unchanged,
source-qualified original Python implementation. Its known hash is a compiled
allowlist, not an uploaded assertion. Read/hash the frozen source; never execute
it. Correlate its exact failure/outcome and canonical request/usage/mailbox pins.
An arbitrary failure text or absence of a claim is insufficient on its own.
This identifies a local refusal lineage. It does not relabel the predecessor's
unknown native outcome as safe or supply historical cleanup evidence.

The new version-3 planning review preserves the parent's scope and token ceiling.
Its canonical successor journal and mailbox are keyed to the original database
identity and Play command, independent of source versions, review IDs or paths.
Only one successor is supported; successors cannot create successors. The original
claim is never rearmed, migrated, removed or changed. The canonical original
continuous-owner slot also fences conflicting/partial owners.

## Diagnose before asking for execution authority

Preparation, backup and status are file-only. The explicit `inspect` operation
opens only a bounded read-only diagnostic connection to the exact reviewed
candidate. It repeats project/brain/latest-original-turn observations. Loaded
idle requires actual restricted native policy and a complete empty **current**
tracker; unloaded means unknown policy and terminals, not zero. Unsupported,
active, permission-wait, changing or unavailable observations refuse.

Diagnostics cannot subscribe, load, start, answer, collect usage or consume the
successor's execution claim. They report actual observation time and always say
`executionAuthorized:false`. Closing a diagnostic is not ownership handoff, and
its old loaded-idle observation never substitutes for fresh send-boundary checks.
There is no automatic polling, keepalive or reconnect loop.

If the brain is unloaded, the honest result is
`brain_not_loaded_no_reload_authorized`. Do not ask for a futile execution
confirmation or create v4. No no-reload protocol can restore an unloaded brain.
An actual permitted loaded runtime remains an independent prerequisite.

The separate [post-disposition maintenance control](POST-DISPOSITION-MAINTENANCE-LOAD.md)
implements the owner's new narrow one-load exception on the same existing host.
It cannot rearm an earlier load, start a model turn, keep an owning planning
connection or extend the original phase. A claimed maintenance attempt fences
competing old-phase planning. An expired successor does not become eligible
because a maintenance load succeeded.

## One combined, scope-bound owner review

One new exact confirmation covers the subscription, one new actual usage
collection and one new inert receipt/proposal turn. It is valid until scope
changes, not a short approval timer. It does not approve Play, recovery, Resume,
workers or source edits. Original Play/inspection/planning approvals do not
confirm this new review. Source qualification confirms nothing live.

After quiescing writers and verifying private backups, claim the original owner
slot before opening one foreground connection. Repeat exact current native
identity/latest-turn/policy/tracker checks and claim before the one atomic
already-loaded-only subscription. Pass that same process-local connection into
the planning consumer. No connection closes between subscription, collection and
turn start; no second review wait or second subscription is inserted.

Only after ownership succeeds does the new consumer claim its permanent journal
and collect actual cumulative usage once. Freshness remains under 120 seconds at
the send boundary. Validate all vectors/calls/sample times against both the old
ledger baseline and the predecessor's later actual observation. Neither can be
refunded or retimestamped. Original budget, reserve and expiry remain unchanged.

Claims precede native effects. Stop, source/binding/parent drift, expiry, gaps,
lost acknowledgement, native permission requests and connection loss fail closed.
Never respond/cancel/reload/reconnect/retry. A consumed or partial owner remains
consumed even when no planning turn was reached. Status is file-only and missing
closure stays unknown. Native completion alone is not a receipt or proposal.

Current empty trackers do not prove historical cleanup. The new result is an
inert planning result, not resumed development, worker completion, phase success,
ownership release, terminal safety or pilot acceptance. The old run, usage/gaps,
missing receipts, captured effects, claims, holds, bindings and expiry stay intact.

## Operator interface

```text
python3 -B -m orchestrator.same_project_lifecycle --platform PLATFORM --workspace WORKSPACE prepare ORIGINAL_PLANNING_REVIEW [--legacy-source EXACT_FROZEN_SOURCE]
python3 -B -m orchestrator.same_project_lifecycle --platform PLATFORM --workspace WORKSPACE inspect SUCCESSOR_REVIEW
python3 -B -m orchestrator.same_project_lifecycle --platform PLATFORM --workspace WORKSPACE backup SUCCESSOR_REVIEW NEW_PRIVATE_BACKUP --writers-stopped
python3 -B -m orchestrator.same_project_lifecycle --platform PLATFORM --workspace WORKSPACE confirm SUCCESSOR_REVIEW --confirm-hash EXACT_NEW_HASH --writers-stopped --backup EXACT_BACKUP
python3 -B -m orchestrator.same_project_lifecycle --platform PLATFORM --workspace WORKSPACE status SUCCESSOR_REVIEW
python3 -B -m orchestrator.same_project_lifecycle --platform PLATFORM --workspace WORKSPACE stop SUCCESSOR_REVIEW --confirm-hash EXACT_NEW_HASH
```

Save the closed `request`, not its preview wrapper. Preserve the exact frozen
source and all predecessor journals. Backup includes their complete bounded file
inventory along with the original registry/ledger/sidecars and both bindings.
The sandbox receives only its new checkout-local data mailbox, never the registry,
database, socket or controller credential. No arbitrary RPC/command/evidence path
or second dispatcher is introduced. Strict Harness is unchanged.

## Qualification and rollout

Tests cover immutable lineage, partial/unknown claims, source/record drift,
single-owner races, monotone cumulative usage/freshness, Pause/Stop/expiry,
unloaded/unknown native prerequisites, lost delivery, permissions, file-only
status, diagnostic non-authority, no fallback and no recursive successor.

The compiled fixture uses a disposable same-brain/project/home with a fake
loopback provider, an explicitly **injected historical preflight refusal**, and
synthetic numeric accounting. The successor itself runs through the real native
subscription, sandboxed helper, explicit new receipt/proposal and completion on
one original connection. The injected predecessor is not claimed to be actual
native unloading or evidence about live history. No live host, credential,
download, paid provider, Action or new project is used by qualification.

```text
python3 -B scripts/qualify_canceled_continuation.py --package EXACT_PACKAGE --evidence NEW_EMPTY_PRIVATE_DIRECTORY --same-project-successor
python3 -B scripts/qualify_canceled_continuation.py --package EXACT_PACKAGE --evidence ANOTHER_EMPTY_PRIVATE_DIRECTORY --same-project-unloaded
```

The second fixture actually closes all creating subscribers, waits beyond its
one-second disposable unload delay, and obtains the real unloaded preflight
refusal. Its diagnostic must observe `notLoaded`, leave policy/terminals unknown,
and perform zero execution calls, usage collections or execution claims. No
predecessor refusal is injected in this negative fixture. Both modes preserve
original rows/claims/binding and make no live native connection.

Keep source, local qualification, manual merge, safe installation, current native
eligibility, exact live review/application and pilot acceptance separate. Do not
hot-patch a live owning observer. Preserve stopped-writer/private verified-backup
rollout gates. This source repairs no live host, activates no review, changes no
binding, reloads no brain and qualifies no live pilot.
