# Forward-only successor of an exited pre-Play host

`public_preplay_successor_restart_v1` is a distinct operator maintenance review,
selected only by `prepare --successor`. The original version-1 repair remains
initial-launch-only; no existing review, approval, journal or failed attempt is
converted. This path handles a later genuine exit of an already issued fresh
pre-Play restart, not replay of its ancestor or durable service supervision.

## Closed lineage and unchanged scope

Follow at most seven issued restart nodes plus the original public launch.
Reject cycles, missing intents/exec claims/status, failed/unknown exec, changed
file epochs, archives or permanent predecessor fences. Each node must retain its
exact kind/spec/review hashes, issued PID/birth identity, original private binding
and verified non-credential archive. Old source pins remain historical evidence;
only the new clean current implementation may execute a new review.

Require repeated fixed absence of every exact predecessor PID, then the existing
bounded binary/home-handle quiescence checks. Never kill, reconnect, unlink a
socket, repair a native store or treat absence as process-tree cleanup. The exit
cause remains unknown unless independently observed; this is not a TTL fix.
An `exec_boundary_issued` journal is not independent proof of prior native
health or successful execution. Those facts and all old effects remain
unqualified; the new review authorizes only a separate launch after quiescence,
not an acknowledgment or successful reclassification of the old attempt.

Use the original binding to validate the unchanged registered brain, dual native
project IDs, checkout, restricted policy, public task/policy build, reviewed
mission, original ended readiness requests and real canceled disposition. Keep
the original registry/ledger fingerprints and every earlier captured sidecar
unchanged. Later private inspection records may be included in the new exact
review; they never grant another inspection load. A readiness-owned intent,
new/changed command, active phase, admission, Stop, workers, permission request,
controller or runner fences this narrow first-phase maintenance path.

The current saved binding may differ only in endpoint metadata: its complete
brain record, package executable and hash must match the original. Pin both
private binding files. This is not native attestation that a dead endpoint was
healthy, and neither endpoint is connected during preparation. A future live
candidate binding still requires fresh native identity/policy/authentication
qualification and a separate exact cutover review.

## New review, one launch

```text
python3 -m orchestrator.public_preplay_host_restart --platform PRIVATE_PLATFORM --workspace WORKSPACE prepare --successor ISSUED_RESTART_ATTEMPT CURRENT_SAVED_BINDING NEW_EMPTY_SOCKET_DIRECTORY NEW_PRIVATE_REVIEW_DIRECTORY
python3 -m orchestrator.public_preplay_host_restart --platform PRIVATE_PLATFORM --workspace WORKSPACE preview NEW_PRIVATE_REVIEW_DIRECTORY/restart.json
python3 -m orchestrator.public_preplay_host_restart --platform PRIVATE_PLATFORM --workspace WORKSPACE exec NEW_PRIVATE_REVIEW_DIRECTORY/restart.json --confirm-hash EXACT_NEW_REVIEW_HASH
```

The new version-2 manifest uses the existing closed field set with a distinct
kind, current scope and complete ancestor pins. Source, scope, current home,
credential metadata or binding drift invalidates its until-scope-changes review;
there is no reading-time countdown. Preparation copies only the existing bounded
opaque non-credential state/history into a new private verified archive.
`auth.json` is metadata-only and remains in place, unopened, unhashed and uncopied.

The canonical new claim is keyed to the exact last issued process epoch/spec,
not the review directory, new socket or source revision. Unrelated or partial
restart claims refuse. Preserve every ancestor claim. New socket/review paths
must be disjoint from all predecessors. Intent, canonical claim and exec claim
precede final repeated validation and the same fixed closed-environment exec.
Partial persistence, drift or uncertain/failed exec permanently consumes it.
Only another genuinely issued, later exited process can have a successor; a
new request ID, directory, timestamp or old approval cannot reset the attempt.

No load, turn, model/login request, native permission response, binding change,
readiness/Play/recovery replay, usage reset, receipt, cleanup, release, checkpoint
or pilot acceptance follows. Current and historical terminal safety stay unknown.
The foreground execution context must outlive the host; no detached process,
automatic restart, model keepalive, launchd service or scheduler is installed.

## Qualification and rollout

Disposable tests cover one and multiple issued ancestors, legacy exclusion,
failed/partial claims, exact approval, fixed exec, PID/home quiescence, source and
binding drift, backup/auth metadata, immutable inspection claims, foreign restart
fences, ancestor replay, cycles/depth, socket reuse and post-claim races.

```text
python3 scripts/qualify_public_host_restart.py --signed-in-preplay --successor-preplay --executable EXACT_BINARY --sha256 EXACT_HASH
```

This compiled fixture reopens a separate temporary home twice after actual owned
process exit. A single cold loopback receipt establishes history; both warm hosts
perform zero loads, turns or model requests. Only synthetic empty auth metadata
is used. It qualifies native same-home reopen behavior; lineage journals and
claims are covered separately by unit fixtures, not live trust/account/pilot
qualification. No live host connection, credentials, Actions or paid service is
used. Run the full local Python/JavaScript and syntax suites before delivery.

Source, manual merge, installation, exact launch review, launch, connectivity,
binding cutover and readiness confirmation remain separate. Stop older writers
and back up private state before installation. Source delivery prepares or
confirms no live launch review and accepts no pilot.
