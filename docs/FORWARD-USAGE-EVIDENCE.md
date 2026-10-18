# Forward-only usage evidence for canceled-attempt planning

This is an explicit version-2 option on the separate
[forward-planning control](CANCELED-CONTINUATION-CONTROL.md), not a new dispatcher,
Resume or repeated Play. Version 1 remains the default with its original retained
report freshness rule. Source delivery does not install or activate either path.

## The timing trap

The [canceled-Play disposition](CANCELED-PLAY-DISPOSITION.md) intentionally freezes
the original ledger, including normal usage-refresh writes. Version 1 then needs
that saved report to be less than 120 seconds old to start its new planning turn.
A scope-bound review can remain correct while this independent observation ages
out. Racing the owner through approvals, renewing the saved timestamp, extending
the phase or weakening freshness is not a repair.

## New review, immutable baseline

Select `prepare --forward-usage-evidence` explicitly. The closed
`canceled_play_forward_planning_v2` review pins the original snapshot-backed
report/high-water amounts and the already configured `observations.json`, exact
private Codex home and directory device/inode/owner/permission identities. It
adds no report-upload, arbitrary-home or model-authored collection route. It
changes no binding, original record, disposition, claim or clock.

The old report may be stale **as a baseline only**. It must still have complete
gap-free numeric vectors for exactly the run's registered brain intervals,
matching scope and retained snapshot, known total/brain high-water amounts and
consistent aggregate/subset accounting. Missing or gapped history cannot become
zero or acquire coverage from a new collection. Only an empty canceled attempt
is supported; strict Harness accounting and workers are outside this path.

Preparation, private backup and status are local-only and collect no telemetry.
The owner review has `validUntil: scope_changes`, not an approval countdown.
Original expiry, source/package/binding pins and evidence freshness still apply.
The new exact review authorizes both one collection and the same bounded new
receipt/proposal turn; it does not add a separate collection approval loop.

## Collection and send boundary

After verified backups, quiesced writers and exact confirmation, the control
durably claims the **same** original-command/database-identity journal as version
1. A version, source, review directory or endpoint change cannot rearm it. Before
any native connection, one exclusive `usage.claim.json` precedes one collection
from exact registered-session log paths. All file components reject symlinks;
files must be private, regular, bounded and unaliased. The complete bounded
inventory, fixed file epochs and hashes must remain stable through the read.
Numeric counters reuse the existing legacy/compaction-aware parser. No transcript
or credential bytes are retained, and `auth.json` is never a collection target.

`usage.json` retains the new actual `collectedAt`, interval, original per-session
sample times, numeric vectors, gaps, baseline/source hashes and exact file
provenance. It lives in the prospective journal, **not** the original ledger.
Completed reads with gaps/regressions remain retained but cannot authorize a
connection. Interrupted/partial reads keep their permanent claim and stay unknown.

Every registered session and vector component must be monotone against the old
baseline, including sample time and call count. The aggregate must exactly equal
those vectors and cover the old phase/brain high-water amounts. Cached input is
already in input; reasoning is already in output. Neither is added again. New
consumption plus the explicit planning ceiling must fit the unchanged phase,
brain and checkpoint-reserve limits. The original deadline is never extended.

Freshness remains **0 <= age < 120 seconds**, using the existing collector limit,
checked after collection, before connection/subscription and again immediately
before `turn/start`. Native I/O delays do not permit another collection. Owner
stop, original ledger/Pause/claim drift, configuration or source drift, expiry,
stale evidence and uncertain delivery refuse. Unknown is never terminal safety.
There is no load, replay, reconnect, permission response or automatic retry.
Once the single turn starts, its pinned pre-send observation remains historical;
service does not recollect it or pretend to measure subsequent model consumption.
The ceiling remains cooperative, not a provider billing cap.

Only the already-loaded-only subscription and one new inert planning instruction
are supported. Current loaded-idle policy/empty-tracker checks remain unchanged
and do not prove historical effects or full descendant cleanup. A new explicit
receipt and inert proposal are still required; native completion alone is not
success or pilot acceptance. Status validates pinned prospective records without
checking that historical evidence is still fresh, renewing it or making any call.
An expired phase still cannot execute, even with a healthy new report.

## Operator sequence

After separate manual merge and a quiesced, backed-up compatible installation,
apply the separately reviewed canceled-Play disposition first. Then prepare:

```text
python3 -B -m orchestrator.canceled_continuation --platform PLATFORM --workspace WORKSPACE prepare ORIGINAL_BINDING ORIGINAL_PLAY CANDIDATE_BINDING TRANSPORT_CONTRACT --max-tokens N --forward-usage-evidence
```

Save its exact closed `request` privately. Use the existing `backup`, `confirm`,
`status` and `stop` commands documented in the planning contract. Only exact owner
confirmation of the new hash may collect/send. Existing disposition/load/Play
approvals cannot confirm it. Do not confirm a stale source-bound review after
installation. No source upgrade refreshes usage, changes a live dashboard/host,
applies disposition or starts the pilot automatically.

## Qualification

Disposable unit fixtures exercise a stale immutable baseline, actual new numeric
reads, monotone session/vector/call/sample accounting, gaps, regression, missing
prefix/logs, high-water and independent budget/reserve/expiry gates, wrong scope,
future/nonfinite observations, duplicate archives, source/config/root/file drift,
symlinks/hardlinks, collection interruption and races, stale-at-send refusal,
owner stop, concurrent confirmations, canonical version fencing and file-only
status after expiry. Original database proofs, sidecars and bindings are checked.

The compiled sandbox qualification uses:

```text
python3 -B scripts/qualify_canceled_continuation.py --package EXACT_PACKAGE --evidence NEW_PRIVATE_EMPTY_DIRECTORY --forward-usage-evidence
```

Its numeric telemetry and original ledger are explicitly synthetic. The actual
compiled native host, owning subscription, sandboxed helper, receipt/proposal and
turn completion use a disposable home and loopback fake model responses only.
Neither synthetic accounting nor current empty fixture trackers attests live
usage, entitlement, terminal safety or a real worker pilot. No download, paid
service, GitHub Action or live native connection is part of qualification.
