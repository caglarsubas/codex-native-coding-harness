# WSP-04D1 — brain-owned native creation handoff

Plan saved before implementation on merged PR #30 (`7f758d2`). This is the
first integration slice toward the supervised single-workspace pilot, not another
alternative scheduler or an autonomous Play release.

## Supported path

The designated brain uses the Codex app's available `list_projects`,
`create_thread`, `read_thread`/`wait_threads` and follow-up tools. The ledger
checks authority and reservations, emits exact creation arguments once, then
records observed native IDs through the existing lifecycle coordinator. The
dashboard continues to notify the existing brain through `codex queue`.

The locally inspected queue help describes existing-task messaging, not new-task
creation. Current app tool schemas expose saved-project worktrees and an explicit
starting ref. Project inventory schema v2 was observed read-only; no task was
created. Tool availability is host/task scoped, not a permanent platform promise.

Official [App Server documentation](https://learn.chatgpt.com/docs/app-server)
describes a public protocol for custom clients, and the
[SDK documentation](https://learn.chatgpt.com/docs/codex-sdk) describes programmatic
agent execution. Neither establishes that starting a separate process attaches
to this existing desktop brain and preserves this platform's ownership protocol.
This increment therefore retains the selected native-brain architecture; no
private desktop endpoint, second model runtime, API key or background dispatcher.

## Implementation plan

- [x] Add a designated-brain CLI integration for an existing admitted reservation:
  begin a one-shot native creation handoff, check it immediately before sending,
  record native creation results and inspect recovery status without reissuing.
- [x] Require standard policy, exact owner task approval and native defaults.
  Refuse Harness, delegated first-pilot approval, overrides, remote/non-Git
  projects and unknown or mismatched project identity before filesystem reads.
- [x] Bind fresh selected project evidence to the registered root and its pinned
  local Git common directory. Verify the exact base commit through the isolated
  Git view. Emit the immutable seed/operation scope and exact starting SHA;
  never substitute a default branch or infer supported model/speed controls.
- [x] Reuse current admission/preflight/budget gates and one-shot creation
  journal; add an optimistic revision check before crossing the boundary.
  Crash or Pause between journal commits must not reissue creation arguments.
- [x] Preserve pending client IDs separately from confirmed task IDs. An error,
  timeout or unsupported native response means uncertainty, never absence or a
  safe retry. Record results/recover receipts after Pause without new effects.
- [x] Exercise the CLI-to-native-tool-shaped handoff and return path with fixture
  adapters and real temporary Git repositories. Cover races, stale mappings,
  replay, interrupted commits, scope/default settings and legacy regressions.

## Delivery limits

No live allocation, run activation, worker creation, product inspection, installed
skill change, schedule change or server restart during source delivery. The brain
still performs the native call; Python never invokes a model or private app API.
Existing owner/runtime setup is not implicitly approved. This narrow integration
does not yet implement live usage/resource collectors, runner execution, result
acceptance, continuation/archival transport, maintenance release or public Play.

Native project/result projections are supplied by the trusted brain from actual
tool observations; shape and binding validation is not cryptographic attestation.
The local Git probe measures only identity/base metadata. Preflight still needs
independent setup, ignored-file copying, packet/lock/predecessor and resource
checks. A task creation receipt proves neither successful execution nor acceptance.

## Brain procedure

This is a source integration interface for an existing admitted reservation, not
an onboarding shortcut. It does not initialize an admission policy, allocate a
budget, approve a task, activate a run, release maintenance fences or opt a live
workspace in. Only the registered brain's current controller token can operate it.
The owner approval must be for creating the exact task/seed at its bound base;
general permission to build the dashboard is not that approval.

Every command uses `python3 -m orchestrator.cli --platform <private-platform-root>
--workspace <exact-id>` followed by the command below. The existing controller
token is supplied through `ORCHESTRATOR_CONTROLLER_TOKEN`, never command-line
arguments, a prompt or a public artifact. JSON input files must be bounded regular
files on canonical paths; no symlinks, FIFOs or oversized files. Keep inputs and
the emitted task prompt private.

1. Observe `list_projects` in the designated brain using the current app tool.
   Select the **exact existing** registered local Git project. Do not guess an ID,
   create/register a project or inspect an unrelated repository. Retain a private
   hash of the native observation. The selected projection is:
   `projectObservation = {observedAt, evidenceHash, project: {projectId,
   projectKind, hostId, path, isGitRepository}}`. For this adapter, `projectKind`
   and `hostId` must be `local`, and `isGitRepository` must be `true`.
2. Prepare `{id, expectedRevision, projectObservation}` from that observation and
   current ledger revision. Call `native-create-begin <worker-id> <request.json>`.
   The response contains `tool: create_thread`, exact `arguments`, and
   `handoffHash`. It crosses the existing local/shared creation boundary **before**
   returning arguments. It does not call the tool. Save this one response privately;
   the helper will not regenerate it on repeat or recovery.
3. Immediately before the native call, consume
   `native-create-check <worker-id> <handoff-hash>`. The helper rechecks current
   authority, account/phase usage, slots, preflight and project/base binding. It
   returns `sendNow: true` once. The selected project observation and handoff must
   still be within 60 seconds (or the stricter admission evidence window). Do not
   treat this as a reusable or delayed permit.
4. In the same brain turn, call the currently available native `create_thread`
   tool **once** with the previously emitted arguments, unchanged. Confirm its
   current schema still supports the emitted fields. If the tool is unavailable,
   rejects the shape, times out, or the brain is interrupted, retain the in-flight
   owner and reconcile. Never substitute CLI `exec`, a private endpoint, a default
   branch, another host, different settings or a second creation call.
5. Retain the tool observation and call
   `native-create-record <worker-id> <result.json>`. Its exact fields are:
   `id`, `handoffHash`, `expectedHash`, `observedAt`, `outcome`, `hostId`,
   `threadId`, `clientThreadId`, `evidenceHash`. `expectedHash` is null for the
   first result, otherwise the current shared `nativeLifecycleHash` from state.
   `observedAt` must be a fresh, actual observation after the consumed check.
   `evidenceHash` identifies the privately retained native result, not a made-up
   activity claim. `hostId` is the selected local host; reconcile any contradictory
   reported host instead of binding it here.
6. For `pending`, supply only `clientThreadId`, with `threadId: null`. For
   `confirmed`, supply the real `threadId` and preserve any previously retained
   client ID. For `uncertain`, preserve all already known IDs and leave genuinely
   unknown IDs null. Never pass a pending client ID to a task-ID tool. A timeout,
   empty task list or missing ID is not `not_created`. This path deliberately
   records activity as `unknown`, including on successful creation.

The task arguments use a saved-project worktree and `startingState` with the
exact seed's SHA as the branch/ref. No `onMissing: create-branch`, working-tree
copy, default-branch substitution, model, thinking or speed override is emitted.
The prompt contains the immutable seed and declared operations, never brain
conversation history, private credentials or unrelated portfolio data. First
handoffs require `edit` and permit only `edit`, `test`, `commit`, `open_pr` in the
contract. Test/acceptance still requires a separate runner grant. No merge,
archival, nested task creation or delegated first-pilot approval is supported.

## Recovery and cooperative Pause

`native-create-state <worker-id>` reads retained IDs, hashes and journal stages;
it returns neither task arguments nor refreshed observation timestamps. The
`creationBoundaryCrossed` field is historical, **not** proof of currently running
activity. `creationRetryAllowed` is always false.

If a native observation committed in shared admission but its local attachment
failed, repeat the **exact same result request**, or use
`native-create-recover <worker-id>` to attach the current shared receipt. Both
work after Pause and neither repeats a native call, releases capacity, resumes a
run or marks a packet accepted. Recovery without a committed native result
refuses; it cannot manufacture one. If creation crossed only the local boundary,
retain that owner and use the existing admission/reconciliation recovery contract.

A failed begin may already have crossed a journal boundary. Always inspect state;
do not infer safe retry from an exception. A successful check whose response is
lost remains consumed. Its separate deterministic receipt also detects a missing
local check pointer. A check transaction that rolled back before returning
`sendNow` did not grant a send; an unchanged fresh handoff can be checked again.

SQLite and the native tool call cannot share one transaction. Pause received
after the successful send check may race with the native call: this is **in-flight
work**, not proof of cancellation. If the brain sees Pause before calling, it must
not call; otherwise it records the result and requests a cooperative safe
checkpoint through existing supervision. The worker prompt requires finishing
only its current bounded operation, preserving progress and ending its turn.
No helper kills a process or silently frees the owner. Handoff/check changes
invalidate older safe-Pause worker inventories.

## Evidence and next gate

See [verification](NATIVE-CREATION-HANDOFF-VERIFICATION.md) for fixture and local
capability evidence. The fixture test covers the CLI → tool-shaped arguments →
pending/confirmed result → ledger path, **not a real native task's acceptance**.
The next integration gate is a qualified native observation/supervision path and
explicit owner activation for a tiny supervised standard-policy pilot, followed
by real task/runner/result evidence. Automatic Play, adaptive model routing,
installation into the live brain and Harness qualification remain separate work.
