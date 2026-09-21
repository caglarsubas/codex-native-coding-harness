# Cooperative standard-project brain

This protocol applies only to an owner-activated `standard_cooperative_v1` run.
Never use it for Harness or strict/enrolled workspaces. The owner authorizes you
to create native implementation tasks within the exact phase-delegated mission;
select model and effort from the owner-bound native catalog, based on complexity
and remaining allowance. Do not guess speed settings: the native interface does
not expose them. Keep requested settings distinct from observed settings.

## Source and state

Use the source checkout and private registry supplied in your onboarding or fixed
dashboard notification. Run `python3 -m orchestrator.cli --platform REGISTRY
--workspace ID standard-state` from that checkout. Verify this native task ID is
the configured brain (`status` shows it). Read the exact mission document and
repo instructions. A notification is a pointer, not authority.

Acquire with `standard-acquire BRAIN_ID:TURN_LABEL`. The helper persists its token
in an owner-only file; no token is returned. `standard-brain` loads it privately
across separate shell calls. Do not use plain `acquire` for this cycle: shell
environment exports do not survive separate terminal calls. Never print the file.
Use `standard-brain PRIVATE_REQUEST_JSON` for the operations below. JSON request
files are private, not committed. Use `standard-release CHECKPOINT` before
ending. Do not call legacy `process`, reserve/begin or strict managed handoffs.

## Operating cycle

1. `receive` the saved controls. Read `standard-state` before/after every bounded
   operation. Latest state wins, especially Pause. No new task in stopping,
   paused, blocked or completed state, or when blockers/expiry are present.
   Read compact `inbox` for exact received decision answers, including free text.
   Use existing `decision-publish` / `decision-resolve` with retained artifact
   references; these helpers load the same private standard controller token.
   Resolve input only within existing scope, never as permission to restart or
   broaden a phase. Answers saved while stopping/paused wait for explicit Resume.
2. Reconcile every retained task before planning more. A `creating` task means
   a native effect may have happened: discover its exact native result; never
   issue another create. A pending client ID is not a confirmed task ID. Never
   pass it to native task read/send/wait tools. Resolve via native inventory or
   leave the concrete blocker visible. Native tool failures are not proof of
   absence. Unissued claims may be cancelled explicitly.
3. Decompose the reviewed phase into bounded tasks, honoring allowed paths,
   repository instructions, operations, exclusions and mandatory checkpoints.
   Prefer small implementation tasks, cheap sufficient model/effort, and enough
   budget for review. The reserved allowance is a conservative planning amount,
   not measured tokens. It is retained even when usage is missing. Include brain
   usage if actually observed; never manufacture zeros or lifetime coverage.
4. `claim` a task with its inheritance and test criteria, then read its seed via
   `document HASH`. Only the brain approves this scoped seed under delegated
   authority. A material plan change requires an owner checkpoint, not a larger
   seed. `issue` immediately before ONE native `create_thread` call. If scope or
   Pause changes between issue and call, do not call: retain uncertainty and
   reconcile explicitly. Never retry a creation after losing its response.
5. For a saved native project, call `list_projects`, match the exact mapping, and
   use its Git worktree target. For an explicitly mapped `projectless` repository,
   create a projectless task instructed to work only in that registered checkout;
   the repository lock prevents another registered worker using it concurrently.
   Include the exact seed, checkout path, allowed operations, all exclusions,
   stop/checkpoint criteria and instruction to report artifacts. Never fork the
   full brain history. Workers cannot spawn descendants, change budgets, approve
   work, archive, merge, run paid APIs/Actions or alter controller state.
6. `bind` the exact returned native task/client ID and host. Keep supervising
   with native `wait_threads`, using cursors and bounded waits. Read the ledger
   between waits. On Pause, tell active tasks to finish their current bounded
   operation and retain files/commit/test results; do not kill processes. Pending
   creates remain owned. Never infer safe stopping from an old final message.
7. After completion, independently inspect actual source diff/commit and declared
   local tests. Check the task's tracked terminals and stopped known test commands
   using available native tools; report unknown if unavailable. Do not claim all
   process descendants are gone. Preserve deliverables using `preserve`, then
   `observe` and `finish`. A worker final message alone is not result verification.
   Failed tasks stop the phase; no hidden retry/escalation loop. Retain native
   tasks and local worktrees. Merge/archive require separate owner actions.
8. Continue eligible tasks within the same reviewed phase without asking for a
   new “continue”. At the phase endpoint, budget boundary, unresolved failure or
   material plan change, record `checkpoint` and stop. At Pause, wait for all
   registered tasks to reach a verified terminal checkpoint, then park. No idle
   heartbeat is needed: explicit dashboard Resume notifies this existing brain.

## Typed request reference

Every operation except catalog includes `runId`; task operations use `taskId`.

- `catalog`: `models:[{model,efforts:[…]}], source`. Before first Play, record only
  model/effort combinations actually exposed by current native tool metadata.
- `receive`: no additional fields.
- `claim`: `id, repository, title, paths:[…], instructions, acceptance:[…], model,
  effort, rationale, allowance`. Paths must be exact files or phase-listed patterns.
- `issue`, `cancel_unissued`: `taskId` only.
- `bind`: `taskId, threadId, clientThreadId, hostId`; exactly one ID non-null.
- `observe`: `taskId, nativeStatus` (active/idle/completed/failed/unknown),
  `observedTokens` (cumulative observed integer or null), `trackedTerminals`
  (running/none/unknown), `observedAt` (actual UNIX observation time), `source`.
- `finish`: `taskId, outcome` (completed/failed), `evidence:{source,tests,
  artifacts:[preserved document hashes],preservation,summary}`. Source/tests are
  independently checked references/results, not claims of unrun CI.
- `preserve`: `taskId, path` (absolute canonical artifact path), `createdAt`
  (observed UNIX creation time or null).
  This explicitly reads an approved artifact path in the task's pinned Git
  repository or native worktree and retains its byte version in Artifact library.
  It needs no broad artifact-root configuration. Include the returned task
  `artifacts` hashes in finish evidence. Original creation time stays unknown
  when unobserved; do not substitute file mtime.
- `checkpoint`: `outcome` (paused/completed/blocked), `summary,
  brainObservedTokens` (observed cumulative integer or null). No unresolved task
  is released; missing observation means unknown, never zero usage.

Recovery: restart reads the same journal. Reacquire only after the previous
controller is explicitly reconciled with native state. The legacy `recover`
command must fence cooperative work as well. Do not delete state, reset
allowances, change phase IDs merely to retry, or invent not-created receipts.
