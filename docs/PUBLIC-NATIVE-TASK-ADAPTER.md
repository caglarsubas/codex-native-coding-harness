# Public-protocol native task adapter

`public_app_server_tasks_v1` is an explicitly selected application-owned backend,
not an automatic fallback for desktop tools. It uses public `thread/start` and
`turn/start` on a privately reviewed app-server connection. It never requests,
forwards or impersonates the packaged desktop's protected tools pipe. Vendor
signature and peer authorization checks remain unchanged.

## Separate runtime and binding review

The separate source-built macOS package and launch-only profile is described in
[PUBLIC-HOST-RUNTIME.md](PUBLIC-HOST-RUNTIME.md). Its explicit staging and owner
review do not install a binding or qualify migration; existing vendor trust,
historical evidence and same-run transition gates remain unchanged.

A newly reviewed private brain entry may contain this closed opt-in in addition
to its `policyEvidence` contract:

```json
"nativeTaskBackend": {
  "protocol": "public_app_server_tasks_v1",
  "sourceCommit": "<exact native source commit>",
  "sourceTree": "<exact native source tree>",
  "trust": "operator_reviewed_build_v1",
  "desktopBridge": "absent",
  "repositoryMode": "repo_exclusive"
}
```

The two source pins must equal `policyEvidence`'s pins. This profile is not
`standard_owned_host_v1` vendor-signature qualification. It cannot change that
launcher, substitute an ad-hoc signature for a vendor identity, launch a host,
bind a dashboard or grant Resume. Require separately reviewed build provenance,
complete runtime dependencies, executable hash, isolated private Codex home,
launch intent and process ownership, actual socket epoch and initialization
identity. Never manufacture a future socket identity. The source-built runtime
does not need protected desktop access because this backend does not use it.

The initial profile has no desktop plugin or external MCP inventory. Before
creation the adapter explicitly reads public `mcpServerStatus/list` with the
actual protocol's `detail: toolsAndAuthOnly`; any non-empty/incomplete inventory
refuses. This is a bounded runtime check, not OS attestation. Host setup must not
inherit desktop-pipe environment variables or the user's plugin/auth home.
Do not disable packaged peer checks or use a signed forwarder to bypass them.

Its isolated home also has no inherited credentials. The separate
[authentication-readiness guard](PUBLIC-HOST-AUTHENTICATION.md) checks actual
non-refreshing account metadata before future public-host brain loading/turn
start and worker creation/first turn. A healthy transport, transferred history
or matching loaded policy does not imply sign-in or model entitlement. No login,
credential copying, provider substitution or replay is part of this guard.

Only future already-confirmed notifications on this new binding retain
`nativeTaskContract` with their independently read effective-policy evidence.
An existing accepted Play keeps its original binding and unknown v1 profile.
No new contract is backfilled into it and no old claim is migrated into a send.

## Brain-led task creation

The designated brain receives its existing owner-confirmed control, acquires
the existing controller and claims a scoped standard task. Its explicit helper is:

```text
python3 -m orchestrator.cli --platform REGISTRY --workspace ID \
  standard-public-task RUN_ID COMMAND_ID TASK_ID
```

The helper carries only exact IDs, seed/context/binding/controller hashes and
its original request time in a private immutable mailbox. It reads no protected
binding or socket and returns progress immediately. Repeated calls read that
same request/reply; they neither renew it nor send again. There is no polling
dispatcher, host discovery or browser-authored RPC. A 30-second collector-start
window is not a host lease, owner approval TTL or phase-duration extension.

`standard-public-task-wait RUN_ID COMMAND_ID TASK_ID --seconds 30` provides a
bounded private progress wait for an already existing request. It never creates
a missing request, connects a socket, recollects evidence or renews a timestamp.
Pause ends waiting immediately. Public brains use this and the retained ledger
observations, not unavailable desktop `list_projects`/`wait_threads` tools.

Only the existing subscribed owned brain observer services that explicit
request. It permanently claims the query first, verifies retained source and
both project identities, repeats current brain/policy reads, and rechecks
registry/ledger authority. Its creation journal precedes the single
`thread/start`. The actual returned UUID, checkout/project, model and effort
must match; a pending ID is never promoted or used as a read target. It retains
the source starting commit, tree and Git layout, seed and exact binding.

The new thread is an independent native root assigned to the exact native
project. The graph's brain edge represents ledger responsibility, not invented
native ancestry or copied parent history. The adapter does not fork the brain.
After creation it independently reads the worker's effective policy twice.
It rechecks Pause, duration, usage/reservations, source-base drift, native
attention and cross-workspace repository/capacity ownership, then permanently
claims its first `turn/start` separately. The worker instruction is generated
from its immutable seed, not arbitrary browser/model-authored commands.

Native creation, first-turn delivery, ended-turn observation, current tracked
terminals, result preservation and completion are distinct. Late facts can be
retained after Pause without resuming authority or releasing ownership. A lost
response consumes its claim; neither stage is retried. A Pause after creation
retains that thread and refuses its first turn. An ended/failed turn never means
idle, empty terminals, successful tests, a preserved result or pilot acceptance.
Uncertain creation/turn status cannot finish through a supplied idle assertion.

After a known ended turn, that same explicitly requested observer makes two
fixed registered-worker/terminal samples and retains the existing standard
native-observation report under the current designated-brain controller. This
avoids exposing the socket to the brain just to inspect its worker. Loaded-idle
and complete current tracked-terminal evidence can satisfy the existing result
gate, not historical cleanup or source/test/artifact verification. Unloaded,
changing or interrupted reads remain unknown; no load/recollection follows.

## Qualified and unsupported scope

This first source version supports at most 16 registered tasks and only the
brain's repository in `repo_exclusive` mode. It preserves cross-workspace
exclusion and exact catalog model/effort/allowance and mission scopes. Existing
issued desktop creations cannot be adopted into it. An opted-in run refuses
ordinary `issue` and manual public-task `bind` instead of offering a fallback.
Existing strict Harness behavior and non-opted-in standard runs are unchanged.

The first consumed public creation claim marks that ledger schema v5; request
preparation, reading and installation never do. Preserve the marker across later
checkpoints/phases, never downgrade it. Older cached helpers cannot reopen v5.
Already running older writers must still be quiesced before activation: a schema
marker is not a process kill. Legacy v4-only recovery/budget/owner-closeout
adapters are not qualified for v5 by this source and must not be used as fallback.

Isolated native worktrees, producer/integration parallelism, worker continuation,
correction messaging, full worker approval relay and installed-host qualification
are **not** qualified by this source. A native server request records
`native_attention_required`; no permission response is emitted and current
terminal coverage remains unknown. Do not advertise this as a complete desktop
replacement. The existing registered-task observation/result/preservation gates
still apply before finishing a known ended task.

## Migration assessment, not a continuation permit

The separately reviewed [identity/history transfer](PUBLIC-IDENTITY-TRANSFER.md)
can preserve one actual project/brain on an empty application-owned destination
through a pinned native build extension and public path resume. Its metadata
result is not cleanup, binding cutover or same-run transition authority; none of
the following assessment gates is weakened by it.

The explicit read-only operator command is:

```text
python3 -m orchestrator.cli --platform REGISTRY --workspace ID \
  standard-public-migration-check RUN_ID CURRENT_REVIEWED_BINDING ORIGINAL_BINDING
```

Read original bytes only; never connect to the historical endpoint. Require
the exact sole receipted original Play, empty unowned paused standard run,
unchanged brain/workspace/checkout/both project IDs/native policy and no pending
controls/legacy owners/merges. Inspect only the separately reviewed current host.
Repeat native project/brain/policy and, only if loaded-idle, current complete
tracked-terminal reads. Unloaded, changing or unsupported reads remain unknown.
Recheck ledger, catalog, endpoint and enrollment afterward.

The assessment cannot install its binding, clear the original policy guard,
authorize loading, collect historical cleanup, fabricate a checkpoint or submit
Resume. It reports `migrationQualified: false` until a separate same-run
transition/evidence contract is actually reviewed and implemented. Even matching
current policy and an empty replacement tracker do not prove old cleanup. Old
Play/recovery bytes, usage/high-water/gaps and original expiry remain unchanged.

## Verification and rollout

Synthetic tests cover private request shapes, controller/seed/build/project
isolation, interrupted claims, no fallback/replay, Pause and budget races,
cross-workspace exclusion, unknown terminal/permission state, old-binding
conservation and read-only migration assessments.

The compiled-runtime fixture is opt-in and requires an exact reviewed binary hash:

```text
python3 scripts/qualify_public_native_tasks.py --executable ABSOLUTE_BINARY --sha256 REVIEWED_HASH
```

It creates one disposable project/thread and receipt-only turn in an isolated
temporary home using a loopback fake provider. It verifies real native project,
model/effort, policy, lifecycle and current-terminal response bytes through the
adapter. No real credentials, live host, cloud model or desktop pipe is used.
It does not qualify filesystem editing, permission handling, installed launch
provenance, historical cleanup, live migration or the pilot in its default
receipt-only mode. `--exercise-tools` separately verifies native `apply_patch`
of the exact disposable `RESULT.md`, a fixed `pwd` command's successful native
result and complete current fixture terminals, with three loopback responses.
That does not qualify arbitrary repository changes, worker permission relaying,
combined integration, historical cleanup or live acceptance.

Source, manual merge, installation, runtime launch/binding review, migration and
live qualification are separate. Quiesce older writers and back up private state
before an authorized installation. Do not overwrite the shared original host or
silently reconnect an ended observer. Public app-server is the documented native
integration surface; Unix WebSocket transport remains experimental, not a
production-support claim. No dependency download, hosted fallback or Actions
workflow is introduced.

## Source qualification record — 2026-10-14

The full v5-source regression ran 2,481 Python tests with one optional skip and
no failures. The subsequent bounded private-wait addition passed all 39 focused
public task/migration/schema/wait tests; all 36 JavaScript suites, 31 web syntax
checks, 117 Python AST checks and diff checks passed. No remote CI pass is claimed.

The exact compiled native candidate passed both receipt-only and tool fixtures:
one disposable project/thread/turn, matching actual policy, native patch artifact,
fixed command checkout/zero-exit result and complete current fixture terminals.
The tool fixture used three loopback responses, no cloud model request and no
desktop pipe configured/advertised. This is source/protocol fixture qualification,
not an installed runtime, approval relay, migration or pilot qualification.

The fresh pilot's read-only audit remained paused with its sole original Play,
1,049,625 recorded local tokens, unchanged original expiry, receipts and gaps,
zero worker attempts and unknown terminal safety. No Play/recovery replay,
usage reset, launch, rebind, load, Resume or acceptance occurred. PR #150 is
stacked on the still-open #149; neither source change is installed by this record.
