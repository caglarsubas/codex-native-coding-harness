# Sandbox-safe cooperative run control

## Cause and separate read-only fix

`standard-state` previously constructed writable Registry and Ledger objects.
That initialized WAL/schema and chmodded the selected state before performing a
read. A brain confined to its checkout could therefore ask for an escalation
just to inspect a run. The permission relay correctly refused its external cwd.

The status/inbox/mission/standard-state CLI routes now open existing private
databases read-only, without schema setup, chmod or writer transactions. They
cannot create a missing ledger or registry. Cold WAL may still need SHM access;
this is not a general sandbox access grant. Future sandboxed brains use the
mailbox below instead of opening either database.

## Prospective original-turn mailbox

For future committed public-backend standard Play/Pause/Resume notifications,
`standard_run_observer_v1` is retained **before** the notification claim and
original native turn. This supports only the reviewed `repo_exclusive` public
backend. Strict Harness, legacy/managed controls, recovery wakes, historical
requests and already attempted notifications do not acquire the marker.

The private handoff pins source bytes, original command/run/brain/workspace,
mission/review/owner receipt, registry/ledger inodes, reviewed binding and backend.
After the single native start is acknowledged, its exact turn is bound once.
An observer-only random signing key remains in process memory; it is never
returned to the brain. Restarting cannot adopt that session or replay a call.

The brain runs from its checkout using the exact source in the notification.
Use `python3 -B` to avoid trying to write bytecode into the protected release.
Read this document before processing a marker-bearing run. Do not use the normal
shared-registry/controller CLI path or access the protected socket.

```text
PYTHONPATH=EXACT_SOURCE python3 -B -m orchestrator.cli --run-handoff ORIGINAL_HANDOFF standard-run-call PRIVATE_CALL_JSON
PYTHONPATH=EXACT_SOURCE python3 -B -m orchestrator.cli --run-handoff ORIGINAL_HANDOFF standard-run-status SEQUENCE
```

Each private call is exactly `{sequence, operation, payload}`. Start at sequence
1 and increase only after a completed, continuation-allowed reply. Calls form an
immutable previous-reply hash chain. The observer requires both the prior
permanent claim and its process-keyed seal before servicing the next sequence.
Client-authored reply files cannot skip an interrupted operation. A call can be
submitted identically only to follow its original result; changed bytes refuse.
At most 256 calls and 64 KiB per request/reply are supported. Over-bound state
stops rather than silently truncating evidence.

The client touches checkout-local private files only: no SQLite, registry,
socket, native RPC, credential or controller token. Status never collects,
services, submits, wakes or refreshes an observation. Its bounded 30-second wait
does not expire or renew owner authority. A claimed call without a reply stays
unknown permanently; never skip it, change its ID or automatically reapply it.

| Operation | Exact payload and existing gate |
| --- | --- |
| `state` | `{}`; bounded selected-run projection, no native collection |
| `acquire` | `{}`; acquire one controller for this exact brain/control/turn; no credential exposed |
| `receive` | `{}`; exact original run-control receipt only; latest run/Pause governs |
| `usage` | `{}`; existing exact-run local counter refresh, all high-water/gap rules preserved |
| `host_inspect` | `{}`; existing one-shot owned-observer metadata helper |
| `journal` | Existing closed claim/cancel_unissued/preserve/finish/checkpoint payload, **without runId** |
| `seed` | `{taskId}`; only that registered task's immutable standard seed |
| `task` | `{taskId}`; existing explicit public task request, never desktop fallback |
| `task_status` | `{taskId}`; follows only an already existing public request |
| `release` | `{summary}`; existing controller, retained terminal checkpoint and settled registered tasks |

For example, the first call is
`{"sequence":1,"operation":"state","payload":{}}`. Verify the named brain/run,
then call acquire, receive, usage and host_inspect with successive sequence
numbers. Use the returned exact mission/catalog/scope and existing standard cycle
to claim a bounded task, read its seed, refresh usage before effects, explicitly
request it and follow its status. Independently inspect source, run actual local
tests and preserve allowed artifacts before finish/checkpoint/release. Result and
terminal evidence are not inferred from a final message or an ended turn.

The original observer services only explicit requests off its heartbeat reader;
there is no scheduler, alternate dispatcher or automatic task selection. Normal
standard controller, mission, capacity, usage, source, repository, policy,
duration and Pause checks remain in the existing implementations. A pending
native permission fences mutations; the mailbox cannot answer or bypass it.
An early request waits until the original notification is accepted, without
consuming its operation claim. Receive does not drain unrelated saved messages,
decisions or historical controls, and no shared-registry conversation command
is appended to this sandbox pointer. Ordinary conversation retains its existing
separate controls and receipts; this mailbox adds no messaging authority.
Original observer/session/run ownership is rechecked inside each existing ledger
write transaction, before and after the operation; an intervening closure rolls
back that transaction rather than becoming authority on a retired connection.
An exception or partial output permanently fences later calls, since a local
effect may already have committed. Release is not process cleanup or acceptance.
No zero usage or safe terminal status is inferred from missing data.

## Held old requests and rollout

```text
python3 -B -m orchestrator.cli --platform REGISTRY --workspace WORKSPACE standard-run-continuation COMMAND_ID
```

This read-only assessment pins the original command/run hashes and reports
whether the original notification already owns this prospective mailbox. It
does not create a handoff, claim, receipt, control or review approval; it never
connects natively or responds to the held permission. An old observer without
the marker reports `held_original_requires_owner_resolution`, not safe-to-retry.

The current v3 Play was already delivered without this protocol. Do not hot-edit
its pinned release, attach a new handoff, backfill a receipt, restart the owning
dashboard/host or reconnect an observer to install this source. Its pending
native request requires a separate exact owner resolution through its original
connection. This delivery does **not** provide or confirm that response or a
new continuation turn. A source merge cannot lift that boundary automatically.

Keep source delivery, manual merge, installation and live qualification separate.
Quiesce older writers and verify private backups before a separately authorized
rollout once native ownership permits it. Preserve every original request,
claim, run, usage/high-water/gap, binding and expiry. No reload, readiness/Play/
recovery replay, automatic permission/cancellation, usage reset, assumed cleanup
or pilot acceptance follows. The original terminal unknowns remain unknown.

## Qualification

`tests/test_standard_run_mailbox.py` uses disposable repositories and explicitly
synthetic native metadata. It exercises prospective preparation, real macOS
sandbox calls with database/registry/network access denied, exact receipts,
measured usage, scoped claim/seed/checkpoint/release, one-shot/concurrent and
interrupted calls, forged reply seals, Pause, missing evidence, changed identity,
source/binding/session closure and held-original conservation. Existing public
task tests separately cover creation/first-turn claims and current registered
terminal reports. These are source/protocol tests, not a live pilot pass or proof
that every future model/permission/usage path will succeed.

Run the complete local qualification with
`python3 scripts/qualify_sandbox_run_control.py --evidence NEW_EMPTY_PRIVATE_DIRECTORY`.
It retains full logs outside source and rejects source-byte changes during the
run. [The evidence ledger](PROJECT-KNOWLEDGE-VERIFICATION.md) records the actual
results separately from installation and live pilot acceptance.
