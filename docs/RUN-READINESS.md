# Workspace run preflight — WSP-03B2

Implementation plan: connect the existing mission, packet and platform-evidence
contracts in an explicit read-only inspection. This does not create a run, grant
authority, reserve tokens, release owners or enable autonomous Play.

- [x] Bind a diagnostic candidate to the selected workspace, exact mission and
  owner-review receipt, phase limits, repository policies and retained baseline.
- [x] Inspect prepared packets conservatively against phase path scope and exact
  seed/approval/preflight bindings. Unknown containment is not permission.
- [x] Separate owner setup, observed evidence and missing platform implementation;
  report who can resolve each blocker and link to the relevant dashboard view.
- [x] Provide explicit dashboard/CLI inspection, JSON report and bounded assistant
  awareness without background collection or persistent mutations.
- [x] Verify isolation, staleness, malformed scope, changed sources, no mutation,
  rendering and regressions in disposable fixtures only.

Results and remaining acceptance boundaries: [verification report](RUN-READINESS-VERIFICATION.md).

The inspection is not an atomic reservation or authority token. Platform evidence
remains externally supplied assertions; a consistent historical review cannot
activate a mission. Existing local packet approvals and dispatch remain unchanged.

## Owner workflow

Select a workspace, open **Run readiness** below Mission & authority, then click
**Inspect run readiness**. Overview also links here. Viewing, polling or asking
the assistant a question does not run an inspection. Each browser tab keeps its
last report separately per workspace; reloading clears that local report.

The result has three sections:

| Section | Who can resolve it | Meaning |
| --- | --- | --- |
| Owner setup | Owner | Current reviewed mission, intended mode, designated brain and recorded project mappings |
| Evidence & coordination | Brain / operator | Unfinished Pause, controller ownership, retained platform inventory/usage evidence and bounded packet coverage |
| Platform development remaining | Platform developer | Run generations, exact effect boundaries, phase release, native admission, execution settings and real pilot acceptance still missing |

Satisfied checks are expandable; blockers remain visible with the relevant view
link. Missing implementation is not an invitation to approve the mission again.
Prepared packets show **path scope**, **recorded legacy eligibility** and
**execution authority** independently. No packet becomes approved from inspection.
Completed/dispatched packets are excluded from the candidate list, but existing
worker ownership still participates in the underlying evidence checks.

Expand the JSON document to inspect exact bindings or download this captured
report. The topbar's existing Export report still exports portfolio metrics;
**Download this inspection** exports this run-readiness snapshot. It is not
automatically registered in the durable artifact library or shared with inference.

## API and CLI

Authenticated `GET /api/workspaces/{id}/run-readiness` performs the explicit
inspection. Overlapping requests in the same dashboard workspace are refused.
There is no POST/activation route, native call or notification. Runtime memory
holds only the last report; ordinary state and assistant requests use its bounded
historical summary without repeating platform inspection. Other workspaces do not
inherit that cached report. The assistant receives blocker codes/groups/owners,
not raw paths, hashes, native IDs, artifact bodies or underlying platform documents.

```sh
python3 -m orchestrator.cli --platform /absolute/private/.platform --workspace example run-readiness
```

The CLI requires explicit registry/workspace routing before constructing a ledger.
Legacy `--state` cannot silently initialize a new inspection workspace. CLI output
is the same diagnostic JSON and does not populate the dashboard's memory cache.

## Binding and scope semantics

A candidate exists only when the exact mission document hash, owner-review
receipt hash/actor/revision and current repository/brain/workspace bindings match.
It pins the phase ID, authority/scope hashes, repository binding hash, workspace
source hash and any retained platform baseline/review. Proposed numeric limits and
the mandatory owner checkpoint remain configuration, not grants or reservations.
The report hash covers the complete returned document except its own hash field.

Each selected seed is revalidated against its SHA-256, queue packet/repository
identity and policy profile. Path containment is deliberately conservative:

- Equal patterns are comparable directly.
- A literal candidate path may match an existing phase pattern using the current
  `fnmatch` semantics.
- A pattern beneath a literal directory's unrestricted `/**` suffix is contained.
- Other glob-to-glob relationships are **not proven**, even if an operator could
  show that one is narrower. Traversal, ambiguous separators and dot components
  never pass. This is lexical scope checking, not filesystem/symlink attestation.

At most 100 prepared packets, 80 paths per seed, 1,000 characters per compared
path and 512,000 UTF-8 bytes per seed are inspected. Omitted packets are counted
and block coverage. No seed bodies, repository source or command argv are returned.
The v1 seed alone does not bind operations or model/effort/speed policy to a phase.
WSP-03B3 adds a separately hashed [task declaration](TASK-CONTRACTS.md), inspected
here for exact current binding. Declared operations, token estimates and requested
settings are shown separately from legacy eligibility and execution authority.
Missing/stale declarations remain visible. Even a bound declaration cannot grant
phase authority: run-aware approval, adaptive policy and native-effect enforcement
remain implementation gates. Declaration documents participate in the source
drift hash, but their free-text rationale is not copied into this report.

Platform diagnostics reuse the existing reconciliation status, which re-evaluates
retained evidence and source bindings without collecting native state. Only a
currently consistent evaluation with a retained baseline and unexpired validity
passes that individual check. Issue codes are aggregated across the platform
because shared resources matter; other workspaces' task/owner identities and
private evidence bodies are not copied into the selected-workspace report.

Workspace input is read in a transaction, platform state is checked separately,
and workspace input is read again. Detected drift discards the candidate hash.
This is **not an atomic cross-database snapshot or admission lock**; platform or
native state can change immediately afterward. The browser labels changed/older
reports and never refreshes observation timestamps. Runtime assistant summaries
are always historical. A missing/unreadable source is not free capacity.

## Rollout boundary

No live ledger, mission, skill installation, schedule, native task or dashboard
process is changed by implementing this feature. No model service is invoked by
inspection. Deploy helper and matching web assets together when separately
authorized; the installed brain skill needs no change for this read-only view.

Autonomous Play remains unavailable. Next implementation work must enforce the
declared packet operations/settings at effect boundaries, introduce exact run generations
and owner activation, and enforce that authority together with shared admission
at every native effect and continuation boundary. Configuration review, diagnostic
hashes and a local test result cannot substitute for those controls or a real pilot.
