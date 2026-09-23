# Standard cooperative runs

This is the separate contract explicitly approved on 2026-09-21. It is not a
relaxation of the strict managed/Harness protocols documented elsewhere.

## Owner workflow

1. Create/designate a native Codex brain and register its private workspace using
   [workspace setup](WORKSPACES.md). Use only standard-policy repositories.
   Never copy an enrolled/strict ledger into this mode. Existing workspaces do
   not opt in automatically.
   The standard brain's `preserve` operation retains only approved task artifact
   paths in the pinned repository or its worktree. It needs no broad artifact root.
   The separate legacy `artifact-add` importer still requires explicit roots;
   see [observation setup](OBSERVATIONS.md). A Git commit alone is not a retained
   dashboard artifact version.
2. In **Mission & authority**, save and review a phase: goal, success criteria,
   exclusions, repository paths, operations, owner checkpoint, parallel/task
   limits, token allowance and checkpoint reserve. Select phase delegation only
   if the brain may approve bounded implementation seeds. Merge stays manual by
   default; the separate future exact-PR opt-in is described below.
3. The first **Review Play** automatically retains a fixed, read-only capability
   request and notifies that workspace's existing brain. The brain follows the
   source [standard cycle](../skills/codex-orchestrator/references/standard-cycle.md),
   records the actually exposed native model/effort catalog against the exact
   request, and releases its setup controller. The catalog is valid for 24 hours
   before activation. The owner does not copy a message between the dashboard
   and Codex.
4. Start the dashboard with the existing `--platform` registry and the explicit
   `--notify-brain /absolute/path/to/codex` option. Open its private session link.
   On the selected workspace's Overview, **Review Play** starts capability
   collection when needed and displays saved, sent, received, failed and overdue
   states. After the receipt, the same intent opens the exact mission/catalog/
   limits preview; then confirm. This authorizes one phase, not the full unbounded
   roadmap. Default duration is eight hours (API supports 1–24).
5. Monitor Overview or Workers & evidence: native links, inherited seeds,
   requested model/effort, results, token gaps and immutable run versions.
   Deliverables preserved with `preserve` appear in the existing versioned
   Artifact library. Knowledge also exposes retained run versions.
   Decision inbox keeps its version-bound free-text/option answers and outcome
   artifacts. Running brains receive them through the standard cycle; answers
   saved while stopping/paused do not wake or resume the brain.
6. **Pause at safe checkpoint** immediately fences new task effects after
   confirmation. The brain supervises already-issued work to a safe terminal
   checkpoint. It does not hard-kill a process. Resume is available only after
   parking; it retains the same run, task attempts, allowances and expiry.
7. Phase completion, failure, significant plan change or insufficient allowance
   stops at an owner checkpoint. Review a genuinely new phase for the next Play.
   Changing a phase ID merely to evade a budget/attempt boundary is prohibited.

## Guarantees and non-guarantees

| Area | Cooperative standard contract |
| --- | --- |
| Scope | Explicit registered workspace tasks; never all account history |
| Authority | Exact reviewed phase plus separate signed owner Play |
| Scheduler | Existing native brain, not Python/background model dispatch |
| Native creation | Durable claim and one-shot issue before the external call |
| Unknown result | Retained ownership; no automatic resend or guessed absence |
| Concurrency | Owner limit, one registered task per canonical Git common directory, maximum 16 registered active tasks across a standard registry |
| Usage | Observed partial totals or unknown; not complete lifetime counters |
| Budget | Brain reservation plus at least each task's conservative allowance; greater observed counts increase charges; no refund/reset on Resume |
| Cleanup | Finished native task and tracked-terminal observations; no whole-process-tree assurance |
| Settings | Actual exposed catalog, brain complexity rationale; requested settings are not execution attestation; speed is not controlled |
| Results | Brain independently inspects source/tests and retains evidence; assertions are not externally attested CI |
| Retention | Native tasks/checkouts retained; no implicit archive, deletion or merge |
| Inference | No API needed for orchestration; existing optional assistant remains separate |

Capability notification retries are deliberately asymmetric. A definitely
unavailable delivery may be retried automatically with the same retained request,
up to three total attempts. An accepted, sending or uncertain delivery is never
resent: the UI polls only for its ledger receipt and falls back to the existing
heartbeat or an operator-visible brain inspection. A brain-side observation error
is retained with a bounded reason and never converted into a guessed catalog.

The dashboard initially reserves 20% of the reviewed phase allowance for the
brain plus the configured checkpoint reserve. Worker claims require room for
their full estimates. These estimates are planning controls, **not a hard spend
cap**: native turns can overshoot, observations can be missing, and an active
bounded step is not forcibly interrupted. Missing usage is displayed as unknown.
Local projectless mappings are explicit (`projectId: projectless`); saved native
Git projects use their normal managed worktree target. External/unregistered work
is outside the capacity claim. A registry with strict enrollment or active legacy
owners needs separate setup/migration, not an automatic bypass.

## Persistence and recovery

`standard-acquire BRAIN_ID:TURN_LABEL` writes an owner-only controller credential
inside the private ledger directory. `standard-brain REQUEST.json` loads it
without printing it; `standard-release CHECKPOINT` releases it and removes that
ephemeral credential. Tokens must never enter source, prompts or reports.

Reads do not refresh observations or create authority. Every journal mutation
retains a content-addressed version. Explicit cooperative activation marks ledger
schema v4; older helpers refuse it. Stop older dashboard/helper processes before
opting in; never downgrade a marker. After interruption, inspect the existing
controller and issued effects with native tools. Do not delete state or reacquire
blindly. Explicit legacy controller recovery fences the standard run as well;
an orphaned private credential file needs operator reconciliation, not a hidden
retry. Dashboard restart invalidates login/previews, but does not reset the run.

The supported native interface was qualified against installed Codex
`0.155.0-alpha.9.2` and the [official app-server reference](https://learn.chatgpt.com/docs/app-server).
Read metadata, token notifications and tracked terminals do not establish the
strict whole-lifecycle guarantees. This is why the standard and Harness contracts
are distinct, not why a strict gate should be marked verified.

## Future exact-PR merge opt-in

Manual merge remains the default. A separately reviewed future standard phase may
opt in to [the one-shot exact-PR merge handoff](STANDARD-MERGE.md), subject to its
existing checks-based repository policy. The brain independently cross-checks the
completed task/result, retained source, fresh GitHub policy/checks and local tests;
only its first check response can emit fixed head-matched `gh` merge arguments.
Unknown delivery is retained and observed, never resent. Dashboard merge history
is separate from CI, runtime and phase acceptance.

Before such a Play, the installed launcher must be updated from its stale
schema-1-only source to the exact compatible merged source, with older writers
quiesced. Shipping this source does not install, migrate, restart or activate a
workspace. This enabling phase stops at an open PR for manual merge.
