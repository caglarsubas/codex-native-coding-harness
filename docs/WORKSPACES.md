# Workspace operations

This guide describes implemented registry behavior. The full phase-autopilot
contract is tracked separately in [the implementation plan](WORKSPACES-AUTOPILOT.md).

## Register an existing portfolio

Keep private files outside Git. The ignored `.platform/` directory holds a
private registry and verified registration-time backups. Each workspace retains
its existing ledger directory; registration never reinitializes or relocates it.

```sh
python3 -m orchestrator.cli --platform /absolute/private/.platform workspace-register harness "Multi-agent harness platform" /absolute/private/.state
```

The default is a preview. Repeat with `--apply` to retain a verified SQLite backup
and register the existing brain/ledger identity. This does not start native work,
change approvals, change the heartbeat, or claim a real implementation pilot.
Registration is a trusted local setup operation, not an arbitrary browser path API.

```sh
python3 -m orchestrator.cli --platform /absolute/private/.platform workspace-list
python3 -m orchestrator.cli --platform /absolute/private/.platform --workspace harness workspace-verify-backup
python3 -m orchestrator.cli --platform /absolute/private/.platform --workspace harness inbox
```

Registry selection without an explicit workspace refuses operational CLI commands.
Existing single-portfolio `--state` usage remains compatible, but cannot be combined
with `--platform`/`--workspace`. New workspace state roots must be separate, private
and canonical; duplicate brain identities, aliases, overlapping roots and unknown
workspace IDs are refused. The installed skill wrapper forwards these explicit
arguments unchanged.

Backups include committed WAL data and logical table checksums. Verification
checks the retained database without restoring it. A live ledger changing after
backup is expected. Never overwrite a live ledger for recovery; stop its clients,
retain the current bytes, inspect the backup and obtain explicit recovery approval.
Replacing a database or brain identity requires recovery; the registry will not
silently adopt the replacement. No automatic restore or destructive cleanup exists.

### Device-number drift after a local reboot

macOS may assign a mounted volume a different device number after reboot. The
normal registry identity check still refuses this change. For an **unchanged
ledger inode and brain only**, the trusted local operator can prepare
`workspace-identity-preview <private-retained-ledger-backup>`, using explicit
`--platform` and `--workspace`. The reference must be a separately retained,
private SQLite backup whose **entire schema and logical contents** match the
current ledger. Registration-time backups may be too old; never overwrite a
reference or create a new current-state copy to pretend it is earlier evidence.

The preview binds the selected workspace/root, current registry contents,
old/new filesystem identities, ledger revision and checksums, reference identity
and checksums, and any existing exact project mapping. It makes no state changes
and has no short timer: changed pins, schema or contents invalidate it.

After independently stopping all older writers and reviewing the exact private
preview, the owner may use `workspace-identity-recover <private-preview-json>
--confirm-hash <displayed-documentHash> --confirm --writers-stopped`. The operator
must obtain exact recovery approval; vague assent, a normal read, or permission
to build source is not confirmation. This command locks registry then ledger,
refuses a running dashboard, verifies fresh private backups of both databases,
and atomically journals only the registry's new device pin plus the corresponding
pin in an **unchanged** existing project mapping. It never restores/replaces the
ledger, updates its contents, refreshes catalog/evidence times, changes either
native project identity, rebinds a host, starts a turn, resumes or renews a run,
or resets tokens, gaps, attempts or receipts. An identical retry returns only
the historical receipt; it cannot repair a later identity change.

Running/unresolved controls, tasks, merge intents, controller/runner ownership,
strict Harness and enrollment/managed ownership remain refused. A changed inode,
brain, missing/changed reference, or reassigned project needs its separate
recovery procedure. The reference is operator-supplied evidence, not independent
native attestation. Stopped-writer acknowledgment is a cooperative local setup
requirement, not proof that every process has ended. Any partial backup is kept
after failure; no identity is applied until both backups and the final checks
pass. Existing host-binding, repository and observation pins remain unchanged
and may need their own exact reviews. Expired phases still cannot Resume.

This source command does not authorize installation or live identity repair.

## Project introduction

Use `workspace-profile-set <private-json> --version <current-version>` to save
the six fields: `goal`, `successCriteria`, `architecture`, `techStack`, `roadmap`,
`references`. Goal, architecture and roadmap are text; the remaining fields are
lists of text. Keep source references non-secret. Version zero means no profile.
Updates preserve prior versions and reject stale revisions. Profile text is data,
not packet authority or instructions to a worker.

This setup does not create a new native brain or register a Codex project. Those
remain explicit native onboarding actions, followed by verified project mappings.

## One dashboard, multiple workspaces

After stopping the old dashboard process (not the brain or workers), start:

```sh
python3 -m orchestrator.cli --platform /absolute/private/.platform serve --port 8768 --notify-brain /Applications/ChatGPT.app/Contents/Resources/codex
```

Open the private URL from `.platform/dashboard-session.json`. The previous server's
browser sessions expire on restart; do not publish either private URL. Each served
ledger has an exclusive dashboard lock. Restart after registering another workspace;
the running server deliberately does not adopt new roots during ordinary reads.

Select a project in the compact workspace header. Selection is tab-local and
opens its graph; no native task starts. The introduction is available in the
contextual inspector. **Edit project introduction** preserves versions and
rejects stale edits.

Select the brain node to send scoped direction to that project's existing
Codex brain and read its retained reply in the inspector. This is separate from
the labelled advisory guide. Delivery, receipt and reply are distinct;
follow-up decisions and artifact links remain in the selected workspace.
Pause/Resume and execution approvals keep their existing dedicated controls.
See [the conversation contract](WORKSPACE-CONVERSATION.md). Native security or
host permission prompts still require Codex; this is not a full transcript mirror.

**All workspaces** compares retained measurements and opens artifacts/roadmaps in
their originating workspace. Workspace rows may overlap; the aggregate uses the
documented deduplication rules and excludes conflicting shared task usage summaries.
New explicit code measurements bind common-directory and conventional origin
identity. Clones/worktrees at the same identified commit count once; different
commits and forks stay separate snapshots. The comparison lists aliases and
excluded observations, with links to the affected workspace. Historical records
without identity evidence remain readable but are excluded until a normal explicit
**Refresh local observations** from that workspace's **Portfolio metrics** view.
Ordinary **Refresh** only reloads retained state. See [the counting contract and
coverage limits](PORTFOLIO-IDENTITY.md); unsupported host aliases are not guessed.

Links use `#/w/<id>/<view>` and artifact/decision links carry their workspace ID.
Every operational API route, export and artifact download resolves that ID through
the registry. Unknown or ambiguous selection refuses the request, never falling
back to the first workspace. The assistant remains scoped to the named workspace
even while viewing the cross-workspace comparison.

Chat, decision drafts and uncertain command IDs are separated by workspace/tab.
Switching waits for in-flight mutations or assistant responses; late read
responses are discarded. The unsent brain-chat draft is retained for refresh
in this browser tab; other transient drafts have their documented boundaries.
Assistant confirmations bind both the browser session and workspace. The server
shares inference capacity, not prompts, conversation history, jobs or action keys.

## What this increment does not enable

**Mission & authority** now prepares a versioned phase configuration and records
exact owner review/revocation. See [mission configuration](MISSIONS.md). It remains
inactive, grants no packet authority and enforces no token/task allocation yet.
Saving or reviewing does not notify the brain. Existing reviews must not become
active merely because a later software upgrade supports activation.

Registration is not delegated packet authority, a token budget or continuous Play.
Existing exact packet approval, pilot limits, cooperative brain controls and native
task procedures are unchanged. Phase authority and global repository/runner/budget
admission are subsequent implementation gates in the saved plan. Do not activate
concurrent development of a shared repository from multiple workspaces: global
mutation reservations are not implemented in this increment.
