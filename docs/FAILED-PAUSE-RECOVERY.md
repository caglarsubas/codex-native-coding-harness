# Recover a saved Pause that never started a turn

`standard_pause_recovery` is a separate, signed checkpoint-only owner control.
It does not clear, reset or resend the original `standard_pause` notification.
Source delivery, merge, installation and live qualification remain separate.

## Owner experience

The one-page workspace and Help offer **Recover saved Pause** when recorded
eligibility holds. This button prepares a preview; it does not send a wake.
An explicit preview request checks bounded native metadata. Normal snapshots,
Help polling and page refreshes never connect, collect evidence or notify a brain.
The owner separately confirms **confirm pause recovery** for that exact preview.
No technical prompt needs composing. Short summaries precede the bindings under
Details. Progress distinguishes recovery saved, native delivery, saved Pause
received, and paused checkpoint retained. A checkpoint is not phase success or
pilot acceptance. An uncertain recovery stays owned and is never retried. One
proved pre-turn failed recovery may offer **Review replacement checkpoint
recovery**, using the same signed control with a new, separately reviewed ID.
No technical prompt is needed; this is never automatic. If the reviewed host has
gone away, the narrow host-continuity review below is required separately from
host launch and dashboard connection review.

The preview is session/workspace/ledger/revision-bound and pins the exact run,
phase, limits, usage, expiry, brain, original Pause fingerprint and notification
hash, reviewed host binding, and latest completed native turn. Its full five-minute
review window begins after inspection. Confirmation rechecks the metadata and
commits a separate one-shot recovery journal before notification. Confirmation
replay, including after expiry, returns its original receipt without native reads
or another send. No current host binding is changed by this source path.

## Narrow eligibility

Require an unfenced registered `standard_cooperative_v1` run in **stopping**,
with dispatch paused, no controller, Brain Stop or handoff, and no tasks, workers,
packets, runner, merges, outstanding decisions or other pending requests.
Strict Harness and managed runs refuse this path. Both the shared enrollment
journal and private workspace sidecar are checked, including interrupted staging.

Require one queued unreceived Pause for that run, with the exact brain and
durable wake hash, valid attempted/finished timestamps, `unavailable` status and
no native turn/delivery/observation fields. Accept only the closed pre-turn
diagnostic (version, stage, reason, reserved RPC code and attempted flags) or the
older bridge's exact pre-turn failure outcome. Observation-marker and turn-start
stages, sending/uncertain delivery, arbitrary unavailable prose and missing
claims refuse. Loading/resuming a thread may have been attempted; this check
proves only that this notification did not start a brain turn.

On the reviewed owned connection, check exact brain/project/checkout, idle or
notLoaded activity, and the latest completed native turn twice, bracketed by
identity reads. The explicit metadata-only `thread/turns/list` reads use descending
order and `itemsView: notLoaded`. Latest reads request one row; the reused exact
turn validator requests 64 rows per page with at most four pages. Missing,
changing, failed/interrupted/active or unsupported reads refuse. Never collect
turn items, transcripts or raw errors. These reads follow the documented
[app-server turn history API](https://learn.chatgpt.com/docs/app-server).
A completed turn does not reconcile its
commands or prove absence of descendants. This path relies on the recorded
empty registered run, not a complete legacy process-tree qualification.

Keep app-catalog and app-server project identities separate. Require the exact
workspace-write/on-request/Code Mode disabled host policy and no pending native
approval. Before resume and immediately before turn/start, the existing bridge
rechecks current ledger gates and matching metadata on the **same connection**.
The final check-to-call interval is cooperative, not atomic native cancellation.
There is no desktop-queue fallback, second dispatcher or automatic reconnect.
The bridge requests `thread/resume` with `excludeTurns: true`: loading this
checkpoint turn does not require hydrating private or paginated history. A
rejected metadata-only resume remains one consumed recovery attempt, with its
failed step retained. There is no fallback to full history and installing a
compatible bridge does not re-arm that attempt.

## One separately reviewed pre-turn replacement

The owner-authorized exception permits at most **two recovery attempts total**
for the same Pause. A second attempt is available only if the first has a closed
native failure diagnostic with `turnStartAttempted: false`, `unavailable` delivery,
valid claim/timestamps and no native turn, delivery, observation or turn-status
marker. Legacy prose alone is insufficient for replacing a recovery. Sending,
accepted, uncertain, received, expired-without-proved-failure, or any attempted
turn start remains fenced. Expiry alone never authorizes another attempt.

Keep the first recovery's run, phase, scope, limits, usage/gaps, expiry, original
Pause and notification hashes unchanged. The current reviewed host and latest
completed native turn must match those bound to the first attempt, in addition
to every fresh repeated identity/activity read and pre-send fence above. Only
the exact separately signed continuity exception below permits a changed host
binding. A newer unrelated turn or a replacement brain is never interchangeable.

The exact signed replacement payload binds the previous command, notification
and permit hashes. In one owner-confirmed transaction, retain the full previous
command and permit under `pauseRecovery.priorAttempt`; give the old command a
`failed` disposition with the replacement ID/time, not a receipt or completion.
Its original payload, fingerprint, creation time and failed native claim are
unchanged. The new journal receives its own one-hour checkpoint-only permit;
the old permit is not renewed and phase duration/budgets are not extended.
Only the new exact request can receive the saved Pause. Replaying either signed
confirmation returns only its historical receipt; the old claim is never resent.
Check the retained snapshot/disposition at confirmation, both send boundaries,
receipt and checkpoint. Drift refuses and transactional interruption rolls back.

The replacement is permanently consumed even if it fails before turn start. No
third wake, ordinary-message bypass, implicit Resume or automatic retry is allowed.

### Same-brain replacement-host continuity

The owner authorized removing the circular dependency on a dead socket without
loosening native identity or retry limits. For this **one second attempt only**,
an operator may separately review/qualify a replacement host and its dashboard
connection, then start the stopped, backed-up dashboard with both:

```text
--brain-app-server-binding PRIVATE_REVIEWED_CANDIDATE.json
--pause-recovery-prior-binding PRIVATE_PRESERVED_PREVIOUS.json
```

This additional option only supplies historical evidence to the existing signed
replacement preview. It is not host launch, host-binding approval, a wake,
an automatic recovery or permission to use the previous connection. The old
file remains private, bounded and immutable, and its complete hash must match
the first failed recovery. A missing old socket or changed old executable is
not grounds to inspect or revive that obsolete endpoint.

Require exactly one brain mapping, identical in both bindings: designated brain,
workspace, native project ID, app-catalog project ID, canonical checkout and
workspace-write/on-request/Code Mode disabled policy. Only endpoint pins may
change. Require the retained catalog mapping, exact registered database identity
and canonical project root to match; names and paths alone are insufficient.
On the already reviewed candidate connection, bracket the repeated latest-ended
turn observations with metadata-only project/brain reads. The exact completed
turn, completion time, brain and native project must match the first failure.
Changing roots, active/unknown activity, a newer turn or pending native approval
refuse. No project metadata update, discovery, resume or turn/start occurs during
inspection.

The same signed replacement preview displays the old/new binding hashes and
unchanged identity/policy/turn under Details. It retains both complete bindings
and catalog/database pins in `hostContinuity`; confirmation rechecks them before
the existing transaction. At both send boundaries, repeat the candidate identity
and turn reads on the actual retained sending connection. Receipt/checkpoint
validate the retained continuity and catalog, never connect to the old host.
Historical confirmation returns only its receipt, even if the endpoint is gone.
This does not re-arm the failed attempt, change run scope/usage/expiry, enable a
third attempt, or authorize any other pending request on the replacement host.

The signed browser envelope carries both hosts' socket identity integers and
the ledger device/inode as canonical decimal strings. Nanosecond identities
exceed JavaScript's exact integer range; sending them as JSON numbers would
round the pins and invalidate an otherwise unchanged preview signature. Verify
the signature and browser/project binding before decoding these strings, and
decode before native inspection or journal retention. The private bindings,
binding hashes, continuity proof and receipts retain their exact integer pins.
Malformed or mixed identity representations fail closed; this is not a relaxed
identity check or permission to reuse a rejected preview after installation.

Source delivery does not install, launch or change either live host binding.
Host qualification, checkpoint receipt, stopped-phase closeout and the actual
native-approval pilot remain separate observed outcomes.

## Designated brain procedure

Read the source skill, `references/standard-cycle.md` and this document completely.
Inspect the exact platform/workspace inbox and `standard-state`. Verify this task
is the designated brain; do not impersonate it or clear another controller.

1. Acquire the existing standard controller. Brain Stop and newer controls win.
2. Use `standard-brain` with only this JSON shape:
   `{"operation":"pause_recovery_receive","runId":"<exact run>","requestId":"<recovery>"}`.
   Do not use generic `receive`/`process` or drain ordinary saved messages.
3. Receive only this original saved Pause. The original payload, failed native
   claim and timestamps remain unchanged; its separate brain receipt is recorded.
4. Retain a standard `checkpoint` with `outcome: paused`, concise known facts,
   unknown evidence and next safe step. No completed/blocked label or task effect
   is allowed by this recovery. `brainObservedTokens` is null unless actually
   measured; preserve all high-water usage and gaps. Known higher usage can be
   recorded through the existing monotone checkpoint field.
5. Release the controller with the retained checkpoint, then end this single turn.

The receive permit lasts one hour. Once received, late safety checkpointing may
finish without renewing delivery or development authority. Guidance allows
500,000 cooperative tokens for this one checkpoint turn, not a phase-budget
increase, provider cap or billing guarantee. The old duration and budget are
never extended. New work, ordinary messages, catalog changes, native approvals,
worker retries/continuations, source edits, settings, policy changes, merges,
Play and Resume are outside this scope. A successor still requires its own
preparation, Review and Play. A paused checkpoint alone does not resolve unknown
usage or qualify a pilot.

## Verification and rollout

`tests/test_pause_recovery.py` covers read-only polling, exact signed confirmation,
HTTP authentication/CSRF, legacy and closed diagnostic provenance, latest-turn
privacy/drift, same-connection checks and Stop race, interrupted enrollment,
foreign identity/policy, uncertainty, historical replay, dedicated receipt and
checkpoint-only scope. JavaScript tests cover next-step selection, progress and
typed confirmation. `tests/manual_pause_recovery_fixture.py` provides rendered
desktop/mobile QA; every native read and send is mocked and state is disposable.
Replacement tests additionally cover immutable failed snapshots, exact owner
binding, unchanged scope/host/turn, unknown-effect refusal, rollback, historical
replay, old-request receipt refusal and the absolute two-attempt bound.
`test_pause_host_continuity.py` additionally covers private historical binding
reads without old-endpoint inspection, signed old/new continuity, catalog/root/
brain/turn/policy drift, both send gates, retained snapshots and late receipt
validation. Actual JavaScript JSON round-trip tests include nanosecond values
above the safe integer range, exact retained binding hashes, malformed signed
wire rejection before native reads, and receipt-only historical replay.
All native responses in these tests are synthetic.
Use `PYTHONPATH=.:tests python3 tests/manual_pause_recovery_fixture.py --host-continuity`
for disposable desktop/mobile preview, confirmation and paused-checkpoint checks.
The fixture never connects to a real host or sends a real native instruction.

Lossless browser-envelope qualification (2026-10-08): the complete local Python
discovery run completed 2,109 tests with one optional Graphify test skipped;
all 31 JavaScript suites, JavaScript syntax checks and diff checks passed.
The disposable continuity fixture accepted a real browser confirmation with
unsafe-range nanosecond pins, followed its simulated receipt to an empty paused
checkpoint, and rendered that result on desktop and at 320px without horizontal
page overflow. Native reads and delivery were mocked. These checks qualify
source behavior, not installed code, live recovery or pilot acceptance.

Run full local Python discovery, all JavaScript suites, syntax and diff checks.
No GitHub Actions or paid service. Quiesce older writers and back up private state
before separately authorized installation. Installing source must not confirm a
preview, notify a brain, change the host binding, reset credentials or replay the
failed Pause. Live checkpoint recovery and native approval qualification remain
separate and must be reported from actual receipts, not fixture success.
