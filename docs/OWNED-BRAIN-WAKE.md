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
  brain UUID, native project ID and checkout directory. No socket discovery, host start,
  runtime download, desktop IPC, remote listener or fallback to the desktop
  queue is permitted. The binding is loaded only at dashboard startup.
- Unix app-server sockets use a WebSocket upgrade and text frames, even through
  the fixed `app-server proxy --sock` byte transport. The endpoint must pin the
  canonical socket itself: the CLI's `--listen unix://PATH` may leave `PATH` as
  a symlink to a private daemon socket, and the symlink is deliberately refused.
- `thread/read` must match brain ID and cwd. `active` uses `codex queue --remote`
  on that same socket. `idle`/`notLoaded` use `thread/resume`, then one
  `turn/start` with the fixed ledger pointer and bound cwd. A competing native
  turn or lost response is uncertain, not a reason to resend.
- The app-server subscription is retained through the turn when possible.
  Only sanitized turn status is recorded. Native approval/user-input requests
  are **not** granted by this source bridge: they are marked as needing native
  attention and the connection is closed. A later approval relay requires its
  own owner-reviewed design and qualification before a live migration that
  might encounter prompts.
- `accepted` means the native queue acknowledged the pointer or app-server
  returned a turn ID. Neither is the brain's ledger receipt, safe checkpoint,
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
      "cwd": "/absolute/exact/brain/checkout"
    }
  }
}
```

Values above are shape examples, not usable identities. The endpoint shape
matches the existing read-only native observer's `inspect_endpoint` output.
Do not copy a live socket or identity into this repository. Any socket or
executable replacement requires an exact new review. The binding does not
grant phase authority or automatically update Codex project membership.

## Evidence and remaining qualification

Local fake-host tests cover idle/unloaded turn start, active same-host queue,
wrong checkout, pre-send failure, post-send uncertainty and private binding
validation. They do not establish that the installed Codex version, desktop
task, native tools and approval workflow interoperate on a real owned host.
The disposable host check on 2026-09-26 validated the WebSocket transport and
read the intended task, but this installed Codex build returned `projectId: null`
for that task. Exact project identity therefore failed closed before
`thread/resume` or `turn/start`; **no ledger receipt was obtained**. The normal
macOS app bundle executable also fails the existing ancestor-permission check
because `/Applications` is group-writable. A private, ad-hoc-signed temporary
CLI copy was used only to diagnose the disposable host, not installed or bound
for live use. Both identity gaps require an owner-reviewed, evidence-backed
solution before a complete pilot or any live migration.
Keep source merge, installed backend, host migration, ledger receipt and live
qualification as separate claims. No GitHub Actions or paid service is used.
