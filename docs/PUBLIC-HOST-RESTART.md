# Safe existing-home public host restart

For a fresh signed-in schema-1 pre-Play home without a completed transfer, use
the separate [pre-Play maintenance profile](PUBLIC-PREPLAY-HOST-RESTART.md).
The transferred-run profile below remains unchanged and refuses credentials.

`public_existing_home_restart_v1` is separate operator maintenance. It fixes the
empty-home launch dead end without replaying launch, transfer, Play or recovery.
The original `public_app_server_host_v1` gate is unchanged. This is not automatic
restart, a boot service, dispatcher, thread load or same-run continuation permit.

## Preconditions and conservation

Require one completed exact public identity transfer, its original issued public
exec journal/claim, the same reviewed monolithic package, and the unchanged empty,
unowned, paused schema-v4 standard run. Both project IDs, catalog mapping, brain,
checkout, original Play, commands, usage/high-water/gaps, checkpoint and expiry
stay pinned. Pending/unknown ownership or transfer cannot use this path. Expiry
stays expiry; process absence never proves terminal/effect cleanup.

The canonical owner-private home must be disjoint from checkout/package/new
socket/review paths and outside shared `~/.codex`. Only bounded native state,
sessions, embedded system skills and native lock/arg0 trees are supported.
Credentials, dotenv, plugins and unknown top-level entries refuse before their
contents are opened. No shared home, credential store or provider is copied.
No native database, lock, config, permission or receipt is repaired/deleted.

Keep the full restricted base config: workspace-write, on-request/user review,
Code Mode/network off, no hooks/apps/plugins or inherited shell environment,
file-only unconfigured credentials. The new existing-home profile may preserve
Codex's already saved `projects.<exact checkout>.trust_level = "trusted"` entry.
No other project/config key is supported. The adapter never adds this metadata:
the new owner review pins its exact bytes/epoch. This is not independent policy
verification or new repository authority. The initial empty-home profile still
requires its byte-exact config without this metadata.

Preparation repeats fixed predecessor-PID absence, a bounded process inventory
excluding matching/ambiguous package processes, and scoped `lsof +D` reads with
no open home handles. Error, stderr, partial data or timeout is unknown and
refuses. These are bounded quiescence observations, not complete-tree cleanup.
The native server's startup coordination is never bypassed.

Twice inventory the whole supported home and copy it into an exclusive private
review directory. Preserve opaque SQLite main/WAL/SHM bytes without SQL reads or
edits. Fsync all files/directories, verify the complete backup, then repeat source,
context and process checks. This is a byte backup, not native semantic attestation.
Refuse hard links, special files, unsafe ancestors and unbounded trees. Retain
only arg0 helper symlinks targeting the pinned binary; never follow/execute them.

## Exact review and one exec

All commands select the exact private platform/workspace explicitly:

```text
python3 -m orchestrator.public_host_restart --platform PRIVATE_PLATFORM --workspace WORKSPACE prepare PREVIOUS_EXEC_ATTEMPT COMPLETED_TRANSFER_DIRECTORY NEW_EMPTY_SOCKET_DIRECTORY NEW_PRIVATE_REVIEW_DIRECTORY
python3 -m orchestrator.public_host_restart --platform PRIVATE_PLATFORM --workspace WORKSPACE preview PRIVATE_REVIEW_DIRECTORY/restart.json
python3 -m orchestrator.public_host_restart --platform PRIVATE_PLATFORM --workspace WORKSPACE exec PRIVATE_REVIEW_DIRECTORY/restart.json --confirm-hash EXACT_NEW_REVIEW_HASH
```

The profile/mode/source-tree/snapshot/context-bound review has no reading-time
countdown. Any scope drift invalidates it. Generic assent, old launch approvals
or transfer/recovery reviews do not confirm it. Preparation and polling start
nothing. Source delivery installs, launches, binds and confirms nothing.

An exact new owner confirmation commits an exclusive intent, canonical
ledger-side restart fence and exec claim before final checks and same-PID
`execve`. Only the pinned binary, fixed Unix listener argv and original closed
environment are used. No desktop pipe, key, proxy, preload or fallback is passed.
Record PID and birth epoch. Drift, interrupted persistence and failed/unknown
exec retain consumed claims. Another directory, touched journal, socket or
proposal cannot resend the same predecessor's restart.

A later genuine host exit may name that issued restart's own attempt as the
predecessor, never its ancestor. A bounded cycle-free chain checks each issued
intent/claim/fence, preserved backup and predecessor-PID absence. Each distinct
process epoch gets a fresh exact review/fence; failed or unknown exec is not
successor authority. Old implementation pins are historical, not permission to
execute old code. The current clean source is always pinned for a new exec.
This version supports at most eight provenance nodes and the same original
paused transfer scope; it does not migrate phases or packages.

The foreground context must still outlive the host. This fixes explicit safe
same-home restart, not survival across desktop exit or a silently installed
detached supervisor/launchd service.

## Separate read-only connectivity

```text
python3 -m orchestrator.public_host_restart --platform PRIVATE_PLATFORM --workspace WORKSPACE inspect PRIVATE_REVIEW_DIRECTORY/restart.json NEW_PRIVATE_EVIDENCE_DIRECTORY
python3 -m orchestrator.public_host_restart --platform PRIVATE_PLATFORM --workspace WORKSPACE status PRIVATE_REVIEW_DIRECTORY/restart.json
```

Inspection requires the issued claim, matching live PID/birth/argv/cwd, unchanged
protected records/config/history prefix and a new actual socket epoch. Never
connect an old endpoint. The closed proxy repeats exact project/brain/latest
ended-turn metadata and complete empty MCP inventory, reads effective policy
without loading, and checks `account/read` with `refreshToken: false`. It saves
separate connectivity evidence and a candidate binding, not a dashboard cutover
or ledger receipt. A file-only status read reconnects/renews nothing.

Transport, membership, loaded policy, sign-in and model access are separate.
An unloaded brain's policy/current terminals remain unknown: no inspection load
is granted. Missing sign-in never triggers credential copying, login, refresh or
provider substitution. Restart/inspection change no original policy evidence,
usage/gaps/expiry, checkpoint, ownership, Play, recovery or pilot acceptance.
All current/historical terminal and effect safety remains unknown. Subsequent
binding, eligible preparation, closeout, mission review and Play remain separate.

## Qualification

Run the full local Python/JavaScript suites plus syntax and diff checks. The
focused tests cover conservation, aliases, config/identity drift, budget/Pause
races, exact approvals, permanent claims, interruption, lineage, PID reuse,
closed metadata methods, authentication privacy and unknown status. No Actions
or paid service is introduced.

`scripts/qualify_public_host_restart.py --executable REVIEWED_BINARY --sha256 REVIEWED_HASH`
uses only a new disposable home and loopback-only argv provider override. One
cold receipt creates real history; the warm native process reopens the same home
over a new real Unix transport with exact project/brain/ended-turn/history
agreement and zero warm loads, turns, write RPCs or model requests. It preserves
native same-checkout trust metadata and the restricted base. The override is
fixture-only: the live launcher has no provider override path. Fixture success
is not live connection, sign-in, migration or pilot qualification.
