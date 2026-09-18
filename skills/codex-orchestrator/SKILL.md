---
name: codex-orchestrator
description: Coordinate explicitly approved development packets across repositories using native Codex tasks, a durable local ledger and an operations dashboard. Use for queue approval, dispatch, reconciliation, checkpointing and recovery in an onboarded portfolio; not for unrelated coding or blanket roadmap execution.
---

# Codex Orchestrator

The existing designated Codex brain is the only scheduler. The local helper is a
transactional ledger and dashboard, not an agent or desktop API client. A user
request to install this tooling does not approve product packets.

Run the installed `scripts/run.py` with `status` first. It resolves the private
installation location and starts the CLI; it never invokes a shell. Read
`references/operations.md` before the first reconciliation, recovery, or dispatch.
If the installation or native tools are unavailable, report that boundary; do not
substitute private app APIs, background agents, cron, or another model service.

For first-drive preparation or readiness questions, use the Readiness section of
`references/operations.md`. Diagnostics and synthetic rehearsal do not authorize
a native task or satisfy the real pilot requirement.

## Authority and dispatch

- Operate only on the configured portfolio. Ask the user before adding unrelated
  repositories, changing policy, or authorizing more work.
- Prepare is not approval. Only an explicit user request for exact packets and
  scope, or the authenticated dashboard approval, authorizes task creation.
  Bind approval to both packet digest and immutable inheritance seed hash.
- Preserve repo AGENTS.md, predecessor contracts, locks, allowed paths and merge
  policy. The Harness profile additionally preserves clean-room access denial,
  exact isolated offline execution, credential ordering, attempt budgets and
  manual live-campaign boundaries. Never execute product acceptance through this
  personal helper or a generic shell.
- Use native task creation only for the approved implementation tasks. Create a
  fresh task with the generated inheritance prompt; do not fork the entire brain.
  Omit model/effort overrides unless the user explicitly selected them.
- Never infer completion from a worker's final message. Independently verify exact
  commit/paths, required CI and each required evidence axis. A merge is not live
  acceptance. Retain completed tasks unless explicitly asked to archive.

## Reconciliation

1. Acquire one controller token with an identity including this brain and turn.
   Keep the token in `ORCHESTRATOR_CONTROLLER_TOKEN`, never in prompts or reports.
2. Read durable state and checkpoint; process typed control requests. Observe
   existing native tasks with compact `wait_threads` snapshots. An in-flight native
   request or uncertain creation must be reconciled before any retry.
3. Verify eligible approved packets, current project mappings, actual refs, packet
   bytes, predecessor evidence, source locks, worktree setup safety, external
   runner occupancy and absence of duplicate work. Respect dependency edge types;
   do not flatten optional runtime edges into build dependencies.
4. Reserve capacity, then call `begin` immediately before native `create_thread`.
   `begin` is a one-shot creation boundary. Call once and record its exact result.
   Record a pending client ID separately; never pass it to tools expecting a task ID.
5. Workers stop before acceptance. Grant the shared runner reservation only after
   observing it idle. Continue that worker through the native messaging tool. Do
   not release until the process has exited and required cleanup is observed.
6. Verify completion or record a blocker. Corrections remain in the same task;
   two unsuccessful no-progress cycles escalate. Preserve attempt counters imposed
   by the packet even if they are stricter than the controller's correction limit.
7. Release the controller with a concise checkpoint. Never age out worker or runner
   ownership merely because the brain or computer went away.

## Scheduling and user interface

Use the app's native heartbeat on this existing brain, every 15 minutes while
approved or active work needs supervision. Inspect for an existing matching
automation before creating one. No unchanged-state notifications. Pause it when
the queue is drained or only user decisions remain and no task is active.

The dashboard can persist pause/approval/hold/priority changes immediately. Resume,
reconciliation, worker checkpoint and archive requests wait for a brain cycle.
An inactive heartbeat is not awakened by the webpage: explain that the user must
say “continue orchestration” in the brain. Do not claim a queued action executed.

Read-only onboarding must not resume dispatch, approve a packet, create a worker,
run acceptance, alter a product repository or auto-enable two-worker concurrency.

## Observations and artifacts

For portfolio monitoring or a requested report, read the Observations section of
`references/operations.md`. Use `observe` for local measurements and `observe
--remote` for explicit read-only GitHub status. These are not reconciliation or
approval. Preserve task artifacts with `artifact-add` before closing a task;
creation times must be observed, not inferred from file modification times.
Never treat local token logs as a subscription bill, a checked plan item as
acceptance, or a historical file reference as preserved historical bytes.
