# Owned standard-brain wake — source boundary

The legacy `codex queue` acknowledgment proves that a message was stored, not
that an unloaded desktop brain began a turn. This opt-in transport uses the
[documented Codex app-server protocol](https://learn.chatgpt.com/docs/app-server)
on a separately owned, already running local host. It is for registered
all-standard projects only. The dashboard remains a ledger and notification
client; the designated brain is still the only scheduler.

Binding configuration is not host health. Separate handshake checks, in-place
review renewal and an opt-in operator supervisor are documented in
[host lifetime and review recovery](HOST-LIFETIME-AND-REVIEW-RECOVERY.md).

Received pre-phase messages whose native turns ended without a retained reply
have a separate [receipt-only recovery](RECEIPT-ONLY-RECOVERY.md) control.
It uses this same bound bridge and one-shot claim, not a diagnostic replay,
generic reconciliation wake, or substitute for activated-phase recovery.

## Contract

- The saved, allowlisted dashboard control is claimed in SQLite before any
  native call. Browser text, target, settings and arbitrary methods never cross
  this bridge. A duplicate request or process restart cannot send it again.
- A private operator binding pins the installed executable, existing Unix
  socket identity, expected app-server initialization identity, each exact
  brain UUID, app-server project ID and checkout directory. When the Codex app
  project catalog uses a different ID for the same project, the binding must
  additionally pin that distinct `catalogProjectId`; the two IDs are never
  inferred from a matching name or directory. No socket discovery, host start,
  runtime download, desktop IPC, remote listener or fallback to the desktop
  queue is permitted. The binding is loaded only at dashboard startup.
- The binding also pins `nativePolicy` to workspace-write sandboxing,
  on-request approvals and Code Mode disabled. Every owned `thread/resume`
  reapplies those exact settings before `turn/start`; an inherited
  danger-full-access/never context can otherwise run an escalated command
  without an app-server approval event. The installed app-server schema lets
  `kind: command` and `environmentId: null` be omitted, so the bridge accepts
  those defaults only when the other scoped fields are complete. The host may
  offer a persistent exec-policy amendment alongside a one-command `accept`;
  the bridge validates the bounded proposal but never sends the amendment or
  session-wide acceptance decision. Missing or changed policy fails closed at
  binding load. This does not authorize a command or approval, and it requires
  separate host qualification before live use.
- Unix app-server sockets use a WebSocket upgrade and text frames, even through
  the fixed `app-server proxy --sock` byte transport. The endpoint must pin the
  canonical socket itself: the CLI's `--listen unix://PATH` may leave `PATH` as
  a symlink to a private daemon socket, and the symlink is deliberately refused.
- `thread/read` must match brain ID, project ID and cwd. `idle`/`notLoaded`
  use `thread/resume` with `excludeTurns: true`, then one `turn/start` with the
  fixed ledger pointer and bound cwd. An already `active` brain is refused before delivery: queuing
  behind its turn would lose this client's approval subscription. A competing
  native turn or lost response is uncertain, not a reason to resend.
  Resume needs metadata and live loading state, not conversation history. The
  installed public schema supports this flag for paginated history as well as
  legacy threads. Missing `turns` or an empty array is permitted in the resume
  response; nonempty or malformed `turns` refuses before `turn/start`. A host
  rejecting the flag fails closed without a full-history fallback or second
  resume. This does not alter the pinned native policy or one-shot claim.
- The app-server subscription is retained through the owned turn. A bounded
  command/file-change approval prompt can appear in the brain inspector, with
  the exact request and one-time accept/decline/cancel choices. The dashboard
  signs a two-minute owner preview bound to the exact ledger revision and
  journals the decision claim before
  answering on that same native connection. It never approves automatically,
  grants session-wide permissions, or sends an unsupported/partial prompt as
  an approval. Acceptance requires a running, unblocked standard phase and
  checkout-bound command/file paths; an exact native permission response does
  not expand the reviewed mission, task or repository scope. The owner still
  evaluates the complete command or change semantics in the exact prompt; a
  syntactically valid path is not semantic safety evidence. The raw prompt is
  ephemeral and owner-only, excluded from the
  inference payload and durable ledger. An expired, resolved, uncertain or
  unsupported prompt fails closed; there is no automatic resend. Other native
  user-input and security requests still require attention outside this relay.
- `accepted` means app-server returned a turn ID. Neither is the brain's ledger receipt, safe checkpoint,
  worker dispatch, result acceptance or proof of turn completion.
- If an exact Brain Stop has been received but remains `checkpointing`, an
  authenticated owner may submit one `brain_checkpoint_continue` control bound
  to that stop command ID. It uses the same durable notification claim and
  owned app-server transport. The brain receives only the existing stop; this
  does not Resume, reopen dispatch, drain ordinary messages, or authorize new
  work. A parked or superseded stop cannot be continued; a queued continuation
  is rejected if that checkpoint parks or a newer brain control supersedes it
  before delivery. Repeated attempts need new explicit owner review and can
  never resend an earlier claimed wake.

## Separate activation review

### Delivery diagnostics are not recovery authority

New failed owned-host notifications retain a closed `nativeFailure` record:
the failed step, a bounded reason, whether `thread/resume` and `turn/start`
were attempted, and a reserved JSON-RPC error code when supplied. Native error
messages, error data, paths, prompts and environment values are not retained.
The dashboard shows these facts under **Details · Failed delivery step** in
control history, brain messages and answered decisions. A returned turn ID
survives a later observer-start failure, but its outcome remains unconfirmed.

A pre-`turn/start` failure is not necessarily pre-resume: the brain may have
been loaded or its restricted settings reapplied. An `unavailable` result does
not authorize a second send, queue fallback or a new control. The durable
notification claim stays consumed. `uncertain` still means a turn may have
started; neither a current successful handshake nor read-only thread metadata
reconstructs a missing receipt or checkpoint.

Older generic failures have no step record. Do not infer their stage from a
new health check or backfill a guessed cause. This source change does not
repair historical native effects, install a host, replay a saved Pause, change
usage coverage or qualify the pilot.

### Installation boundary

Source delivery leaves the current dashboard and brain unchanged. A later
owner-reviewed migration must first quiesce the old dashboard writer and
notification route, then verify a private owned app-server is running, its
capabilities and native prompt handling, the brain task's native project and
checkout, installed skill/runtime compatibility, unresolved sends, controller
and worker state, and a safe checkpoint. Never run the old desktop-queue route
and this route simultaneously for the same ledger. A disposable project pilot
must establish a real start, ledger receipt, pause, restart, ambiguity recovery
and native approval behavior before selecting the live brain. Switching the
server option alone is not live qualification or permission to Play.

The startup option is mutually exclusive with `--notify-brain`:

```text
serve --brain-app-server-binding /absolute/private/brain-wake.json
```

The file is owner-only (`0600`), outside source control, and has exactly:

```json
{
  "endpoint": {
    "executable": "/absolute/installed/codex",
    "sha256": "<reviewed executable SHA-256>",
    "socket": "/absolute/private/owned.sock",
    "socketIdentity": {"device": 1, "inode": 2, "owner": 501, "mode": 384, "changedNs": 1},
    "serverIdentityHash": "<reviewed initialization identity digest>"
  },
  "brains": {
    "11111111-1111-4111-8111-111111111111": {
      "workspaceId": "exact-registered-project",
      "projectId": "22222222-2222-4222-8222-222222222222",
      "catalogProjectId": "33333333-3333-4333-8333-333333333333",
      "nativePolicy": {"sandbox": "workspace-write", "approvalPolicy": "on-request", "codeMode": false},
      "cwd": "/absolute/exact/brain/checkout"
    }
  }
}
```

Values above are shape examples, not usable identities. The endpoint shape
matches the existing read-only native observer's `inspect_endpoint` output.
`projectId` is the ID returned by this owned host's `project/read` and later
`thread/read`. `catalogProjectId` is the separately observed ID from the
complete native Codex app `list_projects` result; omit it only when both IDs
are equal. The native project root must equal the catalog's retained location
and identify the bound checkout's Git common repository. A matching root alone
never creates an ID mapping or authorizes a native write.
Do not copy a live socket or identity into this repository. Any socket or
executable replacement requires an exact new review. The binding does not
grant phase authority or automatically update Codex project membership.

## Evidence and remaining qualification

Local fake-host tests cover idle/unloaded turn start, active-turn refusal,
wrong checkout, pre-send failure, post-send uncertainty, private binding,
owner approval previews, exact one-shot responses, prompt races and isolation.
They do not establish that the installed Codex version, desktop task, native
tools and approval workflow interoperate on a real owned host.
The disposable host check on 2026-09-26 validated the WebSocket transport and
read the intended task, but this installed Codex build returned `projectId: null`
for that task. Exact project identity therefore failed closed before
`thread/resume` or `turn/start`; **no ledger receipt was obtained**. The normal
macOS app bundle executable also fails the existing ancestor-permission check
because `/Applications` is group-writable. A private, ad-hoc-signed temporary
CLI copy was used only to diagnose the disposable host, not installed or bound
for live use. Both identity gaps require an owner-reviewed, evidence-backed
solution before a complete pilot or any live migration.
On 2026-09-28 a private complete copy of the installed, signed CLI bundle
passed signature, executable-hash and endpoint-path checks. A disposable owned
socket read the exact unloaded pilot task without starting a turn. The Codex
app's complete `list_projects` observation and the owned app-server's
`project/list` observation gave **different IDs** for the pilot's same
named/rooted project. `project/read` with the app catalog ID returned project
not found, whereas the app-server listed its own ID. This is a host-surface
identity distinction, not proof that either ID can stand in for the other.
The dual-ID binding above is source-qualified by local tests only; no native
metadata write, ledger receipt, approval response or live binding occurred. A
read-only `native-project-preview` against a separately initialized disposable
ledger and the owned socket passed both project/root checks and showed an
unloaded brain with no project assignment. The preview was **not confirmed**.
The live Codex-Orchestrator entry on this app-server currently has two roots,
including a Harness repository; the one-root qualifier deliberately refuses it.
The disposable success does not qualify that live project or justify dropping
its separate-root safety boundary.
Keep source merge, installed backend, host migration, ledger receipt and live
qualification as separate claims. No GitHub Actions or paid service is used.

The 2026-09-30 disposable legacy-history check obtained a real owned-host turn,
same-turn ledger receipt, retained reply and a restart-safe one-shot claim. Its
Brain Stop fenced dispatch and was received, but remained `checkpointing`:
the brain lacked complete native task/descendant observation. A separate
checkpoint-continuation wake retained its receipt and a checkpoint artifact,
but correctly refused to claim complete inventory. A harmless permission probe
with the host's default Code Mode and danger-full-access context produced no
app-server approval request. A direct disposable native probe subsequently
observed `item/commandExecution/requestApproval` when it pinned Code Mode off,
workspace-write and on-request policy at `thread/resume`, without approving the
request. The dashboard bridge then started a bound disposable turn, retained
the brain's ledger receipt and observed the native approval request on its
owned connection. The paused pilot could not accept it; the connection closed
without a response, and the exact disposable turn was interrupted. Its
controller was recovered with dispatch paused and no workers or runner. An
incomplete or paused prompt must not advertise `accept` even when Codex includes
it in the raw choices. The native approval **request path** is qualified on this
host; the signed owner response path remains unqualified in a running phase.
Complete descendant coverage and a parked **legacy workspace-stop** checkpoint
are still missing. That old stop must remain unresolved; it is not a requirement
to replace the approved cooperative standard phase contract with whole-tree proof.
Neither a receipt nor this prompt observation qualifies live migration or Play.
Do not migrate the live project or enable Play on this basis.

Another **legacy workspace-stop** checkpoint attempt must pass an
evidence-capability gate **before** requesting another owner confirmation.
The observed `codex-cli 0.158.0-alpha.2.1` and subsequent `codex-cli 0.159.2`
contracts expose `thread/list` descendant filters and `thread/loaded/list`, but
[the documented contract](https://learn.chatgpt.com/docs/app-server) describes
stored-thread pages and threads currently loaded in memory, not an exhaustive
historical-and-ephemeral task inventory. The current collector correctly keeps
complete-tree coverage false. A future qualified observer must establish its
coverage from the first native effect, retain gaps across disconnect/restart,
and reconcile every owned task without equating an empty page with no work.
This is a new protocol/host qualification, not a replay of the stopped pilot.
The signed approval **response** remains a separate running-phase pilot gate.

For a separately owner-activated `standard_cooperative_v1` disposable phase,
standard Pause instead fences new effects and checkpoints its registered tasks
and tracked terminals. It does not claim whole-process cleanup, complete native
descendants or parked `workspace_pause_v1` state. A complete-tree collector is
therefore **not** a prerequisite for that standard transport qualification.
Use the [finite standard owned-host pilot guide](STANDARD-OWNED-HOST-PILOT.md),
including the explicit read-only registered-task observer where that host can
provide current loaded-thread metadata. Preserve the old legacy stop, its gap
and its receipts; do not convert, reset, resume or replay it to run this separate
standard qualification. Existing strict/Harness and managed admission contracts
retain their complete-evidence gates.

While an existing workspace Pause is checkpointing with missing/incomplete
inventory, the one-page graph and guided Help show the operator evidence gap and
link to the saved blockers. They do not offer another preparation confirmation,
Play, or duplicate wake as a way to clear it. This is guidance only: it neither
asserts complete coverage nor changes the retained stop, ownership or live host.
The current owned-host transport reports that complete checkpoint inventory is
not qualified. The assistant action catalog therefore withholds its checkpoint-
wake preview while tree coverage is missing or incomplete, even before the
first attempted wake. If a future host qualifies that capability, the catalog
still withholds a repeat preview for the same stop after an accepted or
uncertain native send with the gap unresolved. A proven pre-send unavailable
attempt does not count as a native wake. This is a UI/assistant guard, not a
substitute for host qualification or a change to the explicit typed recovery
protocol.

Future one-shot owned turns now retain a private `nativeThreadObservation` on
their notification claim. The marker is written before `turn/start`, so an
interrupted process leaves an `open` stream instead of an apparent empty tree.
On the bound socket, `thread/started` notifications with an exact witnessed
parent/fork chain to the designated brain retain only thread ID, relation,
ephemeral flag (or unknown) and observation time. Foreign events and text are
discarded; duplicates are idempotent, conflicts and the 128-event cap leave
explicit gaps. Closing the stream retains the native turn status separately.
Every such observation has `complete: false` and the
`owned_stream_not_exhaustive` gap: the documented subscription is not a
guarantee of complete descendant history, and the socket ends with this turn.
These events cannot satisfy `brain-stop-observe`, park a brain, release a worker,
or change `checkpointInventoryQualified`. This source addition does not replay
or repair the already stopped pilot, which began before such coverage existed.

## Explicit native project assignment qualification

The installed app-server v2 schema exposes `project/read` and
`thread/metadata/update` with only `threadId` and `projectId` needed for this
operation. The separate `native-project-*` operator commands use them only for
an existing registered **standard** brain whose exact Codex app project is
already linked in the retained `list_projects` catalog and whose potentially
distinct app-server project ID is explicit in the private binding.
They refuse a conflicting non-null task project, an active turn, unsafe or
unsettled dispatch or brain stop/resume, unresolved task/merge/notification effects, a changed
endpoint, or a project root outside the checkout's verified Git common
repository. This first qualifier accepts exactly one native project root;
multi-root projects need a separate reviewed design. The project is never
inferred from a task title or directory.

The owner first inspects a read-only preview. Example placeholders below are
not real paths or identities; create the saved preview in a private directory
with mode `0600` (for example, set `umask 077` before redirection):

```text
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace EXACT_WORKSPACE \
  native-project-preview PRIVATE_BRAIN_BINDING > PRIVATE_PREVIEW.json
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace EXACT_WORKSPACE \
  native-project-confirm PRIVATE_BRAIN_BINDING PRIVATE_PREVIEW.json \
  --confirm-hash EXACT_PREVIEW_SHA256 --confirm
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace EXACT_WORKSPACE \
  native-project-status
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace EXACT_WORKSPACE \
  native-project-reconcile PRIVATE_BRAIN_BINDING
```

If that assignment is already **verified** and the disposable host socket or
signed executable changes, do not repeat `native-project-confirm` or reconcile
against the replacement binding. A new read-only report can check whether the
replacement host independently sees the same assigned, idle/not-loaded brain,
native project and exact checkout repository:

```text
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace EXACT_WORKSPACE \
  native-project-host-preview PRIVATE_REPLACEMENT_BINDING
```

This command requires a settled, paused standard ledger and the original
verified one-shot assignment. It checks the current catalog and replacement
endpoint without writing a ledger row or calling `thread/metadata/update`.
Its hash is an inspection receipt, **not** a confirmation token for
`native-project-confirm`, a host-binding review, a wake permit or evidence that
native approvals work. A changed host still needs its separate exact owner
review before any native turn. An uncertain or conflicting original assignment
must be reconciled on its original host; this report cannot repair it.

Confirmation rechecks the exact preview and writes a private ledger intent
**before** calling `thread/metadata/update` once. It rechecks the local safety
state, catalog and intent revision under registry→ledger locks and holds those
locks through the bounded native write response. This is a cooperative local
fence, not an atomic transaction with Codex or a lock on external native UI
activity. This explicit confirmation
creates the local journal table; preview and status do not initialize it. A
crash, timeout or lost response after the claim remains uncertain and cannot
authorize another update. `native-project-reconcile` only calls `project/read`
and `thread/read`, preserving the one-shot intent. An already correctly
assigned task needs no write. A verified project assignment is only metadata
qualification: it neither installs/binds a host nor wakes a task, approves a
prompt, starts Play, resets usage, or qualifies the live project. A disposable
pilot must still demonstrate the host and approval path separately.
