# Version 1 record contracts

`post_disposition_maintenance_load_v1` pins the positively closed original load,
complete canceled-Play disposition and exact unknown planning-refusal lineage,
same issued host/candidate binding, source/interpreter and one metadata-only
scope. Its fixed external journal is keyed to the original ledger identity,
brain and Play, never source, review ID or host. Intent/load claim, acknowledgement,
policy/current-tracker observation, failure and closure stay separate. A consumed
or partial claim cannot retry or migrate, and fences competing old-phase planning.
Status is historical and file-only. No old record, usage, expiry, receipt or safety
unknown is rewritten. See [the maintenance contract](POST-DISPOSITION-MAINTENANCE-LOAD.md).

The separate `same_project_forward_planning_v3` review binds the original
version-2 request, complete canonical journal/mailbox pins, positive closed
preflight-stage record (or allowlisted frozen legacy implementation), both usage
baselines and unchanged identity/bindings. Its new fixed successor journal and
original continuous-owner slot cannot be rearmed or chained. One exact combined
review retains subscription, handoff, actual usage and explicit new receipt/
proposal facts; predecessor outcome and terminal safety remain unknown.
Diagnostic observation is non-authorizing and creates no execution claim. See
[SAME-PROJECT-LIFECYCLE.md](SAME-PROJECT-LIFECYCLE.md).

The separate `continuous_connection_handoff_v1` review and external canonical
journal retain one original foreground subscription. Its immutable ready pin,
process birth and nonce bind `continuous_planning_authorization_v1` to a separate
exact planning confirmation. A single-use process-local handoff reuses that
connection without resubscription, load or reconnect. The existing prospective
planning journal/usage/receipt/proposal remains canonical and unchanged in meaning;
partial or consumed attempts cannot switch versions or directories to retry.
File-only status and non-authorizing blocker assessments never claim current
connection health or safety. See [the handoff contract](CONTINUOUS-CONNECTION-HANDOFF.md).

The opt-in `canceled_play_forward_planning_v2` review adds the exact configured
usage source to the separately reviewed planning control. Its canonical attempt
is shared with version 1; neither can rearm a consumed original attempt. A
`prospective_registered_usage_v1` claim and record pin the original usage receipt,
new numeric observation and source/file epochs/hashes outside the frozen ledger.
No timestamp is renewed by reading. Gaps/stale/regressed evidence never permit
send; original budget/expiry and unknown safety stay unchanged. See
[FORWARD-USAGE-EVIDENCE.md](FORWARD-USAGE-EVIDENCE.md).

`canceled_play_replacement_load_v1` is a separate operator review and external
canonical journal, not an original Play receipt or schema migration. It pins
full issued-host provenance, preserved canceled attempt, separate candidate,
source and exact one-load scope. A private permanent intent/load claim precedes
one fixed metadata-only resume. Lost outcomes remain consumed; status validates
acknowledgement/observation pins without native I/O. Original rows, sidecars,
usage, claims and historical binding epochs remain intact. See
[CANCELED-PLAY-REPLACEMENT-LOAD.md](CANCELED-PLAY-REPLACEMENT-LOAD.md).

`already_loaded_subscription_v1` is a separate transport build contract with exact
native source/tree/executable pins, not a ledger command or continuation receipt.
Its one-attempt open connection requires the caller's separate durable owner
claim. No production caller or live approval route is supplied; see
[NO-RELOAD-TRANSPORT.md](NO-RELOAD-TRANSPORT.md). Native subscription acknowledgement
does not authorize a turn, change a binding or settle historical effects.

The runtime validates these contracts explicitly in `orchestrator/core.py`.
Canonical JSON is UTF-8, sorted keys, compact separators, no NaN. Its SHA-256 is
the record identity; this encoding is local to this tool, not RFC 8785 signing.
SQLite uses WAL, synchronous FULL and BEGIN IMMEDIATE for serialized transitions.

## Canceled Play owner disposition

The separate [canceled-Play disposition](CANCELED-PLAY-DISPOSITION.md) uses
`canceled_play_disposition_v1`, not a run-control receipt. Its closed exact owner
review pins the original command/run, full database fingerprints, all sidecars,
sealed original capture and original binding/dual identities. One exclusive
claim precedes one immutable `canceled_play_unqualified` snapshot, changing no
original row or timestamp. Either side fences normal writes even after partial
commit, deletion or corruption. Scope-bound review has no timer expiry. The
continuation assessment grants no native action, reload, replay, usage reset,
binding change, terminal safety or pilot acceptance.

## Prospective sandbox-safe run mailbox

[SANDBOX-SAFE-RUN-CONTROL.md](SANDBOX-SAFE-RUN-CONTROL.md) defines the closed
`standard_run_observer_v1` handoff, exact original-turn binding and bounded
sequential request/permanent claim/reply chain. An original-process-only HMAC
seal authenticates prior completed replies at the next service boundary;
interruption or unknown output fences every later call. No restart adoption,
historical attachment, permission response, reload, control replay, usage reset
or inferred terminal safety is included. Read-only CLI objects use existing
private databases with SQLite mode=ro/query_only and cannot initialize schema.

## Fresh pre-Play successor-host maintenance

[PREPLAY-SUCCESSOR-HOST.md](PREPLAY-SUCCESSOR-HOST.md) adds the explicitly
selected version-2 `public_preplay_successor_restart_v1` manifest. It retains
the same closed top-level fields as v1, but pins complete issued ancestor
intent/status/exec/fence/archive/binding records and current unchanged first-phase
scope. Its new permanent fence binds the last process PID/birth/spec hash,
not the proposed socket, source or review directory. Partial/failed/unknown
records never authorize another attempt. Historical status is file-only;
no old launch/inspection approval is converted or terminal safety inferred.

## Readiness-owned first-phase lifecycle

[READINESS-OWNED-LIFECYCLE.md](READINESS-OWNED-LIFECYCLE.md) defines the signed
`codex_readiness_start` workflow and `readiness_owned_load_v1` private review.
The canonical ledger/brain/database-identity claim precedes the new command;
exclusive load-claim, load-ack and close journals distinguish intent, native
acknowledgment and original connection closure. Its version-3 pre-Play handoff
pins the exact review hash. Historical receipt validation correlates the original
canonical claim, handoff, loaded policy, command/turn and evidence. Missing or
partial records stay unknown and consumed. No inspection claim is reused, old
request rewritten, usage reset, binding changed or terminal safety inferred.

At the browser boundary only, the signed request is exactly
`{id, contextHash, readinessStartJson}`. The last field is the canonical inner
review as text so JavaScript cannot round nanosecond private file identities.
Decode only after the outer signature/session/project checks; reject duplicate
keys, non-finite values, noncanonical text, extra fields and mismatched IDs or
contexts. Store the original inner object under `payload.readinessStart`, with
its original hash and integer epochs. This changes no command/claim/handoff
schema or one-shot allowance and provides no old-preview migration or replay.

## One-shot pre-Play inspection load

[PREPLAY-INSPECTION-LOAD.md](PREPLAY-INSPECTION-LOAD.md) defines private
`public_preplay_inspection_load_v1` reviews. They pin clean source, original
fresh restart/exec claim, exact current binding/process/socket, dual project IDs,
first mission, original receipt/disposition and complete registry/ledger proofs.
The canonical ledger/brain/database-identity claim precedes the private intent
and load claim; another review directory or endpoint cannot mint a second load.
The original foreground connection has a separately reviewed, non-renewable
observation window. Missing closure or load acknowledgment stays unknown.
Read-only reconciliation never loads or repairs it. Observations are not old
catalog receipts, usage, terminal cleanup, a checkpoint, Play or pilot acceptance.

## Fresh pre-Play public host restart

[PUBLIC-PREPLAY-HOST-RESTART.md](PUBLIC-PREPLAY-HOST-RESTART.md) defines the
operator-only `public_preplay_home_restart_v1` manifest, source/scope/backup/file
epoch pins, separate metadata-only credential epoch, canonical predecessor fence
and exclusive intent/exec claim. These are private launch-maintenance records,
not native receipts, readiness evidence or installed bindings. Historical status
does not probe or retry the host. Unknown current/historical terminal safety,
original request outcomes and old usage/claims stay unchanged.

## Canceled readiness disposition

[READINESS-DISPOSITION.md](READINESS-DISPOSITION.md) defines the separate
`standard_readiness_disposition_v1` owner snapshot, not a brain command receipt.
It retains the complete original queued command and a hash-bound exact review,
source/mission/catalog/binding/database pins, local exclusive claim pin and dated
`canceled_readiness_unqualified` outcome. Original request and notification bytes
are immutable; raw `queued` and effective `disposed_unqualified` are distinct.
Core transaction guards validate the claim/snapshot/original command before and
after writes. A partial or changed record fences writes; no automatic reapply,
native effect, policy grant, terminal-safety assertion or Play follows. Future
catalog readiness needs a separately requested distinct command and real receipt.

## Pre-Play catalog observer receipt

The separately documented [public-host variant](PUBLIC-HOST-READINESS.md) uses
handoff version 2 with the same original-observer transport. It adds the backend
contract hash and permanent `capabilities-claim`/`capabilities` sidecars before
turn/start. `nativePublicReadinessProfile` records loaded-only identity rather
than a resume acknowledgement; `nativePublicReadinessHash` protects the capture.
The designated brain's closed `public_catalog_ack` names only its exact request
and evidence hash. The existing atomic catalog receipt retains `publicReadiness`
and the original native observation time. No desktop schema, arbitrary model
list, late/backfilled capture or interrupted claim can substitute. These records
establish neither model entitlement, execution, cleanup nor pilot acceptance.

See [PREPLAY-READINESS.md](PREPLAY-READINESS.md). A future first-phase schema-1
`standard_catalog_refresh` notification may retain `preplayCatalog` version 1,
transport `preplay_catalog_observer_v1`, and `handoffHash` before turn/start.
Private checkout-local request/claim/reply files pin the original handoff and
closed brain-authored catalog/error. The existing observer atomically commits
the normal catalog/error receipt plus `preplayReceipt` (request/handoff hashes,
brain/turn IDs and binding hash). It grants no reusable controller, native
permission, execution or terminal-safety authority. Legacy requests are never
backfilled, interrupted claims never replayed, and reply files never authorize
Play independently of the actual ledger receipt.

## Disjoint successor lineage

See [SAFE-SUCCESSOR.md](SAFE-SUCCESSOR.md). A separately owner-reviewed
`standard_successor_v1` request pins a valid immutable quarantined predecessor,
its preserved run/usage/expiry and repository identities, and one existing
disjoint target's metadata/DB/registry/mission/binding file epoch. It has no timer
expiry and no Play/native/release authority. Exclusive target and registry
outgoing claims precede one target snapshot and schema-v7 pointer; incomplete
claims remain fenced, never auto-repaired or replayed. No source ledger changes.

The target's separate signed fresh Play includes `successorHash` and the closed
`successorBoundary`; the new run and owner receipt retain that same lineage.
Already-loaded-only delivery records `nativeLoadedProfile` using
`successor_loaded_only_v1`, then independently reported native policy tied to the
one new command/turn. It records no resume acknowledgment. Explicit owned-host
inspection returns version 2 with `loadedProfile`; older resume/report schemas
stay unchanged. Current loaded metadata and item lifecycle evidence never
establish historical cleanup, terminal safety or pilot acceptance.

## Public native standard task transport

See [PUBLIC-NATIVE-TASK-ADAPTER.md](PUBLIC-NATIVE-TASK-ADAPTER.md). A future exact
notification may retain `nativeTaskContract` for the separately reviewed public
backend. A task's closed `publicNative` record binds its immutable seed, command,
host binding and source-base commit/tree/layout to separate permanent creation
and first-turn claims. Returned native UUIDs, reply hashes, stage and original
observation time remain distinct from task completion and tracked terminals.
Private request/collector/reply sidecars never include a socket, prompt or token.
Unknown delivery cannot use desktop fallback or supplied idle to settle ownership.
Migration assessments grant no new authority and change no old records.

## Application-owned public host

See [PUBLIC-HOST-RUNTIME.md](PUBLIC-HOST-RUNTIME.md). The separate schema-1
`public_app_server_host_v1` manifest pins the closed monolithic package and
source bundle, exact checkout/home/socket-directory identities, fixed config
file epoch, restricted native policy and unconfigured credential mode. Its
owner review hash binds profile, exec mode and the manifest hash. An exclusive
private intent and exec claim permanently consume that launch attempt.
Historical status permits only issued/failed/unknown exec, with host-ready,
native qualification, binding and restart false and terminal safety unknown.
No ledger schema, original Play, usage, native observer or run is migrated.

The separately named [existing-home restart](PUBLIC-HOST-RESTART.md) pins the
completed transfer/predecessor chain, full private native-home snapshot,
verified opaque backup, current implementation tree, new socket-directory
identity and unchanged registered standard scope. A canonical per-predecessor
sidecar fences all review-directory alternatives before one exec. Its issued
record includes PID/birth epoch, with readiness false and terminal safety
unknown. Read-only connectivity records remain separate from candidate binding
installation, authentication/model access, receipts and phase authority. No
database schema or old control bytes are changed.

The separate [public pilot inspection](PUBLIC-PILOT-INSPECTION.md) specification
pins its clean implementation, original transfer/run/Play, issued live process,
current binding/socket, native pre-observation and a fixed load-or-observe action.
Its exact owner review is valid until scope drift. Exclusive intent, canonical
original-run/Play fence and optional inspection-load claim are private sidecars,
not a new ledger schema or old receipt. Append-only observations retain actual
current policy and tracked terminals; an uncertain load remains unacknowledged
after later read-only reconciliation. Historical safety, migration, Resume,
closeout and pilot acceptance remain unknown/false respectively.

Future `public_pilot_inspection_subscription_v2` manifests add only the closed
`subscription: {protocol: foreground_connection_v1, maximumSeconds: 15..300}`
field. The original-run/Play canonical fence is identical across versions; no
v1 claim is migrated or renewed. Exclusive `subscription-open.json` and
`subscription-close.json` sidecars bind the same spec/connection UUID and record
foreground ownership, maximum lifetime and historical closure outcome.
Append-only observations retain that owner identity. A missing close record is
`unknown_not_reconnectable`, not evidence of an active subscriber. No ledger
schema, run/control, usage, expiry or current/historical terminal assertion is
rewritten; ending a connection is not native process cleanup.

## Portfolio

`schemaVersion: 1`, `brainId`, `repositories[]`. Each repository has exactly:
`id`, `path` (absolute local path or null), `projectId` (verified native ID or null),
`ref`, `mergePolicy` (`manual` or `required_checks`), `policyProfile` (`standard` or
`harness`). Configuration stays private. Adding a repo requires user scope approval;
the initializer is not a discovery or authorization tool.

Changing path/projectId/ref invalidates pending approvals and preflights; an
active worker blocks that change. Policy and brain changes still require explicit
migration. Read-only readiness observations cannot edit these bindings.

## Inheritance seed

Exact fields: `schemaVersion`, `repository`, `policyProfile`, `packetId`,
`packetDigest`, `packetPath`, `catalogCommit`, `baseSHA`, `branch`, `objective`,
`rationale`, `allowedPaths`, `contracts`, `predecessors`, `locks`, `execution`,
`acceptance`, `stopConditions`, `completionAxes`.

All source paths are repository-relative. Packet and locks use SHA-256; base and
catalog use full Git commits. Branch starts with `codex/`. Each predecessor has
repository, packetId, axis, evidenceSHA256, reference. Each lock has path, sha256.

Execution has wrapperArgv, prefetchCommands, offlineAcceptanceCommands (all direct
argv arrays), and isolation. Harness requires OS_ENFORCED_DENY_ALL_OUTBOUND;
standard uses REPOSITORY_POLICY. The helper never executes those arrays.

Minimum completion axes are source/ci, plus merge for required-checks policy.
Additional required axes can be selected but not removed after approval. Seed
changes invalidate approval; a seed cannot replace a packet already owning a task.

## Queue and dispatch

Queue identity is `repository:packetId`, unique even when digest or base changes.
Approval records the user action, time, seed hash and packet digest. Preflight
records explicit checks/evidence and expires after 300 seconds.

Worker states: reserved → starting → running → awaiting_acceptance → accepting →
verifying → complete. Blocked is recoverable but retains ownership. Starting is
uncertain until native identity is resolved; it must never auto-retry creation.
Client IDs are distinct from task IDs. There is no automatic ownership expiry.

## Control request

See [the machine-readable control schema](../schemas/control-request.schema.json).
Exactly `id`, `kind`, `expectedRevision`, `payload`. Reusing an ID with identical
content returns the previous result; changing its content is refused. A stale
revision refuses the action before any mutation.

Kinds and payloads:

| Kind | Payload |
|---|---|
| approve | queueId, seedHash, packetDigest |
| hold | queueId, held boolean |
| prioritize | queueId, priority integer 0–999 |
| pause / resume / reconcile | empty object |
| brain_stop / brain_resume | empty object; cooperative lifecycle, no worker dispatch grant |
| checkpoint / archive | workerId |
| listening | enabled boolean; native scheduling and dispatch remain separate |
| decision_response | decisionId, decisionHash, optionId, note, confirmed=true |

Only typed controls are accepted. There is no shell, prompt-execution, filesystem
write, repository-delete or native-tool proxy endpoint. The HTTP layer cannot
acquire the controller token, prepare packets, preflight, dispatch or certify work.

## Versioned design decisions

For `decision_response`, `optionId: null` denotes a standalone nonblank free-text
answer in `note`. A non-null ID must match a published option. The response stores
the exact text and a server-derived `answerKind`; existing option responses without
that additive field remain readable. Neither answer type grants execution authority.

The additive `decisions` table stores immutable version-bound questions with
mutable receipt/outcome state. Matching `snapshots` retain the original question
document. `meta.decisionListener` is an explicit owner preference (absent=false);
`inboxCheckedAt` and heartbeat `observedAt` are observations, not dispatch grants.
No existing packet/worker records or approvals are migrated. See
[decision contract and recovery](DECISIONS.md).

Dashboard response and allowlisted pending control commands may have an additive `notification` record for the
one-shot native wake attempt. `accepted` means the CLI acknowledged queueing;
only designated-brain `process` marks receipt, and artifact-bound resolution
marks the outcome. Legacy commands need no migration. Notification state is
not part of the original request fingerprint and never changes its answer.

`meta.brainControl` retains desired state, phase, commandId, requestedAt and the
last checkpoint. Legacy absence means running/ready. Exact schema and safety
gates are documented in [Brain control](BRAIN_CONTROL.md). Brain checkpoint
documents use the existing immutable snapshots table; no ownership is released
by saving a stop intent or checkpoint.

## Completion envelope

Exactly `schemaVersion`, `seedHash`, `commit`, `changedPaths`, `pr`, `evidence`,
`preserved`, `reviewReference`. Evidence has all eight axes: source, ci, merge,
artifact, deployment, runtime, assurance, tenant. Each has status (`verified`,
`unverified`, `not_applicable`, `failed`) and reference. Verified requires a
reference; every contract-required axis must be verified. The brain separately
checks that the evidence is authentic, fresh and bound to the exact result.

Archive is allowed only for complete, preserved work, followed by native inactive
state verification. No automatic deletion API is provided.

## HTTP

Assistant workflow previews (`POST /api/assistant/preview` or an inference action)
are transient signed documents bound to one browser session, ledger, project and
brain. `/api/assistant/confirm` delegates mission review to the existing mission
request journal, standard controls to their existing signed request, and preparation
or verbatim brain instructions to the existing conversation command. The response
labels the workflow and wraps that adapter's retained result. Replaying its ID
recovers the original receipt and never issues a second notification. Explicit
usage refresh binds the current run and records a `standard_usage_request` receipt
atomically with the existing measurement, so an uncertain reply cannot erase known
consumption or turn missing counters into complete coverage. No separate
assistant execution ledger or task scheduler is added. See
[assistant-led workflow](ASSISTANT-LED-WORKFLOW.md).

`GET /api/workspaces/<id>/assistant/help` is an authenticated read-only projection
and optional signed preparation preview. The visible Help button confirms only
that fixed bounded instruction through the normal conversation adapter. No new
execution ledger exists: its command receipt, notification, received time and
reply remain the durable progress records. The reserved preparation/follow-up
message prefixes correlate this run's history; they grant no authority. An older
phase's reply cannot supply the current phase's next action. Polls never confirm
controls, refresh usage or send notifications.

Static: GET `/`, `/app.js`, `/style.css`. Auth: POST `/api/login`, GET `/api/session`.
Authenticated reads: GET `/api/state`, `/api/documents/<sha256>`, `/api/export`.
Mutation: POST `/api/commands` with exact origin, authenticated cookie and CSRF token.
All state includes a ledger revision and server timestamp. `/api/state` exposes the
latest 100 audit events and full-history derived delivery totals. Snapshot reads
do not change revision and never disclose controller tokens.

## Ended-Pause receipt/checkpoint recovery

The separately signed `standard_pause_receipt_recovery` records one ended-Pause
receipt/checkpoint attempt under `standardRun.pauseReceiptRecovery`. Its payload
pins the original Pause fingerprint/notification, scope hash, run/phase/brain,
unchanged binding and repeated completed-turn metadata. The new notification
retains `receiptRecoveryObservation` only after loaded-idle, known-empty current
tracked-terminal checks; unloaded coverage stays null/unknown. Receiving changes
only the original Pause status/receipt, never its notification. The recovery
checkpoint explicitly retains unknown historical effects/terminals and incomplete
task-tree coverage, preserving every usage field and original expiry. No second
attempt, effect settlement or qualification follows. See
[ended-Pause receipt recovery](ENDED-PAUSE-RECEIPT-RECOVERY.md).

An ended recovery without its receipt/checkpoint is projected as blocked from
retained native turn/observer metadata only. The projection writes nothing and
never infers idle, terminal cleanup or replay authority. New private operator
host intents require schema 2 and a complete runtime-package integrity pin;
legacy launch records remain historical, not fresh launch authority. See
[runtime preflight](HOST-RUNTIME-PREFLIGHT.md). The separately documented
[continuation proposal](ENDED-RECOVERY-CONTINUATION-PROPOSAL.md) is not an
executable control or a second recovery attempt.

## Cooperative exact-PR merge records

Optional reviewed authority `mergeMode` defaults to `manual`; `brain_exact_pr_v1`
requires standard phase delegation and the existing checks-based repository policy.
Standard result evidence may add an exact `headSHA`. Merge binding, source,
observation and delivery receipt snapshots are content-addressed and immutable;
`standardRun.merges` projects their current state and original observation time.
Source records additionally pin `localBinding` (common-directory key, layout hash,
canonical origin), revalidated after remote I/O. Observation reports retain
`policyBindings`, `checkBindings` and effective `queue` metadata/hashes rather than
raw GitHub bodies. Missing/unsupported coverage remains a refusal. The emitted
one-shot effect uses the synchronous SHA-bound REST merge endpoint via `gh api`;
no queue, auto-merge or asynchronous fallback is allowed.
One run consumes one immutable PR/request slot. Issued/uncertain journals retain
ownership without another argv or automatic retry. See [STANDARD-MERGE.md](STANDARD-MERGE.md)
for fields, evidence bounds, absence handling and launcher rollout prerequisites.

## Cooperative registered-native-task observation

`standard_native_observation_v1` is an immutable, content-addressed snapshot for
one exact registered standard run and reviewed owned-host binding. Its request
has exactly `id`, `runId`, `expectedRevision`, `contextHash`, `bindingHash`; a
`standard_native_observation_v1_request` snapshot retains the request hash,
report hash, run ID and original retention time. Identical replay reads only that
historical receipt; it never reconnects to the host or refreshes evidence clocks.

Reports retain workspace/brain/run identity, binding/context hashes, collection
times, bounded registered-task samples, redacted source hashes and explicit gaps.
A pending native identity, unavailable status or incomplete terminal pagination
has unknown activity/terminals and a null count, never zero. Confirmed task status
is sampled around the complete bounded terminal listing and repeated; disagreement
invalidates the sample. Local authority and catalog/binding context are rechecked
after native I/O before one atomic retention transaction.

The run/task pointers `nativeObservationHash` bind saved task observations to that
report. A later caller-supplied observation clears the task pointer rather than
inheriting measured provenance. Finish validates a referenced report's exact task,
run, brain, workspace and original observation time in addition to its existing
result and inactivity checks. Projection reads expose saved metadata only.

This collector observes registered standard tasks and tracked terminals, not a
complete native descendant inventory or process cleanup. It measures no tokens,
releases no ownership and authorizes no execution. It cannot satisfy a legacy
Brain Stop or strict Harness gate. See [the pilot and collector guide](STANDARD-OWNED-HOST-PILOT.md).

## Owner closeout of an expired empty standard phase

The signed `phase_close` adapter retains a completed local `standard_closeout`
command with its exact request hash and run ID. `standardRun.ownerCloseout`
contains the request ID, owner closeout time, blocked/unqualified outcome,
verbatim previous checkpoint, recovery/reply bindings and bounded ended-turn
metadata. The new checkpoint records expiry without replacing historical
usage, gaps, native-effect records or the prior checkpoint's observation time.
Run and audit revisions advance normally; no counter epoch is reset.

Only an expired, empty paused standard run with the exact recovery receipt,
reply and stable ended native turn is eligible. This command has no native
notification, settlement, permission-relay or pilot-acceptance meaning. Exact
receipt replay never repeats collection or changes a newer run. Help then uses
the existing separately confirmed conversation request to prepare a successor;
Review and Play remain separate. See [expired-phase closeout](EXPIRED-PHASE-CLOSEOUT.md).

## Owned native connection loss

The separately owner-confirmed `notification.turnRecovery` journal records the
exact original command/turn, signed review hash, unchanged binding hash, private
controller/context hashes, claim time, cancellation delivery (`unknown`,
`acknowledged`, `not_needed`) and status (`awaiting_end`, `controller_recovered`).
Repeated metadata observations retain exact turn/activity and original query time,
with `effectOutcome: unknown` and `taskTreeComplete: false`. The raw controller,
prompt and native response bodies are never exposed. The original notification
is not rewritten as successful recovery. An identical confirmation is a receipt
replay; later explicit checks never resend the cancellation. Recovering the exact
abandoned controller leaves the run stopping, dispatch paused, deadline/usage/gaps
preserved and checkpoint absent unless independently retained. See
[orphaned-turn recovery](ORPHANED-TURN-RECOVERY.md); it grants no phase success.
An ended-turn-only replacement review additionally retains both complete private
bindings, original binding hash and reviewed original-PID/launch-claim provenance
under `hostContinuity` and `retiredHost`. It never rewrites the original
notification/profile or migrates a consumed claim. Native delivery is
`not_needed`; loaded-idle/terminal evidence and conditional controller recovery
remain distinct from effect settlement, checkpoint retention and acceptance.

The explicit replacement-only `load_for_inspection_then_reconcile` review adds
`inspectionLoad`: a consumed `claimed`/`issued`/`acknowledged` journal, requested
restricted policy, the original unloaded observation, separately reported resume
profile and `historicalTerminalCoverage: unknown`. Its native delivery may be
`inspection_load_acknowledged`; that is not terminal proof. Unloaded observations
use `trackedTerminals: null` and `terminalCoverage: unknown`, not zero. Subsequent
fresh known-empty reads use `observed_current_host`, without promoting historical
effects or tree coverage. No automatic load or another consumed attempt exists.

The signed `controllerCredential` fingerprint pins only device/inode/owner/mode,
size and byte hash, never token contents. After independently checked inactivity,
`controllerCredentialRetirement` retains the exact private archive receipt or
explicit `not_present` fact. Exclusive linking preserves bytes across interruption;
only the exact consumed recovery may finish that retirement. Arbitrary stale files
or archives never become permission to clear ownership or overwrite credentials.
Private archives remain outside source, transcripts and inference history.

Future owned notifications may add `nativePermissionObservation` with
`version: 1`, `turnId`, `requestHash`, supported approval `method`,
`observedAt`, `expiresAt`, `endedAt` and a closed `reason` enum. Unbound
or unsupported requests may instead retain `nativeAttention` with
`version: 1`, exact owned `turnId`, `observedAt` and a closed `reason`.
These are lifecycle diagnostics, not a prompt, response claim, native result or
effect reconciliation. Raw native command/reason/path/item text is never stored
in either record. Existing records without a cause remain unknown. Owner reads
do not add these observations or refresh their original times.

A saved notification may retain `nativeTurnStatus: connection_lost` and
`nativeConnectionLoss` with exactly `reason`, `observedAt`, `outcome: unknown`,
and `replayed: false`. Reasons are bounded transport categories:
`endpoint_changed`, `heartbeat_missing`, `proxy_unavailable` or
`websocket_closed`. No native error text, socket path or transcript is retained.
The original notification acknowledgment and command receipt are independent;
loss neither fabricates a brain receipt nor erases an existing receipt.

The thread observation finishes `unconfirmed` with incomplete coverage. Its
original events/times remain; an ended observer does not prove the native turn
or effects ended, release ownership, restore usage coverage or authorize replay.
State reads expose this retained record without reconnecting or renewing it.
See [disconnect lifecycle](HOST-DISCONNECT-ROOT-CAUSE.md).

## Separate recovery of a pre-turn failed standard Pause

The signed `standard_pause_recovery` command and `standardRun.pauseRecovery`
journal retain one checkpoint-only attempt for an exact empty stopping phase.
The original Pause payload, failed notification and its original observation
times remain unchanged. Its separate receipt may become completed; native
delivery, recovery receipt and paused checkpoint remain distinct records.
`scopeHash` pins run limits, usage, expiry and task/effect scope, while
`notificationHash` pins the original failed claim. Metadata-only latest-turn
checks remain explicitly not effect reconciliation.

No retry, Resume, phase completion, usage-gap clearance or pilot acceptance is
inferred. Failed/uncertain recovery remains owned and never arms a second wake.
Reads do not connect or renew evidence. See [failed-Pause recovery](FAILED-PAUSE-RECOVERY.md)
for exact eligibility, owner review, designated-brain procedure and source-only
rollout boundaries.

## Metadata-only owned resume

Owned wake requests use the installed public `thread/resume` parameter
`excludeTurns: true`. The response must omit `turns` or contain an empty array;
private history is neither needed nor retained. An unsupported flag or malformed
response preserves the failed one-shot notification and its closed stage record,
without another resume, full-history fallback or turn start. This protocol fix
does not repair historical claims, create another recovery permit, change the
host binding or clear usage gaps. Source tests are not live qualification.

## Sandbox-safe host evidence and brain allowance correction

New owned notifications pin `hostInspectionTransport: owned_observer_v1`.
One private controller/context-bound request, durable collector claim and
immutable reply retain fixed read-only host metadata. No request means no
collection; timeout/interruption never grants direct socket access or a resend.
The observed timestamp remains the original query time. See
[host evidence](STANDARD-HOST-EVIDENCE.md).

The signed local `standard_brain_budget` command retains its exact owner preview
hash and `standardRun.budgetReviews` old/new allowance entry. It is completed
locally, never notifiable, and leaves the phase paused. Original Play/review
receipts, mission/total/reserve/task limits, expiry, checkpoint and all usage/gaps
remain intact. Replaying its receipt never applies an older amount. See
[brain allowance correction](STANDARD-BRAIN-BUDGET.md). Source, installation,
owner reallocation, Resume and live pilot acceptance remain separate.

## Owner-only exhausted-recovery inspection

`standard_ended_recovery_record` is a completed **local owner record**, never a
brain receipt or notification. Its `payload` pins `runId`, `recoveryId`,
`requestHash` and private `recordHash`. One ledger transaction retains the full
original Pause, exhausted recovery, unchanged run/usage/gaps/expiry, exact signed
request and repeated metadata evidence in that hash-addressed snapshot. Receipt
replay verifies the snapshot bytes without collecting or refreshing evidence.

Its outcome stays `blocked`, qualification `unqualified`, historical terminal
coverage/effect outcome `unknown` and task-tree completeness `false`. Neither
current empty tracked terminals nor this receipt is safe-checkpoint or closeout
evidence. The original requests remain untouched and unresolved. See
[owner inspection record](ENDED-RECOVERY-RECORD.md).

## Separate historical reconciliation and terminal closeout

`standard_historical_effects` records private bounded native-history/local-inventory
hashes, exact repeated observations, all original commands and the unchanged run.
Unknown effects stay blocked. `standard_terminal_closeout` requires the exact prior
reconciliation and independently known non-execution plus fresh known-empty current
terminals. Its separate atomic owner receipt closes only as blocked/unqualified,
without replacing the previous checkpoint or any original receipt, usage or expiry.
Both are local-completed, idempotent and non-notifiable. The immutable validated
`historicalEffectClosures` sidecar distinguishes original queued requests from future
pending work; it never fabricates a brain receipt or permits another send.
See [historical evidence and closeout](HISTORICAL-EFFECT-CLOSEOUT.md). Executed-effect
cleanup, live installation and pilot acceptance remain outside this source adapter.

New version-2 historical reports retain stable persisted-item entry hashes,
same-turn saved call-result hashes, typed completion linkage and per-effect
`missingEvidence` requirements. Optional signed `hostChain` pins all retired
request bindings and their exact private launch-artifact provenance; it never
selects an old connection or grants a recovery permit. Older version-1 receipts
stay immutable. Interrupted pagination cannot discard already observed pages,
and missing results or historical cleanup stay unknown rather than permitting
closeout. No usage, observer status or receipt is rewritten by this evidence path.

Historical previews now retain the complete report only in the signed request,
not again in preview details. The rendered missing-evidence list reads that
same report (older preview projections remain readable). This corrects real
multi-host review envelopes that exceeded the authenticated request bound through
duplication; it neither drops requirements nor expands the bound. Source-only
delivery does not submit a historical record, settle effects, reset usage, send
another native request or qualify the pilot.

## Read-only cleanup qualification output

The separate `independent_historical_effect_evidence_v1` operator report embeds
the unchanged cleanup collection plus original capture availability and exact
positive result linkage. `nativeEffectCapture` on future owned standard sends
anchors an exclusive hash-only item journal before turn/start and seals its
original file/chain/turn. It is not a brain receipt, complete inventory, process
cleanup record or execution-disposition grant. Old absent/unsealed captures
remain unavailable/incomplete; imports cannot backfill them. See
[independent original-effect evidence](INDEPENDENT-HISTORICAL-EVIDENCE.md).


`historical_cleanup_collection_v1` is private operator output, not a new ledger
command, signed authority or settlement proof. Its closed read-scope plan pins
original command/run/context, exact revision, scope, binding and host-chain hashes.
The output retains original collection times, hashed source observations,
unchanged historical evidence, repeated current tracker facts and per-effect
missing lifecycle/cleanup requirements. It accepts no caller attestation flags.
The documented source cannot qualify complete historical cleanup. All mutation,
cleanup verification, ownership release, execution and pilot flags remain false.
No schema migration or consumer promotes the report into a receipt or closeout.
See [collector contract and qualification](CLEANUP-COLLECTOR.md).

## Ended-recovery device review receipt

`workspace_device_ended_recovery_v1` is a distinct registry identity-repair
document/receipt, not a ledger command or native receipt. It retains the exact
run and Play/Pause/consumed-recovery hashes, immutable original binding file epoch,
both native project IDs, unchanged full ledger/reference and registry checksums,
and explicit retained-only/unknown native evidence. The confirmed transaction
changes only selected device pins and journals its verified private backups.
No original ledger bytes/records, usage/gaps, expiry, ownership or native effect
claim is rewritten. Receipt replay returns the original immutable result without
repinning a later device. Default and pending-Play repair documents remain separate.
See [the device-only contract](ENDED-RECOVERY-DEVICE-REVIEW.md).

## Loaded-policy evidence adapter (2026-10-14)

The opt-in `loaded_thread_policy_v1` binding identifies the exact reviewed native
source/build contract. An explicit workspace-authenticated dashboard check
repeats project/thread metadata and native effective-policy reads without loading,
waking, writing ledger proof or authorizing continuation. Only cached closed
diagnostics enter state polling; unloaded/unsupported/contrary/drifting evidence
stays unknown. A later failure cannot fall back to an older positive check.

Future one-shot owned deliveries retain actual policy evidence separately from
the original v1 resume acknowledgement, before turn start. The record binds the
exact brain/command/turn, binding, executable/source hashes and observation time.
Only supported matching future evidence satisfies the policy prerequisite; an
old v1 Play is never backfilled. The existing sandbox-safe brain handoff repeats
the fixed read and preserves the native-effect inventory gap and all authority,
terminal-cleanup, usage and ownership boundaries.

The repaired compiled CLI passed the adapter's isolated four-read fixture, with
no model turn, live connection or live native write. Rendered 1440px and 320px
disposable checks kept unknown policy visible, exposed no Resume and produced
no phase-control submission or horizontal overflow. These are source/fixture
results, not live native-tool trust, runtime installation or pilot acceptance.
An exact new socket binding still requires actual reviewed launch provenance,
socket epoch and initialization identity; a pre-launch scope packet is not a
binding or activation approval. See [the adapter contract](NATIVE-POLICY-EVIDENCE-ADAPTER.md).

## Exact public identity transfer — 2026-10-14

The separate `public_identity_transfer_v1` operator contract snapshots one
complete self-contained registered brain history from the unchanged original
accepted Play's reviewed host. Require its received command, exact latest ended
turn and closed owned observation; unconfirmed delivery/observers are not a
transfer permit. A separately reviewed application-owned destination must keep
the same workspace, checkout, brain and both project IDs, while independently
reporting empty native catalogs and the fixed no-credential restricted config.

The native source-build extension restores actual observed project metadata
through the empty local store's transaction, not stock import or operator SQL.
Public path resume inspection-loads only a complete copied history, then the
native metadata assignment retains its original membership. Private source/file/
context/build pins, until-scope-changes owner review and separately fsynced stage
claims precede the three fixed native writes. A canonical original-run/Play-ID
sidecar prevents another attempt through a new directory, review, late original
metadata observation or replacement endpoint. Complete JSONL publication is
atomic; no native reader sees its partially written prefix.

The local result is metadata transfer, not a brain receipt, checkpoint, current
health, historical cleanup, binding cutover, original policy-guard release, Resume
or pilot acceptance. Original databases/commands/usage/gaps/expiry remain unchanged;
source and historical terminal safety stays unknown. Partial/interrupted claims
remain consumed and file-only status never reconnects, refreshes or retries.
See [the transfer contract](PUBLIC-IDENTITY-TRANSFER.md) and
[native source delivery](../native-runtime/README.md).

## Safe shared-home single-brain export — 2026-10-14

The separately named `shared_codex_exact_brain_export_v1` collector reads only
one exact native-returned brain rollout from the current OS user's shared
Codex home. It never enumerates/copies the home, reads credentials/plugins/native
stores/sibling histories, changes original permissions or emits a native write.
Repeated metadata, complete history/byte/file/directory pins and original paused
run/Play context precede a disjoint private archive. Partial retention remains
unknown and is never overwritten. Status is historical and file-only.

Only an explicit new export-pinned version-2 transfer specification may use that
archive, with fresh original source rereads at every unchanged native claim
boundary. The v1 private-source gate, native build/owner review, original-run/Play
permanent fence and separate restoration/load/membership claims remain intact.
Export cannot grant a launch/binding, historical cleanup, policy proof, receipt,
checkpoint, Resume, clock extension, usage reset or pilot acceptance.

The source passed 2,583 Python tests (one optional skip), 31 new focused tests,
36 JavaScript suites, syntax/AST/diff checks and disposable desktop/mobile checks.
Actual compiled legacy/paginated shared fixtures used only loopback source receipts,
with zero transfer turns/model requests and no live/cloud writes. Explicit owner
qualification also retained the original pilot's exact single-brain archive,
preserving both complete private databases and all original usage/expiry/receipts.
The expired run, unverified original policy and terminal unknowns remain fenced.
No runtime launch, native transfer, dashboard installation or live control follows
this source delivery. See [SHARED-BRAIN-EXPORT.md](SHARED-BRAIN-EXPORT.md).
