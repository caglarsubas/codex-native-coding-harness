# Codex Orchestrator — personal tooling

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
