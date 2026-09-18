# From observation to a supervised first drive

The **Readiness** view is deterministic. It explains what the ledger knows and
what the operator must still verify; it never authorizes work, calls a native
task tool, resumes dispatch, wakes a heartbeat or treats AI prose as a control.

## Operating sequence

1. **Inspect:** use Inspect local readiness. This reads configured Git roots/refs
   and file metadata only. It does not fetch, execute repository code, inspect
   credentials, run setup/acceptance, or make inference requests.
2. **Observe native state:** in the designated brain, call native `list_projects`
   and `read_thread`. Record the scoped result with `native-observe`. A directory
   on disk is not a saved native project. A model-generated ID is not a mapping.
3. **Prepare one real task:** agree on one useful objective, exact allowed paths,
   current base/catalog commits, predecessors, acceptance route and stop rules.
   Produce an immutable seed. The [first-pilot proposal](FIRST_PILOT.md) is a
   candidate, not an executable or approved packet.
4. **Approve exact scope:** review the seed in Approved queue, acknowledge its
   scope, and approve the exact packet/seed hashes. This still creates no task.
5. **Preflight in the brain:** verify live project/base/packet/locks, policy,
   predecessor evidence, safe worktree setup, duplicate work and runner capacity.
   Metadata checkmarks are not substitutes for these independent checks.
6. **Request resume separately:** the brain processes the request and crosses the
   one-shot creation boundary for that approved item only. Start with one worker.
7. **Supervise and verify:** preserve uncertain ownership through restarts; review
   source, CI, artifacts, merge and any required runtime/tenant axes independently.
   Repository-specific manual merge rules remain in force.
8. **Accept the real pilot:** only an independently verified, preserved native
   worker can qualify for two-worker concurrency. Pause when no approved work or
   active supervision remains. No automatic scope expansion follows pilot success.

## Freshness and authority

Local readiness metadata and operator-recorded native inventory expire after 15
minutes. The native import must be captured within five minutes when recorded.
Brain checkpoint age has its own 30-minute indicator. Actual packet preflight has
a stricter five-minute lifetime and is rechecked at reservation and creation.
The heartbeat label is the ledger's recorded state, not a live native poll.

Readiness reports **parked**, **supervision required**, or **brain check required**,
never "autonomous launch authorized." Packet previews use the same eligibility
function as dispatch, plus pause/capacity/ownership checks, but do not acquire a
controller or certify external facts. A stale read-only page cannot authorize a
new task. Refresh and reverify before any consequential action.

Changing a repository's path, saved project ID or configured ref invalidates
pending approvals and preflights. An active worker prevents such a mapping change.
Policy changes still require explicit migration. Initializer calls do not remove
repositories or silently move work between projects.

## Native observation format

The native tools are called by the brain, not the web server. Save their observed
result to a private JSON file with this shape, then run `native-observe`:

```json
{
  "schemaVersion": 1,
  "observedAt": 0,
  "brain": {"id": "EXACT_CONFIGURED_BRAIN_ID", "status": "idle"},
  "projects": [
    {
      "projectId": "ID_RETURNED_BY_NATIVE_TOOL",
      "path": "/absolute/path/to/configured/repository",
      "hostId": "local",
      "isGitRepository": true
    }
  ]
}
```

Replace `observedAt` with the actual current Unix observation time. Accepted brain
states are `idle`, `running`, `unavailable`, `unknown`; do not invent a running
state from an active browser. The importer drops projects outside configured
roots and refuses duplicate IDs, future/stale timestamps, unexpected fields and
another brain identity. This is an auditable operator observation, not a signed
native attestation. It never edits portfolio mappings or authorizes dispatch.

The brain object also accepts an optional `title` (1–200 characters), copied
verbatim from native task tools. Overview's [Brain activity](BRAIN_ACTIVITY.md)
panel uses this title and a separate, shorter activity freshness window. Local
activity metadata is not a substitute for the native readiness observation.

The available native connector lists saved projects but does not expose a project
registration operation. Register an existing checkout through the normal Codex
project UI, then discover its actual ID again. Do not edit private app databases
or bypass setup/permission controls. Worktree setup and ignored-file copying need
an explicit native-settings review even when no repository settings file exists.

## CLI

```sh
python3 -m orchestrator.cli doctor
python3 -m orchestrator.cli native-observe .state/native-observation.json
python3 -m orchestrator.cli readiness
python3 -m orchestrator.cli rehearse
```

`doctor` collects local metadata and prints diagnostics. `readiness` reads retained
observations and current ledger gates. Neither runs product acceptance.
Authenticated `POST /api/readiness` accepts only `{"operation":"inspect"}` or
`{"operation":"rehearse"}`, with the existing Host/Origin/session/CSRF guards.
The browser cannot submit a native inventory, custom command, path, seed or script.

## Isolated rehearsal

Rehearsal uses a temporary synthetic ledger with no product source. It exercises
pause, approval, preflight, one-shot creation, uncertain-start recovery, pending
identity, runner ownership and completion separation. Native creation arguments
are inspected and discarded; no native API, subprocess acceptance or model call
occurs. The temporary directory is automatically cleaned up; only a clearly
labeled, versioned synthetic report is retained in the real artifact library.

This does not test real worktree creation, inherited setup, CI, runner isolation,
remote push, PR/merge or tenant acceptance. No fixture can certify the real pilot.
Dashboard polling reads state only and never triggers inspection or rehearsal.

## CI boundary

A workflow filename is not green CI, and absence of `.github/workflows` does not
rule out an external CI system. The operator must identify the actual approved
CI route and bind evidence to the exact commit. The minimum source/CI completion
contract is unchanged. Do not relabel manual local tests as CI or create a hosted
runner/paid service to make the readiness indicator green.
