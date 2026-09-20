# WSP-03B4 — run authority kernel

Update: [WSP-04E](MODEL-POLICY.md) also accepts an exact current owner-reviewed
adaptive model/effort policy. The native-default-only restriction below describes
the original increment. Policy review is not run activation; all mission,
checkpoint, expiry and admission gates remain. No live rollout is included.

Plan saved before implementation, continuing merged PR #22 (`9e0485f`).

This increment implements the durable authority half of Play. It has no HTTP or
CLI activation route and cannot create tasks. The native adapter must later
couple these checks to shared admission, ownership recovery and effect receipts
before an owner-facing Play control is enabled. An internal authority receipt
alone is never a native execution permit.

## Implementation checklist

- [x] Exact owner-confirmed run authorizations, immutable history, expiry and
  monotonic generations bound to workspace, brain, mission and phase review.
- [x] Exact contract-bound owner approval or explicitly delegated brain approval;
  keep Harness exact-owner-only and default native settings only in this kernel.
- [x] Revalidate authority on every task check, including phase/contract changes,
  held tasks, stop intent, expiry and revoked approvals.
- [x] Atomically fence run authority on Pause, brain stop, mission changes and
  controller recovery. Ordinary Resume must not re-arm a fenced generation.
- [x] Brain-initiated stop reasons reuse cooperative checkpointing; retain the
  exact checkpoint before another owner authorization can be recorded.
- [x] Refuse legacy dispatch for run-managed ledgers, retain format/history on
  retries, and test concurrent/restarted/partially failed operations.

## Boundaries

The Python kernel is an internal integration seam, like the admission kernel;
there is deliberately no browser, assistant, installed-skill or CLI write route.
No live state is initialized or migrated when this source is installed or read.
The first explicit internal authorization upgrades that ledger to v3 atomically.
Stop and upgrade older processes before any eventual live rollout; a format marker
cannot stop an already-cached old helper. Do not downgrade markers or remove
authority records to regain legacy dispatch.

Run authorization records owner intent, not running activity. Capacity, fresh
usage, host capabilities, native settings, worktree safety, acceptance and delivery
evidence remain separate checks. No allocation or token counter is reset here;
a new generation is not a new budget. Unfinished workers retain ownership.

Only the explicitly selected `native_defaults` settings policy is supported by
this increment. All task model/effort/speed requests must therefore be null.
Adaptive settings need a separately reviewed exact policy and verified destination
capabilities. No inferred model choice, silent fallback or account-wide setting
change is permitted.

Every future native effect and continuation must revalidate the current run,
exact task approval and admission immediately before effect intent is retained.
The authority check does not produce native argv, start a scheduler, notify a
brain or grant permission to bypass product repository rules.

## Internal contract

`orchestrator.run_authority` is callable only by trusted future integration code
or isolated tests. The `actor` parameter is a trusted caller assertion, not an
authentication mechanism. A future owner route must authenticate and authorize
the owner, validate CSRF/origin and bind its exact preview before calling it.
The designated-brain methods additionally require the current controller token
whose owner matches that workspace's brain. No browser can select an actor or
supply a native target through this increment.

| Method | Retained effect; never a native permit |
| --- | --- |
| `authorize` | Exact owner intent for one reviewed phase, explicit native-default settings, expiry and a new monotonic generation |
| `approve_task` | Exact current contract and run hashes, actor, semantic scope assessment and immutable approval history |
| `revoke_task` | Withdrawal of an exact approval, retaining earlier versions even after stop/expiry |
| `check_task_in` | Revalidate scope, actor, operation, settings, stop state and expiry in the coordinator transaction; return separate admission-required status |
| `stop` | Designated-brain stop condition and the existing cooperative brain/worker checkpoint command; no process kill or release |
| `read` | Internal retained state, explicitly no activation or execution authority |

All mutations use SQLite `BEGIN IMMEDIATE`. Exact request replay returns its
hash-verified historical receipt without reapplying an effect. Reusing an ID for
different content or an operation refuses. Distinct requests at the same revision
have one winner. Requests are bounded to 16,000 UTF-8 bytes and immutable records
to 32,768; malformed/oversized records do not become permissions. There is no
remove-run, downgrade or unfence command.

An authorization binds workspace/brain, mission hash and review receipt, mission
revision, phase ID, checkpoint destination, repository mapping/policy hashes,
authority limits and settings policy. Expiry must be within 24 hours; the kernel
does not schedule expiry polling. Every authority check rechecks time. A future
active brain must checkpoint when expiry or other necessary evidence is lost.

Task approvals remain distinct from the legacy seed-only `approval` field. They
do not mark a queue item dispatchable. Exact-owner mode refuses brain approval;
phase-delegated mode allows it only within the current owner intent and existing
repository rules. Harness cannot select phase delegation. A semantic assessment
is a retained brain/owner judgment, not proof that generated code is in scope.
Independent result verification and repository constraints remain mandatory.

Held, changed, stale or superseded contracts cannot pass a task check. Requested
overrides fail under native-default policy instead of being silently dropped.
Reprepare retains approval history but invalidates its current binding. Approvals
cannot be used to replace an already owned task; continuation needs its own
future adapter path. A grant never substitutes for fresh packet preflight.

## Stop, checkpoint and release

Run intent follows `authorized_intent → fenced → checkpointed`. These are ledger
states, not native activity labels. Every new owner authorization receives a new
generation and retains the previous run hash; old approvals cannot carry over.

Workspace Pause, advanced dispatch pause, controller recovery and mission changes
fence authority atomically with their existing local state change. A dispatch
pause remains a hold on new work; workspace Pause/brain stop uses the stronger
worker/descendant safe-checkpoint protocol. Neither is a hard kill. Resume brain
only wakes the brain; ordinary Resume never restores run authority or bypasses
the run-managed legacy-dispatch fence.

The brain may stop for a phase checkpoint, roadmap completion, plan revision,
budget revision, exhausted corrections or lost evidence. These reasons are
cumulative: a later ordinary pause cannot erase a mandatory review boundary.
Only the existing verified park operation attaches its exact retained checkpoint
to the run. Missing/uncertain worker state still blocks parking; ownership and
native activity remain separate. Corrupt run metadata keeps its fence but cannot
prevent an otherwise valid safety pause/park.

A new owner intent must release that exact current parked checkpoint. A
brain-initiated boundary additionally requires a newly reviewed mission/phase or
bounded correction scope; the owner cannot release it with an unchanged review.
The checkpoint's preserved artifacts and proposed next scope are distinct from
independent success/acceptance evidence. A second stop after a brain-only wake
requires the newer checkpoint, not an earlier one.

Reauthorization never opens a new budget allocation here. The future coordinator
must preserve cumulative phase/task-attempt usage across generations and must not
treat a new run hash as permission to reset any budget or retry ceiling.

## Required next integration

WSP-04C1 now supplies the internal reservation/creation-intent journal described
in [DISPATCH-ADMISSION.md](DISPATCH-ADMISSION.md), including same-phase budget
continuity and cross-store receipt recovery. It does not implement the native
adapter, continuation, maintenance-fence release or owner-facing activation below.

Before public Play, implement and verify the cross-store/native coordinator:

1. Resolve reconciled ownership, exact repository/runner identities and fresh
   account plus brain/worker/review usage; retain all existing maintenance fences.
2. Bind one recoverable admission intent to exact run/task approvals and cumulative
   phase budget. Recheck authority and capacity at creation and continuation
   boundaries; no unchecked caller-supplied booleans as native permission.
3. Record one-shot effect attempts, pending versus confirmed native IDs, uncertain
   outcomes and recovery before retries. No timeout implies non-creation or release.
4. Connect authenticated exact owner Play/approval/release controls and immediate
   brain notification only after the adapter enforces them. Update the installed
   skill explicitly, then qualify a separately authorized real pilot.

The kernel check returning `authoritySatisfied: true` always also returns
`executionAuthorized: false`, `admissionRequired: true` and
`nativeAdapterAvailable: false` in this increment. Source delivery is not live
activation. See [verification evidence](RUN-AUTHORITY-VERIFICATION.md).
