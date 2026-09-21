# Convergence plan after PR #42

Baseline verified 2026-09-20: PR #42 merged at
`393a53bcf284b3b30a71aaa863fcff59ab05f588`. This is a planning estimate from the
remaining requirements in WORKSPACES-AUTOPILOT.md, not measured percentage progress
or a promise that the dashboard already runs autonomously.

## Estimate and definition of done

After the correction-handoff increment below, budget **10–14 further implementation/
review iterations for the standard-workspace experience**, including supervised
rollout. The **full original plan including Harness-specific integration is closer
to 12–18**. One iteration means a bounded PR/review/merge or a separately authorized
acceptance cycle. Related work should be delivered as complete milestones, not
split into another PR for each internal helper. Extra fixes consume the range's
contingency; report new blockers instead of silently increasing the scope.

Progress after PR #43: WSP-05C delivers milestone 1's coordinator and delegated
handoff composition in source/fixtures. Once that increment is merged, the remaining
estimate is **9–13 iterations for standard workspaces**, or **11–17 including
Harness**, under the same prerequisites and contingencies. Live orchestration is
still gated by the operating-loop, rollout and acceptance milestones below.

These estimates are conditional on supported native capabilities, usable owner-
approved pilot environments and decisions being available. External qualification
is not solved by another code PR. Unsupported per-task speed control must remain
explicitly unavailable; do not invent a native argument or change global settings.
Do not count a checked source item as installed, running or accepted.

Progress after PR #44: WSP-04E supplies milestone 2's reviewed policy and
creation/correction integration in source/fixtures. Once this increment merges,
estimate **8–12 further standard-workspace iterations**, or **10–16 including
Harness**, with the same prerequisites. Host observation collection and live
model-choice acceptance remain in milestones 3/10; no dashboard activation follows.

Progress after PR #45: WSP-04F adds bounded public native metadata collection,
but local schema qualification found no read-only complete lifetime-counter or
whole-process-tree cleanup proof. Milestone 3 remains **partial/capability-gated**;
the estimate is not decremented for this partial delivery. The **8–12 / 10–16**
ranges remain conditional, not a promise that more source PRs can replace a missing
qualified host source. See [collection boundaries and next decision](NATIVE-EVIDENCE-COLLECTION.md).

Progress after PR #46: WSP-09A advances the independent portfolio-identity part of
milestone 9 while milestone 3 remains capability-gated. Clone/worktree code totals,
distributed aliases, conflicts, exports and numeric assistant context now share
one counting contract. Synthetic scale and fixture-browser checks are retained in
[portfolio identity](PORTFOLIO-IDENTITY.md). This does not complete runner fairness,
host-alias qualification or live portfolio acceptance; the conditional **8–12 /
10–16** ranges are unchanged. No dependency is bypassed to activate Play.

The standard-workspace exit criterion is a real two-workspace mission that the
owner starts once in the dashboard, which performs multiple authorized task cycles,
explains model/effort choices and usage, preserves results, obeys Pause and phase
gates, and resumes without duplicate work. The final Harness gate also preserves
its exact packet, clean-room, zero-bill and trusted-runner execution contract.

Progress after PR #47: WSP-03C advances milestone 5 with immutable phase checkpoint
reports and exact owner-reviewed next-generation release binding. This is source
and fixture delivery, not public Play. New-generation task correction/rereview,
measured shared-usage presentation and full phase-exit qualification remain open;
milestone 3 is still capability-gated. The conditional **8–12 / 10–16** estimates
are unchanged for this partial milestone. See [phase checkpoints](PHASE-CHECKPOINTS.md).

Progress after verified PR #48: WSP-03D exposes those saved reports through the
selected-workspace dashboard and bounded assistant metadata. Explicit inspection
shows original versions/times, separate outcomes, unknown usage and stale/missing
evidence without adding approval or activation controls. This advances the
visibility portion of milestones 5/6, not their complete exit criteria; native
capability qualification and the conditional **8–12 / 10–16** ranges are unchanged.
See the [saved increment plan and owner workflow](CHECKPOINT-VISIBILITY-PLAN.md).

## Current increment

- [x] WSP-03F source after verified PR #55: exact-owner review-only authority for
  unaccepted settled standard results under a later current run, unchanged-commit
  collector/proof reuse, fresh independent review and immutable result history.
  Historical retries preserve the latest outcome; revocation/Pause fence new work.
  This advances milestone 5, not its native correction or full phase-exit gates.
  The public owner adapter, native evidence qualification and Play remain separate;
  conditional **8–12 / 10–16** ranges are unchanged for this partial milestone.
  See [saved plan and contract](GENERATION-RESULT-REVIEW.md). No live rollout or Actions.
  Local verification: 1,467 Python tests, all twelve JavaScript UI suites,
  JavaScript syntax, Python compilation and diff whitespace checks passed.
- [x] WSP-03E source after verified PR #54: selected-workspace checkpoint review
  and withdrawal controls, signed five-minute previews, exact report/next-mission/
  settings/expiry confirmation and durable withdrawal checked in the grant
  transaction. This completes the owner-decision surface, not milestone 5's
  new-generation correction/phase-exit qualification or milestone 6's Play.
  The conditional **8–12 / 10–16** ranges remain unchanged; native evidence
  qualification still cannot be replaced with more source PRs. See
  [checkpoint owner controls](CHECKPOINT-CONTROLS.md). No live rollout or Actions.
  Local verification: 1,446 Python tests, all twelve JavaScript UI suites and
  disposable two-workspace browser checks passed.
- [x] WSP-05F source after verified PR #53: selected-workspace retention inspection,
  signed expiring review/revoke previews, explicit cleanup consent and same-session
  transaction-bound owner confirmation. Historical retries do not reapply authority;
  chat receives cached facts/navigation only. This closes milestone 8's owner-control
  portion, not descendant/non-Git output preservation or qualified safe archival.
  The conditional **8–12 / 10–16** ranges remain unchanged. See
  [owner retention controls](RETENTION-CONTROLS.md). No live rollout or Actions.
  Local verification: 1,421 Python tests, all eleven JavaScript UI suites and
  disposable two-workspace browser checks passed.
- [x] WSP-05E source: opt-in exact-run owner retention review/revoke, capped
  designated-brain archive requests, accepted preservation binding and existing
  one-shot handoff composition. Revoked policies block new sends; late outcomes
  preserve historical authority and attempt counts. This advances milestone 8,
  not its complete exit criterion: owner UI, descendant/non-Git output retention
  and independently qualified host evidence remain. The conditional **8–12 /
  10–16** ranges are unchanged. See [delegated retention](DELEGATED-RETENTION.md).
  Local verification: 1,399 Python tests and ten JavaScript UI suites passed;
  the existing proxy-fixture race also passed 50 repetitions after stabilization.
  No live archival or Actions.
- [x] WSP-04D7 source: selected-workspace accounting inspection, phase charge and
  reservation breakdown, separate shared account/capacity projections, scoped
  download and cached overview/assistant facts. This advances the budget-visibility
  portion of milestones 5/6, not their full exit criteria. It does not qualify a
  native counter source or expose new Play/phase/budget controls. The conditional
  **8–12 / 10–16** ranges are unchanged. See [budget visibility](BUDGET-VISIBILITY.md).
  Local verification: 1,372 Python tests, ten JavaScript UI suites and disposable
  two-workspace browser checks passed. No live rollout or Actions execution.
- [x] WSP-04D6 source: scoped terminal handoff CLI closes the command gap between
  managed supervision and result review, including proof retention, conclusive
  non-creation and shared-first receipt recovery. Composition is fixture-only;
  qualified host facts, onboarding and live operating-loop acceptance remain.
  This advances milestone 7 without completing it; conditional **8–12 / 10–16**
  ranges are unchanged. See [terminal handoff](TERMINAL-HANDOFF.md).
  Local verification: 1,356 Python tests, nine JavaScript UI suites and
  skill/temporary-install checks passed. No live rollout or Actions execution.
- [x] WSP-05D source: event-bound wait receipts, read-only change/supervision
  classification and managed brain-cycle guidance across existing handoffs.
  Repeated unchanged wakes do not need another decision or evidence artifact.
  This advances milestone 7, but does not complete its live exit criterion:
  qualified host evidence, terminal adapter, onboarding and supervised acceptance
  remain prerequisites. The conditional **8–12 / 10–16** estimates are unchanged.
  See [event waits](BRAIN-EVENT-WAITS.md). Local verification: 1,331 Python tests,
  nine JavaScript UI suites and skill/temporary-install checks passed.
  No live installation, schedule change or Actions execution.
- [x] WSP-03D source: read-only phase report history, retained-proof inspection,
  context comparison, workspace dashboard and bounded historical assistant facts.
  No polling inspection, owner release, shared-store initialization or live Play.
  Local verification: 1,300 Python tests, nine JavaScript UI suites and disposable
  two-workspace browser checks passed. No Actions workflow or run was triggered.
- [x] WSP-03C source: parked-phase report artifacts, recorded result/criterion/axis
  projections, exact owner review and transaction-bound subsequent run release.
  Replay, changed-source/report refusal and same-phase accounting continuity are
  covered in local fixtures. Local verification: 1,285 Python tests and eight UI
  test files passed. No live report, owner release, installation or Play.
- [x] WSP-09A source: explicit identity-bound measurements, canonical recorded
  snapshot aggregation across clones/worktrees, counting coverage, scoped links,
  independent pagination and local-only refresh controls. Local verification:
  1,255 Python tests and eight UI test files passed; two-workspace fixture browser
  checks passed. No live observations, controller changes or Actions execution.
- [x] WSP-04F source: exact owner-pinned existing endpoint, bounded public read-only
  proxy, phase-owned root/descendant/configured-setting/terminal metadata, immutable
  diagnostic reports, replay and explicit counter/cleanup/telemetry gaps. No live
  connection or promotion into admission/acceptance; milestone 3 is not complete.
  Local verification: 1,230 Python tests, seven JavaScript UI test files and the
  JavaScript syntax check passed; no Actions workflow or run was triggered.
- [x] WSP-04E source: exact owner-reviewed model/effort profiles, host catalog
  binding, complexity quality/token floors, bounded same-task escalation and
  distinct requested/applied/observed records. Existing one-shot handoffs enforce
  selection; native defaults remain unchanged. See [model policy](MODEL-POLICY.md).
  Local verification: 1,199 Python tests and 7 JavaScript UI test files passed;
  no live activation or Actions execution.
- [x] WSP-05C source: explicit brain lifecycle decisions, atomic phase-delegated
  standard task approval, guarded admission and existing handoff composition.
  The two-packet fixture independently reviews the first result and admits the
  next packet without another owner approval. See [the coordinator contract](BRAIN-COORDINATOR.md).
  Local verification: 1,165 Python tests and 7 JavaScript UI test files passed;
  no live activation or Actions execution.
- [x] WSP-05B source: guarded same-task correction handoff and CLI, with retained brain
  rationale, exact scope, one-shot send, conservative usage and recovery tests.
  This closes the correction transport-argument seam, not the autonomous loop.
  Local verification: 1,135 Python tests and 7 JavaScript UI test files passed.
  See [the handoff contract and limits](CORRECTION-HANDOFF.md); live use is not
  activated or accepted by these source results.

## Delivery milestones

| # | Deliverable | Exit evidence |
| --- | --- | --- |
| 1 | Source complete: brain lifecycle coordination, delegated task selection and inheritance (WSP-05C) | Create/continue/handle/wait decisions, exact delegated scope and two-packet progression qualified in fixtures; live operating-loop acceptance remains in 7/10 |
| 2 | Source complete: owner-reviewed adaptive model/effort policy (WSP-04E) | Host capability binding, allowed choices, quality/escalation bounds and requested/applied/observed records qualified in fixtures; speed/Ultra remain gated, live collection/acceptance remain in 3/10 |
| 3 | Partial: native metadata collector (WSP-04F); complete host/counter source still required | Public metadata reads qualified in fixtures; complete ephemeral membership, whole-process cleanup and non-resetting lifetime usage remain capability-gated, not inferred |
| 4 | Controlled onboarding and maintenance release | Exact owner review, migrated ownership/baselines, interrupted-release recovery and no implicit upgrade activation |
| 5 | Partial: checkpoint report/release binding, owner review/withdrawal and internal settled-result rereview (WSP-03C / WSP-03E / WSP-03F); native corrections and phase-exit qualification remain | Exact next-scope/settings/expiry and same-commit rereview permission, immutable outcomes and durable revocation; no inferred phase acceptance, public release, automatic crossing or usage/attempt reset |
| 6 | Partial: checkpoint/budget visibility, owner checkpoint decisions and assistant metadata (WSP-03D / WSP-03E / WSP-04D7); Play remains | Saved evidence/accounting inspection, explicit owner review/withdrawal and unknown/stale budget balance suppression; version-bound start, immediate notification, brain receipt and recovery still require qualification; Pause dominates races |
| 7 | Partial: managed-cycle guidance/event-bound waits (WSP-05D) and terminal command path (WSP-04D6); rollout/acceptance remain | Source guidance composes guarded handoffs through terminal accounting and result review, and refuses duplicate unchanged waits. Qualified host evidence, live quiet scheduling and operating-loop acceptance remain gated; no helper scheduler or native polling |
| 8 | Partial: exact-run delegated retention, owner controls and one-shot archival (WSP-05E / WSP-05F); broader preservation and qualification remain | Signed owner review/revoke, age/attempt bounds and root-only lifecycle qualified in fixtures; descendant/untracked-output safeguards and independently observed safe archival remain |
| 9 | Partial: canonical portfolio metrics (WSP-09A); broader scale/fairness qualification remains | Same-origin clone and local worktree snapshot totals, explicit coverage, 3,200-row aggregation and two-workspace fixture browser checks; host aliases, runner fairness and full live portfolio qualification remain |
| 10 | Standard-workspace supervised acceptance and runtime rollout | Two real workspaces, multiple task cycles, Pause/resume, gates, budget stops and exact installed/running revision independently verified |

The numbering is a work-package inventory, not permission to bypass dependencies.
Milestones 1/6/7 must be qualified together before live Play; 3/4 precede live
admission. Some can share one PR, while integration/recovery may require another.
The 10–14 range is an engineering estimate, not ten already specified packets.

Full-plan additions: the compatible trusted Harness execution/evidence adapter,
then owner-authorized Harness migration/qualification rehearsal. Budget another
2–4 iterations if the external launcher, independent trust, host and zero-cost
runner prerequisites are available. Missing prerequisites remain an external
blocker with a named next action, never permission to provision or incur charges.

## Cost and authority

Local validation only. No Actions workflow/job/runner, new paid API, automatic
merge, live task, installation, schedule change or maintenance release follows
from this plan. Each live acceptance/activation step needs its exact separate
owner scope. Installed tooling must be quiesced/upgraded before new protocols are
used; no mixed-version writer or downgrade safety is claimed.
