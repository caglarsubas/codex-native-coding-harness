# Separate forward-planning control and replacement-host review

This is source, not installation or live authority. Read the original
[canceled-Play disposition](CANCELED-PLAY-DISPOSITION.md),
[no-reload transport](NO-RELOAD-TRANSPORT.md) and
[existing-home restart](PUBLIC-HOST-RESTART.md) contracts first. None of their
ordinary gates is relaxed. Strict Harness and arbitrary held controls are outside
this path. A canceled Play never receives a retroactive brain receipt.

## Exact scope

`orchestrator.canceled_continuation` implements a separate operator-reviewed
**forward-planning** turn, not Resume, worker dispatch or a repeated Play. It
requires the complete separately confirmed disposition of the exact empty,
unowned, canceled/interrupted standard Play. `retained_in` validates every original
row and sidecar. The new journal lives under the registry, outside the original
ledger; the checkout-local data mailbox also stays outside that ledger. Original
requests, missing receipts, run, claims, captured effects, usage/gaps, repository
holds, expiry and binding bytes/epochs remain immutable.

The candidate binding file is a separate reviewed input, never installed over the
old binding. It pins one exact source-built package, private endpoint, brain,
checkout, both project IDs and restricted policy. No capability is inherited from
the old binary. A source/client/interpreter/package change invalidates review.
Review validity is scope-bound, not a short approval timer; actual evidence
freshness and the original phase clock still apply.

The original registered-session usage report must already have its matching
retained snapshot, known cumulative brain/total/high-water values, no reported
coverage gaps and a collection age below 120 seconds at the send boundary. A
local registered-session measurement is not billing, provider or full descendant
coverage. The explicit planning allowance (1–100,000 tokens) must fit the unchanged
brain allocation, total phase allocation and checkpoint reserve. It is a
cooperative one-turn ceiling, not a provider-enforced billing cap. Missing usage
cannot become zero, and neither this control nor polling refreshes the old usage
report or extends an expired phase.

## Claim, subscription, receipt and proposal

Preparation and backup are local-only. Confirmation requires a new exact hash,
quiesced writers and verified private registry/ledger/claim/binding/capture
backups. A canonical original-command/database-identity directory is exclusively
claimed before native I/O. A new review directory, ID, source revision or failed
attempt cannot reset it.

On the same pinned connection, repeated metadata reads require the exact original
interrupted turn still latest, an already-loaded idle brain, actual restricted
policy with Code Mode disabled and a complete known-empty **current** tracker.
Unknown is not empty. Claim subscription before the one experimental
`thread/subscribe`; check metadata again, then claim before the one new
`turn/start`. There is no `thread/resume`, reconnect, permission response,
cancellation, discovery or alternate endpoint fallback. Native loaded lookup and
subscription serialize against unload. Current tracker emptiness never attests
historical effects, descendants or cleanup.

The server constructs the fixed planning instruction and pins its data-client
argv. The brain can explicitly `receive`, then retain only a bounded inert
`{summary,nextSteps}` proposal through its checkout mailbox. The original observer
checks every request against preserved local scope and its same connection,
claims each operation once and retains its own new receipt/result. The sandbox
never receives the registry, database, controller credential or protected socket.
The original Play and all standard dispatch routes remain fenced.

Completion requires the exact new native turn to complete **and** both explicit
new receipt and proposal records. Native acknowledgement or a final chat message
alone is not a receipt. A native permission/server request ends observation as
attention-required without answering it. Lost/uncertain delivery, source drift,
owner stop, expiry or partial journals remain consumed and unknown. The explicit
stop file sends no native cancel. Status is file-only and validates retained
receipt/result pins; it never reconnects, replays or collects new native evidence.
No successful planning result is worker completion, phase acceptance or terminal
safety.

Operator entry points (all paths are exact private canonical inputs):

```text
python3 -B -m orchestrator.canceled_continuation --platform PLATFORM --workspace WORKSPACE prepare ORIGINAL_BINDING ORIGINAL_PLAY CANDIDATE_BINDING TRANSPORT_CONTRACT --max-tokens N
python3 -B -m orchestrator.canceled_continuation --platform PLATFORM --workspace WORKSPACE backup REVIEW NEW_BACKUP --writers-stopped
python3 -B -m orchestrator.canceled_continuation --platform PLATFORM --workspace WORKSPACE confirm REVIEW --confirm-hash EXACT_NEW_HASH --backup NEW_BACKUP --writers-stopped
python3 -B -m orchestrator.canceled_continuation --platform PLATFORM --workspace WORKSPACE status REVIEW
python3 -B -m orchestrator.canceled_continuation --platform PLATFORM --workspace WORKSPACE stop REVIEW --confirm-hash EXACT_NEW_HASH
```

The first command prints a bounded preview; save its `request` privately for the
remaining commands. The operator-only path does not add a second dashboard
dispatcher, change installed skills or automatically confirm a chat preview.

## Replacement host is a distinct launch-only review

`orchestrator.canceled_host_review` may prepare a new binary on the original
isolated signed-in home after the exact original host has genuinely exited. It
pins the original canceled attempt even before a separate disposition is applied;
launch review does **not** apply that disposition. Validate the entire issued
pre-Play host lineage, original package/brain/checkout/dual IDs and retained binding,
all prior launch claims and archives, repeated fixed PID absence, exact binary
process inventory and no open home handles. These prove only maintenance
quiescence, never descendant cleanup or terminal safety.

Require a distinct complete reviewed package and disjoint new private socket and
review directories. Back up bounded native non-credential state opaquely.
`auth.json` is metadata-pinned in place: never opened, hashed, decoded or copied.
Foreign history, unsupported files/plugins/config, changed credential epoch,
aliases, archive drift or unknown writers refuse. A clean exact source tree and
all old/current pins are rechecked at preview and exec.

The exact new owner hash permits only a foreground same-PID exec of that binary
with the unchanged isolated home and a new private socket. The permanent claim is
outside the old ledger and keyed to its identity plus last issued process epoch,
so changing directories/packages cannot reset it. Unknown or interrupted exec is
consumed. No detached fallback, host probing, sign-in, native read, brain load,
turn, binding change, Play, recovery, Resume or pilot acceptance is included.

```text
python3 -B -m orchestrator.canceled_host_review --platform PLATFORM --workspace WORKSPACE prepare PREVIOUS_ISSUED_ATTEMPT ORIGINAL_BINDING ORIGINAL_PLAY NEW_PACKAGE NEW_EMPTY_SOCKET_DIR NEW_REVIEW_DIR
python3 -B -m orchestrator.canceled_host_review --platform PLATFORM --workspace WORKSPACE preview REPLACEMENT_JSON
python3 -B -m orchestrator.canceled_host_review --platform PLATFORM --workspace WORKSPACE status REPLACEMENT_JSON
python3 -B -m orchestrator.canceled_host_review --platform PLATFORM --workspace WORKSPACE exec REPLACEMENT_JSON --confirm-hash EXACT_NEW_HASH
```

Preparing this review grants no launch. The review has no timer expiry; scope
changes invalidate it. Connectivity, a separately reviewed candidate binding,
actual loaded state and a new planning control are later evidence/authority steps.
A replacement process cannot resurrect the exited process's in-memory brain.
If the stored thread is unloaded, the no-reload planning control must refuse.

## Native ended-turn predicate repair

The supplemental native patch in
`native-patches/subscribe-ended-turn-status.patch` fixes a specific subscription
guard: native history retains interrupted turns, and `active_turn_id()` also
falls back to finished history. ID presence is not activity. The guard now tests
an explicitly `inProgress` metadata status, alongside the unchanged native idle,
agent-state and unload-lock checks. This does not infer current/historical cleanup
from an ended turn. It is an operator-reviewed experimental build, not stock
public API support, vendor desktop trust or a policy exception.
The patch uses zero-context hunks; apply/check it against the pinned predecessor
source with `git apply --unidiff-zero`, not an arbitrary newer vendor checkout.

The qualified replacement source is commit
`cd935163b03fbbe3d26a464be5c199a31011b120`, tree
`26323f8f8aea3827361be30d75826551c61277e8`. Its monolithic macOS ARM64
executable SHA-256 is
`f7129d8763a45268aaa136b3a50de20acfcb6e07458a672d6c253d6d727f2ec9`;
the private complete source bundle SHA-256 is
`75afedbcf75dd35cd4ffa489cbf3850747be1e5b6762ba9ef8fdc2381e981021`.
The existing Rust toolchain/dependencies were used offline. The intact ad-hoc
signature is file-integrity provenance, not vendor desktop peer trust or a
reproducible-build attestation. No live executable was replaced.

## Qualification and live limits

Unit fixtures cover receipt/result correlation, source/package/identity drift,
wrong confirmation/backup, canonical consumed claims, lost acknowledgement,
native permissions, unknown usage, original expiry, owner-stop and latest-turn
races. Host fixtures verify credential non-reading, archives, package separation,
old claims, one exec boundary and no automatic retry or connection.

`scripts/qualify_canceled_continuation.py` combines the actual production control
with a compiled disposable native Unix host and a real sandboxed receipt/proposal
helper. The old ledger is explicitly synthetic; its native identity matches a
genuinely canceled fixture turn. All model responses come from a labelled
loopback fake. This is not live usage/effect attestation or a real worker pilot.
The separate existing-home fixture proves a warm host reads persisted metadata
without loading it or sending a second model request.

Source qualification, PR/manual merge, installation, launch review/confirmation,
connectivity, binding review, disposition and continuation remain separate steps.
The live v3 original host is absent, its usage is not measured, and its no-reload
and terminal-safety constraints remain intact. Source delivery prepares a host
review only; it does not make the pilot complete or start development.
