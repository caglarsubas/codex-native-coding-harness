# Observer heartbeat and forward-only preparation reconciliation

## Prospective transport repair

Slow filesystem/process checks previously blocked the foreground WebSocket reader.
A matching pong could sit behind data while a check exceeded its deadline,
reporting loss despite a healthy host. The old adapter omitted the typed reason;
its generic historical failure must not be backfilled with an inferred cause.

Future observations use one bounded I/O reader on the **same original pipe**.
It decodes frames and handles control pings/pongs while the foreground owner checks
authority. It cannot execute callbacks, send JSON RPCs, connect, load, subscribe,
notify, retry or keep a closed connection alive. Only the foreground owner checks
Stop/scope/expiry, services mailboxes and authorizes effects. Preserve event order,
finite count/byte bounds and explicit overflow uncertainty. Closing the original
proxy stops and joins its reader, without killing or restarting the native host.

The 15-second cadence, 10-second missing-pong threshold, exact nonce/endpoint epoch,
read/phase deadlines and 120-second send freshness are unchanged. Data or wrong
pongs cannot renew health. Future failures retain their typed loss reason.

## Independent evidence, not another effect

`transferred_preparation_completion_evidence_v1` is an explicit operator read,
not restoration of the ended observer. Only a closed v5 transfer with positive
restore/load/assignment/subscription records, an acknowledged new preparation
turn, **both original explicit receipt and inert proposal**, and transport loss
while observing that turn qualifies. Partial/changed/unlisted records, missing
receipts, permission requests, Stop and foreign events remain fenced.

Read current code only. Historical PR-181 requests need exact immutable allowlisted
source hash/epoch evidence, never old-source import/execution. Validate original
database identities/fingerprints, disposition, canonical claims, all owner/consumer
records, cumulative usage/limits, unchanged expiry/new clock, historical bindings
and the originally issued destination PID/birth/package/config/socket. Inspect
credential privacy metadata only; never open/hash/copy credentials or refresh them.

On one independent **read-only** connection to that reviewed destination, repeat
exact project/full-brain/latest-turn metadata and non-refreshing account/routing
identity. Require unchanged prior history followed by exactly the acknowledged
new `completed` turn. Its exact native-returned history must preserve the immutable
archive prefix and correlate one new start/completion. An unloaded brain can expose
persisted completion, but policy and tracked terminals remain unknown. No load,
subscription, observer reconnect, discovery, permission response, cancellation,
refresh, native write or new turn exists here. Revalidate original state after I/O;
changing/unsupported/interrupted reads remain unknown without fallback.

Append `intent.json` and `evidence.json` to a new disjoint private directory only.
Never edit the old `incomplete_unknown` outcome, receipts, usage, clocks, claims,
bindings, databases or repository holds. File-only status never connects, collects
telemetry or renews observation time. Explicit later reads cannot rearm an effect.

Positive evidence says `preparation_completion_observed`, not `planning_completed`,
cleanup, terminal safety, phase success or pilot acceptance. Post-turn usage remains
uncollected/unknown. The original conditional binding review stays fenced. A distinct
`reconciled_preparation_binding_review_v1` may propose a future cutover pinned to
the positive evidence **and preserved lost outcome**. It installs nothing: later
application needs exact owner review, quiesced writer, private verified backups and
fresh host/membership checks. No worker, Play or Resume authority follows.

```text
python3 -B -m orchestrator.handoff_reconciliation --platform PLATFORM --workspace WORKSPACE collect ORIGINAL_TRANSFER_REVIEW NEW_PRIVATE_EVIDENCE --handoff-source EXACT_FROZEN_PR181_SOURCE
python3 -B -m orchestrator.handoff_reconciliation --platform PLATFORM --workspace WORKSPACE status NEW_PRIVATE_EVIDENCE
python3 -B -m orchestrator.handoff_reconciliation --platform PLATFORM --workspace WORKSPACE binding-review NEW_PRIVATE_EVIDENCE
```

Current-source fixtures omit `--handoff-source`. Collection is explicit, never
polling/Help/dashboard refresh. It needs no new execution confirmation because it
has no execution capability. Source delivery installs nothing, stops no writer,
reads no live native host, confirms no control and qualifies no pilot. Merge,
safe rollout, live collection, conditional binding application and acceptance
remain separate.

## Qualification

Disposable pipe tests cover slow/blocked checks, buffered matching pongs, missing/
wrong pongs, endpoint replacement, count/byte overflow, Stop and bounded shutdown.
Synthetic evidence tests cover lineage, original receipts, unloaded completion,
changed/partial claims, identity/history/account drift, allowlists, private output
and file-only status/review.

The compiled fixture injects loss **after actual native completion** with both
sandboxed receipt/proposal retained. After actual one-second idle unload, the
production collector observes the same completed turn without reload/subscription.
Old unknown records, ledgers, bindings and accounting are unchanged. All model
responses are loopback fakes; launch/ledger/numeric usage/expired-clock/preflight
lineage are labelled synthetic or injected. No live host, credential, cloud call,
download, paid service or GitHub Action is used.

```text
python3 -B scripts/qualify_canceled_continuation.py --package EXACT_PACKAGE --evidence EMPTY_PRIVATE_DIRECTORY --transfer-reconciliation
python3 -B scripts/qualify_canceled_continuation.py --package EXACT_PACKAGE --evidence ANOTHER_EMPTY_PRIVATE_DIRECTORY --transfer-slow-foreground
```

The second fixture blocks foreground validation for 26 seconds, longer than the
unchanged 15+10-second heartbeat window. It requires an actual matching native
pong during the block and positive same-connection preparation completion.
