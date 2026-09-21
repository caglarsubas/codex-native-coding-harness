# Codex Orchestrator — personal tooling

## Workspace conversation (2026-09-21)

The owner requested project selection and routine Codex interaction through the
dashboard. Authenticated owner messages may use the closed, brain-bound reconcile
payload described in docs/WORKSPACE-CONVERSATION.md. The bridge still sends only
a fixed pointer, never message text as argv. Only the designated brain may retain
its reply. Conversation grants no packet/phase approval, target access or bypass
of stop, budget or policy controls. Native security prompts remain native.

## Owner-approved standard-project contract (2026-09-21)

`standard_cooperative_v1` is a separate opt-in run protocol. The owner explicitly
approved registered-task scope, observed usage with gaps and checkpoint budget
stops, and task/tracked-terminal checks rather than whole-process-tree cleanup.
See docs/STANDARD-PROJECT-COMPLETION.md. Standard Play must bind an exact reviewed
phase and explicit owner confirmation; review alone never activates anything.
Only the native brain dispatches. No Harness, strict enrollment or imported-owner
fence may enter this protocol. All strict-mode requirements below remain intact.
The fixed notification bridge may also notify committed standard Play/Pause/
Resume controls; source upgrades do not install or activate live workspaces.

This is private development tooling, not a Harness product repository. Do not
edit Harness product checkouts from this workspace. Product workers must follow
their own approved packet, allowedPaths, AGENTS.md and trusted execution rules.

Use Python standard-library tooling. No runtime downloads or external telemetry.
The user-authorized optional llm-inference-engine integration is the only model
service exception: load its credential server-side from a Git-ignored .env, send
only the documented bounded status projection and, for assistant chat, explicitly
submitted messages plus bounded process/capability/decision/artifact metadata on explicit request,
use an allowlisted on-prem model, and never dispatch or mutate based on model output alone.
Chat may propose only server-catalogued existing typed controls. A separate explicit owner
confirmation of the exact, signed, expiring, revision-bound preview is required before the
normal ledger submission and notification path. No model-authored commands, direct native
execution, implicit packet approvals or inferred confirmations. Keep durable command receipts
separate from transient chat, and preserve every existing control gate.
Never commit endpoint credentials or the supplied credential document. No hosted
provider fallback or new paid-service integration. The installed PyYAML is used
only by the read-only packet importer; it never executes a packet. Tests use
temporary fixture repos.

The owner requires no extra GitHub Actions billing. Keep verification local;
do not add/enable Actions workflows, dispatch/rerun jobs, provision runners or
introduce paid CI services. Inspect workflow configuration read-only before
pushing a branch/PR; stop if it could trigger unapproved billable execution.
No workflows are currently configured. Missing checks are not passing CI; never
weaken an approved task's evidence requirements to manufacture CI success.

Run `python3 -m unittest discover -s tests -v` and `node --check web/app.js`.
Keep `.state/` private. Never commit auth tokens, conversation transcripts or
the live SQLite database. No background dispatcher or private Codex API. The
owner-authorized notification bridge may invoke only the installed `codex queue`
CLI with a fixed message to the configured existing brain after a validated,
committed dashboard decision response or typed resume/reconcile/checkpoint/archive/
brain_stop/brain_resume or locally applied approve/hold/prioritize/listening/pause
control awaiting its brain receipt. A brain stop is a cooperative checkpoint, never
a process kill. Saved ordinary inputs do not wake a stopping/parked brain; only
explicit brain resume does. No response text, arbitrary argv, target,
model or effort comes from the browser. Claim before sending; never blindly retry
uncertain delivery. All worker operations and authority remain with the brain.

Dispatch defaults to paused. Queue authorization must identify exact packet and
seed hashes. A request to build this controller is not product packet approval.

Workspace mission/phase authority records are configuration-only in WSP-03A.
Owner review is not packet approval, delegation, enforced budget or activation.
The brain can propose drafts under its controller but cannot review/revoke them.
Do not read `reviewed` as executable authority or auto-activate on upgrade. See
docs/MISSIONS.md; resource/budget admission and run/checkpoint gates must ship
before a separate exact owner-bound activation can enable autonomous Play.

WSP-04A's admission kernel is capacity accounting, not execution authority. It
has no allocation/dispatch write route or native-dispatch integration. Do not initialize
live allocations, auto-adopt owners or change legacy dispatch during an upgrade.
The explicit platform-resources command is read-only, bounded metadata inspection;
its snapshot is not a lock. WSP-04B must implement legacy-owner adoption, authority
fences and cross-database recovery before using the kernel for native operations.

WSP-04B1 enrollment is an explicit maintenance fence, not activation. Do not run
platform-enroll or its recovery on live state merely because tooling is upgraded.
It has no unfence path in this version. Retain both the private file and SQLite
fence; never delete them to bypass a refusal. Updated legacy --state commands
must honor either signal. Only safe-stop supervision and reconciliation of
existing native work may continue; no new tasks, acceptance, retries or merges.
See docs/ENROLLMENT.md for exact scope, recovery and remaining activation gates.

WSP-04B2 provides explicit owner-confirmed quarantined ownership import only.
See docs/OWNERSHIP-ADOPTION.md. No automatic live adoption, guessed resource
identity, zero-usage assumption or implicit budget grant. Preserve every owner
version and both platform sidecars; do not delete a fence or pin to recover.
Imported ownership is not verified native inventory or executable run authority.
An empty recorded inventory is not proof of free global capacity. Kernel policy
initialization is allowed only by this exact maintenance review or isolated tests;
new allocations remain unavailable through public routes.

WSP-04B3 validates externally supplied evidence and retains exact owner-reviewed
versions and cumulative usage baselines. See docs/ADMISSION-RECONCILIATION.md.
A consistent report is not independently authenticated native evidence, an owner
release, a budget grant or run activation. Never fabricate coverage/cleanup flags,
refresh observation timestamps on read or reset an account/task counter epoch to
hide usage. Do not collect or record a live baseline merely to upgrade the tooling.

WSP-03B1 workspace Pause is cooperative safety coordination, not autonomous Play
or mission activation. Retain the exact stop's worker set and every subsequently
observed descendant. No early Resume, guessed idle state, disappearing owner,
forged coverage or read-refreshed evidence timestamp. Only the designated brain
may retain native pause observations and park with their exact current hash.
Keep checkpoint retention, current native inactivity and ownership release
separate. Do not reinstall the skill or alter a live brain/schedule just to ship
source changes. See docs/WORKSPACE-PAUSE.md for rollout and legacy boundaries.

WSP-03B2 Run readiness is an explicit read-only inspection, not a run controller.
Candidate/report hashes are diagnostic bindings, never authority or reservations.
Do not activate from a configuration review, infer operation permissions from
path containment, or treat retained platform assertions as native attestation.
Keep owner setup, evidence gaps and unimplemented controls distinct. Reads must
not initialize admission, release owners, notify tasks or update evidence clocks.

WSP-03B3 task contracts are immutable designated-brain proposals, not packet or
run authority. Only a current exact reviewed phase can bind a declaration. Keep
requested settings separate from applied/observed facts; no opaque setting ID
proves host support or owner policy. Contract-bearing packets cannot use legacy
approval/reservation/creation, even after reprepare. Preserve invalid/stale pointers
for recovery; never remove them to regain legacy dispatch. The first explicit
proposal atomically marks that ledger v2; ordinary reads/upgrades do not. Before
live use, stop and upgrade all older processes and back up private state. Do not
downgrade the schema marker or run an older cached helper against that ledger.
See docs/TASK-CONTRACTS.md; no installation or live schema change is part of source
delivery. Existing v1 seeds and untouched legacy packets retain their contracts.

WSP-03B4 is an internal run-authority kernel, not an activated native controller.
No CLI, HTTP, assistant or installed-skill activation path exists. Do not call it
on live state as part of an upgrade. Exact owner run intent, generation-bound task
approval and an authority check are not capacity reservations or native permits.
The future adapter must enforce both authority and shared admission at effect and
continuation boundaries. Keep Pause/recovery/mission-change fences atomic; ordinary
Resume cannot re-arm an old generation. Phase/budget/plan boundaries require a
newly reviewed mission or bounded correction scope and exact checkpoint release.
Run generations never reset token usage, task-attempt counts or resource ownership.
First internal authorization upgrades metadata to v3; old cached processes must
be stopped/upgraded first. Preserve all schema markers, declarations and history.
See docs/RUN-AUTHORITY.md. No live activation or mixed-version rollout is authorized.

WSP-04C1 connects internal run authority to shared reservation and a recoverable
creation-intent journal; it is NOT a native adapter or Play activation. See
docs/DISPATCH-ADMISSION.md. Keep registry -> workspace -> admission lock order,
stable same-phase accounting and deterministic task ownership. A local creation
intent alone prohibits retries; retain it as in-flight even if shared advancement
failed. Receipt recovery must not create a claim, reset counters, release resources
or unpause a workspace. Existing enrollment/adoption fences have no bypass. Never
use legacy bind/transition/runner/completion for an admission-managed worker.
Native result binding and same-run correction receipts use WSP-04C2 below;
terminal ownership release uses WSP-04C3a below. No live kernel setup or
activation is authorized by source delivery.

WSP-04C2 adds internal native-result observations and same-run edit-correction
continuation receipts. See docs/NATIVE-LIFECYCLE.md. Pending client IDs are not
confirmed tasks; acknowledgment is not a finished turn or acceptance. Never resend
an uncertain or locally retained continuation, erase a native binding, or release
tokens/resources on idle/finished observations. Fresh authority, preflight and
admission plus a retained scoped instruction artifact are required before a new
correction intent. Two consecutive no-progress corrections block further work.
Observations/recovery may retain facts after Pause but do not resume execution.
Keep the kernel journal and local receipts consistent, and invalidate old Pause
inventory when the native lifecycle changes. No native transport, live setup,
new-generation continuation approval, maintenance release or public Play is shipped.

WSP-04C3a provides internal confirmed-terminal settlement only. See
docs/OWNERSHIP-SETTLEMENT.md. Never equate idle, a worker final message or a complete
evidence shape with independently verified terminal facts. Require fresh complete
task/descendant inactivity, retained task-scoped handoff bytes, final cumulative
usage and exact resource cleanup; refuse unresolved sends, controls and runners.
Shared release commits before its local receipt. Recover only that receipt after
interruption, never a second release or erasure of a newer owner. Preserve all
maintenance fences, native identities, task attempts and actual usage including
overruns. Settled workers are not accepted/complete or eligible for archival;
keep their packet held for separate result review. No not-created recovery,
runner execution, native transport, public Play or live migration is authorized.

WSP-04C3b adds internal standard-policy shared runner coordination. See
docs/RUNNER-COORDINATION.md. Acquisition, local-first launch intent, process exit
and cleanup release are separate facts. Either launch marker prohibits retries;
unknown delivery never means unlaunched. Release only the exact runner key after
fresh idle/full-process-tree cleanup evidence; retain repository and token holds
until separate terminal settlement. One reservation per worker, including cancelled
reservations; no implicit retry allowance. Test authority, immutable execution,
retained instructions and fresh admission are required at both launch boundaries.
Harness acquisition is refused until its trusted launcher/isolation and packet
attempt contract are integrated. Preserve maintenance/Pause fences and newer
owners during receipt recovery. External observations are assertions, not native
attestation. No process commands, transport, live installation or Play activation.

WSP-04C3c adds internal reconciled non-creation accounting in the existing terminal
journal. See docs/CREATION-RECOVERY.md. Never infer absence from an empty list,
missing ID, timeout or unknown outcome. Require a final exact creation result,
complete attempt/descendant/effect reconciliation, retained attempt-scoped bytes,
fresh cleanup and explicit zero task counters. Known native work, continuations,
runners or contrary Pause history cannot use this outcome. Close the old attempt
permanently, preserve pending IDs/task counts/cumulative usage, keep the packet
held and never retry automatically. Pause may omit a nonexistent task checkpoint
only with the exact retained non-creation receipt and artifact; fresh complete
Pause inventory and all other checkpoint gates remain required. No live rollout,
transport, maintenance-fence release or Play activation is authorized.

WSP-04C3d adds internal standard-policy result review after confirmed settlement.
See docs/RESULT-REVIEW.md. Require exact current run/task authority, retained
result/criterion/axis proofs and a separately bound reviewer report; no worker or
descendant self-review. Byte/hash/ID checks validate supplied assertions, not
independent Git/CI/native attestation. Never fabricate evidence or promote other
axes from source/CI/merge. Harness requires its future trusted acceptance adapter.
Reviews are atomic local outcomes; never change shared usage/owners or reopen the
closed attempt. Accepted admitted tasks remain in safe-Pause supervision; legacy
archive/pilot shortcuts are fenced. No rereview, native transport, public write
route, live upgrade or autonomous Play activation is authorized by source delivery.

WSP-04C3e adds explicit internal local source-structure collection for settled
standard-policy tasks. See docs/SOURCE-OBSERVATION.md. Derive paths/base/branch
from the approved task and require its pinned local common-directory identity.
Use only the configuration-isolated, bounded read-only Git view; no fetch, source
worktree read, tests, hooks, filters or remote observation. Harness must refuse
before filesystem inspection. Recheck authority after I/O before atomic artifact
retention; exact replay never recollects or refreshes time. Source structure is
not semantic correctness, CI, preservation or acceptance. Collector proofs need
their exact journal and request receipt; older supplied evidence remains explicitly
caller-supplied. No new public route, live collection, skill update or Play rollout.

WSP-04D1 adds a designated-brain CLI handoff for an already admitted standard-policy,
exact owner-approved task. See docs/NATIVE-CREATION-HANDOFF.md. The helper emits
native creation arguments once and consumes a fresh pre-send check once; the brain,
not Python, calls the current native tool. Bind the actual selected local Git project
and exact seed base through the isolated read-only view. Omit model/effort/speed
overrides. Never reissue after a creation boundary, lost response or consumed check;
retain pending client IDs separately and uncertainty as owned capacity. Late result
recording and receipt-only recovery may proceed after Pause, never resume it.
The check-to-native-call gap is cooperative in-flight work, not atomic cancellation.
No live allocations, approval/activation route, native task, installed skill update,
schedule change or maintenance-fence release is authorized by source delivery.

WSP-04D2 adds brain-owned read-only native task/account observation CLI interfaces.
See docs/NATIVE-SUPERVISION.md. Use exact owned confirmed task IDs and actual native
tool results; a completed old turn never proves current idle, and missing status
stays unknown. Preserve source hashes without conversation/tool content. Task
observations cannot prove full descendants, token coverage, cleanup or acceptance,
or release ownership. Bind account limits to window duration and a private account
identity; unknown/exhausted/new-account evidence fences new effects without legacy
fallback. Never convert usage percentages into phase/task token counters. Replay
is historical and does not refresh timestamps. Upgrade/activation must quiesce
older writers; no coexistence or downgrade contract is provided. Do not weaken
the current two-window policy merely because one native window is absent. No live
observation write, allocation, installation, schedule change or Play activation is
authorized by source delivery.

WSP-04D3 adds designated-brain cumulative phase usage state/record CLI commands.
See docs/PHASE-USAGE.md. This composes supplied evidence, not native collection.
Preserve exact workspace/allocation/account and task-tree bindings, brain baseline,
full-lifetime worker counters, counter epochs and per-session high-water marks.
Unknown/regressed coverage must fence new work without removing known charges;
report timestamps cannot refresh older samples. Incorporate settlements only with
their exact retained final session counters; never release ownership or infer
acceptance from accounting. Recheck both shared membership and local effect context.
No direct legacy usage overwrite after journal activation. Do not use dashboard
best-effort totals, account percentages or fabricated coverage as phase evidence.
No live baseline/observation write, mixed-version rollout, allocation, installation,
schedule, policy relaxation or Play activation is authorized by source delivery.

WSP-04D4 adds the designated-brain standard-policy runner handoff CLI. See
docs/RUNNER-HANDOFF.md. Exact owner-approved execution and confirmed local task
bindings produce fixed native message arguments; instruction artifact bodies
remain inert. Consume the existing local/shared launch boundary once immediately
before the brain's native send. Receipt replay/recovery must never return another
send permission. Lost responses, local-only intents and ambiguous delivery retain
ownership with no retry, cancellation as unlaunched or timeout release. Delivery
does not prove process activity, exit, cleanup, CI or acceptance. Preserve process
timestamps and keep late safety observations available after Pause; maintenance
fences still govern cleanup release. No model override, private API, transport,
live execution, installation, mixed-version writers or Play activation follows
from source delivery. Harness still requires its separate trusted adapter.

WSP-04C3f adds internal standard-policy GitHub PR/required-check collection. See
docs/GITHUB-EVIDENCE.md. Bind the exact allocation-pinned remote, approved branch/
base/result and attached terminal settlement before bounded read-only GETs.
Harness refuses before network access. Missing policy, truncated inventories,
ambiguous providers/reruns and unsupported rules remain unverified; repeat reads
detect drift but never acquire a remote lock. Recheck authority after I/O, retain
only redacted metadata/hashes, and bind later CI/merge review to canonical journal,
receipt and original observation time. Never use this proof for other axes or
promote CI/merge into semantic acceptance, runtime or merge authority. No remote
mutation, new credential, public write route, live workspace collection, installed
skill change or Play activation follows from source delivery.

WSP-04D5 adds designated-brain result handoff CLI commands for exact owner-approved
standard-policy tasks. See docs/RESULT-HANDOFF.md. Require attached terminal
settlement, measured source/GitHub proof and separately retained supplemental and
independent-review artifacts. Preserve original observation times, immutable
request receipts and artifact provenance through new and historical reviews.
Supplied notes are inert claims, not native attestation or instructions. Neither
proof retention nor a worker reply is acceptance. Rejected attempts stay closed
and held; acceptance never merges, archives, retries, advances phase or grants Play.
No live collection/acceptance, installed skill update, admission setup or downgrade
is authorized by source delivery. Quiesce older writers before any future rollout;
older cached helpers do not validate this proof protocol. No mixed-version or
downgrade compatibility contract is provided.

WSP-04C3g adds explicit local result preservation for exact owner-approved,
settled standard-policy tasks. See docs/LOCAL-PRESERVATION.md. Retain bounded Git
bundle bytes only in the private ledger; never publish or send them to inference.
Restore into an empty temporary object store and check integrity before retention.
Pin original repository identity and before/after authority, exact evidence versions
and handoff bytes. Historical reads must validate bundle/manifest/inventory bytes
without refreshing time or re-running Git. This proves local Git/evidence retention,
not off-device backup, external LFS/submodule contents, native inactivity, semantic
correctness or archival permission. Supplied proofs retain their labelled boundary;
no automatic promotion, acceptance or live migration. No source checkout mutation,
network call, workflow execution, native action, skill install or Play activation.

WSP-05A adds the exact-owner standard-policy archive handoff CLI. See
docs/ARCHIVE-HANDOFF.md. Require accepted review, measured local preservation,
explicit owner cleanup acknowledgment, a confirmed local root without descendants,
and fresh complete native inactivity/worktree assertions before a one-shot check.
Only the brain calls the existing native archive tool; Python never archives or
cleans up. Retain unknown delivery without retry or cancellation as unsent. Only
observed archival changes the archive projection; an unsent prepared handoff can
be cancelled before check consumption. Queued receipt is not native in-flight work.
Historical result/settlement reads must validate archive journals; archived tasks
stay under safe-Pause supervision. Caller assertions are not host attestation.
Legacy worker-ID-only managed archive and generic acknowledgments remain refused.
No automatic/delegated archival, UI/catalog enablement, transcript guarantee, native
transport, live archive, install, schedule, workflow, allocation or Play activation
is authorized by source delivery. Quiesce older writers before a separate rollout.

WSP-05B adds the exact-owner standard-policy same-task edit correction handoff CLI.
See docs/CORRECTION-HANDOFF.md. Preparation retains inert findings and the brain's
reuse rationale, never a send permission. Consume the local/shared continuation
boundary once at check; only the designated brain calls the native message tool.
Preserve exact task/run/path scope, native defaults, Pause/maintenance, cumulative
usage and two-no-progress bounds. Unconsumed preparations may be superseded with
new version bindings; historical receipts never restore older authority or renew
freshness. Unknown delivery and unmatched local intents retain ownership without
retry, cancellation as unsent or timeout release. Late facts and receipt-only
recovery must not resume work. No delegated/Harness/new-generation correction,
native transport, automatic task selection, live send, install, schedule, workflow,
allocation, maintenance release or Play activation follows from source delivery.
Quiesce older writers before a separate rollout; no downgrade safety is claimed.

WSP-05C adds brain-cycle inspect/decide/read/reserve composition. See
docs/BRAIN-COORDINATOR.md. The brain chooses create/continue/handle/wait from exact
current context; Python never chooses autonomously, calls native tools or creates
run/allocation authority. Delegate approval only inside an existing owner-authorized
phase-delegated standard-policy run, atomically with its version-bound decision.
Never replace a revoked/stale approval, reset task counters or infer authority from
wait/handle notes. Recheck the exact latest decision at both reservation stages;
historical decisions cannot restore old permission. Existing intents survive
supersession, Pause and interruption and use explicit receipt recovery.
Valid owner-delegated standard-policy task approvals are now supported by the
creation/correction/runner/result handoffs, superseding their earlier exact-owner-
only source restriction. All current authority/admission/evidence checks remain;
Harness and delegated archival keep their separate gates. No model override,
live native effect, installed-skill/schedule change, onboarding, maintenance release,
automatic phase release or Play activation is authorized by source delivery.
Quiesce older writers and prepared handoffs before separate rollout; no downgrade
or mixed-version writer contract is provided.

WSP-04E adds owner-reviewed adaptive model/effort policy and brain-only
capability/selection/observation CLI. See docs/MODEL-POLICY.md. This supersedes
earlier native-default-only handoff restrictions solely for an exact current
owner-reviewed adaptive run. No live setting changes or rollout are authorized.
Capabilities are bounded fresh observations of the destination native tool schema,
not a hard-coded model catalog or host attestation. Native defaults remain unchanged.
Only exact model/thinking fields may be emitted at existing creation/correction
send boundaries. Speed and Ultra remain unqualified; no global settings, API tier,
fallback model or paid-provider integration. Retain owner quality floors, work-token
floors and escalation limits; insufficient budget never permits a quality downgrade.
Requested/emitted, reported-applied and observed settings are separate. New adaptive
corrections/runner effects need fresh matching observations after the last consumed
boundary; delivery, a worker reply or a supplied model name alone is not proof.
Policy changes fence the run; uncertainty retains owners/tokens and never resends.
Owner review/revoke methods require an authenticated trusted caller; WSP-04G below
adds only their owner HTTP adapter, never brain authority. Preserve all Pause,
maintenance, Harness, acceptance and accounting guards. Quiesce older writers/
prepared handoffs before separately authorized rollout.

WSP-04G exposes model-policy inspection/review/revoke in Mission & authority. See
docs/MODEL-POLICY-CONTROLS.md. Bind signed previews to selected workspace, browser
session, ledger identity, exact revision/context, reviewed mission and recorded
catalog; atomically revalidate before the existing policy write and run fence.
Keep model/effort/profile/quality/token choices explicit and confirmations unchecked.
Missing/stale capabilities block review, not intact-policy revocation. Catalogs
remain designated-brain observations, not live host availability or benchmarks.
Historical retries cannot restore revoked authority. Polling/chat get cached
closed counts/status only; no model names/profiles, owner actions or proof reads.
No native settings change, provider call, brain notification, run intent, shared
accounting initialization, usage reset, maintenance release, install or Play.

WSP-04F adds explicitly requested, owner-pinned public native metadata collection.
See docs/NATIVE-EVIDENCE-COLLECTION.md. The sole additional read transport is the
reviewed installed executable's fixed `app-server proxy --sock` invocation against
an existing private local socket. No auto-start, default endpoint, daemon, private
API, remote listener, arbitrary RPC, task resume/subscription, model call or native
mutation. Bind phase-owned roots, complete returned pages, parent chains and endpoint
identity; recheck ledger scope/revision after I/O. Drop conversation, command and
error bodies. Configured settings are not per-turn telemetry; persisted descendants
are not complete ephemeral coverage; tracked terminal absence is not OS cleanup;
account/goal counters are not lifetime phase usage. Keep all four gaps explicit and
never promote a report into execution, model application, accounting, settlement or
acceptance. Owner endpoint methods require a trusted authenticated caller; WSP-04H
below supplies the owner-only HTTP adapter. No live
endpoint, installation, private ledger, schedule or maintenance changes follow from
source delivery. Milestone 3 stays open until the missing host evidence is qualified.

WSP-04H adds selected-workspace owner observation-endpoint controls in Run readiness.
See docs/NATIVE-OBSERVER-CONTROLS.md. Inspection reads bounded saved metadata only;
preview fingerprints existing files without execution or connection. Review requires
paused dispatch and an exact open standard-policy allocation. Bind signed previews
to browser session, registry/ledger/shared-store identity, revision and endpoint
fingerprints; use lossless decimal strings for nanosecond identities in browser JSON.
Confirm under registry/local/shared locks, retaining the shared allocation lock until
the local receipt is durable. Revocation of an intact review must remain available
when endpoint files, saved reports or shared accounting are unavailable. Historical
retries return the original receipt and cannot restore revoked access. Keep drafts
workspace-local, confirmations unchecked, times original and incomplete coverage
explicit. Polling/chat see cached closed metadata only. No public collection,
discovery, connect/start, brain notification, native mutation, accounting setup,
maintenance release, assistant owner action, installation, schedule change or Play.

WSP-09A adds canonical recorded portfolio counting, not resource identity authority.
See docs/PORTFOLIO-IDENTITY.md. Capture hashed common-directory and conventional
origin identity only during an explicit measurement, with before/after checks.
Summary/exports must not probe Git or resolve repository paths on read. Count each
identity/commit/policy once; different commits and forks stay distinct. Keep alias
rows, legacy identity gaps, changed settings and conflicts visible; never silently
fall back from a newer failed observation or infer zero from missing coverage.
Literal origin matching is descriptive, not a verified host alias, reservation,
token proof or migration decision. Preserve scoped assistant projections and all
admission/Pause/maintenance rules. No live refresh, rollout or Actions follows.

WSP-03C adds retained local phase checkpoint reports and exact owner review before
subsequent run intent. See docs/PHASE-CHECKPOINTS.md. Reports are historical claims,
not phase acceptance or fresh activity; unknown shared usage stays unknown. Keep
result axes, original observation times and checkpoint artifact bytes distinct.
Only the brain prepares reports and uses their controller-scoped CLI; the
authenticated dashboard may inspect them read-only under WSP-03D below. Owner
review uses the authenticated WSP-03E adapter below. Bind release to the latest unchanged
report, exact next reviewed mission, settings and expiry in the grant transaction.
Missing/superseded reviews cannot
use the old release path. No resume, dispatch, new retry, budget reset, ownership
release, acceptance, merge or archive follows. Quiesce older writers before a
separate rollout; no mixed-version/downgrade contract, live installation, public
Play or workflow execution is authorized by source delivery.

WSP-03D adds explicit, authenticated, selected-workspace checkpoint history and
retained-proof inspection. See docs/CHECKPOINT-VISIBILITY-PLAN.md. Polling and chat
must not inspect proofs, prepare reports or initialize shared accounting; expose
only cached bounded metadata to the assistant. Keep unavailable, superseded,
changed-source and uncheckable-current-context states separate. Inspection never
renews report/checkpoint timestamps or establishes acceptance, usage or native
inactivity. Reads cannot acquire a controller, notify, approve, release or resume.
Preserve workspace-generation guards, original artifact versions and the closed
navigation allowlist. These report reads add no public release or Play endpoint.

WSP-03F adds internal exact-owner authorization to review an unaccepted settled
standard-policy result in a later current run. See docs/GENERATION-RESULT-REVIEW.md.
Bind the original intent/settlement, exact previous outcome and same commit to the
current reviewed descendant run and still-covered mission scope. The brain cannot
mint permission; WSP-03G supplies only an authenticated owner HTTP adapter, not a
CLI shortcut or native resume. Keep old task
approval/contract and closed attempts unchanged. Before/after collector I/O must
check current authority, exact commit, Pause and maintenance. A fresh independent
review consumes one permission and appends an immutable result version; accepted
results cannot reopen. Preserve all old proofs/receipts in result reads, settlement
recovery and phase reports. Historical retries never restore projections or revoked
authority, reset usage, release ownership or authorize corrections. Bounded history
requires explicit migration, not pruning. No live rollout or downgrade safety.

WSP-03G exposes exact settled-result permission controls in Workers & evidence.
See docs/REREVIEW-CONTROLS.md. Explicit inspection is scoped to one workspace and
task and never collects proofs. Signed five-minute previews bind browser session,
ledger identity, exact revision/context, current run, original intent/settlement,
previous outcome and unchanged commit. Revalidate and write in one transaction;
retry only the identical signed request and never restore revoked permission.
Revocation remains available after Pause or damaged result proofs when its own
history is intact. Polling/chat receive cached closed counts/status only, never
proofs, owner actions or inference-authored approvals. Keep drafts and late
responses workspace/task scoped, confirmations unchecked and proof reads explicit.
No acceptance, notification, shared accounting initialization, native call, run
release or Play follows. This supersedes WSP-03F's internal-only owner surface,
not its evidence, scope, Harness, preservation or native qualification gates.

WSP-03E adds explicit owner checkpoint review/withdrawal, not run authorization.
See docs/CHECKPOINT-CONTROLS.md. Bind signed five-minute previews to workspace,
ledger identity, browser session, exact revision/context and explicit confirmation.
The current report, next reviewed mission, settings and next-intent expiry remain
mandatory. Inspect proofs only on explicit reads/previews/confirmation; polling
and chat receive cached closed counts/status only and cannot submit decisions.
Withdraw one exact review through a retained receipt and durable denial projection;
validate both inside every subsequent grant transaction. New reviews do not
supersede old reviews automatically. Withdrawal does not stop a run whose grant
already committed; use safe Pause. Historical replay never reapplies permission.
Missing/corrupt history fails closed; no report preparation, native notification,
task approval, shared-store initialization, admission or Play follows. Quiesce
older writers before separately authorized rollout; no downgrade safety is claimed.

WSP-05D binds wait decisions to recorded event hashes and adds read-only
brain-cycle-wait-state. See docs/BRAIN-EVENT-WAITS.md and the source skill's
references/managed-cycle.md. Unchanged input does not justify another decision,
evidence artifact or idle model poll. Quiet eligibility is not native inactivity,
schedule authority or a send permit; stop, retained/quarantined ownership,
pending receipts, incomplete result review and explicit listening dominate it.
Never route managed workers through legacy effect commands. Missing native
capabilities, terminal adapters and release/Play authority remain gated; the
guidance is not a rollout, live skill install or background scheduler. Preserve
old unbound decisions without claiming event coverage or downgrade compatibility.

WSP-04D6 adds a designated-brain terminal-handoff CLI for standard-policy local
tasks. See docs/TERMINAL-HANDOFF.md. This supersedes the internal-only terminal
entry-point limitation, not its evidence or rollout gates. Require explicit
confirmed/not_created outcome and exact attempt-bound proof provenance. State
reads must not attach a missing receipt. Reuse the shared-first terminal journal;
settle/recover preserve attempts, actual usage, newer owners and separate result
acceptance. Qualified external evidence remains mandatory; never promote public
metadata, a final reply or account percentages into complete descendants,
full-process cleanup or lifetime counters. No live migration, native collector,
runner adapter substitution, retry, install, schedule change or Play is implied.

WSP-04D7 adds explicit selected-workspace budget inspection. See
docs/BUDGET-VISIBILITY.md. Read existing private stores with bounded read-only
connections; never initialize admission, collect native samples or take controller
authority from a dashboard read. Reuse kernel arithmetic without double-counting
cached/reasoning subsets. Unknown, incomplete, stale or changed phase evidence
suppresses the balance. Account percentages/global recorded counts are separate
from phase tokens and exclude legacy/unmanaged capacity. Cached overview/chat
facts are historical; no background inspection or assistant budget action. Keep
foreign workspace/native identities and proof content out of the projection.

WSP-05E adds exact-run owner-reviewed retention delegation. See
docs/DELEGATED-RETENTION.md. This supersedes explicit-owner-per-archive requirements
only for the designated brain's policy-bound accepted standard local root tasks.
No policy means no delegation; phase task-approval authority alone is insufficient.
Review/revoke use authenticated-owner seams; WSP-05F below adds their dashboard
adapter, not brain CLI authority. Require an exact phase-delegated run, paused owner
setup, explicit cleanup acknowledgment, accepted measured preservation, age and
attempt limits. Each request
consumes an immutable per-worker slot and exact-run allowance; cancellation,
revocation, supersession or uncertainty never resets it or allows an owner-actor
fallback. Recheck policy at prepare/check while preserving the existing one-shot
native boundary, fresh root-only safety evidence and all Pause/maintenance gates.
Historical/late outcomes remain recordable after revocation without another permit.
No token/ownership release, acceptance promotion, native call, retry, cleanup,
rollout or Actions follows. Quiesce older writers before separately authorized
installation; descendant/output preservation and host qualification remain.

WSP-05F adds selected-workspace owner retention inspection and signed review/revoke
controls. See docs/RETENTION-CONTROLS.md. Require scoped authentication/CSRF, exact
revision/context/run/policy/ledger identity, a same-session five-minute preview,
explicit confirmation and separate cleanup acknowledgment. Verify and commit in
one transaction; historical receipt replay never reapplies a revoked policy. Keep
inspection read-only and bounded; polling/chat receive only cached status/numeric
metadata, never proof reads, policy actions or native calls. An unavailable current
run cannot gain delegation; a retained intact policy can still be revoked. Do not
manufacture paused setup, run intent, maintenance release or Play from this page.
No rollout, live owner policy, native archive, notification, schedule or Actions
follows source delivery. All one-shot safety and accounting gates remain unchanged.
