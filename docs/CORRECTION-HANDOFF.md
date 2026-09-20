# WSP-05B — same-task correction handoff

Update: [WSP-04E](MODEL-POLICY.md) binds adaptive corrections to the current or
explicitly escalated owner-approved model/effort selection. Fresh matching native
settings observations, bounded escalation and profile token floors are required;
all existing one-shot, scope, no-progress, budget and Pause checks remain.
Native-default corrections still emit no setting overrides. No live activation.

Update: [WSP-05C](BRAIN-COORDINATOR.md) also permits exact designated-brain task
approvals inside an owner-authorized delegated standard phase. The original
exact-owner-only boundary below is superseded only for that case; current run,
scope, budget, Pause and one-shot checks remain. No live activation is included.

Plan saved before implementation after PR #42, on `393a53b`.

- [x] Retain the brain's reason for continuing the exact owned task, rather than
  creating a new task, plus its immutable correction-artifact and estimate bindings.
- [x] Prepare without a send permit; consume the existing local-first/shared
  continuation boundary once at check, then emit fixed native message arguments.
- [x] Recheck exact owner/standard/local scope, native defaults, current authority,
  fresh idle evidence, Pause, maintenance, usage and no-progress limits at send.
- [x] Keep delivery acknowledgment, uncertain outcome and finished/idle/progress
  observations separate. Late facts/recovery must not resend or free ownership.
- [x] Exercise subprocess CLI, concurrent checks, corruption, interruptions,
  supersession, two no-progress corrections and full local regressions.

No live correction, task, model change, installation, dashboard restart, schedule,
maintenance release, allocation or autonomous Play is included. The designated
brain remains the only native caller. This does not complete lifecycle selection,
delegated approval, new-generation correction or the full operating loop.

## Supported scope

This is a brain-owned CLI for one **edit-only correction in the same run and
existing task**, before terminal settlement. It composes the existing continuation
journal rather than creating another dispatcher. It supports only an exact
owner-approved standard-policy task, confirmed on the local host. Delegated task
approval and Harness's trusted correction/acceptance adapter remain separate.

The designated brain decides to continue and supplies a rationale and reuse
reason. The helper retains that decision; it does not select work or a model.
Native message arguments contain only the existing host/task IDs and a fixed,
scope-bound prompt. Model, effort and speed overrides are omitted. Review findings
are retained private artifact bytes and embedded as labelled untrusted JSON data,
not executable commands or permission. No acceptance run, new task, push, PR,
merge, deployment, archival or new paid service is authorized by this handoff.

## Brain procedure

Use an already admitted task in the selected registered workspace, with its
current designated-brain controller. Commands share this prefix:

```text
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace EXACT_WORKSPACE
```

Keep `ORCHESTRATOR_CONTROLLER_TOKEN`, request files, findings and receipts private.
Requests must be regular UTF-8 JSON files of at most 16,000 bytes. Duplicate fields,
non-finite values and symlinks are refused. No implicit workspace or legacy state
fallback is supported; these commands cannot initialize admission or activate Play.

| Command suffix | Purpose |
| --- | --- |
| `correction-handoff-state WORKER` | Read the latest decision, journal hash, continuation and cumulative correction reservation |
| `correction-handoff-prepare WORKER REQUEST_JSON` | Retain exact findings, rationale and bindings; no send permit or native arguments |
| `correction-handoff-check WORKER HANDOFF_HASH` | Revalidate and consume the one-shot continuation boundary, returning arguments for one immediate native send |
| `correction-handoff-record WORKER REQUEST_JSON` | Record exact acknowledgment, uncertainty or separately observed completion |
| `correction-handoff-recover WORKER` | Reattach retained receipts without another send permit or ownership release |

1. Observe the existing native task and usage using their own evidence interfaces.
   Read correction state and the current workspace revision. A historical state
   read does not refresh native observations or prove inactivity.
2. Prepare with these exact fields:

   ```text
   id, expectedHash, expectedRevision, operation: "edit",
   estimates: {workTokens, reviewTokens, handoffTokens},
   findings, rationale, reuseReason
   ```

   `expectedHash` is the currently attached native journal hash;
   `expectedRevision` is the current workspace revision. Findings must be nonempty
   and at most 8,000 UTF-8 bytes. Each estimate is a positive integer. Preparation
   binds the findings artifact to the worker, intent, repository and version,
   retains the decision, and returns its `handoffHash` without reserving additional
   shared tokens or sending anything. Authority, fresh idle state, runner clearance,
   coverage, account headroom and no-progress limits must already permit correction.
3. Immediately before the brain calls the native tool, check that exact latest
   handoff. Preparation expires after 60 seconds. The check revalidates scope,
   authority, Pause/maintenance, preflight, budget and exact findings at both local
   and shared continuation boundaries. Only a successful check returns `sendNow`
   and arguments for **one** `send_message_to_thread` call by the brain. Python
   never calls the native tool. Do not store that output as a reusable permission.
4. Record the actual native outcome with:

   ```text
   id, expectedHash, handoffHash, continuationHash,
   hostId, threadId, outcome, observedAt, evidenceHash, progress, activity
   ```

   Use the current native journal hash and exact retained handoff/continuation and
   host/task IDs. `acknowledged` or `uncertain` requires `progress: null` and
   `activity: "unknown"`. After acknowledgment, `finished` requires a separate
   fresh idle observation and boolean `progress`. Bind `evidenceHash` to actual
   observed evidence; do not fabricate acknowledgment, inactivity or progress.
   A completed old turn or message receipt alone does not prove this turn finished.
5. Independently review progress before another correction. Two consecutive
   finished no-progress cycles block further correction. A verified progress cycle
   resets that counter, not token charges. Every consumed shared continuation adds
   its estimate to the existing cumulative reservation; this interface never frees
   resources, settles usage, accepts a result or advances a phase.

Supplied observations are labelled caller evidence, not native/host attestation.
Late result recording and receipt recovery remain available after Pause. They
cannot resume work. Once the task has terminal settlement, use the result/settlement
readers; this correction interface requires an actively owned claim. Changes needed
after terminal review require a separately authorized new-generation path.

## Replay, supersession and interruption

- Exact preparation retries return the immutable historical receipt. Concurrent
  retries recheck that receipt inside the write transaction. Reusing an ID with
  different content refuses. Replaying an old receipt never makes it latest,
  refreshes its timestamp, reserves tokens or grants a send.
- An **unconsumed** preparation may be superseded by a newly revision-bound
  request, for example after expiry or changed findings. Only the latest can be
  checked. Original decisions, findings and receipts remain retained.
- Check commits the local intent before the shared continuation journal and token
  reservation. Concurrent checks cannot emit two send permissions. If interruption
  leaves only the local marker, retain the in-flight ownership and investigate;
  neither reprepare, timeout nor recovery can treat it as unsent or resend it.
- A shared commit with a missing local receipt can be reattached without another
  native effect. Lost output, ambiguous delivery or failure after a consumed check
  never permits a retry. Reconcile actual native evidence instead.
- The check-to-native-call gap is cooperative in-flight work, not atomic
  cancellation. The brain and worker must honor stop controls and checkpoint
  safely; no process kill or cancellation of already executed effects is claimed.
- State and receipt recovery contain no findings text or native message arguments.
  Missing/tampered pointers, artifact bytes or exact bindings fail closed. Retained
  history is bounded; its maintenance is explicit, never automatic deletion.

## Rollout and remaining work

This source increment does not install the skill, modify a live ledger, restart
the dashboard, change schedules, release maintenance or dispatch work. Quiesce and
upgrade older writers before any separately authorized use; mixed-version writers
and downgrade compatibility are not claimed. The brain operating loop, delegated
policy, adaptive settings, trusted observation collection and supervised acceptance
remain in [the convergence plan](COMPLETION-PLAN.md).

## Local verification

Focused correction/native-lifecycle/runner regression: **106 tests passed**.
The new correction suite covers 32 cases, including a subprocess CLI round trip,
concurrent preparation/checks, stale findings, corrupt bindings, missing pointers,
Pause and authority races, uncertain delivery, receipt recovery, historical replay,
budget/coverage refusal, malicious findings and the two-no-progress bound.

Full local regression: **1,135 Python tests passed**; `node --check web/app.js`,
all **7 JavaScript UI test files**, and `git diff --check` passed. GitHub read-only
inspection reported **0 configured Actions workflows and 0 runs** before push.
No workflow was added/enabled or job dispatched. Missing CI checks are not passing
CI. No native message or live workspace operation is used by these tests.
