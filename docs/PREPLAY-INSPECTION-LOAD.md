# One-shot pre-Play inspection load

`public_preplay_inspection_load_v1` is a separate **operator-only** path for the
unloaded first-phase public brain. It is not a readiness request, recovery,
Play, phase Resume, host restart, dashboard restart, binding change or pilot
acceptance. Source delivery and preparation do not load the live brain.

## Exact boundary

Require an issued `public_preplay_home_restart_v1` with its original launch,
permanent exec claim, same-attempt PID/birth/argv/cwd and exact current socket.
Verify repeated predecessor-PID absence and that the issued PID owns the socket.
The original endpoint is historical bytes only; never reconnect to it. Preserve
the unchanged single brain, checkout, both project IDs, backend/build/policy,
catalog mapping, reviewed mission, registry and ledger identities.

Only an empty, unowned, paused schema-1 all-standard first-phase project qualifies.
Every original readiness turn must be ended with its original closed observer,
no unresolved permission and either its correlated version-1 non-retryable
`native_schema_unavailable` receipt (handoff/request/claim/reply hashes) or the
separately retained canceled-readiness disposition. A failed status alone is not
a receipt; no old capture/source is executed or backfilled. Pending/uncertain requests, tasks, packets,
controller, runner, decisions, strict enrollment, Brain Stop, handoff, admission,
successor or quarantine ownership refuse. All original requests, usage/gaps,
claims, receipts, disposition, expiry and bindings stay immutable.

Read only the previously pinned history/installation prefixes and fixed restricted
native configuration. Do not enumerate the native home, open credentials/native
SQL, change trust, log in or refresh a token. Non-refreshing account metadata,
complete empty MCP inventory and repeated exact project/brain/latest-ended-turn
reads are required. Preparation requires `notLoaded`, null policy and unknown
tracked terminals. Already loaded/active is not an excuse to resume again.

## Review and commands

```text
python3 -m orchestrator.public_preplay_load --platform PRIVATE_PLATFORM --workspace WORKSPACE prepare ISSUED_PREPLAY_RESTART CURRENT_REVIEWED_BINDING NEW_REVIEW_DIRECTORY --subscription-seconds 300
python3 -m orchestrator.public_preplay_load --platform PRIVATE_PLATFORM --workspace WORKSPACE preview NEW_REVIEW_DIRECTORY/load.json
python3 -m orchestrator.public_preplay_load --platform PRIVATE_PLATFORM --workspace WORKSPACE apply NEW_REVIEW_DIRECTORY/load.json --confirm-hash EXACT_LOAD_REVIEW_HASH
python3 -m orchestrator.public_preplay_load --platform PRIVATE_PLATFORM --workspace WORKSPACE reconcile NEW_REVIEW_DIRECTORY/load.json
python3 -m orchestrator.public_preplay_load --platform PRIVATE_PLATFORM --workspace WORKSPACE status NEW_REVIEW_DIRECTORY/load.json
```

Read routes never instantiate Registry/Ledger writers. The exact review has
**no timer expiry**: only scope changes invalidate it. The owner reviews one new
hash, not an old launch, connection, readiness or recovery approval. Preparation
and preview create no execution claim and never confirm themselves.

Before application, quiesce other maintenance writers and use the exact clean
qualified source. Application creates private logical registry/target backups,
checks integrity and every reviewed row, and verifies copied private input bytes.
Recheck unchanged scope before and after backup and at the effect boundary.
This is not a global atomic lock on the native app or unrelated writers; a racing
Pause/control/change consumes the attempt and refuses continuation. No database
rows or schema markers are written by this protocol.

A canonical ledger/brain/database-identity claim is committed **first**, then the
private intent/load claim, before exactly one fixed `thread/resume`. Review
directory, endpoint, launch attempt, source change or timestamp cannot create a
second allowance. A partial, failed or unknown claim is never retried or migrated.
The native call uses exact brain/cwd, `excludeTurns:true`, workspace-write,
on-request/user approval, and Code Mode/goals/apps/plugins/hooks disabled. No
model override, history injection, command, permission response or turn is sent.

After acknowledgment, independently repeat loaded-idle identity, exact latest
ended turn, actually enforced restricted policy and complete current empty
tracked-terminal reads. Retain observations separately, never backfill a failed
readiness receipt or promote configured policy into observed enforcement.
Reconciliation is read-only on the original reviewed host; it never loads or
reconstructs a missing acknowledgment. Status is file-only and historical.

## Foreground lifetime is not approval expiry

The original load connection owns a separately reviewed 15–300-second foreground
observation window (normally 300). This starts **only after application**; it is
not a countdown on the owner review. There is no daemon, automatic reconnect,
second load, keepalive turn, timer override, ownership transfer or renewal.
The original process/connection and monotonic deadline are pinned. Close on
completion, interruption, drift, new activity or failure. A missing close record
means unknown ownership, never active merely because a PID/timestamp exists.

The existing host may unload an unsubscribed idle brain after its own grace
period. Closing the observation connection does not promise durable loading.
A future separately owner-confirmed **distinct** public readiness request can
own its own normal subscription while the brain is loaded; this load path does
not create, confirm, send, retry or wait for that request. Any such state change
ends this inspection scope. Missing that window never grants a reload allowance.

`thread/read` is a non-loading read; `thread/resume` reopens a session and owns
its event subscription. See the [official app-server protocol](https://learn.chatgpt.com/docs/app-server).
The pinned native binary, not a newer documentation default, determines its
actual no-subscriber grace. No change to that native lifecycle is made here.

Current empty tracked terminals are not historical process/descendant cleanup or
whole-terminal safety. Current/historical terminal safety remains **unknown**.
Loading and matching current policy do not provide a catalog receipt, model
entitlement, old receipt, controller, checkpoint, ownership release, Play or
pilot acceptance. Future readiness and Play remain separate owner decisions.

## Qualification and rollout

Unit fixtures cover exact reviews, unknown/failed claims, no second directory or
host allowance, Stop/Pause/request/usage/identity drift, private backups, unloaded
policy, already-loaded refusal, lost acknowledgment and file-only status.
The opt-in compiled-native qualifier creates only disposable projects/homes and
loopback fixture work, exercises the fixed load/proxy and repeated enforcement,
and verifies zero warm turns/provider requests. No live brain is loaded.

```text
python3 scripts/qualify_public_host_restart.py --inspection --preplay-load --subscription-seconds 75 --executable EXACT_BINARY --sha256 EXACT_HASH
```

Source, manual merge, installation, exact live review and application are separate.
Preparing a live review changes no dashboard/host/binding, sends no native load
or readiness/Play/recovery, resets no usage and accepts no pilot.
