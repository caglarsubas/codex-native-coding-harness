# WSP-04F — bounded native evidence collection

Plan saved before implementation on PR #45 merge
`6566d9e7731f1761707dc2f61829916a62dc0c21`.

## Scope and capability finding

Milestone 3 needs real task-tree, host-cleanup and cumulative token evidence.
The existing desktop tools do not expose all those facts. The official
[App Server reference](https://learn.chatgpt.com/docs/app-server) documents
metadata-only thread reads, descendant listing and background-terminal inspection.
The installed CLI's generated schema also distinguishes configured model/effort
from per-turn execution telemetry. Token update events are not a retrospective,
non-resetting per-task lifetime counter API.

This increment implements collection of available metadata through the installed
CLI's documented `app-server proxy --sock` interface to an explicitly reviewed
existing local server. It does not start a server, subscribe/resume a task, execute
a turn, read private Codex databases/logs, or make a model call. No automatic
endpoint discovery, default socket, private protocol, remote host or fallback.
Source/schema checks are not live endpoint qualification.

- [x] Add internal owner review/revoke for an exact private socket and executable
  fingerprint; no brain/public owner route or activation.
- [x] Bound a one-shot JSON-RPC proxy to metadata-only read operations, deadlines,
  byte/page/task limits and strict response IDs. Reject requests from the server;
  retain no raw conversational fields, terminal commands or error bodies.
- [x] Collect exact phase-owned roots and connected descendant metadata, archived
  and non-archived pages, configured settings and tracked terminal identities.
  Re-read topology/status for drift; do not claim an atomic or complete task tree.
- [x] Retain immutable, context-bound reports with original observation times,
  historical replay and actionable capability gaps; no accounting promotion,
  ownership release, model-setting application or execution permit.
- [x] Expose designated-brain plan/collect/state commands, qualify races and
  malformed/partial observations in isolated fixtures, and run local regressions.

## Explicit limits

Persisted descendant listings cannot prove all ephemeral/unreported descendants.
Empty tracked-terminal lists cannot prove OS process-tree exit or resource cleanup.
Configured settings cannot prove the model used for every turn. Account percentages,
goal counters and dashboard rollout aggregates cannot supply phase lifetime tokens.
Reports therefore keep complete tree/cleanup/counter/telemetry claims false and
leave admission, settlement and model-policy guards unchanged. Unknown fields are
not zero, idle, applied or complete. Milestone 3 remains open pending a qualified
source for those missing facts; do not decrement the completion estimate merely
because this collector merges.

No live endpoint is connected or reviewed during this coding run. No installed
skill, dashboard, schedule, native task, allocation, private ledger, credential,
maintenance fence or model setting is changed. Local verification only; no Actions
workflow, runner or paid API. Harness refuses before endpoint/file access.

## Source qualification performed

Inspected `codex-cli 0.155.0-alpha.9.2` help and generated its experimental JSON
schema into a temporary directory, without starting a server or connecting to a
live endpoint. This is a public experimental protocol, not a production-support
claim. Qualification must be repeated for the separately approved deployed host.

| Generated schema | SHA-256 |
| --- | --- |
| ThreadReadParams.json | `dfe040c6ac71d30795b8be3f3ff232e66f362a37f883b491e5d1ea367f470db4` |
| ThreadReadResponse.json | `d685105cfc1430330376770fd05616814b30d2ecbc3e590780a90a66fdd36bc3` |
| ThreadListParams.json | `5daf371b2852c409d4405c95f79cddb2d92a1ee89da808b2c5112ef16a57432c` |
| ThreadBackgroundTerminalsListResponse.json | `b56b1cbcb1d60079ee9f9caaeef29cad869a25b4a6d356566f7c9f672faa7bf4` |

No generated full schema, local native IDs, socket path, home path, conversation,
credentials or logs are published. The public reference supports the selected
methods; the generated schema supplies exact locally available parameter shapes.

## Owner setup boundary

The initial WSP-04F kernel had no owner HTTP route. WSP-04H now adds authenticated
[owner controls in Run readiness](NATIVE-OBSERVER-CONTROLS.md) for inspection and
signed review/revoke confirmation only. There is still no owner CLI, assistant
action or public collection route. Trusted owner code may call `review_endpoint` while dispatch is
paused, for an exact existing standard-policy allocation. Its request has `id`,
`expectedRevision`, `allocationId`, `endpoint` and explicit `confirmed: true`.
The actor string is a trusted caller label, not authentication. The owner adapter
checks session/CSRF, scope and exact version-bound confirmation; the brain cannot review
or revoke its own endpoint through its CLI.

The endpoint is the exact result of the internal, non-connecting
`inspect_endpoint(executable, socket_path, server_identity_hash)` inspection:

- Canonical absolute executable path, bounded regular executable bytes and SHA-256.
- Canonical existing Unix socket in a private directory; device, inode, owner,
  mode and change time are pinned. Paths cannot contain symlinks, and unsafe
  ownership/write permissions refuse. A normal socket replacement needs new review.
- Expected digest of the independently observed initialization identity object:
  `userAgent`, `platformFamily`, `platformOs`, `codexHome`. Keep the original home
  private; only the identity digest is retained. This is consistency checking,
  not cryptographic host attestation or protection from a malicious same-user host.

The endpoint record binds allocation fingerprint, workspace and brain. Revoke
uses exact `endpointHash`, `id` and `expectedRevision`. Historical review replay
cannot undo revocation. Missing/rolled-back records require explicit recovery.
Review authorizes only this bounded read path, not tasks, model calls, usage
baseline changes, run activation or release of any maintenance/ownership fence.

## Brain CLI

Use the existing designated controller token in its environment, never in files,
prompts, logs or command arguments. An already initialized registry, selected
workspace and allocation are required; reads never initialize them.

```sh
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace EXACT_WORKSPACE native-evidence-plan ALLOCATION_ID
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace EXACT_WORKSPACE native-evidence-collect ALLOCATION_ID PRIVATE_REQUEST_JSON
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace EXACT_WORKSPACE native-evidence-state ALLOCATION_ID
```

Plan/state never connect. Collect requests contain exactly `id`, `expectedRevision`,
`expectedHash`, `contextHash`, `endpointHash`; use the bindings returned by plan.
The JSON file is limited to 16,000 bytes with the existing strict regular-file,
duplicate-key and finite-JSON checks. It cannot contain targets, RPCs, paths,
credentials, arbitrary commands, native mutation options or owner approval.

Collection derives roots from the allocation and confirmed native ownership, not
titles/cwd. Pending IDs and foreign workspace brains/roots cannot become query
targets. Non-archived and archived descendant pages must have terminating explicit
cursors; parent chains must reach the exact owned root. Previously known tasks
cannot silently disappear. Two metadata passes detect drift but are not a lock or
proof of complete ephemeral task coverage.

The child command is exactly the reviewed executable plus `app-server proxy
--sock` and the reviewed socket. No shell, default endpoint, auto-start, daemon,
network listener, model provider, or arbitrary RPC fallback is present. After
identity-checked initialization, only metadata-only `thread/read`, exact scoped
`thread/list` with `useStateDbOnly: true`, and `thread/backgroundTerminals/list`
are sent. Inherited API keys and the controller token are not passed to the proxy.
Notifications are discarded. Server requests, errors and mismatched response IDs
refuse; they are never answered as approvals or retried with mutation methods.

Bounds: 15-second proxy deadline, 128 RPCs, 8 pages per list, 8 owned roots,
64 total task samples, 1 MB response buffering and 8 MB total output. Bounds are
ceilings, not a guarantee that every combination fits the RPC/report budget.
Socket/executable pins are checked before and after reads. Only the owned proxy
process is terminated at cleanup; the native server/tasks are never stopped.

## Retention and interpretation

Collection releases ledger locks during I/O, then rechecks revision, phase scope,
endpoint review and latest report before atomic retention. Pause/revocation or
scope changes during I/O prevent commitment; they cannot atomically cancel an
already in-flight read. A newly requested safety collection while paused may
record facts without resuming work. Exact replay returns the old receipt without
reconnecting or refreshing timestamps. A failed new collection retains an empty,
unavailable report instead of falling back to an older apparently healthy snapshot.

Reports retain bounded task identity/ancestry/status, configured model/effort,
loaded-versus-persisted setting provenance, hashed tracked-terminal identities,
source digests and observation times. Preview, transcript, command, cwd, PID,
rollout path, server home and native error text are excluded. Reads expire after
60 seconds without updating their clocks. `notLoaded` is unknown, never idle.
Stable repeat reads are not proof of complete inventory, cleanup or counters.

Nothing in this report is promoted into existing lifecycle, accounting, model
application, settlement or acceptance records. All four capability gaps remain
explicit even when every metadata query succeeds. Reports are private diagnostic
artifacts, not native execution permits or ownership release receipts.

## Next qualification decision

To finish milestone 3, qualify a host-owned observation source covering complete
task/descendant membership, non-resetting full-lifetime counters with brain phase
baseline, and whole-process-tree cleanup. Do not substitute account usage, mutable
goals, partial rollout metrics or empty tracked terminals. A live source/installation
needs its explicit owner scope; no additional helper PR can manufacture that evidence.

## Local verification

- Full Python suite: **1,230 tests passed** in 414.375 seconds, including 31 new
  collection/proxy tests. The focused evidence/supervision/usage/model/coordinator
  suite separately passed 169 tests.
- All seven JavaScript UI test files and `node --check web/app.js` passed.
- Real subprocess round trips used temporary fake executables, sockets and ledgers;
  no live native endpoint or model service was connected.
- Read-only repository checks found zero Actions workflows and zero workflow runs.
  These are local test results, not hosted CI, live operation or acceptance evidence.
