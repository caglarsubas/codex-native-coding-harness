# WSP-05C — brain lifecycle coordinator

Update: [WSP-04E](MODEL-POLICY.md) adds owner-reviewed adaptive model/effort
selection. Create candidates enforce the selected profile's token floor;
adaptive continuation candidates also need fresh matching settings observations.
These checks do not select or activate a policy automatically.

Update: [WSP-05D](BRAIN-EVENT-WAITS.md) binds new wait decisions to recorded event
categories and adds read-only `brain-cycle-wait-state DECISION_HASH`. An unchanged
wait cannot be appended again under a new request ID. Old decisions remain
historical/unbound; no automatic migration, schedule change or live rollout follows.

Plan saved before implementation against PR #43 merge
`7018268a5cbe438fac8c6c6202f206b1e5180050`.

- [x] Provide bounded, read-only selected-workspace lifecycle context: current run,
  eligible packets, retained workers, next handoff and actionable blockers.
- [x] Retain explicit brain decisions to create, continue, handle planning here or
  wait, including rationale, reuse reason, exact context and named resume event.
- [x] Compose phase-delegated standard-policy approval with a create decision
  atomically. Exact-owner mode never gains inferred approval; Harness stays gated.
- [x] Connect the selected create decision to existing recoverable admission;
  revalidate the decision at both reservation boundaries, never call native tools.
- [x] Allow valid owner-delegated standard-policy approvals through existing
  creation, correction, runner and result handoffs; preserve all other checks.
- [x] Reuse exact inheritance seeds and expose the next eligible packet after
  ordinary completion. Wait/handle decisions grant no product execution authority.
- [x] Exercise two-packet progression, delegated and exact-owner boundaries,
  concurrent/replayed decisions, Pause and reservation recovery, plus regressions.

No live workspace activation, native task/message, model change, installation,
maintenance release, schedule change, acceptance or Actions execution is included.
This coordinates existing handoffs; it does not run the future native brain loop.
Adaptive settings, host collectors, dashboard Play and supervised acceptance retain
their separate milestones in COMPLETION-PLAN.md.

## What this connects

The designated brain remains the decision maker and the only native caller. The
coordinator supplies a current, bounded choice context and records the brain's
choice; it does not call an LLM, select a model, schedule itself or operate a Codex
task. It requires an existing registered workspace, controller, owner-reviewed run
and shared allocation. It cannot create those prerequisites, remove enrollment
fences, change dispatch/Pause or activate a mission.

For standard-policy tasks, an owner-authorized `phase_delegated` run can now use
the existing creation, correction, runner and result handoffs with its exact
designated-brain approval. Every effect still checks the current run, task contract,
approval, preflight, resource ownership, usage and relevant freshness. Historical
scope validation is not executable authority. Exact-owner mode still needs exact
owner task approval. Harness and delegated archival remain unavailable through
these adapters. No model, effort or speed override is introduced.

## Selected-workspace commands

Commands share the prefix:

```text
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace EXACT_WORKSPACE
```

Use the selected brain's private `ORCHESTRATOR_CONTROLLER_TOKEN`. Never place it
in a prompt or repository. JSON files must be regular UTF-8 files, at most 16,000
bytes, with no duplicate fields or non-finite values; symlinks are refused.

| Command suffix | Purpose |
| --- | --- |
| `brain-cycle-inspect` | Read current run, candidates, retained ownership, budget and next handoff hints |
| `brain-cycle-decide REQUEST_JSON` | Retain an explicit create/continue/handle/wait choice and, if permitted, exact delegated approval |
| `brain-cycle-read DECISION_HASH` | Read the original decision, rationale, target, version and receipt without renewing it |
| `brain-cycle-wait-state DECISION_HASH` | Compare recorded event categories and supervision needs without writing or polling native tools |
| `brain-cycle-reserve DECISION_HASH` | Reserve the selected create target through the existing recoverable shared admission protocol |

Inspection contains no transcript or artifact bodies and never approves, reserves,
refreshes evidence or emits native arguments. It returns the current `contextHash`
and workspace `revision`. Candidates use existing preflight, predecessor-axis,
contract, local/shared capacity, task-attempt and minimum token-headroom checks.
They are point-in-time choices, not capacity reservations or send permissions.
The actual estimates and every effect are checked again. Inventories are bounded
to 500 rows per relevant table and explicit byte limits; excess refuses instead of
silently truncating coverage. Larger-portfolio qualification remains separate.

### Decision schema

Every decision has the exact fields below; unused values must be `null`:

```text
id, expectedRevision, contextHash, choice, queueId, workerId, estimates,
rationale, reuseReason, scopeAssessment, resumeEvent
```

- `create`: select one eligible `queueId`, provide `scopeAssessment` and positive
  `estimates: {workTokens, reviewTokens, handoffTokens}`. Work tokens cannot undercut
  the task declaration. Leave `workerId` and `resumeEvent` null. A missing approval
  can be created only under the exact owner-delegated phase grant and is committed
  atomically with the decision. Existing approval is preserved; revoked, stale or
  superseded approvals are never silently replaced.
- `continue`: select one exact `workerId` whose current owned journal has fresh
  confirmed idle evidence, no unresolved send/runner, valid edit authority and fewer
  than two consecutive no-progress corrections. Leave queue, estimates, scope
  assessment and resume event null. This returns the correction handoff as the next
  step, not a message or correction permission; that handoff rechecks findings,
  estimates, authority and one-shot delivery independently.
- `handle`: record why bounded planning/review should stay in the brain. Leave
  queue, worker, estimates, scope assessment and resume event null. This grants no
  product edit, acceptance, publication or other effect authority.
- `wait`: record a specific nonempty `resumeEvent`, with no target, estimates or
  scope assessment. This is a durable reason to await new input/evidence; it neither
  enables polling nor changes a heartbeat. Existing in-flight work still requires
  its normal supervision and safe-stop procedure.

All choices require nonempty bounded `rationale` and `reuseReason`. Selecting
`handle`/`wait` after Pause records planning only; it does not bypass the stop.
Artifact text or a chat answer cannot choose/confirm this controller operation.
The native brain must make the decision under its authenticated controller.

### Reservation and inheritance

Call reserve on the exact latest create decision within 60 seconds. Both local
and shared reservation stages revalidate that decision, selected seed/contract and
approval, as well as all existing run, Pause, maintenance and admission checks.
Reservation retries can recover the same pre-creation claim; they cannot create a
second attempt or cross a creation boundary again. A lost local receipt uses the
existing dispatch recovery path and preserves all ownership and token charges.

After a successful reservation, use the existing native creation begin/check/
record protocol. It generates the immutable seed inheritance packet and now names
the seed, mission and task-contract hashes explicitly. The brain calls the native
tool once; this coordinator never creates a task itself. Existing correction,
runner and result protocols remain separate bounded operations. Their historical
acknowledgments do not authorize another effect.

After independent result acceptance, inspect again. The accepted task remains
retained, but a new eligible packet can be selected under the same still-valid
phase grant. A final worker reply alone never qualifies. Predecessor dependencies
retain their required evidence axes; settlement or completion does not automatically
merge, archive, cross the phase checkpoint or revise the token budget.

## Replay and recovery

Decisions bind both ledger revision and the shared-state fingerprint. Changed
usage, ownership, context, scope or approval requires a new inspection. Concurrent
identical requests retain one approval/decision; different content with the same
ID refuses. Replays return only the original historical receipt, including after
Pause, without restoring an older latest pointer or renewing the 60-second window.

The latest decision, version chain and immutable request receipt are checked before
selection/admission. A new decision can supersede an unused choice, but never erases
an existing dispatch intent, uncertain send, attempt count or resource owner.
Interruption between reservation stages leaves the existing explicit recovery
boundary, not permission to allocate under another identity. Missing/tampered
history fails closed. History maintenance is explicit after 1,000 decisions.

## Delivery boundary and qualification

This source increment supersedes the earlier exact-owner-only restriction of the
standard creation/correction/runner/result handoffs only where a valid retained
owner-delegated phase grant applies. It does not authorize live rollout. Stop and
upgrade older writers before separate activation; no mixed-version/downgrade
compatibility is claimed. Prompt hashes change, so never reuse prepared handoffs
across an upgrade. Keep source, merge, installed skill, runtime and live acceptance
as separate evidence states.

Fixtures cover delegated approval and recovery, actual subprocess CLI requests,
native-shaped one-shot inheritance, same-task correction/runner messages, measured
local source plus stubbed GitHub result review, and selecting/reserving a second
packet after the first is accepted. They do not prove live native transport or
autonomous Play.

Local verification on 2026-09-20: all 1,165 Python tests passed, including the
29 coordinator tests and delegated preservation/unauthorized-approval cases.
All 7 JavaScript UI test files, `node --check web/app.js` and `git diff --check`
passed. GitHub reported zero configured Actions workflows and zero runs before
publication. Missing CI checks are not passing CI; no workflow or job was enabled.
