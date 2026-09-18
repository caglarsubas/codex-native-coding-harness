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

Use **Development workspace** in the left menu. Selection is tab-local and opens
Overview; no native task starts. The introduction appears before operational
status. **Edit project introduction** preserves versions and rejects stale edits.
**All workspaces** compares retained measurements and opens artifacts/roadmaps in
their originating workspace. Workspace rows may overlap; the aggregate uses the
documented deduplication rules and excludes conflicting shared task usage summaries.
Different checkout clones are not claimed as the same canonical repository yet.

Links use `#/w/<id>/<view>` and artifact/decision links carry their workspace ID.
Every operational API route, export and artifact download resolves that ID through
the registry. Unknown or ambiguous selection refuses the request, never falling
back to the first workspace. The assistant remains scoped to the named workspace
even while viewing the cross-workspace comparison.

Chat, decision drafts and uncertain command IDs are separated in memory per
workspace/tab. Switching waits for in-flight mutations or assistant responses;
late read responses are discarded. Reload clears transient drafts, as before.
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
