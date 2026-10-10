# Version 1 record contracts

The runtime validates these contracts explicitly in `orchestrator/core.py`.
Canonical JSON is UTF-8, sorted keys, compact separators, no NaN. Its SHA-256 is
the record identity; this encoding is local to this tool, not RFC 8785 signing.
SQLite uses WAL, synchronous FULL and BEGIN IMMEDIATE for serialized transitions.

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
