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
pilot acceptance. A failed/uncertain recovery stays owned; no second attempt is
offered for the original Pause.

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

Run full local Python discovery, all JavaScript suites, syntax and diff checks.
No GitHub Actions or paid service. Quiesce older writers and back up private state
before separately authorized installation. Installing source must not confirm a
preview, notify a brain, change the host binding, reset credentials or replay the
failed Pause. Live checkpoint recovery and native approval qualification remain
separate and must be reported from actual receipts, not fixture success.
