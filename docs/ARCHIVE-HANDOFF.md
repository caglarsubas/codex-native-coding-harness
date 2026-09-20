# WSP-05A — owner-requested archive handoff

Plan saved before implementation, following PR #37 merged at
`cc2abdee9229b680bd3505c6fc486743b5310eca`.

## Plan

- [x] Require a new explicit owner archive request bound to the accepted review,
  measured local preservation artifact and acknowledged managed-worktree cleanup.
  Legacy worker-ID-only requests remain refused for admission-managed tasks.
- [x] Add designated-brain state/prepare/check/record CLI operations. The helper
  never archives: a consumed one-shot check returns the exact native tool arguments
  for the brain. No new tasks, direct app-server API, shell command or scheduler.
- [x] First scope is an exact owner-approved standard-policy local root task with
  no descendants. Require fresh complete inactivity and preserved-worktree assertions
  after the owner request, retained result/bundle/evidence integrity and no pending
  controls. These assertions are not independent host attestation.
- [x] Preserve Pause/maintenance boundaries and uncertain outcomes. Historical
  replay never returns another send permit. Late observations remain possible;
  do not mark archived until confirmed, infer descendant archival or release usage.
- [x] Keep accepted-result and safe-Pause validation coherent after archive;
  archival is not proof of current native inactivity or immunity from later unarchive.
- [x] Test owner bindings, one-shot concurrency/crashes, rollback, stale/unknown
  evidence, late results, retained preservation and legacy bypass refusal locally.
  No Actions workflows, paid service, live archive, installation or Play activation.

## Native safety boundary

Codex-managed worktrees can be cleaned up when their task is archived. This
motivates explicit cleanup acknowledgment and fresh preservation checks; it is not
permission to delete files directly. See the [official worktree documentation](https://developers.openai.com/es-419/docs/environments/git-worktrees).
Only the existing native `set_thread_archived` tool is a permitted caller boundary.
Source delivery does not invoke it or change installed operator guidance.

This is an explicit-owner first handoff, **not automatic phase-delegated archival**.
The original task must have exact owner approval, a confirmed terminal settlement,
separate accepted result review and `local_preservation_v1` proof. A supplied
preservation note cannot substitute. The original run must remain current and
unpaused for preparation and the send check. Harness, remote hosts, descendants,
the brain itself and attempts with unresolved checkpoint/archive controls refuse.
No budget or ownership is released by this helper.

The preserved Git bundle covers committed objects and retained evidence, not
uncommitted/untracked files, external LFS/submodule contents or native transcripts.
The brain must separately verify that nothing recoverable would be lost by native
worktree cleanup, retain the evidence and supply `worktreePreserved: true` only
then. Missing inspection capability or incomplete knowledge blocks this path;
neither an old terminal settlement nor an idle task proves preservation. The
helper validates supplied assertions and hashes, not independent host truth.

## Operator sequence

Use the already registered workspace and private designated-brain controller token.
Commands require both `--platform` and `--workspace`; no cwd/default selection or
state initialization is supported. Request files are bounded, finite JSON with
duplicate fields refused. Never put controller tokens, evidence or private bundle
bytes in the public repository or inference prompts.

```sh
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace EXACT_WORKSPACE archive-handoff-state WORKER_ID
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace EXACT_WORKSPACE archive-handoff-prepare WORKER_ID PRIVATE_PREPARE_JSON
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace EXACT_WORKSPACE archive-handoff-check WORKER_ID PRIVATE_CHECK_JSON
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace EXACT_WORKSPACE archive-handoff-record WORKER_ID PRIVATE_OBSERVATION_JSON
```

1. `state` validates retained result/preservation history and reports the exact
   `ownerRequestPayload`, current workspace revision and any attempt history. It
   makes no current native observation and returns no send permission. The two
   booleans in its payload describe required explicit acknowledgment, **not an
   approval inferred from calling state**.
2. Only after a separate explicit owner request, submit the existing typed
   `archive` control through the authenticated control endpoint or existing
   `command` CLI. Bind its ID/current `expectedRevision` and exact payload:
   `workerId`, `reviewHash`, `preservationArtifactId`, `confirmed: true`,
   `allowManagedWorktreeCleanup: true`. Accepted actors are `dashboard` and
   `explicit_user_via_brain`; neither a model proposal nor the designated brain's
   own decision is an owner request. Managed-task archive controls remain hidden
   in the dashboard and assistant until a later qualified UI integration.
3. The brain's existing `process` records receipt and returns
   `archive_handoff_required`, without native arguments. The command remains
   queued until preparation; receipt alone must not claim native work is in flight
   or prevent safe parking. Legacy generic archive processing/acknowledgment cannot
   bypass this handoff.
4. Obtain fresh complete native inactivity/worktree evidence and call `prepare`
   with exactly `commandId`, `expectedRevision`, `inventory`. It atomically retains
   one immutable handoff, marks the command processing, and returns `handoffHash`,
   `checkRequired: true`, `sendPermit: false`. It returns no native arguments.
5. Reobserve after preparation. Immediately before the native call, invoke `check`
   with exactly `handoffHash`, current `expectedRevision`, `inventory`. It rechecks
   current run, Pause, maintenance, root-only coverage and preserved evidence, then
   atomically consumes the send boundary. Exactly one successful check returns
   `tool: set_thread_archived` and `{hostId, threadId, archived: true}`. Only the
   brain calls that existing native tool. Python never calls app-server/private
   APIs or performs filesystem cleanup. A replay cannot return another permit.
6. Record an actual exact-task native outcome. A missing response, exception or
   unarchived listing after the call is `unknown`, never permission to retry.
   Read-only reconciliation may later confirm `archived`. Never invent an outcome
   or infer it from completion, elapsed time or an accepted packet.

The check-to-call gap is cooperative in-flight work, not an atomic native lock or
cancellation guarantee. Do not hold the permit for later use. If interrupted after
the check, retain uncertainty and reconcile without sending again. If Pause arrives
before the check, cancel the unsent handoff; after consumption, no unsent claim is
allowed even if the caller believes the native call did not happen.

## Request evidence

Both preparation and send-check inventories have exactly:

- `observedAt`, `evidenceHash` (SHA-256 of retained inspection evidence);
- `complete: true`, `includesDescendants: true`, `effectsComplete: true`;
- `tasks`: exactly one `{hostId, threadId, status: "idle", observedAt,
  evidenceHash, worktreePreserved: true}` for the owned root.

Times are actual Unix observation times, not retention or retry times. Both must
be fresh under shared admission policy. Preparation's task observation must follow
the owner request, review and terminal settlement; check's must follow preparation.
Every already-known descendant prevents this first root-only path. Complete tree
coverage and absence of other effects are caller assertions; if unavailable, stop.

`record` has exactly `id`, `handoffHash`, `expectedObservationHash` (null for the
first observation), `hostId`, `threadId`, `outcome`, `observedAt`, `evidenceHash`.
The observation must be fresh and follow its send boundary or latest observation.
Reuse an ID only for an identical retry of **recording**, never for another native
call. The receipt identifies its caller-supplied, non-attested trust boundary.

| Observation | Gate and retained result |
| --- | --- |
| `cancelled` | Prepared but never checked; command rejected, worker not archived |
| `unknown` | Check consumed; command processing, archival unconfirmed, no retry |
| `archived` | Check consumed and exact native archive observed; command completed |

Unknown can be superseded only by a newer unknown or confirmed archive observation.
Terminal observations cannot be replaced; exact historical replay returns the old
receipt without overwriting newer state or refreshing time. History is bounded to
16 linked observations, then requires operator reconciliation. A cancelled or
consumed attempt cannot be prepared anew by deleting its journal or using a new ID.
No retry/reversal contract is included in this increment.

## Recovery and rollout boundary

Historical reads and late outcome recording remain available after Pause, expiry
or maintenance, but cannot issue a send permit or resume anything. Corrupt or missing
review, bundle, evidence, command, slot or observation receipts fail closed. All
local handoff/check/result projections and events commit atomically; shared
ownership and usage are unchanged. The result remains separately accepted, never
silently promoted to pilot acceptance or delivery evidence.

Completed archived tasks remain in future safe-Pause inventories: archive is not
a live inactivity proof, and a user can later unarchive a task. Handoff/check/outcome
hashes invalidate older Pause observations. Uncertain processing controls prevent
parking until reconciled; queued unprepared requests do not count as in-flight.

Quiesce older helpers before any separately authorized rollout. No mixed-version
writer/downgrade contract, installed-skill update, schedule change, maintenance
release, live task archival, public Play or supervised pilot follows from this PR.
See [local verification](ARCHIVE-HANDOFF-VERIFICATION.md). Remaining WSP-05 work
includes delegated continuation/next-task selection, retention policy/UI and live
native/host qualification; this first handoff does not complete that milestone.
