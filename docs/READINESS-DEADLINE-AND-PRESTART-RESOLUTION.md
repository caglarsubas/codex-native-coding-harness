# Readiness deadlines and forward-only pre-start resolution

Source and disposable qualification install nothing, confirm no live review and
send no native request. Preserve all runs, requests, consumed claims, usage/gaps,
clocks, repository holds and bindings. Neither this repair nor its resolution
grants a reload, readiness/Play/recovery replay or terminal-safety assertion.

## The deadline defect

The sender opened a native proxy with one absolute 15-second deadline, then
entered a ledger transaction. A completed historical admission validates source,
backups, Git identity and preserved claims on transaction entry and exit. Under
load that local work could exhaust the native deadline before the next account
read. Concurrent status reads also requested registry writer locks, producing
`database is locked` and a disconnected display. Neither symptom proves host
loss or bad credentials. A fresh read-only successful account check cannot
retroactively complete the failed original request.

The corrected sender validates its saved request before opening the connection.
Only a prospective readiness-owned send starts its fixed 900-second window and
bounded control-frame reader on that original pipe, immediately after connection
initialization. Each foreground RPC has a separate at-most-15-second I/O budget,
capped by the original window. Local work cannot consume the next RPC's short
budget or renew the overall window. Actual native delay still times out. The
reader handles control frames only; it cannot issue RPCs, run authority callbacks,
reload, retry, reconnect or become an independent keeper. The turn observer uses
that same reader instead of starting it again.

Exact identity, authentication, policy, empty current trackers, admission,
foreign-owner, Pause and source checks remain at existing boundaries. Native
load/send scope must remain within 120 seconds; per-RPC budgets do not refresh
those observations. An expired overall window refuses before another RPC/write.
Legacy transports do not acquire this readiness window. Registry list/root
status uses a query-only WAL snapshot, while every writer retains its original
write transaction and effect checks. A display snapshot is never authority.

## Narrow consumed-attempt resolution

`readiness_prestart_resolution_v1` supports only one unchanged, empty, unowned,
paused schema-1 or completed-admission schema-7 first-phase standard project.
It must have exactly one original readiness-owned request, its canonical claim,
verified original backup and exact version-3 prospective handoff. The positive
original failure must be precisely `authentication_check / deadline_exceeded`,
with `resumeAttempted=false`, `turnStartAttempted=false` and finished unavailable
delivery. Original scope must have been `notLoaded`. These positive facts—not
missing records alone—identify the supported pre-load failure. Unknown/accepted
delivery, turns, profiles, permissions, retry history, capture, receipts, any
load claim or acknowledgment, or unlisted readiness files refuse.

An optional original close record must positively say `no_turn_started`, null
turn ID, closed connection, no reconnect and unknown terminal safety. It can
corroborate the original diagnostic but cannot replace it. The pre-fix PR187
path did not create this close before loading; its missing close is preserved,
not backfilled. No original record is rewritten.

Require the exact unchanged binding/dual project IDs, reviewed mission,
admission/source continuity and predecessor holds. The operator supplies the
immutable original source path explicitly. Hash all its original Python bytes
and epochs without importing or executing them; only current-source requests or
the qualified PR187 implementation hash are supported. This is historical
validation, not compatibility for sending the old request from new source.

## Operator procedure

Use the separately installed qualified source and explicit routes. None of these
commands opens a native connection. Preview and status are read-only. Review is
valid until scope changes, not a short timer. The brain cannot confirm it.

```text
python3 -B -m orchestrator.readiness_prestart_resolution --platform PLATFORM --workspace TARGET preview EXACT_BINDING ORIGINAL_COMMAND EXACT_ORIGINAL_SOURCE
python3 -B -m orchestrator.readiness_prestart_resolution --platform PLATFORM --workspace TARGET backup PRIVATE_REVIEW NEW_PRIVATE_BACKUP --writers-stopped
python3 -B -m orchestrator.readiness_prestart_resolution --platform PLATFORM --workspace TARGET confirm PRIVATE_REVIEW --confirm-hash EXACT_NEW_HASH --backup NEW_PRIVATE_BACKUP --writers-stopped
python3 -B -m orchestrator.readiness_prestart_resolution --platform PLATFORM --workspace TARGET status
```

Save only the returned `request` as the private review. Separately quiesce older
writers, verify their actual stopped state, and back up target/registry SQLite
contents, original sidecars, binding and review in a new disjoint private folder.
The flag alone is not process-exit evidence. After exact new owner approval,
registry-then-target locks repeat the complete scope and backup checks. One
permanent file claim precedes one new unqualified snapshot. Partial persistence
stays fenced. A repeated identical confirmation only reads the retained outcome;
it never reapplies, resets, creates another allowance or sends a notification.

Every original target row, metadata/revision, command/notification, mission,
usage, claim, handoff, missing receipt and binding remains intact. Retained
validation subtracts only the one new snapshot before comparing all original
table fingerprints. Missing/corrupt claims, changed rows or binding epochs fail
closed. Both the claim and committed outcome permanently fence ordinary writes.

The UI distinguishes the original queued status from the new unqualified
disposition. It removes the false pending-reply wait and shows an inspection
action, never a readiness retry, another load or Play button. Current and
historical terminal safety remain unknown; repository ownership is not released.

## Continuing the pilot

Resolution is not a capability catalog, brain receipt, checkpoint, successful
readiness, new native allowance or pilot acceptance. It does not make an unloaded
brain runnable under a no-reload constraint. A separately supported and exactly
reviewed prospective continuation would still be needed; do not disguise a
replay as a new ID or use the canceled-turn disposition's incompatible gates.
Source delivery stops at a qualified source change for manual merge. Safe
installation, this exact live review and any later native authority are separate.

## Qualification

Use real disposable SQLite/Git admissions and labelled fake native metadata.
Cover slow local validation versus slow I/O, fixed global expiry, heartbeat
ownership, stale scope, legacy behavior, concurrent query-only status reads,
ordinary and admitted resolution, positive failure flags, lost/partial claim,
changed source/binding/old rows, verified backups, duplicate confirmation and
absence of another load/turn/Play. Render desktop and 320px views with no control
POSTs or native calls. Run full local Python/JavaScript/syntax checks; no download,
paid service, GitHub Actions or live qualification follows from these fixtures.
