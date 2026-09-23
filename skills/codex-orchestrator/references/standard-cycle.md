# Cooperative standard-project brain

This protocol applies to the fixed pre-Play capability request and to an
owner-activated `standard_cooperative_v1` run.
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

## Pre-Play capability request

When `standard-state.catalogRefresh.status` is `queued`, process that exact
request before Play. Inspect only the current native creation/message tool schemas;
do not infer a catalog from documentation, remembered availability or global
settings. Record the actual model/effort combinations with `catalog` and the exact
`requestId`. This atomically retains the catalog and completes the dashboard
receipt. If the schema cannot be observed, use `catalog_error` with that same
request ID, a bounded code/detail and an honest retryable flag. Do not leave the
owner waiting on a free-form reply, and do not start Play, create a worker, change
settings or resume a stopped brain. Release the controller after either receipt.

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
   tasks and local worktrees. Archive requires a separate owner action. Merge stays
   manual unless the exact future phase uses the explicit opt-in below.
8. Continue eligible tasks within the same reviewed phase without asking for a
   new “continue”. At the phase endpoint, budget boundary, unresolved failure or
   material plan change, record `checkpoint` and stop. At Pause, wait for all
   registered tasks to reach a verified terminal checkpoint, then park. No idle
   heartbeat is needed: explicit dashboard Resume notifies this existing brain.

## Typed request reference

Run operations below include `runId`; the pre-Play catalog operations use
`requestId`, and task operations also use `taskId`.

- `catalog`: `requestId, models:[{model,efforts:[…]}], source`. For an automatic
  pre-Play request, bind the exact pending request ID and record only model/effort
  combinations actually exposed by current native tool metadata. A direct catalog
  without `requestId` remains available only when no automatic request is pending.
- `catalog_error`: `requestId, code, detail, retryable`. This closes the exact
  request with a visible failure; it does not create capabilities or authorize a run.
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

## Optional exact PR merge in a future reviewed phase

Manual merge remains default. Only the exact current reviewed phase with
`authority.mergeMode: brain_exact_pr_v1`, phase delegation, one standard repository
with `merge` scope and existing `required_checks` repository policy can use this
exception. Workers still never merge. Read source `docs/STANDARD-MERGE.md` fully
before using it. This enabling phase itself stops at an open PR for manual merge.

Before any future merge-enabled Play, separately update the installed launcher
from its stale schema-1-only source to the exact compatible merged source. Stop
older writers and verify the actual launcher revision/schema support first. Source
work does not authorize installation, policy migration, live changes or activation.

1. Independently inspect the completed registered task and record its exact result
   commit as `headSHA` in `finish` evidence. Cross-check the diff, all Python tests,
   every JavaScript suite, syntax and diff checks at that exact commit. Observe all
   registered tasks/tracked terminals freshly; unknown coverage stops here.
2. `merge_prepare` with one immutable `requestId`, exact PR/base/head `binding`
   and independent `evidence` per the source contract. The helper retains measured
   source bytes and fresh GitHub evidence. Explicit no-workflow observation plus
   complete local evidence is required when there are no required checks; absence
   never means passing CI. Prepare grants no effect permission.
3. `merge_check` with the same run/task/request and fresh evidence. It rechecks
   authority after I/O and commits the one-shot issued boundary. Only the first
   successful response emits fixed synchronous `gh api --method PUT .../merge`
   argv. Re-read latest state immediately before executing it once. Pause, brain
   stop or changed authority wins; do not execute, retain uncertainty. Never retry
   a lost check response or add flags/commands to the emitted argv.
   Use only the exact returned synchronous PUT arguments, with the pinned `sha`
   and `merge_method=merge`. Never substitute `gh pr merge`, an asynchronous
   endpoint, queue/auto-merge, admin bypass or a fallback. Effective classic/ruleset
   queue state and PR auto-merge must be positively disabled in both rounds;
   unknown refuses. Full policy/check metadata must agree, and optional duplicate
   contexts/reruns refuse too. Local branch/origin/layout are rechecked after I/O.
4. `merge_receipt` with delivery `acknowledged`, `unknown` or `failed` retains
   uncertainty; `merge_reconcile` observes the exact PR. Open after issue stays
   uncertain, closed/unmerged is not-merged, exact remote merge is merged. Late
   observations after Pause never resume work. Do not resend, reset ownership or
   claim phase acceptance, runtime, deployment, CI or archival from merge state.
5. Keep the run retained until unresolved merge delivery is reconciled. Preserve
   the immutable binding, original observation times and dashboard history. Stop
   at the reviewed owner checkpoint. No next-phase approval follows from merge.
