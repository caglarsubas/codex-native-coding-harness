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

The standard-workspace exit criterion is a real two-workspace mission that the
owner starts once in the dashboard, which performs multiple authorized task cycles,
explains model/effort choices and usage, preserves results, obeys Pause and phase
gates, and resumes without duplicate work. The final Harness gate also preserves
its exact packet, clean-room, zero-bill and trusted-runner execution contract.

## Current increment

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
| 3 | Complete native/host observations and phase-counter collection | Real owned task-tree coverage, retained process/cleanup evidence and non-resetting usage; unknowns stop new work |
| 4 | Controlled onboarding and maintenance release | Exact owner review, migrated ownership/baselines, interrupted-release recovery and no implicit upgrade activation |
| 5 | Phase reports, checkpoint release and bounded new-generation corrections | Reviewed evidence report binds the next scope; no automatic boundary crossing or reset of usage/attempts |
| 6 | Dashboard Play/phase controls and assistant integration | Explicit version-bound start, immediate notification, brain receipt, recovery and truthful blocked states; Pause dominates races |
| 7 | Native brain operating loop and quiet recovery scheduling | Updated reusable guidance composes all handoffs; no duplicate sends or background helper scheduler; idle owner waits do not poll models |
| 8 | Delegated retention and complete preservation/archival lifecycle | Selected retention policy, descendant/untracked-output safeguards, preserved knowledge and independently observed safe archival |
| 9 | Portfolio identity/deduplication and scale qualification | Canonical clone/worktree totals, shared-runner fairness, larger-portfolio performance and browser isolation evidence |
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
