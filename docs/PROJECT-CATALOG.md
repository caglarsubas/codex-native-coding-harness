# Codex projects in the dashboard

The dashboard uses **Project** for its development lifecycle. Internal workspace
IDs, `/api/workspaces` routes, `#/w/...` bookmarks and CLI `--workspace` arguments
remain compatible. A Codex project can contain many repositories and tasks; a
repository is not automatically a separate orchestration project.

## Native inventory

Use the native Codex `list_projects` tool and retain its **complete** JSON result
in a private local file. Do not reconstruct it from task titles, screenshots,
directory scans or `config.toml`. The catalog retains native project order,
labels and `(hostId, projectId)` identities. ChatGPT projects are excluded. Two
different native identities are not merged merely because their paths match.
Paths are hashed, never returned in the dashboard catalog or used for scanning.

From this dashboard's source checkout:

```sh
python3 -m orchestrator.cli --platform /private/platform project-sync /private/projects.json --observed-at ORIGINAL_UNIX_SECONDS
python3 -m orchestrator.cli --platform /private/platform project-list
```

Use the real tool observation time, not a time invented during replay. An older
observation cannot replace a newer one. A failed tool read is not an empty list:
keep the last successful observation and report the failure. An actually empty
successful inventory is valid. Polling only reads retained data; no new transport,
native task, private API or independent scheduler is installed.

**All projects → Sync changes from Codex** prepares a scoped request to an existing
brain. The owner reviews and sends it in Brain conversation. Respect Pause and
retain the normal reply; do not resume work merely to update this catalog. Import
only the project list. Never change bindings, register ledgers or start development
as part of that request. After the reply, **Reload saved list** loads the newly
retained catalog. This is explicit synchronization, not continuous live mirroring.

## Bind existing history once

An owner may connect an existing registered ledger to an exact native project:

```sh
python3 -m orchestrator.cli --platform /private/platform project-bind existing-id --host-id local --project-id EXACT_NATIVE_ID --catalog-hash REVIEWED_HASH --confirm
```

This changes presentation only: no ledger/profile/brain/repository membership,
approval, pause, mission, budget or task is changed. Bindings are one-to-one and
cannot be silently reassigned. Rename follows native identity. A changed native
path or registry brain/database identity requires review instead of retargeting.
If a project disappears, its old ledger stays in a separate **Retained projects**
group. Historical measurements never count unconfigured projects as zero.

Newly listed projects have no operational controls until separately configured
with an existing brain and private ledger. Setup is still an operator workflow;
selection and catalog import do not authorize creating a brain or a development
run. Existing registration/mission/Play gates continue to apply.

The additive catalog tables live only in the private platform registry. Back up
that SQLite database with its backup API before first live import. No product
ledger migration or installed skill update is required. Reads of an older
registry do not create these tables.
