# Development workspaces and mission autopilot

Status: revised implementation plan incorporating the owner's workspace-brain,
phase-authority, project-introduction and continuous-development requirements.
The autonomy direction is settled: configurable delegation to each brain within
user-defined phase checkpoints. This document does not activate a workspace,
grant a live packet approval, change a model, start a schedule, or authorize
merging. Implementation evidence and remaining gates are recorded in section 10.

Prepared 2026-09-18 against tooling commit
`6ea0d3b4b5acea29e7c3252da170a4eb313093c7`. That is an inspected local baseline,
not a claim about current main, deployment or product acceptance.

## 1. Product outcome

The owner manages separate product-development lifecycles from one dashboard.
**Multi-agent harness platform** becomes one development workspace, not the
identity of the entire orchestration application. A workspace can span several
repositories and native Codex projects; it is not itself a Codex project or an
OpenAI organization/tenant.

Each workspace has a designated brain, mission, versioned roadmap, repository
policies, knowledge, tasks, decisions, artifacts, usage allocation and activity
history. The owner defines what should be delivered and the limits, then presses
**Play**. Routine authorized planning, implementation, verification and handoffs
continue without repeated chat instructions. Genuine decisions return to the
dashboard with a specific next action.

Selecting a workspace opens its Overview with a short project introduction first:
goal, success criteria, architecture, technology stack, roadmap progress and next
user checkpoint. The workspace keeps developing its authorized roadmap until the
user presses **Pause**, a configured phase checkpoint is reached, the roadmap is
complete, or the brain identifies a reason it must stop. Completion of an ordinary
packet or native task is not itself a reason to ask the user to continue.

Success means a real two-workspace pilot can complete bounded work, show exactly
why each task/model/effort was selected, preserve evidence, stop safely and resume
without duplicate work or cross-workspace effects. A green UI or fixture test is
not that pilot.

## 2. Current implementation and required change

Inspected source currently supports one brain per `Ledger`, one ledger per
`Dashboard`, and separate state directories/ports for other portfolios. Worker
capacity and runner ownership are ledger-local. `begin_creation` returns native
task arguments without model/effort overrides. The installed skill resolves one
installation and its default state directory.

Existing capabilities to reuse:

- Exact packet/seed approval, preflight, reservation and uncertain-creation recovery.
- Native task creation and supervision by the brain, not the HTTP server.
- Immediate fixed-purpose notification after durable dashboard controls.
- Cooperative brain stop, checkpoint preservation and explicit resume.
- Versioned artifacts, roadmap observations, delivery evidence and usage metrics.
- Three adjustable panes and an assistant with confirmed typed controls.

Missing capabilities are workspace routing/isolation, mission authority,
cross-workspace reservations, budget-aware admission, model-routing policy and a
continuous mission controller. Merely relabeling Resume or adding a selector
would not implement these.

## 3. Configurable brain authority and phase checkpoints

### Selected direction: phase-bounded delegated authority

The owner configures a workspace authority profile and approves a versioned
mission/phase envelope before its first Play. The approval covers:

- Objective, success criteria, selected roadmap slice and explicit exclusions.
- Named repositories, allowed paths, permitted operation classes and existing
  repository execution/merge requirements.
- Whether the brain may prepare only, execute exact owner-approved packets, or
  approve its own in-scope packets within an authorized phase.
- New task creation versus continuing existing tasks, bounded corrections,
  verification and knowledge handoffs inside that workspace's Codex environment.
- Explicit maximum concurrent managed tasks and total new tasks per phase/run.
- An explicitly selected allowed model/effort/speed policy, escalation limits and
  phase/workspace budget limits. No configuration is silently opted in.
- Whether verified, inactive completed tasks may be archived after preservation.
- Phase exit criteria, mandatory user checkpoint destinations, expiry, retry
  limits and reasons requiring a new decision.

Inside this envelope, the brain may decompose work into new tasks and continue
without asking for each routine step. Every generated task still receives an
immutable packet/seed and a brain approval/admission record binding it to the
workspace, active phase, mission version and delegated authority version. The
system records **brain-approved under delegated phase authority**, not falsely
**owner individually approved**. Every approval retains its scope assessment and
exact packet/seed hashes, and is independently enforced at dispatch.

Changes to objective, repositories, public contracts, destructive-data behavior,
licensing, credentials, external access, provisioning, billing or protected
delivery actions require a separate decision. A model's recommendation, ordinary
chat answer or roadmap checkbox is not an authorization event.

The mission admission checker enforces structural constraints and policy limits;
it cannot prove semantic scope or make generated code safe. The trusted brain
must review scope, and independent verification must check actual results. If
membership in the mission is ambiguous, publish a focused decision.

### User-configurable authority profile

| Setting | Meaning |
| --- | --- |
| Packet approval authority | Prepare only; exact owner approval; or brain approval within the active authorized phase |
| Checkpoint destinations | Named phase/milestone boundaries, exit evidence and the next action requiring user release |
| Maximum parallel tasks | Hard admission ceiling for managed task reservations and active task ownership |
| Task/retry limits | Maximum new tasks per phase/run and bounded correction/escalation attempts |
| Token allowance | Workspace and phase allocations, warning threshold and reserved checkpoint/verification headroom |
| Model / effort / speed | Exact permitted configurations, quality floor and escalation/cost constraints |
| Delivery authority | Commit/push/PR/merge/deployment permissions constrained by each repository's policy |
| Retention | Whether the brain can archive completed inactive tasks after verified preservation |

The effective concurrency is the minimum of workspace allowance, global available
capacity and repository/runner/pilot constraints. Migration preserves existing
pilot and capacity gates; configuring a higher number cannot bypass them.
Reserved, starting, blocked and
otherwise owned unfinished tasks count; a missing native response cannot free a
slot. Completed historical chats do not consume active-task slots, whether or not
archived. The one designated brain is accounted separately; review/planning
worker tasks count like implementation tasks. Show both numbers in the UI.

Nested agents or model modes that create additional agents must not bypass the
policy. Unless their creation can be bounded and observed under the same budget
and capacity policy, exclude them from the permitted execution configurations.
No automatic escalation may raise concurrency, authority or budget limits.

Policy edits are versioned, authenticated owner actions with a visible diff.
Reducing authority immediately fences incompatible new actions and initiates
safe reconciliation of affected work. Increasing it requires explicit owner
approval. Existing approvals are revalidated against the current profile; stale
phase/policy decisions cannot authorize a new task.

### Phase checkpoint contract

A versioned phase defines its objective, allowed work and dependencies, success
criteria, required evidence axes, token/task envelope, mandatory checkpoint
destinations and permitted successor. The UI states **May run until: [checkpoint]**
before Play. Missing phase/checkpoint definitions are setup gaps, not unlimited
roadmap permission. Ordinary milestones inside the authorized segment do not
interrupt progress; mandatory checkpoints always do.

At a mandatory checkpoint, stop admitting work beyond the boundary, bring owned
tasks to safe checkpoints and preserve a phase report: delivered items, exact
commits/PRs, verified and outstanding criteria, artifacts, actual/unknown usage,
remaining risks and a proposed next-phase plan. Independent verification is still
required even when the brain authored and approved the packets.

The workspace then shows **Awaiting phase review**. The owner can release the next
phase, request an in-scope correction, revise the plan/budget, or keep it paused.
Release is bound to the exact report, next-phase scope and authority versions.
Play cannot cross an unreleased checkpoint. Neither a completed checkbox nor a
worker's final message can release it. The brain cannot move or remove a user
checkpoint to avoid review. Any permitted correction runs within an explicit
bounded correction scope and then returns to the same checkpoint.

Example only: approve design-to-prototype work with a checkpoint before production
integration. The brain may prepare/approve/execute multiple prototype packets;
it cannot start production integration just because the prototype tests passed.

### Compatibility: approved queue only

Play continuously executes only exact owner-approved packet/seed pairs. The
brain can prepare proposals, but new packets wait for approval. Batch review can
approve an explicit finite set of exact hashes; changing a seed invalidates that
approval. This remains useful for tightly regulated repositories.

### Harness-specific boundary

The existing Harness workspace retains exact packet approval, one-packet/one-PR,
allowedPaths, predecessor locks, clean-room isolation, declared acceptance and
independently authorized live execution. Selecting mission mode in a generic UI
must not bypass those rules. Until a separately approved compatible policy change,
Harness uses the approved-queue mode. A configurable authority profile can narrow
these restrictions but cannot grant an exception to them. Standard workspaces may
adopt delegated phase authority after the tooling contract and skill are explicitly
updated for it. This design choice does not rewrite product repository policies.

This draft does not change the existing `AGENTS.md`, installed skill or live
approval records. No new paid API or hosted fallback is proposed.

## 4. Workspace and platform boundaries

| Workspace-owned | Platform-shared |
| --- | --- |
| Brain identity and checkpoint | Available native capabilities and account-limit observations |
| Project introduction, repositories, mission and phase/roadmap versions | Global managed-worker capacity and fairness |
| Queue, workers, decisions and receipts | Canonical repository and physical runner reservations |
| Artifact bytes/versions and knowledge references | Shared inference-service capacity, not shared chat context |
| Budget allocation and attributed usage | Deduplicated aggregate metrics and unallocated usage |
| Assistant context, drafts and confirmations | Local authentication and workspace registry |
| Delegated packet authority, checkpoint destinations and execution policy | Capability validation and global reservation enforcement |

Use a private registry and a separate ledger/artifact namespace for each workspace.
The registry assigns opaque stable IDs and stores trusted root mappings. Browser
requests select a registered ID, never an arbitrary path, native task target or
executable. The public repository contains schemas and synthetic examples only.

The same brain cannot control two active workspaces. Repository identity must
resolve aliases, remotes and worktrees to a canonical identity. Initially, shared
repositories are read-only in additional workspaces; concurrent mutation requires
an explicit future policy. A platform-level runner key must identify the physical
resource, not a workspace-local label.

This is separation within a single-owner local application, not a claim of OS
isolation or multi-user tenant security. Repository and trusted-runner boundaries
continue to provide their own enforcement.

### Shared reservations, not another agent scheduler

Each workspace brain decides whether to open a new task, continue an existing
task, handle a bounded planning step itself or wait. Model, effort, speed and
parallelism decisions run in that brain's native Codex context under the approved
profile, not in the dashboard chat service or a separate routing agent. Native
tasks remain in the workspace's mapped host/projects and are visible in Codex.
A small transactional platform ledger only grants capacity/resource/budget reservations.
It does not generate prompts, create native tasks, call models in the background
or become a second autonomous dispatcher.

Acquire global reservations before the local creation boundary. Revalidate the
workspace run generation, mission hash and stop intent immediately before native
creation. Since the two ledgers and native task service are not one transaction,
use an explicit recoverable sequence: requested reservation, local binding,
creation attempted, native identity confirmed, reconciled release. Every phase
has one idempotency key. Uncertain effects retain ownership; no timeout can prove
a task or runner disappeared. Reconcile unmanaged resource usage separately.

## 5. What Play actually does

First use opens an inline **Review phase authority & start** view. After a phase
has been approved, subsequent Play presses resume its remaining scope; unchanged
settings do not require another routine approval. A changed mission or unreleased
phase boundary requires review. Controls are always tied to the visible workspace
name. Play starts an ongoing roadmap run, not just one packet.

1. Validate authentication, workspace identity, revision, mission approval,
   active phase, authority version and platform capability. Persist one idempotent
   run request with a new generation.
2. Check current capacity/budget evidence and hard prerequisites. A known blocker
   is shown immediately with a link to resolve it; do not show an empty queue.
3. Notify that workspace's existing brain immediately using the supported fixed
   bridge. A stopped brain is explicitly resumed as part of this reviewed Play
   intent. Only the mission's permitted dispatch is enabled after brain receipt.
4. The brain receives the run, reconciles unfinished effects, reads retained
   knowledge and selects the next eligible unit of work before the next checkpoint.
5. Decide whether to continue an owned task or open a new one. For a new task,
   materialize a bounded packet, record the permitted owner/brain approval,
   validate preflight, choose model/effort/speed and reserve resources. Create the
   native task in the mapped Codex environment with an isolated worktree as
   required. Record pending IDs distinctly from confirmed task IDs.
6. Supervise, verify results, preserve artifacts and update the mission checklist.
   Continue with the next eligible task, opening independent tasks up to the
   effective parallel limit, while phase authority, budget and resources permit.
7. At a user Pause or brain stop condition, run the same safe checkpoint protocol.
   At a mandatory phase boundary, retain the report and await user release. At
   roadmap completion, retain final evidence. Ordinary task completion goes back
   to step 4 without a routine permission question.

Play is one user intent but multiple durable steps, not an atomic native operation.
Its receipt reports each step. A partial failure stays recoverable; a double-click
or reconnect must not create another brain, worker, schedule or budget reservation.

If no brain exists, Play opens **Connect a brain**. Creating a native brain is an
explicit onboarding action through supported Codex tools, not an implicit side
effect of viewing a workspace. Missing native project mappings need supported
registration; no private Codex database writes.

### Honest activity states

| State | Meaning and next action |
| --- | --- |
| Setup required | No usable brain, mission, repository mapping or execution capability; open setup |
| Ready | Reviewed scope exists; no claim that a task is running |
| Starting | Run saved; show notification acknowledgement and brain receipt separately |
| Planning | Brain is actively preparing a scoped task; no worker claimed yet |
| Developing / verifying | Fresh observations identify the actual task and current step |
| Waiting for resource | Identify the owner of the shared runner/capacity and the resume condition |
| Needs your decision | Show the exact new boundary and its decision link |
| Waiting on external dependency | Show dependency, last evidence and the event that permits retry |
| Budget limited | Show affected limit, reserve and observed reset time when available |
| Pausing safely | New effects fenced; identify each bounded step still finishing |
| Paused at checkpoint | Retained checkpoint and native inactivity independently observed |
| Awaiting phase review | Phase/checkpoint report ready; next phase is not released |
| Plan revision needed | Brain retained a material plan-change proposal; user decision required |
| Completed | Mission success criteria independently verified; delivery axes remain separate |
| Recovery needed | Native delivery/effect is uncertain; reconcile instead of resending |

Keep run intent, observed native activity, dispatch permission and evidence
freshness as separate fields. Stale data says **Last observed …**. An empty task
queue alone proves neither idleness nor completion.

### Pause, brain-initiated stops and continuation

**Pause** is the primary workspace control and means pause the whole development
run, not merely pause new worker dispatch. Its help text is **Stop the brain and
its tasks at safe checkpoints**. It immediately fences new approvals, substantive
planning, creation, acceptance, retries and merges. Already running bounded
operations finish safely, workers checkpoint and the brain retains the combined
checkpoint and pauses recovery scheduling before parking.

The brain stops doing development immediately on observing Pause, but remains
available for safety-only coordination until its workers are quiescent. Stopping
the supervisor first and leaving workers unattended would not satisfy this
contract. Task seeds require cooperative control checks between bounded steps.
The dashboard shows which workers/operations remain active and never claims
**Paused** until native inactivity and retained checkpoints are verified. No
process kill, automatic archival, inferred reservation release or fixed stop
deadline is implied. Missing/uncertain worker evidence keeps **Pausing safely**
with a concrete blocker.

The brain initiates the same checkpoint protocol on reaching a mandatory phase
checkpoint or the roadmap end, detecting a crucial plan-change possibility,
needing an increased token allowance, exhausting bounded corrections, or losing
required authority/evidence. Record a typed stop reason, initiating actor, safe
checkpoint and exact resume condition. It may propose a plan or budget revision
but cannot approve its own expanded authority or silently continue beyond a gate.

**Hold new tasks** may exist only as an explicitly labeled advanced dispatch
control; it is not the primary Pause button. Pause intent dominates ordinary
answers, scheduled wakes and budget-reset events. Only a newer explicit Play
resumes a parked run, after any phase release or policy revision is approved.
Routine resource waits stay within the active run and may recover automatically
under the approved policy; they do not require the owner to repeat “continue.”

While the brain is active, use native task waits for completion/attention. Native
heartbeat recovery covers active work across turns. Dashboard decisions wake the
correct brain immediately. The desktop does not provide general completion
webhooks to this helper; do not promise them or build an unsupported listener.
Pure owner/external waiting pauses model polling. A known timed wait may use an
explicitly authorized native follow-up. Report the next check and its cost
implication; stay quiet while nothing meaningful changes.

Local scheduling requires the computer and Codex app to remain running. This is
not an always-on cloud controller. See [official scheduled-task documentation](https://learn.chatgpt.com/docs/automations?surface=app).

## 6. Brain-owned task, model, effort, speed and budget decisions

For each eligible work item, the brain records one lifecycle decision:

- **Continue:** reuse the existing task for the same packet, bounded corrections
  or its review follow-through when ownership, context and policy still match.
- **Create:** start a fresh seeded task for a distinct packet, independent parallel
  work, a needed role separation or unsuitable existing context. State why reuse
  was rejected and check capacity before creation.
- **Handle in brain:** perform bounded roadmap planning, scope review or
  reconciliation within its orchestration authority; count its usage too.
- **Wait / checkpoint:** no eligible work, insufficient capacity or an explicit
  stop boundary; record the reason and next permitted event.

Opening a new task is a deliberate brain decision, not an automatic consequence
of a roadmap checkbox or a web request. Conversely, don't overload the brain
with all implementation work just to avoid new tasks. Preserve task separation
and one-packet/one-PR requirements; reuse must not expand a worker's packet scope.

Owner onboarding selects either **Use my Codex defaults** or an explicit
**Adaptive policy**. Defaults remain unchanged until that choice. An adaptive
policy contains exact allowed model IDs, supported effort and speed sets, a quality
floor, per-role preferences, escalation ceiling and retry budget. Resolve capability
from the actual destination host; do not infer availability from a pricing page.

The brain makes an explainable selection under a server-enforced policy; a
deterministic ruleset supplies bounds and suggestions rather than replacing the
brain as the decision maker. Assess ambiguity, blast radius, dependency count,
verification difficulty, failure history, context, urgency and remaining budget.
Select a permitted configuration expected to meet the quality floor efficiently:

- Routine bounded edits: permitted efficient model, low/medium effort.
- Multi-file implementation or debugging: permitted balanced model, medium/high.
- Architecture, security-sensitive review or difficult unresolved faults:
  permitted stronger model/higher effort, within explicit limits.
- Escalate only after retained failure evidence, not merely elapsed time; preserve
  stricter packet retry limits and stop after the policy's no-progress ceiling.

These are proposed workload classes, not a benchmark-backed ranking or a selected
model configuration. Official guidance notes that greater reasoning effort can
cost more time/tokens; actual supported combinations must be checked.
[Models and reasoning controls](https://learn.chatgpt.com/docs/models).

Record requested and observed model/effort/speed separately, lifecycle choice,
phase/policy versions, rationale, alternatives, usage snapshot, estimated allowance
and actual observed usage. If native configuration cannot be verified, mark it
unknown. Never claim savings
from unmatched tasks. Changes within an existing worker occur only between turns
at a recorded checkpoint under the approved policy; no mid-turn silent downgrade.
Keep bounded corrections in the same task when useful. Preserve the designated
brain rather than repeatedly discarding its decision history.

### Speed is a separate, capability-gated choice

The brain may choose speed only among the owner's permitted modes and within the
same budget/quality policy. Fast mode is not equivalent to lower reasoning effort
or a smaller model, and can consume more credits. Do not hard-code a multiplier
or claim a latency guarantee; retain the applicable pricing/usage basis when
available. [Official Codex speed controls](https://learn.chatgpt.com/docs/agent-configuration/speed).

Current app task-creation and follow-up tool schemas expose model and effort,
but no per-task speed parameter. Therefore automated speed changes are a capability
gap to verify during implementation, not a delivered feature. Record requested,
applied and observed settings distinctly. If the supported adapter cannot apply
speed, show **Automatic speed selection unavailable** and preserve the effective
native setting; require review if the mission demands another speed. Never invent
a tool argument, send a slash command as ordinary chat and call it applied, or
rewrite account/global configuration that could change other workspaces. Use a
future supported per-task control only after its behavior has been verified.

### Budget facts and enforcement limits

Account usage windows are shared, not independent workspace wallets. Workspace
token allocations are local admission controls, not provider-enforced billing
caps. Raw input, cached input, output/reasoning and service-reported credits must
remain separately labeled. Token logs are not subscription invoices.

The authority editor must state the accounting unit and window. For raw-token
allowances use total input plus total output, showing cached input as a subset
of input and reasoning as a subset of output, not double-counted extras. Phase
and workspace totals include brain planning/supervision and all managed task
usage. Track assistant-service usage separately and include it only under an
explicit named allowance. Reconcile estimates with observed usage, retaining
unknown attribution and reservation headroom instead of calling it zero.

Before admitting work, check fresh account-limit evidence, remaining mission
allocation and global outstanding reservations. Reserve estimated headroom for
the worker, brain supervision, verification and safe checkpointing. Unknown or
stale measurements cannot be treated as unlimited. A configured policy may reduce
concurrency or choose another already permitted model; it must never lower required
quality or safety to fit a budget. Otherwise checkpoint and show **Budget limited**.
If completion needs a larger allowance, preserve the estimate and alternatives
in a budget-revision decision and pause safely before consuming checkpoint
headroom. Only the owner may raise the limit.

Do not claim a hard token/dollar stop: active native turns and unrelated account
activity can exceed an estimate. Provide hard bounds only for locally enforceable
counts, such as new task admissions, retries and concurrency. Any credit purchase,
usage reset or paid API fallback remains outside automatic policy. User-specific
remaining usage is not queried or changed by this design document.
[Official usage and pricing distinctions](https://learn.chatgpt.com/docs/pricing).

## 7. Knowledge inheritance and task closing

The brain keeps durable, versioned knowledge outside its chat context. Each new
worker receives only what its task needs:

- Workspace/run/phase/task IDs and exact mission/authority/policy/packet/seed hashes.
- Objective, rationale, acceptance criteria and explicit exclusions.
- Repository identity, actual base commit, allowed paths, contracts and locks.
- Relevant decisions and architecture excerpts with immutable references.
- Predecessor evidence, known failures, interfaces and unresolved assumptions.
- Execution/merge policy, selected model/effort/speed, limits, next mandatory
  checkpoint and cooperative pause/stop conditions.
- Required output: commit/PR, tests, artifact references, residual risks and a
  concise continuation summary.

No full brain transcript, unrelated workspace data, credentials or prohibited
source material enters the seed. Untrusted artifacts are evidence, not executable
instructions. The brain promotes verified outcomes into shared knowledge with
provenance; worker claims alone cannot rewrite governing decisions.

“Close” means archive a completed, inactive task only if the mission explicitly
permits it and preservation has been independently verified. Retain commits on
durable refs/remotes as required, relevant untracked outputs, artifacts and the
continuation summary outside the worktree before archival. Default to retaining
tasks until this policy is selected. Never delete a brain or unfinished task.
Codex may remove managed worktrees when tasks are archived; this is why a chat
history reference alone is insufficient preservation.
[Official worktree lifecycle](https://learn.chatgpt.com/docs/environments/git-worktrees).

## 8. UX brief for the three-pane application

Audience: the local owner steering multiple products, checking progress quickly
and making exceptional decisions. Primary action: select a workspace, understand
the project and its next authorized outcome, then Play or Pause. Preserve the existing
assured, precise, composed editorial ledger from `.impeccable.md`; do not redesign
typography or add external assets as part of workspace support.

- **Left navigation:** workspace switcher above the existing menu; an All
  workspaces view; names/search as the collection grows. A collapsed rail still
  exposes the active workspace and a labeled switching control.
- **Middle workspace:** persistent workspace identity, mission, observed state
  and Play/Pause. The selected workspace's Overview starts with the short executive
  project introduction described below, followed by current task/next step,
  required decisions, roadmap and the existing evidence/metrics/artifact views.
  Advanced budgets, routing explanations and policies use disclosure, not an
  initial wall of controls.
- **Right assistant:** visibly scoped to the current workspace, explains state
  and links to exact records. All-workspaces mode can compare bounded aggregates;
  every proposed action still names one target workspace and requires the normal
  typed confirmation. No unreviewed chat command becomes mission authority.

Retain collapsible panes, keyboard/pointer resizing and narrow-screen focused
mode. Keep Play/Pause available without relying on icons or hover. Use text and
focusable controls, not color alone, for activity and blocker distinctions.

Selecting a workspace navigates to that workspace's Overview by default, without
starting or stopping its run. The selected workspace is tab-local, not a global
server selection; two browser tabs can inspect different workspaces safely.
Workspace-qualified deep links can still open a specific record directly.
Workspace switching preserves separate transient drafts/chat histories but sends
only the selected workspace's context. Cancel or ignore in-flight stale responses
using workspace ID and request generation. A signed action prepared in workspace
A can never be confirmed against workspace B, even if record IDs collide. Every
deep link carries workspace identity plus exact artifact/decision version.

All-workspaces view uses a compact status list: workspace, mission, current step,
blocker, usage and last observation. Individual workspace views retain details.
No default Play-all control. Aggregate token/task metrics deduplicate native
identities; code metrics deduplicate canonical repository/commit snapshots.
Shared and unallocated usage stays explicit rather than counted twice.

Empty state: **Create a workspace**, then connect brain, repositories and mission.
No approved mission: **Define what Play should deliver**. Delivery failure:
**Start saved; brain notification not confirmed**, with a recovery link. Completed:
show deliverables and verified/unverified axes, not a generic “all done.”

### Project introduction: first content in workspace Overview

Use a compact, readable introduction rather than a large dashboard of counters:

1. **Goal:** one or two sentences on what the product is and why it exists.
2. **Success criteria:** a few concrete outcomes with verified/pending status.
3. **Architecture:** a short description of major components and boundaries,
   linked to the current architecture artifact; expand for the diagram/details.
4. **Technology stack:** concise languages, runtimes, frameworks and key services,
   with source references and unknowns rather than guessed technologies.
5. **Roadmap status:** current phase, completed/total tracked items, active work,
   important blocker and the next user checkpoint. Checklist completion is not
   substituted for deployment/runtime/tenant acceptance.

Keep the collapsed introduction roughly 150–250 words, with details one click
away. Goals and criteria come from the user-approved project charter; architecture
and stack come from pinned workspace artifacts/repository observations. The brain
maintains a versioned ProjectProfile with references, observed/updated timestamps
and proposed changes requiring review when they alter approved intent. Live status
is a separate current projection, not a cached narrative posing as live evidence.

An optional inference-written summary uses the existing tenancy and bounded,
explicitly permitted context; it remains labeled as a generated draft. Show the
structured introduction immediately without waiting for inference or spending
tokens on each navigation. New workspace: **Add a project introduction**; missing
fields: **Not documented**; stale source: show its timestamp and update action.
The existing operational executive brief remains below this project introduction
and answers “what is happening now,” not “what are we building.”

The workspace authority editor shows the effective approval mode, current phase,
**May run until**, task capacity and token headroom. The task list exposes **Why
this task? / Why this configuration?** with the brain's recorded rationale. At a
phase gate, show **Review phase & release next**; at a budget/plan stop, show the
specific revision proposal instead of a generic disabled Play button.

Implementation references: Impeccable interaction, spatial and responsive guides.
The owner's four additions are incorporated here; this is a design/implementation
plan, not a claim that the described controls have shipped.

## 9. Data, API and security changes

New records: Workspace, ProjectProfileVersion, MissionVersion, PhaseVersion,
AuthorityProfileVersion, MissionApproval, PacketApproval, PhaseCheckpoint,
CheckpointRelease, WorkspaceRun, ExecutionPolicyVersion, BudgetObservation,
ResourceReservation, LifecycleDecision and DispatchDecision.
Every derived task/admission is bound to workspace ID, run generation, mission
hash, phase/checkpoint/authority/policy versions and exact packet/seed hashes.
PacketApproval records owner versus delegated-brain actor and authority origin;
WorkspaceRun records pause/stop actor, reason and resume conditions.
Revoking/changing policy blocks future admissions; it does not pretend already
running work was cancelled.

Proposed routes are `/api/workspaces` and
`/api/workspaces/{id}/state|commands|assistant|artifacts|runs|profile|authority|phases`.
They are design targets, not existing endpoints. Server resolution supplies the ledger, notifier,
inference context and authorization boundary. Include workspace identity in
command fingerprints, signed assistant previews, artifact keys and audit events.
Use per-workspace jobs/caches and a shared inference concurrency limit without
ever sharing prompt contents. Keep credentials only in ignored server-side files.

Retain loopback-only service, Host/Origin checks, HttpOnly sessions, CSRF, bounded
payloads and no-store responses. Reject traversal/symlink/unknown workspace roots,
ambiguous mapping and cross-workspace object references. This release does not
add users, network exposure or a hosted tenancy system.

## 10. Incremental implementation and acceptance

Each increment is a bounded tooling branch/PR; none implements product packets.
Do not mix these changes into unfinished assistant-controls publication.

### WSP-01 — registry, isolation and migration

- [x] Versioned private registry and explicit workspace-aware CLI/skill routing.
- [x] Per-workspace ledger/context factories and scoped authenticated reads.
- [x] Read-only migration preview of the existing portfolio into the first workspace.
- [x] Register the current ledger in place; preserve brain identity, receipts,
      approvals, artifact hashes, metrics and all native tasks. No reinitialization.
- [x] Back up with SQLite's supported backup flow; verify hashes/counts, restart and corruption detection. Recovery remains an explicit manual operation, not an automatic restore.
- [x] Tests with two synthetic workspaces, colliding IDs, invalid roots and restart.

Local migration evidence: existing brain retained, all 15 ledger tables match the
registration backup, including 78 artifact versions. Ledger revision did not
change. No native task, approval, heartbeat or product mutation was performed.

### WSP-02 — workspace navigation and scoped assistant

- [x] Workspace switcher, All workspaces view and scoped deep links.
- [x] Overview-first selection and versioned executive project introduction with sources.
- [x] Separate static project purpose/architecture from live operational brief/status.
- [x] Per-workspace jobs, drafts, assistant context and confirmation binding.
- [x] Recorded aggregate/distributed usage, delivery, artifacts and roadmap with explicit deduplication and coverage. Different clones are not yet canonicalized together; conflicting shared-session summaries are excluded.
- [x] Two-workspace browser checks: switching, draft retention, scoped chat, profile save and narrow-screen selection; automated stale-response and confirmation-isolation tests.
- [ ] Larger-portfolio browser/performance qualification and full canonical clone/worktree identity (WSP-04).

See [implemented workspace operations](WORKSPACES.md). WSP-03 through WSP-06 remain
open: this release does not rename legacy Resume into continuous Play or grant
delegated packet authority. Cross-workspace concurrent mutation is not enabled.

### WSP-03 — delegated phase authority and truthful Play/Pause

WSP-03 is split into reviewable increments. **WSP-03A** is configuration-only:
immutable mission/phase/authority drafts, authenticated owner review/revocation,
policy validation and the dashboard editor. It grants no execution authority.
**WSP-03B/C** add actual delegation, phase release and run/control state machines,
and cannot activate before WSP-04 resource/budget admission is enforced. This
dependency prevents a reviewed numeric allowance from posing as an enforced limit.
See [implemented mission configuration](MISSIONS.md). Existing `reviewed` records
must never activate automatically on upgrade; activation requires a new exact
owner-bound action.

**WSP-03B1** implements the cooperative Pause portion independently of activation:
the selected workspace's primary control, exact retained worker/descendant
evidence, checkpoint blockers and explicit brain resume after parking. See
[workspace Pause](WORKSPACE-PAUSE.md). It does not implement Play, run generations,
phase release, native inventory collection or worker continuation authorization.

**WSP-03B2** adds an explicit [run-readiness inspection](RUN-READINESS.md) joining
the current mission/review, prepared packet path containment and retained platform
evidence. It separates owner setup from evidence gaps and unimplemented controls.
Its candidate hash is diagnostic, not a run generation, activation or reservation.

**WSP-03B3** adds [phase-bound task declarations](TASK-CONTRACTS.md): exact
mission/review/seed and repository-policy bindings, checked operation/path subsets,
requested settings, estimates, rationale and immutable proposal history. These
packets are fenced out of legacy seed-only approval/dispatch. This is the task
contract prerequisite, not delegated approval, native settings application or Play.

**WSP-03B4** adds the internal [run-authority kernel](RUN-AUTHORITY.md): exact
owner-confirmed generations, expiring intent, exact/delegated task approvals,
atomic Pause/mission/recovery fences and exact checkpoint release. Brain stop
boundaries require a newly reviewed scope. No public activation route or native
admission adapter is enabled; neither a generation nor approval is a native permit.

- [x] WSP-03A: versioned mission, phase, repository scope, owner checkpoint and proposed authority limits.
- [x] WSP-03A: explicit exact-hash owner review/revocation, stale-write and policy-change checks.
- [x] WSP-03A: workspace editor, immutable history, retained drafts and truthful inactive state.
- [x] WSP-03A: designated-brain draft-only procedure and bounded assistant awareness.
- [x] WSP-03A: isolated tests for empty scope, Harness/manual merge, retries and workspace isolation.
- [x] WSP-03B1: primary workspace Pause, evidence-bound worker/descendant checkpointing and visible progress.
- [x] WSP-03B1: prohibit early resume, preserve ownership across retries and distinguish saved checkpoints from current inactivity.
- [x] WSP-03B2: read-only exact mission/review binding, conservative packet-scope assessment and platform-baseline diagnostics with workspace-scoped reports.
- [x] WSP-03B3: closed phase/task declarations, bounded estimates/requested settings, immutable brain proposal history and no legacy dispatch downgrade.
- [x] WSP-03B4: internal run/approval/checkpoint lifecycle kernel, stop races and legacy bypass fences; no public Play or native effect integration.
- [ ] Implement the selected configurable authority model in tooling/skill contracts.
- [ ] Activate workspace authority with enforced packet, checkpoint, task and token admission.
- [ ] Mission/phase review, delegated packet approval/revocation and exact version checks.
- [ ] Phase report, independent verification and owner-bound checkpoint release.
- [ ] Durable workspace-run intent, immediate notification, receipt and recovery states.
- [ ] Autonomous Play integrated with workspace Pause and run generations; reject duplicate activation and pause/play races.
- [ ] Brain-initiated safe stops for phase completion, material plan changes and budget revisions.
- [ ] Empty scope, unavailable brain, manual merge and strict Harness policy tests.

### WSP-04 — shared resources and adaptive routing

**WSP-04A** implements the private atomic capacity kernel and read-only resource
audit, with synthetic contention/recovery/accounting tests. It is not connected
to native dispatch. **WSP-04B1** implements explicit maintenance enrollment,
durable fences on upgraded legacy routes and retained-owner recovery; it does not
activate runs or populate the kernel. See [the enrollment contract](ENROLLMENT.md).
**WSP-04B2** imports retained legacy owners as quarantined claims, preserving
unknown mappings/usage and conflicts with durable kernel identity and cross-database
receipt recovery. It does not independently verify native activity or grant capacity;
see [ownership adoption](OWNERSHIP-ADOPTION.md). **WSP-04B3** validates bounded
operator-supplied inventory, mapping and account/usage assertions and retains
versioned review/baseline receipts; see [evidence reconciliation](ADMISSION-RECONCILIATION.md).
It does not collect or independently attest native observations, release owners
or activate runs. Trusted observation collection, exact authority, run fences
and native-effect receipt integration remain required before
the full admission items below can be checked. See [the implemented contract and
remaining integration gates](ADMISSION.md). Do not activate a reviewed mission
or initialize live allocations as an upgrade side effect.

**WSP-04C1–C3g** now connect internal run authority to shared reservation,
native-result/correction journals, terminal settlement and
[standard-policy runner coordination](RUNNER-COORDINATION.md). These are tested
internal records, not native transport, trusted operator observations or Play.
The runner lifecycle is one-shot, holds resources through uncertainty, and
separates cleanup release from repository/token settlement. Harness acceptance
remains blocked until trusted execution and packet-specific attempt limits are
integrated. The full live admission/activation items below remain unchecked.
[Reconciled non-creation closure](CREATION-RECOVERY.md) now seals failed attempts
with explicit finality/absence/cleanup/zero-usage evidence, preserving identities
and attempts without retry. This does not collect independent native evidence.
[Separate result review](RESULT-REVIEW.md) now records exact standard-policy
acceptance or rejection after terminal settlement, preserving all evidence axes,
closed attempts and safe-Pause supervision. It validates retained proof bindings,
not their independent external truth. An optional
[local source observer](SOURCE-OBSERVATION.md) now measures exact local Git
structure under pinned identity, retains provenance and binds the complete diff
to a later review. It does not establish source semantics, CI, remote delivery or
preservation. The optional [GitHub observer](GITHUB-EVIDENCE.md) now collects exact
remote PR and required-check metadata through bounded read-only requests, retaining
provider identity, unknown coverage, drift checks and original-time provenance.
It does not prove workflow trust, semantic correctness or merge authority. Broader
native/host/external-preservation qualification and Harness acceptance remain unimplemented.
Completion does not enable legacy pilot or archival paths.

The optional [local preservation collector](LOCAL-PRESERVATION.md) now retains a
bounded self-contained Git bundle after restoration into an empty object store,
along with an exact inventory of retained handoffs and result evidence. Separate
review checks those bytes/versions and original collection time. This proves local
Git/evidence retention, not off-device backup, external LFS/submodule payloads,
native transcript preservation, acceptance or archive authorization. Verification
remains local; no Actions workflow or billable CI is added.

**WSP-04D1** adds the [brain-owned creation handoff](NATIVE-CREATION-HANDOFF.md):
a designated-brain CLI emits exact native task arguments for an already admitted
standard-policy reservation, consumes a current send check once, and binds actual
native result projections through the existing journal. The brain still performs
the app tool call. Local saved-project identity, exact base SHA, owner task
approval and native defaults are required. This is fixture-qualified integration,
not a live pilot, installed skill change, automatic dispatcher or Play activation.

**WSP-04D2** adds [native supervision](NATIVE-SUPERVISION.md): the brain obtains
exact single-task wait arguments, records normalized current native activity, and
records account-wide limits into an immutable shared journal. Unknown status
stays unknown even when an older turn completed. Window duration, not slot order,
determines short/weekly coverage. New incomplete or exhausted observations fence
admission; replay cannot revive old healthy evidence. These interfaces provide no
complete descendant inventory or cumulative phase-token accounting and do not
release resources, install an observer, change the window policy or activate Play.

**WSP-04D3** adds [cumulative phase accounting](PHASE-USAGE.md), connecting
supplied per-session counter evidence to admission and effect checks. It retains
the brain's phase baseline and each owned task tree's full lifetime usage, preserves
counter epochs and high-water marks, and incorporates exact terminal counters without
double charging. Unknown coverage or a changed context blocks new work. This is not
a native counter collector, qualified live coverage or autonomous phase execution.

**WSP-04D4** adds the [brain-owned runner handoff](RUNNER-HANDOFF.md): explicit
reservation, exact acceptance message preparation, one-shot pre-send launch check,
delivery observation, process/cleanup recording and receipt recovery. The brain
still calls the native messaging tool. Delivery does not prove process execution,
CI or acceptance; uncertain sends never retry. Standard policy only, with no
trusted host collector, installed operator upgrade or live activation.

**WSP-04D5** adds the [brain-owned result handoff](RESULT-HANDOFF.md): a settled,
exact owner-approved standard-policy task can collect measured source/GitHub
evidence, retain bounded supplemental proof, inspect its original provenance/time
and receive one separate acceptance/rejection. The brain still performs semantic,
criterion and preservation review; no worker claim or LLM output auto-accepts a
result. Historical receipts never refresh evidence. This closes the result CLI
integration seam, not live native/host qualification, continuation or archival.

- [x] WSP-04A: common-directory/conventional-origin identity observation and explicit platform-wide owner/alias audit.
- [x] WSP-04A: atomic multi-resource, global/workspace slot and token reservations in an isolated capacity kernel.
- [x] WSP-04A: fresh account/phase observation checks, checkpoint headroom and conservative settlement accounting.
- [x] WSP-04A: two-process contention, transaction rollback, restart and uncertain-creation retention fixtures.
- [x] WSP-04B1: exact owner-reviewed enrollment scope, journal-before-fence ordering and explicit recovery after partial setup.
- [x] WSP-04B1: legacy CLI/HTTP Resume, creation and acceptance-acquisition fences; no time-based release of retained owners.
- [x] WSP-04B2: exact owner-reviewed retained-owner import into quarantined shared claims, including unknown/duplicate native identities and runner-only owners.
- [x] WSP-04B2: durable platform fence and kernel inode pin, atomic import, interrupted cross-database receipt recovery and cached-client admission fences.
- [x] WSP-04B3: explicit evidence coverage/freshness diagnostics, exact owner-reviewed versions and non-resetting account/task cumulative baseline anchors.
- [x] WSP-04B3: read-only current re-evaluation, source/version concurrency checks, crash replay and retained ownership/fences.
- [x] WSP-04C3e: bounded standard-policy local commit/ancestry/branch/diff observation, retained collector/request proof and no timestamp refresh on review/replay.
- [x] WSP-04C3f: bounded exact GitHub PR/required-check observation, conservative policy/provider coverage, drift checks and retained CI/merge proof; no remote mutation or live workspace write.
- [x] WSP-04C3g: explicit local Git bundle and evidence preservation, source-independent restore/integrity check, private atomic retention and exact review-version binding; no archive or off-device backup claim.
- [x] WSP-04D1: one-use native creation handoff/check and CLI return-path fixtures; exact project/base/defaults, Pause races and conservative result recovery.
- [x] WSP-04D2: exact native task/account observation CLI, safe status/limit projections, current-evidence admission fences and replay/Pause/privacy fixtures.
- [x] WSP-04D3: cumulative phase/session accounting, baseline/epoch continuity, settlement incorporation and effect-context checks; supplied evidence only, no live collector.
- [x] WSP-04D4: exact standard-policy runner message handoff and separate delivery/process/cleanup CLI with one-shot send and Pause/crash fixtures; no native transport or live execution.
- [x] WSP-04D5: exact-owner standard-policy result CLI, source/GitHub collector composition, supplemental proof journal and separate review with historical reads; no automatic acceptance or live activation.
- [ ] Trusted native/operator observation collection and live evidence qualification; supplied assertions are not independent attestation.
- [ ] Canonical repository/runner identity and transactional platform reservations.
- [ ] Brain-owned new/continue/handle/wait decisions with reason and immutable task seed.
- [ ] Explicit model/effort/speed policy and requested/applied/observed decision records.
- [ ] Verify supported speed adapter; honest unavailable state when no per-task control exists.
- [ ] Fresh account usage observation, workspace allocations and reserved headroom.
- [ ] Atomic concurrency limits including starting/uncertain/review/nested task boundaries.
- [ ] Contention/fairness tests; stale/unknown budgets, fast-mode cost and unavailable-model tests.
- [ ] Crash recovery across reservation, local dispatch, native create and confirmation.

### WSP-05 — continuous development and knowledge lifecycle

- [ ] Mission-scoped task decomposition/admission, inheritance and bounded correction.
- [ ] Completion supervision, independent review, evidence promotion and next-task selection.
- [ ] Continue after ordinary packet completion without asking for routine owner instructions.
- [ ] Safe archival policy with preservation verified before native archive.
- [ ] Quiet waiting, explicit decision wakeups and native recovery scheduling.
- [ ] Tests for malicious artifact instructions, exceeded scope and no-progress cycles.

### WSP-06 — supervised acceptance and rollout

- [ ] Existing Harness migration rehearsal without product dispatch or policy changes.
- [ ] Owner-approved low-risk mission in a separate standard-policy workspace.
- [ ] Real native tasks visible in Codex with observed execution configuration and exact worktree.
- [ ] Mid-mission Pause, worker/brain quiescence, retained checkpoint and duplicate-free Play resume.
- [ ] Brain approves an in-phase packet but cannot approve past a gate or increase its own limits.
- [ ] Mandatory phase completion stops the workspace until explicit next-phase release.
- [ ] Major plan/budget changes cause safe stops; ordinary task completion continues the run.
- [ ] Two-workspace contention and no cross-workspace assistant/action leakage.
- [ ] Verify source, CI, merge, installed skill, running revision and live behavior separately.
- [ ] Document limitations and enable the selected autonomy mode only after acceptance.

## 11. Recorded decisions and activation settings

The owner's edits settle these design requirements:

1. Each workspace brain owns the decision to open/continue tasks and select
   model, effort and supported speed settings inside its Codex environment.
2. The owner selects a workspace in the UI and sees its executive project
   introduction first on Overview.
3. Packet-approval authority, user checkpoint destinations, maximum parallel
   tasks and token budgets are configurable per workspace/phase.
4. Play continues roadmap development until user Pause, a mandatory checkpoint,
   roadmap completion or an explicit brain stop condition. No repeated “continue”
   is required for routine task boundaries.

Prepare-only and exact-owner-approval remain configurable restricted modes;
phase-delegated approval is the requested autonomous operating mode, not an
unresolved yes/no question. Concrete model/effort/speed allowlists, numeric token
and concurrency limits, checkpoint locations, archive permissions and repository
policies are explicit setup values before a workspace is activated, not guessed
live changes in this document. The existing Harness workspace keeps its stricter
rules until any compatible policy amendment is separately authorized.
OpenClaw remains deferred.
