# Checkout-local pre-Play capability receipt

## Root cause and scope

The normal CLI constructs a registry and ledger before handling `standard-state`.
Those constructors use SQLite writer transactions. A brain sandbox limited to
its own checkout cannot write a shared registry outside it, so even this read
can request escalation. The native accept relay correctly requires a running
reviewed phase; relaxing that gate before Play is not a solution. Nor is simply
opening SQLite `mode=ro`: a cold WAL database may need writable SHM sidecars.

For **future first-phase, schema-1 all-standard projects only**, the original
`standard_catalog_refresh` notification may prospectively retain a
`preplay_catalog_observer_v1` handoff in the bound checkout's private ledger
directory. The fixed notification names it before the original `turn/start`.
The brain uses only the closed helpers below. Neither helper opens SQLite,
constructs a registry/ledger, reads a controller credential or connects to any
native socket. No wider sandbox write grant or pre-Play native accept exception
is introduced. Strict Harness and existing controller-based catalog calls are
unchanged.

## Designated brain procedure

Use the exact source and absolute handoff path in the original fixed pointer.
Verify that this native task is the named brain. These helpers are an exception
to the normal standard-cycle registry/controller procedure for this receipt only:

1. `python3 -m orchestrator.cli --preplay-handoff HANDOFF standard-preplay-state`
   returns original request/brain/workspace/mission context, **not** fresh run or
   terminal evidence. Do not run `inbox`, `standard-state`, `standard-acquire` or
   `standard-release` against the shared registry for this path.
2. Inspect only the model/effort combinations actually exposed by current native
   creation/message schemas. Do not infer them from documentation, memory,
   global settings, successful configuration overrides or requested policy.
3. Write one private regular JSON file (mode 600, one link, at most 64 KiB).
   A successful result has `operation: catalog`, the exact `requestId`,
   `models: [{model, efforts: [...]}]` and bounded `source`. If observation is
   unavailable, use `operation: catalog_error`, the same `requestId`, bounded
   `code` and `detail`, and boolean `retryable`. An error is a completed receipt
   attempt, not a successful catalog or permission to retry automatically.
4. `python3 -m orchestrator.cli --preplay-handoff HANDOFF standard-preplay-receipt RESULT_JSON`
   publishes exactly one immutable closed request. A bounded 30-second wait
   does not expire or renew its authority. If pending, follow only
   `standard-preplay-status` with the same handoff. Status reads cannot publish,
   collect, claim or resend. A changed result is refused.
5. End after the receipt. No controller is acquired/exposed/released by this
   narrow relay; there is no controller to clean up. Do not answer native
   permissions, start Play/workers, change bindings/policy, Resume or recover.

## Existing owned observer and durable outcome

The existing original observer services only that explicit mailbox, off its
heartbeat reader. There is no new native connection, dispatcher, scheduler,
turn, load or retry. The server pins the source bytes, original handoff hash,
registry/ledger identity, brain, workspace, mission/context, unchanged binding,
command and exact current owned native turn. The original notification must be
accepted, the observer still open and not superseded, with no recorded pending
native approval. A Stop, different mission, controller, task/packet, active run,
pending control, strict enrollment, changed identity/source or ended/unknown
observer fences the receipt.

The observer claims the exact request once **before** processing it. Under the
existing registry-then-ledger serialization, the designated brain's result goes
through the same closed `catalog` / `catalog_error` validation as controller
calls. The catalog/error, normal command receipt and hash-only `preplayReceipt`
marker commit atomically. No reusable controller grant or other operation is
reachable. SQLite rollback leaves no partial catalog. An interrupted claim or
lost reply is never applied again, even if the request is submitted identically;
inspect its original durable command. Reply/status files are progress, not owner
authority; only the actual ledger receipt can satisfy the catalog prerequisite.

The handoff contains no endpoint, registry path, credential or raw native prompt.
Private immutable handoff/request/claim/reply files remain in `.state/`; never
commit them. No request means no collection. There is no request timer requiring
another approval; the original subscription and unchanged context bound it.

## Qualification and rollout boundary

Disposable tests deny registry/SQLite/network access in a real macOS sandbox,
exercise cold read-only WAL files, and cover one-shot claims, lost replies,
identity/source/mission changes, Stop/approval races and observer closure.
They qualify this source protocol, not a live native model catalog or pilot.

Source delivery installs nothing and changes no live ledger, host or binding.
Do not overlay source or restart a dashboard while it owns a pending turn.
An already delivered legacy request cannot acquire this new handoff: preserve
its notification, permission prompt and unknown outcome. This repair is not
permission to cancel/accept it, replay readiness/Play/recovery, reload a brain,
reset usage or declare terminal safety. A separately authorized, forward-only
resolution of that pending original turn is required before a new phase can
proceed. Review, native capability receipt, Play and pilot acceptance remain
separate evidence and authority states.
