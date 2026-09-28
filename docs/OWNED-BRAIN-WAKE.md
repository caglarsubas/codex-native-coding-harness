# Owned standard-brain wake — source boundary

The legacy `codex queue` acknowledgment proves that a message was stored, not
that an unloaded desktop brain began a turn. This opt-in transport uses the
[documented Codex app-server protocol](https://learn.chatgpt.com/docs/app-server)
on a separately owned, already running local host. It is for registered
all-standard projects only. The dashboard remains a ledger and notification
client; the designated brain is still the only scheduler.

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
- Unix app-server sockets use a WebSocket upgrade and text frames, even through
  the fixed `app-server proxy --sock` byte transport. The endpoint must pin the
  canonical socket itself: the CLI's `--listen unix://PATH` may leave `PATH` as
  a symlink to a private daemon socket, and the symlink is deliberately refused.
- `thread/read` must match brain ID, project ID and cwd. `idle`/`notLoaded`
  use `thread/resume`, then one `turn/start` with the fixed ledger pointer and
  bound cwd. An already `active` brain is refused before delivery: queuing
  behind its turn would lose this client's approval subscription. A competing
  native turn or lost response is uncertain, not a reason to resend.
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

## Separate activation review

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
