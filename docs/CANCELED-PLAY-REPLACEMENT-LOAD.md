# One separately reviewed replacement-host load

The owner explicitly authorized one new reviewed load of the persisted v3 brain
on a replacement host. This is a narrow exception to the earlier no-reload
instruction, not permission to repeat an inspection, readiness request, Play,
recovery or uncertain native effect. The existing already-loaded-only planning
control and every original claim keep their contracts.

`canceled_play_replacement_load_v1` is an operator-only metadata inspection. It
starts no model turn and grants no phase Resume or worker dispatch. It preserves
the original canceled/unreceived Play, run, usage/gaps/expiry, claims, capture and
historical binding bytes and epochs. Loading is not phase continuation or pilot
acceptance. Current and historical terminal safety remain unknown.

## Ordering and exact review

1. Separately review and issue the existing
   [replacement-host launch](CANCELED-CONTINUATION-CONTROL.md). This load adapter
   cannot launch, reconnect to a retired host, sign in or install a binding.
2. With the issued replacement actually running, use `candidate` to inspect only
   local files/process/socket metadata and obtain its proposed binding. Save it
   as a new private file outside the native home. Historical bindings are inputs
   only and must not be overwritten. No native RPC is made in this step.
3. Prepare the load review, inspect its exact hash and scope, stop older ledger
   writers, and verify private backups. Only the new exact hash confirms this
   one load. Scope validity has no approval countdown. Source delivery or a broad
   instruction does not confirm an unseen host/brain/socket specification.
4. Confirmation commits a canonical permanent intent outside the old ledger
   before connecting. Repeated exact project/brain/latest interrupted-turn,
   inactive/unloaded state, unknown unloaded policy/tracker, empty MCP inventory
   and non-refreshing sign-in reads precede the fixed load. A durable load claim
   is committed before the one `thread/resume` with `excludeTurns: true`, the
   unchanged checkout and restricted policy, Code Mode/goals/apps/plugins/hooks
   disabled. No model/provider/effort override or arbitrary configuration is sent.
5. On that same original connection, repeat identity/latest-turn, actual native
   restricted policy, loaded-idle and complete empty current tracker checks.
   Preserve separate acknowledgement and observation records. Close the original
   connection; the result is then historical, never renewed current evidence.

This maintenance load deliberately happens **before** local canceled-Play
disposition: its complete original scope must still match the issued replacement
review. It neither applies that disposition nor bypasses it. Later usage
retention and local disposition need their own existing exact owner controls;
the old run must not be rewritten after its immutable disposition. A read-only
token diagnostic is not a retained usage receipt. The
[forward-planning control](CANCELED-CONTINUATION-CONTROL.md) still requires actual
retained gap-free usage within unchanged limits/reserve/expiry and a new exact
review. Its result is an inert proposal, not resumed development.

## Provenance, backups and consumption

Require the exact issued replacement review, full issued original-host lineage,
original database/sidecar/binding pins and dual project identities. Verify the
replacement package, PID/birth/argv/cwd, original-PID absence, new socket epoch,
restricted config, preserved native history prefixes and native backup. Native
`auth.json` is checked by metadata only; no credential bytes are opened, copied,
hashed or refreshed. Unknown/failed exec, changed metadata or partial ownership
is not a running-host proof or another launch permit.

The journal is keyed to the original database identity, brain and Play command,
not the candidate host, review directory, source revision or new ID. Its intent
consumes the attempt even if connection/preflight fails. A missing acknowledgement
or uncertain exit stays unknown. No alternate directory or replacement host can
retry it. Already-loaded or active brains are not adopted or reloaded by this
path. Changed latest turns, unsupported policy/terminals, native permission
requests and owner Stop fail closed; no permission response or native cancel is
sent. Concurrent confirmations have only one canonical owner.

Backups preserve both databases and all original sidecars, historical/candidate
bindings and issued-launch provenance in a new disjoint private directory.
Database integrity, logical fingerprints, original/backup bytes and file epochs
are verified before any claim. No backup can be placed inside the old ledger,
registry, native home, checkout, package or launch review.

## Operator interface

Run from the exact clean merged source; the actual registry/workspace and paths
are explicit private inputs:

```text
python3 -B -m orchestrator.canceled_load --platform PLATFORM --workspace WORKSPACE candidate REPLACEMENT_JSON
python3 -B -m orchestrator.canceled_load --platform PLATFORM --workspace WORKSPACE prepare REPLACEMENT_JSON NEW_CANDIDATE_BINDING
python3 -B -m orchestrator.canceled_load --platform PLATFORM --workspace WORKSPACE backup LOAD_REQUEST NEW_BACKUP --writers-stopped
python3 -B -m orchestrator.canceled_load --platform PLATFORM --workspace WORKSPACE confirm LOAD_REQUEST --confirm-hash EXACT_HASH --backup NEW_BACKUP --writers-stopped
python3 -B -m orchestrator.canceled_load --platform PLATFORM --workspace WORKSPACE status LOAD_REQUEST
python3 -B -m orchestrator.canceled_load --platform PLATFORM --workspace WORKSPACE stop LOAD_REQUEST --confirm-hash EXACT_HASH
```

Save the closed `request` from preparation, not its preview wrapper. `status`
reads retained files only; it cannot reconnect, reload, refresh usage or renew a
lease. `stop` is an explicit permanent local fence, not a native cancellation.
Neither turns a partial claim into a reusable one. There is no background
keeper, automatic restart or timer-driven model call.

## Qualification boundaries

Unit fixtures cover full issued-host provenance, exact review/backup, private
state conservation, permanent claims, concurrent confirmation, native drift,
unknown acknowledgement/tracker/authentication, policy mismatch, owner Stop,
credential non-reading and interrupted connection closure.

The compiled native cold/warm fixture uses a disposable home and labelled fake
loopback provider. It genuinely creates and cancels a disposable original turn,
exits its cold host, then runs the production load control on its warm host. The
launch provenance and canceled ledger are explicitly synthetic; full launch
provenance is covered separately by unit fixtures. It verifies one actual
metadata load, actual restricted native policy/current tracker and zero warm
model requests. It is not live launch authority, authentication entitlement,
historical cleanup or pilot acceptance.

The official [OpenAI app-server documentation](https://learn.chatgpt.com/docs/app-server)
distinguishes stored reads, `thread/resume` and `turn/start`; the pinned native
build and disposable execution, not current documentation alone, establish this
implementation's behavior. Source, manual merge, safe installation, exact host
launch, exact load confirmation, later accounting/disposition and actual pilot
qualification remain separate. No live operation follows source qualification.
