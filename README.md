# Codex Native Coding Harness

A local operations ledger and dashboard for an existing Codex task acting as the
brain of a multi-repository development workflow. The brain prepares bounded
inheritance packets, creates native implementation tasks inside an approved queue,
supervises them, and independently verifies completion.

**The webpage is not an agent scheduler.** It records typed requests in SQLite;
an opt-in bridge immediately notifies the existing brain of saved decision
answers and typed controls through the legacy `codex queue` route or a separately
reviewed [owned standard-brain app-server](docs/OWNED-BRAIN-WAKE.md). The brain performs worker operations. No private desktop API, runtime download
or external telemetry is used. Orchestration needs no model API key. An optional,
user-configured inference service can draft advisory briefs and answer dashboard
questions on explicit request. It may propose existing typed controls, but has no
controller authority: an exact owner confirmation is required for submission.

## What is included

**New opt-in standard contract:** [Cooperative standard runs](docs/STANDARD-COOPERATIVE-RUNS.md)
connect exact owner Play/Pause/Resume to the existing native brain, bounded phase
delegation, task inheritance and observed-usage accounting. Existing workspaces
are unchanged. Strict managed/Harness activation remains separate; descriptions
of internal kernels and unavailable strict Play below still apply to that mode.
See the [completion checklist](docs/STANDARD-PROJECT-COMPLETION.md).

- Portfolio-neutral controller, with `standard` and stricter `harness` policies.
- Versioned, immutable seeds and completion envelopes; digest-bound approvals.
- Single-controller ownership, one worker per repository, and serialized managed
  acceptance. One worker initially; two only after a verified real pilot.
- Safe handling of uncertain creation, pending native IDs, process interruption,
  stale approval, pause races and retained ownership.
- Loopback dashboard with queue, workers/evidence, knowledge, events, metrics and
  Markdown report export. Local authentication, Host/Origin checks and CSRF guard.
- Personal Codex skill and a runbook for native tool operations and recovery.
- Read-only Git metrics: aggregate and per-repository snapshots at exact commits.
- Optional evidence-linked executive brief on Overview, using an allowlisted
  on-prem model through `llm-inference-engine`. Versioned output, freshness,
  service-reported usage, and a preview of the exact aggregate data sent.
- Contextual AI assistant with bounded, transient chat and server-validated links
  to dashboard views, decisions and artifact versions; bounded operational/capability
  awareness and expiring, state-bound, owner-confirmed action previews.
- A [session map](docs/SESSION-MAP.md) as the landing page: the project brain,
  registered tasks, selectable responsibility connections, and details below.
  Search, state filters, a list alternative and fresh-activity animation make
  recorded work easier to follow; stale and uncertain states stay explicit.
- Three collapsible panes, draggable/keyboard splitters and remembered layout;
  the advisory assistant starts collapsed for new layouts. Existing preferences
  are preserved, with focused single-pane navigation on narrow screens.
- A top-toolbar **Back** button follows this tab's visited dashboard pages and
  project switches, including linked artifacts and decisions. It survives reloads,
  cooperates with browser Back/Forward, and is disabled at the first dashboard
  entry or while a request is in flight. Browser navigation waits for an in-flight
  request; it does not cancel work. History contains routes only, never chat or
  credentials; at most 100 prior routes are tracked per entry.
- Private development projects with isolated ledgers, scoped assistant/actions,
  versioned project introductions and an All projects comparison. The selector
  mirrors the retained native Codex project inventory; newly listed projects stay
  unconfigured until explicitly bound. See [project catalog synchronization](docs/PROJECT-CATALOG.md) and
  [workspace setup and current limits](docs/WORKSPACES.md); continuous phase
  autopilot remains tracked separately, not implied by registration.
- Mission/phase configuration and exact owner review, deliberately inactive. A
  [shared admission foundation](docs/ADMISSION.md) adds a tested internal capacity
  kernel and explicit read-only `platform-resources` audit; native dispatch and
  autonomous Play are not yet connected to it.
- Explicit [maintenance enrollment and interrupted-setup recovery](docs/ENROLLMENT.md)
  preserve existing ownership and fence upgraded legacy launch paths. This is not
  automatic migration or Play; no live enrollment should be inferred from an upgrade.
- Owner-reviewed [retained ownership adoption](docs/OWNERSHIP-ADOPTION.md) imports
  historical tasks/runners into shared admission as quarantined claims, preserving
  conflicts, unknown usage and interrupted-import receipts. It does not enable Play.
- [Admission-evidence reviews](docs/ADMISSION-RECONCILIATION.md) compare bounded
  external observations with retained owners and preserve account/task usage
  baselines across versions. Freshness, coverage and counter resets stay explicit;
  no native collection, ownership release or activation is implied.
- Optional [local result preservation](docs/LOCAL-PRESERVATION.md) retains a
  bounded private Git bundle after a source-independent restore check, with exact
  handoff/evidence versions. Local retention is not automatic acceptance, archival
  permission or off-device backup.

Development verification is local. Do not add/enable GitHub Actions workflows,
dispatch/rerun jobs or provision paid CI: the owner requires no extra Actions
billing. Read-only GitHub evidence checks do not execute workflows. Missing CI
remains unavailable, never silently replaced by local-test success.

Start with **Roadmap & Play**. It shows the current phase and one next action:
prepare a proposal, review the plan, confirm Play, follow sessions, or review a
checkpoint and prepare the next phase. **Prepare next phase** fills an editable
message in Brain conversation; review and send it yourself. It never starts work.
For the complete flow and state explanations, see the
[Roadmap & Play guide](docs/ROADMAP-PLAY-UX.md).

**Session map** remains the activity monitor. Click a node or connection to inspect
its conversation, evidence or metadata below the graph. **Phase setup & recovery →
Advanced controls** contains historical and recovery details, including optional
brain handoff. Normal phase iteration does not require a brain replacement.

Use the top **Navigation / Project / AI assistant** controls to show or collapse
panes. Drag either divider, or focus it and use Left/Right (Shift for larger
steps; Home/End for limits). **Reset layout** restores defaults. Type in the right
panel and choose **Send** (or Cmd/Ctrl+Enter). Suggested questions only fill the
box. Chat links navigate. To act, request a supported control and separately confirm
its exact inline preview. Brain activity and worker dispatch are different controls.
See [Assistant guide and data boundary](docs/ASSISTANT.md).

AI briefs are unverified drafts. Initial live trials exposed occasional narrative
errors; factual-accuracy qualification remains open. Deterministic metrics and
independent evidence remain authoritative.

This coordinates native tasks; it does not replace repository policy, a trusted
runner, OS isolation, independent review or human authorization. The local owner
and the brain are trusted. Ledger evidence references are checked for structure,
not cryptographically certified by the controller.

## Quick start

Use Python 3.11+; the controller and tests use only the standard library. The
optional YAML packet importer additionally requires an **already installed**
PyYAML. Do not install dependencies during a restricted execution run.

1. Copy `config/portfolio.example.json` into `.state/portfolio.json`. Fill in an
   existing brain task ID, repository paths, actual saved Codex project IDs,
   authoritative refs, and merge policies. `null` project IDs block dispatch.
2. Initialize and test:

   ```sh
   python3 -m orchestrator.cli init .state/portfolio.json
   python3 -m unittest discover -s tests -v
   node --check web/app.js
   python3 scripts/install_skill.py
   ```

3. Start the dashboard:

   ```sh
   python3 -m orchestrator.cli serve
   ```

   To enable immediate decision delivery, use the absolute path to the installed
   Codex CLI (resolve its current installed path on the host):

   ```sh
   python3 -m orchestrator.cli serve --notify-brain /absolute/path/to/installed/codex
   ```

   Keep this option on subsequent restarts. Without it the bridge is disabled,
   clearly reported in the dashboard. No CLI is downloaded or daemon started.
   A queue acknowledgment does not prove an unloaded desktop brain began a turn.
   The alternative owned-host source path is opt-in and requires a separate
   activation review; it is not selected by this command.

   Open the private URL in `.state/dashboard-session.json` in a Codex browser
   panel. It uses a local bootstrap token in the fragment, clears that fragment,
   and establishes an HttpOnly, SameSite session. Never publish the private URL.
   Choose **Remember this browser** in the top bar to stay signed in for 7, 30,
   or 90 days, including through server restarts. Then bookmark the ordinary
   workspace URL. **Browser access** offers renewal, sign-out and explicit
   all-browser revocation. See [Browser access](docs/BROWSER-ACCESS.md).
   The server binds only `127.0.0.1`; it is not a network-deployment server.
4. In the designated brain, invoke `$codex-orchestrator` for **read-only onboarding**.
   Keep dispatch paused until a real packet is explicitly approved and verified.

Closing the browser does not stop a brain or worker. Stopping the local server
does not cancel tasks. Restarting rotates the private bootstrap link and temporary
sessions, but preserves unexpired remembered browser sessions and ledger state.
Keep the computer and Codex app running for local scheduled work.

## Control semantics

| Action | Immediate effect | Native effect |
|---|---|---|
| Approve / hold / prioritize | Update reviewed ledger state; notify brain | Brain receipts current state; no task creation by notification alone |
| Pause | Block the next creation boundary; supersede queued resumes | Does not cancel running or already-starting tasks |
| Resume worker dispatch / reconcile | Save and notify existing brain now | Brain records receipt and applies the scoped control; active turns finish first |
| Checkpoint worker | Save and notify brain | Brain sends a cooperative checkpoint request |
| Archive completed task | Save after preservation checks; notify brain | Brain verifies inactivity and uses native archive |
| Wake / Resume brain | Save intent and notify the same native task | Recover retained state; worker dispatch unchanged |
| Stop brain at safe checkpoint | Pause new dispatch immediately; notify brain | Reconcile workers/runner, retain checkpoint, pause heartbeat, then end turn |
| Pause workspace (registered workspace) | Fence new preparation/approval/dispatch; retain the worker set; notify brain | Evidence-bound worker and descendant checkpoints, runner cleanup and paused schedule; resume only after parking |
| Answer a decision | Save the version-bound answer; notify the existing brain if enabled | Idle pickup immediately, or native queue behind an active turn; brain records receipt and scoped outcome |
| Use event-driven waiting / enable periodic idle checks | Save preference; notify brain | Brain pauses idle scheduling or enables explicit idle checks; active work remains supervised |

The [Decision inbox](docs/DECISIONS.md) separates recorded answers, brain receipt,
design outcomes and implementation approval. Immediate notification removes the
heartbeat delay for new answers and controls; it does not interrupt a busy brain
or grant execution authority. [Brain controls](docs/BRAIN_CONTROL.md) distinguish
stop intent, safe checkpoint and native turn completion. While stopped, ordinary
inputs are saved until explicit Resume brain, which can wake the task even with
its heartbeat paused. The brain then restores scheduling per saved policy.
Registered workspaces use **Pause workspace** as the primary Overview control.
[Workspace Pause](docs/WORKSPACE-PAUSE.md) shows the outstanding checks and keeps
dispatch-only controls in a separate disclosure. **Resume brain from checkpoint**
does not enable autonomous Play or authorize new worker work.
**Run readiness → Inspect run readiness** now compares the selected mission's
exact review, prepared packet scope and retained platform inventory/usage evidence.
It separates owner setup, evidence gaps and missing software controls, with a
downloadable JSON report. [Run readiness](docs/RUN-READINESS.md) is read-only;
neither a satisfied check nor its diagnostic candidate hash grants execution.
The brain can now prepare a [phase-bound task declaration](docs/TASK-CONTRACTS.md)
with exact operations, requested settings and a token estimate. Inspect it from
the packet's queue review or Run readiness. Declaration-bound packets cannot use
the old seed-only approval path; run-aware activation remains unimplemented.
An [internal run-authority kernel](docs/RUN-AUTHORITY.md) now retains exact owner
intent, generation-bound task approvals and checkpoint release, with atomic stop
fences. It has no public activation route; native admission/effect integration is
still required before Play is available.
The [internal dispatch-admission bridge](docs/DISPATCH-ADMISSION.md) now couples
those approvals to shared reservations and a recoverable one-shot creation-intent
journal. It preserves phase budgets across run generations and refuses duplicate
creation after interrupted commits. It still makes no native calls, cannot release
maintenance fences and has no public Play route.
The [native lifecycle coordinator](docs/NATIVE-LIFECYCLE.md) adds pending/confirmed
task bindings, uncertain-result recovery and budgeted same-task correction intents.
Delivery acknowledgment and finished-turn evidence remain separate. These are
internal records, not native transport or live activation; idle never frees ownership.
The [terminal settlement coordinator](docs/OWNERSHIP-SETTLEMENT.md) can release an
internally managed confirmed task's reservation after complete, fresh terminal
reconciliation and preserve its actual usage. Crash recovery attaches the exact
receipt without releasing a newer owner. Settlement is not packet acceptance;
independently verified native evidence and Play activation remain separate gates.
The [shared runner coordinator](docs/RUNNER-COORDINATION.md) adds standard-policy
reservation, one-shot launch intent, process observations and cleanup release.
An uncertain launch keeps its owner; runner release keeps repository/token holds
for terminal settlement. It runs no commands, permits no automatic retry, and
refuses Harness acceptance until its trusted launcher and attempt policy are
integrated. No live state is changed by a source upgrade.
The [separate result-review coordinator](docs/RESULT-REVIEW.md) records acceptance
or rejection of a settled standard-policy packet only with exact result, criteria,
evidence-axis and independent-review artifact bindings. It leaves shared usage and
ownership unchanged. Acceptance is not deployment, pilot qualification or archival;
accepted tasks remain covered by safe Pause. This is internal source functionality,
not external evidence collection, a Harness acceptance adapter or live Play.
The [local source observer](docs/SOURCE-OBSERVATION.md) now supplies an optional
measured structural proof for that review: exact local commits, ancestry, branch
tip and complete changed paths, with out-of-scope findings and retained provenance.
It uses an isolated read-only Git view and never fetches, reads worktree contents,
runs tests or marks a packet accepted. CI/remote/preservation/semantic evidence
remain separate. It is internal standard-policy tooling, not a Harness adapter
or a new dashboard/Play control.
The [GitHub result observer](docs/GITHUB-EVIDENCE.md) supplies optional remote
PR/required-check evidence for the same review. It binds exact head/base/branch and
pinned repository identity, collects through bounded read-only GitHub requests,
and retains redacted provenance. Missing policy, ambiguous checks and empty check
sets stay unverified. CI, observed merge, semantic acceptance and runtime remain
separate; this internal helper does not merge, dispatch or activate Play.
The [brain-owned creation handoff](docs/NATIVE-CREATION-HANDOFF.md) connects an
already admitted, exact owner-approved standard-policy task to one-use native
`create_thread` arguments. The designated brain checks immediately before sending,
calls the app tool, and records pending, confirmed or uncertain results through
the existing lifecycle. It binds the actual local saved project and exact base,
preserves native settings defaults and refuses duplicate sends. This is a CLI
integration seam, not installed live automation or autonomous Play; source delivery
creates no native task and does not release any activation/maintenance gate.
The [native supervision interface](docs/NATIVE-SUPERVISION.md) lets that brain
record current task activity and account-limit observations through versioned
CLI receipts. It separates current status from old turn outcomes, retains no chat
content, and blocks admission on incomplete or exhausted account evidence. Missing
windows remain unknown; account percentages never substitute for complete phase
token accounting. These source interfaces do not install an observer, enable
autonomous Play, release task ownership or qualify live acceptance.
The [phase usage accounting bridge](docs/PHASE-USAGE.md) composes explicitly
supplied cumulative brain/task-tree samples into a stable phase budget. It retains
baselines and counter epochs, exposes known per-session/per-role totals, and
reconciles exact settled usage without charging it twice. Missing/regressed
coverage blocks new work without erasing known usage. This is not a live token
collector: source qualification and activation remain separate requirements.
The [runner handoff CLI](docs/RUNNER-HANDOFF.md) connects an existing approved
standard-policy task to a single-use acceptance message. The brain consumes the
launch check and calls the native tool; the helper separately records delivery,
process exit and cleanup. Uncertain sends retain ownership and never retry.
This does not execute tests, qualify host evidence or activate live automation.
The [result handoff CLI](docs/RESULT-HANDOFF.md) connects a settled owner-approved
standard-policy task to explicit source/GitHub collection, task-bound proof
retention and separate acceptance or rejection. Measured facts and supplied
review claims stay distinct; historical reads/replay cannot renew old evidence.
No worker response automatically completes a packet, and acceptance does not
merge, archive, retry or advance the roadmap. Live activation remains separate.
The [owner-requested archive CLI](docs/ARCHIVE-HANDOFF.md) adds a separate one-shot
handoff for an accepted, locally preserved standard-policy root task. It requires
explicit cleanup acknowledgment and fresh safety evidence; the brain calls the
native tool. Uncertain outcomes never retry. This does not enable automatic
archival, managed archive UI controls or live Play.
The [non-creation recovery coordinator](docs/CREATION-RECOVERY.md) can close a
failed creation attempt only after explicit final absence, cleanup and zero-task-
usage evidence. It retains attempt counts and pending IDs, keeps the packet held,
and never authorizes a retry. Safe Pause recognizes the retained proof without
asking for a checkpoint from a nonexistent task; empty lists alone cannot do so.
The 15-minute heartbeat remains a
recovery fallback while enabled. Delivery is not receipt: unavailable, ambiguous
and overdue states keep the answer and explain the next action. Keep the computer
and Codex running. Native turns and scheduled checks consume model usage.

[Actionable follow-ups](docs/CONTINUATION.md) keep blocked answers visible until
the brain publishes a concrete proposal, a new decision or a named external
dependency. Event-driven waiting pauses model polling while awaiting owner input;
new dashboard events wake the same brain. A paused heartbeat cannot recover a
failed notification, which stays visible for manual recovery.

In **Mission & authority**, [model & effort policy controls](docs/MODEL-POLICY-CONTROLS.md)
let the owner inspect a recorded catalog, explicitly choose profile quality/token
floors and escalation limits, then preview and confirm review or revocation.
Policy changes fence existing run authority; they do not call a model, change
native settings or start Play. Catalog freshness and separately authorized run
intent remain mandatory. The dashboard assistant's inference model is separate.

In **Run readiness → Observation endpoint**, [observer setup controls](docs/NATIVE-OBSERVER-CONTROLS.md)
let the owner inspect, preview and confirm access to an existing private local
metadata endpoint, or revoke its review. Configuration starts blank and requires
an existing standard-policy phase allocation; it never discovers or starts a
server. Saved collection reports retain their original times and explicitly show
incomplete evidence. No connection, model call or Play follows from these controls.

Never blindly retry a `starting` worker or `processing` native action. Reconcile
its unique dispatch/request identity against actual native state first.

## Reuse with another project

For registered workspaces, **Phase checkpoints** shows saved phase-report versions
and lets you explicitly inspect their retained evidence. It separates unfinished
work, recorded worker results, stale/missing evidence and unknown phase usage.
The assistant receives cached metadata only. Opening the page does not prepare a
report, approve a release or start Play. See the [checkpoint owner workflow](docs/CHECKPOINT-VISIBILITY-PLAN.md).

In **Workers & evidence**, owners can explicitly inspect a settled result and
preview/confirm permission to review its unchanged commit in a later authorized
phase, or revoke that permission. Original review versions and saved independent
reports remain readable. This grants review permission only: no result acceptance,
task restart, brain notification, budget reset or Play follows. See the
[rereview owner workflow](docs/REREVIEW-CONTROLS.md).

The planned [development workspaces and phase-bounded autopilot](docs/WORKSPACES-AUTOPILOT.md)
will bring separate portfolios into one dashboard with executive project introductions,
workspace brains, configurable packet approval and phase checkpoints. Brains will
choose tasks and execution settings within user-defined concurrency/budget limits;
Play continues development and Pause reaches safe worker/brain checkpoints.
This is an implementation plan, not an available feature. The current
separate-directory workflow follows.

The Harness portfolio is a private configuration, not hard-coded into this repo.
For another portfolio, create a separate private configuration and state directory:

```sh
python3 -m orchestrator.cli --state .state/another-portfolio init .state/another-portfolio.json
python3 -m orchestrator.cli --state .state/another-portfolio serve --port 8769
```

Use the `standard` profile for ordinary repositories, with their own AGENTS.md,
execution requirements and manual/required-checks merge policy. Use `harness`
only when its deny-all-outbound trusted execution contract applies. The controller
refuses an in-place policy downgrade. No product source changes are needed merely
to install this tool. OpenClaw and other agent interfaces are out of scope.

## Prepare the first supervised drive

Open **Readiness** to inspect checkout/native-mapping gaps, packet launch blockers,
brain freshness and the separate real-pilot gate. Run the isolated lifecycle
rehearsal to test ledger transitions without touching product work. Its report is
synthetic and cannot enable dispatch or two-worker concurrency.

Read the [readiness runbook](docs/READINESS.md) and [first-pilot proposal](docs/FIRST_PILOT.md).
Project registration, safe worktree setup, a valid CI evidence route, exact packet
approval and a live brain cycle remain required. The webpage cannot directly
change the native heartbeat or silently register projects; it can notify the
brain to process a saved control through the supported queue bridge.

The [runtime provenance view](docs/RUNTIME.md) distinguishes the server-start
checkout from the current source tree and explicitly observed GitHub revision.
It flags dirty/changed/stale evidence and recommends manual restart when needed;
it never pulls code, restarts the process or treats a merge as deployment.

## Metrics and privacy

```sh
python3 -m orchestrator.cli scan
python3 -m orchestrator.cli export
```

Counts cover tracked UTF-8 text including blank/comment lines, grouped as source,
tests, docs and config/data. Exclusions and exact commit IDs are recorded. They are
not executable SLOC or test coverage. Worktrees are not counted multiple times.
Missing measurements are unavailable, not zero. Delivery metrics cover only tasks
managed by this ledger. Historical messages/tasks, model/effort, token and cache
observations can be imported from configured local Codex logs. The dashboard
includes Token usage, Git & delivery, Artifact library and Roadmap views. See
[observation setup and limits](docs/OBSERVATIONS.md). Missing sources remain
unavailable; retained local logs are not account-wide billing records.

Do not infer subscription charges from API token prices, or causal model effects
from unmatched tasks. Reports and the entire `.state/` directory are private and
Git-ignored. The public repository must contain no personal paths, native task IDs,
approvals, tokens, live databases or conversation transcripts.

## Documentation

- [Docker Compose gateway with native Mac backend](docs/DOCKER-COMPOSE.md)
- [Local account sign-in and password reset](docs/LOCAL-ACCOUNT.md)
- [Operator runbook](skills/codex-orchestrator/references/operations.md)
- [Record contracts](docs/RECORDS.md)
- [Acceptance and known boundaries](docs/ACCEPTANCE.md)
- [Inference setup, privacy and future uses](docs/INFERENCE.md)
- [Official scheduled-task documentation](https://learn.chatgpt.com/docs/automations)
- [Official worktree lifecycle](https://learn.chatgpt.com/docs/environments/git-worktrees)

No hosted CI workflow is installed. Run the local checks above; product-specific
acceptance and required self-hosted checks remain owned by each product repository.
