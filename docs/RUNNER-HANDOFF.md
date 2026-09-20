# WSP-04D4 — brain-owned runner handoff

Plan saved before implementation, following merged PR #33 (`2c1acc3`).

Connect the standard-policy runner coordinator to explicit designated-brain CLI
operations. The helper emits a bounded message for an existing confirmed task;
the brain remains the only native caller. No live activation accompanies delivery.

## Implementation checklist

- [x] Expose runner reservation, process observation, cleanup release and receipt
  recovery through explicit selected-workspace/controller operations.
- [x] Prepare a version-bound handoff from the exact approved execution contract,
  runner reservation and retained instruction artifact; no model/effort override,
  arbitrary prompt, command execution or Harness acceptance.
- [x] Consume the one-shot launch boundary immediately before a native send,
  rechecking authority, Pause, current journal, artifact bytes and budget. Concurrent
  checks and replay must never return another send permission.
- [x] Record acknowledged/uncertain delivery separately from process activity,
  exit, cleanup, ownership settlement and result acceptance. Lost sends stay held.
- [x] Test the complete fixture workflow, tampering, stale evidence, Pause races,
  contention, crash recovery, cross-workspace identity and CLI boundaries.
- [x] Update roadmap, operator documentation and verification evidence.

## Boundaries

This increment does not send native messages, run commands, change live ledgers,
install skills, restart the dashboard, alter schedules or release maintenance
fences. Standard policy only. Trusted runner/host observations and complete native
descendant/counter collection still require independent qualification before an
owner-authorized pilot. Supplied evidence remains a caller assertion, not native
or host attestation. Neither delivery acknowledgment nor exit code establishes
CI, semantic correctness or acceptance.

## Brain procedure

Use only an already admitted, exact owner-approved standard-policy worker with a
confirmed **local task ID**, not a pending client ID. The current controller must
belong to the registered workspace brain. This CLI does not initialize admission,
approve a task, create a run or opt a workspace into execution. No HTTP/assistant
write route, helper scheduler or private desktop transport is introduced.

All commands have the prefix:

```text
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace EXACT_WORKSPACE
```

Keep `ORCHESTRATOR_CONTROLLER_TOKEN`, JSON inputs, evidence and emitted arguments
private. Input files are bounded regular files (16,000 bytes), not symlinks or
FIFOs. Requests use the existing closed runner schemas in
[runner coordination](RUNNER-COORDINATION.md), always with `id` and `expectedHash`.
Use unique request IDs across the worker's whole native journal.

1. Independently observe native task idle, runner idle, cleanup, current approved
   execution and account/phase headroom. Missing evidence blocks the workflow.
   `runner-handoff-state WORKER` reads existing bindings without refreshing them.
2. Call `runner-handoff-acquire WORKER REQUEST_JSON` with the `acquire` schema.
   This holds the pinned runner and additional work/review/handoff tokens under
   the existing coordinator. It does not start tests or consume another task slot.
3. Obtain a fresh runner idle observation **after** acquisition. Call
   `runner-handoff-prepare WORKER REQUEST_JSON` with the coordinator's `begin`
   schema: `{id, expectedHash, runnerKey, reservationId, observation}`. It returns
   `tool: send_message_to_thread`, exact `arguments`, `handoffHash` and
   `mustCheckBeforeSend: true`. Save that one response privately. The message
   contains the approved seed's execution contract, exact worker/runner/seed
   bindings and fixed stopping rules. The instruction artifact is a hash-bound
   audit reference only; its body cannot inject instructions into the message.
4. Immediately before sending, call `runner-handoff-check WORKER HANDOFF_HASH`.
   It rechecks current authority, preflight, worker controls, budget, artifact
   bytes and evidence freshness. The handoff is valid for at most 60 seconds
   (stricter admission freshness still applies). It commits the existing local
   launch marker, then the shared launch intent, then attaches the local receipt.
   Only this first successful call returns `sendNow: true`.
5. In the same brain turn, use the available native `send_message_to_thread` tool
   with the saved arguments **unchanged**, without model/effort overrides. No
   helper command calls that tool. If it is unavailable, a stop intervenes, or
   output was lost, do not substitute another transport or repeat the check/send.
   Preserve ownership for reconciliation. A check is not a reusable permit.
6. Record the actual delivery observation using
   `runner-handoff-delivery WORKER REQUEST_JSON` with exactly:
   `{id, expectedHash, handoffHash, hostId, threadId, outcome, observedAt, evidenceHash}`.
   `outcome` is `acknowledged` only with native acknowledgment for that exact
   target; otherwise `uncertain`. The evidence hash references retained private
   native evidence. Neither an error nor a timeout proves a message was not sent.
   The helper checks bindings, not the truth of this caller-supplied observation.
7. Use `runner-handoff-observe-process WORKER REQUEST_JSON` with the existing
   process schema. Current native activity alone does not prove process identity,
   full tree exit or host cleanup. Preserve a nonzero exit code as observed.
8. Only after fresh independently observed exit, native idle and cleanup, call
   `runner-handoff-release WORKER REQUEST_JSON` with the existing release schema.
   This releases the runner key only; repository ownership and token holds remain
   until [terminal settlement](OWNERSHIP-SETTLEMENT.md). Result acceptance remains
   a separate [review](RESULT-REVIEW.md), never a message acknowledgment.

The native tool schema is supplied by the active Codex task and can vary by host
or app version. Check its availability before preparing. Public app documentation
does not substitute for that tool contract or qualify runner/descendant evidence.
No SDK, app-server process, provider credential or new model service is added.

## Recovery and Pause

`runner-handoff-state WORKER` returns the current journal/attached hashes, runner
status, delivery status and whether a local/shared send boundary was consumed.
It never returns arguments or a send permission. `runner-handoff-recover WORKER`
only attaches the latest retained receipt, and does not refresh source timestamps.

- Before the check, preparation is inert. An unlaunched reservation can be
  canceled with fresh complete cleanup evidence. Cancellation does not restore
  the worker's single runner attempt. Expired preparation cannot be regenerated
  as a hidden retry; do not edit the database to clear it.
- A crash or Pause between local and shared launch commits leaves a local-only
  intent. It remains a blocker even if no message was observed. Existing recovery
  preserves it; a later explicit reconciliation contract is required to close it.
- A crash after shared commit can recover the receipt, not the permission to send.
  Lost check output and uncertain native delivery never authorize resend or
  cancellation as `unlaunched`. There is no claimed native exactly-once guarantee.
- The check-to-tool-call gap is cooperative in-flight work, not atomic cancellation.
  If the brain sees a stop before sending, it must not send. It must retain the
  consumed boundary and report the blocker, not erase it or guess a safe release.
- Late delivery/process facts remain recordable after Pause. Acknowledgment does
  not set native activity to running/idle, change runner status, refresh process
  timestamps or release any resource. An acknowledged delivery cannot be
  downgraded or re-timestamped. Exact request replay is historical; it never
  regresses newer process state or renews evidence age.
- Cleanup-only release still honors maintenance fences; observations and receipt
  recovery do not clear them. After terminal ownership settlement, this active
  worker interface no longer appends runner history.

Quiesce older controller/helper writers before any explicitly approved rollout.
No mixed-version writer/downgrade compatibility or live migration is claimed.
See [verification](RUNNER-HANDOFF-VERIFICATION.md). Remaining gates include trusted
host/native inventory and live counters, preservation qualification, owner setup,
a low-risk standard-policy pilot and subsequent two-workspace acceptance. The
later [result handoff](RESULT-HANDOFF.md) now connects settled standard-policy
tasks to measured source/GitHub evidence and a separate review outcome; it does
not settle native work or infer acceptance from runner exit.
