# Codex-native orchestration roadmap

This is recorded implementation progress, not deployment, pilot, or product
acceptance authority. Items change through reviewed repository edits.

## Foundation — v1

- [x] Reusable portfolio configuration and repository-specific policies
- [x] Durable approval, inheritance, worker and evidence ledger
- [x] Native brain workflow and bounded task creation contract
- [x] Authenticated local operations dashboard
- [x] Read-only codebase snapshots and repeatable reports
- [ ] Complete a real approved implementation-worker pilot
- [ ] Enable two-worker concurrency after independent pilot acceptance

## Observability — v2

- [x] Import local token usage with duplicate and continuation handling
- [x] Show repository, task, model and effort usage distributions
- [x] Observe worktrees, branches, commits and explicit GitHub status
- [x] Preserve and read artifact versions across scoped tasks
- [x] Show versioned roadmap checklist sources
- [x] Verify importer, security, lifecycle and dashboard regressions
- [x] Publish and merge the observability extension (PR #2)

## Advisory intelligence — v3

- [x] Optional server-side inference client and ignored credential configuration
- [x] Bounded aggregate-only executive brief with evidence references
- [x] On-demand Overview controls, stale/error states and explicit data preview
- [x] Versioned brief artifacts and separate service-reported token counts
- [x] Verify live routing, complete-answer rejection and regression tests
- [x] Verify rendered generation, evidence preview and artifact-version reading
- [ ] Qualify narrative accuracy with repeatable portfolio fixtures
- [x] Publish and merge the inference extension (PR #3)
- [x] Align with Planeon issue #38: streamed briefs/chat, pinned local models, shared token-budget checks, both-model availability and clone-wide credential-document ignore rule (source/local verification; runtime rollout separate)

## Operational readiness — v4

- [x] Deterministic readiness view with per-repository blockers and next actions
- [x] Scoped native inventory observations with explicit freshness
- [x] Shared read-only packet eligibility explanation and dispatch enforcement
- [x] Invalidate approvals on mapping changes; preserve active ownership
- [x] Isolated lifecycle rehearsal with retained synthetic evidence
- [x] First-pilot scope proposal and explicit CI/setup/approval gates
- [x] Update the brain skill with read-only readiness and rehearsal procedures
- [x] Verify browser readiness controls and complete regression checks
- [x] Publish and merge the readiness extension (PR #4)
- [ ] Register the selected pilot repository and verify native setup
- [ ] Resolve and verify the pilot's CI evidence route
- [ ] Approve and complete one real native-worker pilot

## Runtime provenance — v5

- [x] Separate server-start checkout, current checkout and observed GitHub revision
- [x] Detect dirty, changed-source, changed-revision and unknown/stale states
- [x] Explicit metadata checks without automatic fetch, pull, restart or dispatch
- [x] Regression tests for runtime fingerprints, privacy and remote error handling
- [x] Verify rendered runtime inspection and clean-restart comparison
- [x] Publish and merge the runtime provenance extension (PR #5)

This maintainer implementation does not qualify as the real native-worker pilot.

## Brain visibility — v6

- [x] Place brain activity, freshness and dispatch state at the top of Overview
- [x] Read bounded local brain event metadata without retaining conversations
- [x] Show recent activity in Knowledge and link the latest retained brain artifact
- [x] Distinguish checkpoint age, native observations and implementation workers
- [x] Verify regression tests and rendered browser interactions (112 tests)
- [x] Publish and merge the brain visibility extension (PR #6)

## Dashboard-first continuation — v7

- [x] Versioned decision inbox with immutable artifact links and explicit scope
- [x] Authenticated owner answers, one-time receipt and artifact-bound outcomes
- [x] Standalone free-text answers without choosing a suggestion; exact text retained
- [x] Preserve duplicate, superseded and interrupted response states
- [x] Separate idle decision listening from implementation dispatch authority
- [x] Compact inbox CLI and native-brain continuation procedure
- [x] Verify full regression suite and rendered decision interactions (133 tests)
- [x] Install updated skill and activate the existing native listener
- [x] Verify a real brain-published decision in the dashboard
- [ ] Complete a real dashboard-approved implementation-worker pilot
- [x] Publish and merge the dashboard-first continuation extension (PR #7)

## Immediate decision notification — v8

- [x] Opt-in supported native queue notification of the existing brain
- [x] Durable one-shot claim, duplicate protection and ambiguity recovery
- [x] Separate notification, brain receipt, scoped outcome and dispatch authority
- [x] Regression suite (147 Python tests) and delivery presentation checks
- [x] Live CLI wake verified against independent brain receipt and retained outcome
- [x] Verify rendered saved-answer and notification states in an isolated fixture
- [x] Publish and merge the immediate-notification extension (PR #8)

## Brain control and safe checkpoints — v9

- [x] Immediate native notifications for pending typed controls, not just answers
- [x] Separate brain resume/stop from worker dispatch and native activity
- [x] Cooperative checkpoint gates, supersession and retained ownership
- [x] Stopped-input deferral and resume from the retained checkpoint
- [x] Preserve stale last-observed idle instead of an ambiguous unknown label
- [x] Regression suite (164 Python tests) and control presentation checks
- [x] Install cooperative inbox-check and checkpoint guidance for the brain
- [x] Verify rendered control lifecycle and checkpoint reader in an isolated UI fixture
- [x] Brain-control extension merged as PR #9

## Contextual assistant and workspace panes — v10

- [x] Request-only chat using the existing server-owned inference tenancy
- [x] Bounded context preview, exact answer snapshot, transient chat and usage
- [x] Validated links to views, specific decisions and artifact versions
- [x] No assistant tools, controller actions, approval or conversation persistence
- [x] Three collapsible panes with remembered widths and keyboard/pointer dividers
- [x] Responsive workspace and focused single-pane mode for narrow screens
- [x] Regression and isolated browser checks, including failure/draft recovery
- [x] Verify configured live inference transport (not factual-accuracy qualification)
- [x] Assistant/pane extension merged as PR #11 into the brain-control branch

## Operational assistant and confirmed controls — v11

- [x] Share dashboard evidence collection with the assistant; preserve freshness/unknown states
- [x] Bounded per-domain records, capability catalog, available controls and explicit coverage
- [x] Inert model proposals; signed, session-bound, expiring and revision-bound owner confirmation
- [x] Existing typed control validation and one-shot native notification; no parallel dispatcher
- [x] Exact free-text decision excerpts, no inferred option or packet approval
- [x] Receipt-aware action cards; no automatic retry or optimistic completion
- [x] Regression and fixture/browser verification, including stale previews and stopped-brain answers
- [x] Live richer-context SSE reply and exact brain-stop preview verified; no live control submitted
- [x] Publish the integrated PR #11 baseline and v11 increment to main (PR #12)

## Development workspaces and phase-bounded autopilot — planned v12+

See [the workspace/autopilot design and acceptance plan](WORKSPACES-AUTOPILOT.md).
The [post-PR #42 convergence plan](COMPLETION-PLAN.md) groups the remaining work
into end-to-end milestones and records conditional iteration estimates.
These are planned tooling increments, not live mission or product authorization.

- [x] Record owner's phase-bounded delegation, brain-owned task routing and Play/Pause requirements
- [x] WSP-01: private workspace registry, isolated state and verified in-place migration
- [x] WSP-02 foundation: workspace selection, executive project introduction, recorded aggregates and scoped assistant
- [x] WSP-09A: conventional clone/local worktree code-snapshot deduplication, visible exclusions/aliases, shared export/inference counting and bounded pagination (local/synthetic/browser fixtures; not live acceptance)
- [ ] WSP-02 broader scale qualification, explicit host-alias mapping and shared-runner fairness
- [x] WSP-03A: versioned mission/phase authority configuration, exact owner review/revocation and policy-safe editor (inactive)
- [x] WSP-04A: isolated shared-capacity kernel, conservative token accounting and explicit read-only resource audit (not connected to native dispatch)
- [x] WSP-04B1: explicit maintenance enrollment, durable legacy dispatch fences, retained-owner journal and interrupted-staging recovery (no activation/unfence)
- [x] WSP-04B2: owner-reviewed quarantined ownership import, conservative conflict/slot inventory, durable kernel identity and cross-database receipt recovery (no native reconciliation/activation)
- [x] WSP-04B3: bounded external-evidence reconciliation, versioned exact owner reviews and cumulative usage-baseline continuity (no native collector, ownership release or activation)
- [x] WSP-03B1: selected-workspace safe Pause, retained worker/descendant checkpoint evidence, progress blockers and explicit post-checkpoint brain resume (no autonomous Play)
- [x] WSP-03B2: explicit run-readiness inspection binding current mission review, conservative packet path scope and retained platform evidence; scoped dashboard/report/assistant diagnostics (no run activation)
- [x] WSP-03B3: immutable brain-proposed phase/task operation declarations, requested-settings/estimate binding, version history and legacy bypass fences (no delegated approval, adaptive policy or native activation)
- [x] WSP-03B4: internal owner-bound run generations, exact/delegated task approval, atomic stop fences and checkpoint release kernel (no public activation route or native admission adapter)
- [x] WSP-03C: immutable phase checkpoint report artifacts, separate recorded result/evidence axes and exact owner-reviewed subsequent-generation binding; historical replay, stale-report refusal and preserved cumulative accounting (local fixtures; no public release, phase acceptance or new-generation correction adapter)
- [x] WSP-03D: selected-workspace phase report history, explicit retained-proof inspection, original versions/times and bounded historical assistant metadata; missing/stale/superseded evidence stays explicit (no public review/release, measured phase usage or Play)
- [x] WSP-04C1: internal authority/admission bridge, cumulative phase binding, recoverable shared reservations and one-shot creation-intent journal (no native calls, maintenance-fence release or public Play)
- [x] WSP-04C2: internal pending/confirmed/uncertain native-result bindings and same-run edit-correction journal, cumulative correction reservations, delivery-versus-finished evidence and receipt recovery (no native transport or release)
- [x] WSP-04C3a: internal confirmed-terminal ownership settlement, complete handoff/descendant/cleanup/usage evidence checks, conservative actual-token accounting and cross-store receipt recovery (not packet acceptance or native attestation)
- [x] WSP-04C3b: internal standard-policy runner reservation, one-shot local/shared launch journal, exact process observations and cleanup-only release with retained repository/token holds (no commands, automatic retry or Harness acceptance adapter)
- [x] WSP-04C3c: internal reconciled non-creation closure, final attempt/absence/cleanup/zero-usage evidence, retained client identities and terminal receipt recovery; safe-Pause exception for a verified nonexistent task (no automatic retry or native absence collector)
- [x] WSP-04C3d: internal standard-policy result review after terminal settlement, exact result/criterion/axis proofs, independent-review byte binding, atomic acceptance/rejection and replay; preserve safe-Pause supervision and block legacy archive/pilot shortcuts (not external attestation or live activation)
- [x] WSP-04C3e: explicit internal local source-structure observation against pinned standard-policy Git identity, isolated metadata-only Git view, complete diff/scope findings, atomic artifact/journal provenance and result-review binding (no CI/remote/semantic acceptance or live collection)
- [x] WSP-04C3f: bounded standard-policy GitHub PR/required-check metadata collection, exact remote/head/base/provider binding, unknown-coverage and drift refusal, atomic redacted provenance and original-time result-review validation (no merge authority, runtime proof or live ledger activation)
- [x] WSP-04D1: designated-brain one-use native creation handoff CLI, exact local project/base and owner/default-settings binding, consumed pre-send check, pending/confirmed/uncertain return path and receipt recovery (fixture qualified; no live task, installation or Play activation)
- [x] WSP-04D2: brain-owned task/account observation CLI, exact task/version-bound status projections, private account identity and duration-based limits, superseding unknown/exhausted admission fences and historical replay (no complete descendant/phase-token coverage, installation or Play activation)
- [x] WSP-04D3: brain-owned cumulative phase usage CLI, immutable per-session baselines/epochs, owned task-tree coverage, conservative high-water accounting, exact settlement incorporation and admission/effect-context fences (supplied evidence; no live counter collector or activation)
- [x] WSP-04D4: brain-owned standard-policy runner handoff CLI, exact execution/target binding, non-replayable send check, separate delivery/process/cleanup records and receipt recovery (no native transport, trusted host collector or live activation)
- [x] WSP-04D5: brain-owned owner-approved standard-policy result CLI, measured source/GitHub proof collection, atomic supplemental proof provenance, historical reads and separate review outcome (no native attestation, merge, archive, continuation or live activation)
- [x] WSP-04D6: brain-owned standard local terminal CLI, attempt/task-bound proof retention, explicit confirmed/non-creation outcomes, read-only detached-receipt state and safe recovery; composition through independent review and next delegated packet (fixtures, not qualified host evidence, native activity or live activation; [protocol](TERMINAL-HANDOFF.md))
- [x] WSP-04C3g: exact-owner standard-policy local Git preservation, independent temporary restore/integrity check, private bundle and task evidence manifest, original-time and historical byte validation (bounded local retention, not off-device backup, acceptance or archive authority)
- [x] [Collector replay reliability — issue #41](COLLECTOR-REPLAY.md): transaction-bound receipt recheck for GitHub/source/preservation, deterministic concurrent replay and preserved authority/maintenance/evidence guards (source fix, no live rollout)
- [x] WSP-05A: exact-owner standard-policy archive handoff, accepted review/local preservation binding, explicit cleanup acknowledgment, root-only fresh safety assertions, one-shot send boundary and uncertain/late-result recovery (CLI fixtures; no live archive, delegated retention policy or Play activation)
- [x] WSP-05B: exact-owner standard-policy same-task correction handoff, retained brain reuse rationale/findings, one-shot scope-bound message, cumulative reservations, no-progress and receipt recovery guards (CLI fixtures; no delegated/new-generation correction, native send or Play activation)
- [x] WSP-05C: explicit brain create/continue/handle/wait decisions, atomic owner-delegated standard-policy task approval, guarded reservation and native inheritance/handoff composition; next-packet progression after independent result acceptance (fixtures only; no native loop, activation, adaptive settings or Harness adapter)
- [x] WSP-05D: recorded event-bound waits, duplicate-idle-decision prevention and integrated managed-cycle skill guidance; no native scheduler, live installation or operating-loop acceptance ([plan and boundaries](BRAIN-EVENT-WAITS.md))
- [x] WSP-04E: exact owner-reviewed adaptive model/effort profiles, fresh host catalog binding, complexity/quality and token floors, bounded same-task escalation and distinct requested/applied/observed evidence at existing handoffs (fixtures; no speed/Ultra, public owner route, live settings or Play activation)
- [x] WSP-04F: owner-pinned existing public native endpoint, bounded read-only metadata collection and immutable phase-owned diagnostic reports (fixtures; complete task-tree/counter/cleanup/telemetry sources remain unqualified, no admission promotion or live connection)
- [ ] WSP-04C3 remainder: broader CI/workflow-trust/external preservation and resource/host/native qualification, trusted Harness acceptance adapter, new-generation continuation/rereview and native transport before exact owner Play activation
- [ ] WSP-03: configurable brain authority, phase checkpoint releases and safe Play/Pause
- [ ] WSP-04: brain-owned task/model/effort/speed choices, parallel limits and token admission
- [ ] WSP-05: continuous phase-scoped development, inheritance and preserved task archival
- [ ] WSP-06: real supervised two-workspace acceptance and verified runtime rollout

## Other future increments — not yet authorized implementation packets

- [ ] Native attachment coverage beyond retained local file references
- [ ] Historical artifact recovery from selected Git revisions
- [ ] Matched-task model/effort comparisons and configurable price scenarios
- [ ] Notifications for explicit usage budgets and evidence changes
- [ ] Onboard a second portfolio through the workspace acceptance plan above

OpenClaw integration remains deferred.
