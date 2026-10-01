# Recover a received request without replay

`brain_reply_recovery` is a separate pre-phase receipt control, not paused-phase
`standard_recovery`, native approval, legacy checkpoint continuation, or a retry.
Source delivery and merge do not install it, send a wake or complete a pilot.

## Owner experience

The graph's brain-chat inspector offers **Check missing brain reply** for an
eligible received request. This explicitly reads bounded native metadata.
Opening, refreshing and polling the inspector never connect or notify a brain.
The five-minute signed preview explains:

- The original message was received, but its reply is missing.
- One receipt-only turn may retain that reply without rerunning its instruction.
- Dispatch stays paused; diagnostic success is not implied.

Exact scope, native observation and expiry stay under **Details**. The owner
confirms separately. The signature binds workspace, ledger, browser session,
revision, original request fingerprint, brain and reviewed host binding. Native
metadata is independently rechecked at confirmation and the send boundary.
After a lost response, recover the same confirmation receipt; never prepare
another wake. Delivery, receipt, retained reply and pilot acceptance are distinct.

## Eligibility and evidence

Require a registered, paused, empty standard project: no activated run, packets,
workers, controller, runner, Brain Stop, maintenance or managed-run fence.
There must be one processing, already received owner message, an accepted
`owned_turn_start` notification and its exact native turn ID. Other pending
controls need their own reconciliation. Strict Harness refuses this route.
An uncertain original send, missing receipt, absent turn, unsupported method,
stale observation or changed native identity stays unknown.

The existing pinned local `app-server proxy --sock` client performs only
`thread/read` with `includeTurns: false` and `thread/turns/list` with
`itemsView: notLoaded`, descending order, 64 entries per page, at most four
pages. Two matching exact-turn reads are bracketed by brain identity/activity
reads. Check idle/notLoaded activity and the exact app-server project and
checkout; keep its ID separate from the pinned Codex app catalog ID.
No transcript, turn items, command body or error body enters the observation.
The lifecycle status remains `effectOutcome: not_reconciled`: an ended turn
does not prove a command ran, a permission was granted or a diagnostic passed.

The turn-list method is experimental; unsupported hosts have no full-history,
desktop queue, discovery, automatic start or alternate-dispatcher fallback.
See [Codex app-server documentation](https://learn.chatgpt.com/docs/app-server).

## Designated brain procedure

This procedure supersedes ordinary conversation draining for this exact recovery.
Read the source's orchestrator skill and operator procedure completely. Inspect
the exact platform/workspace inbox, verify this task is the designated brain,
and keep Brain Stop and newer controls dominant.

1. Acquire the existing brain controller. Never impersonate it, create a
   replacement, or clear another controller based on age.
2. Use `brain-reply-recovery-receive RECOVERY_ID`. Do not call generic
   `process` or drain other inputs.
3. Read the returned original `messageId` and receipts as historical context,
   not permission to execute again. Inspect the existing outcome read-only.
4. Retain a concise explanation with `brain-message-reply ORIGINAL_MESSAGE_ID
   PRIVATE_REPLY_JSON`, using the existing closed reply schema. Explain known
   facts, uncertainty and the next safe action; do not claim pilot acceptance.
5. Release the controller with a retained checkpoint and end this single turn.

Only this brain's normal reply closes the original message and transactionally
completes the recovery receipt. Native final text alone does not write a reply.
If the original reply arrives before any recovery delivery claim, the unsent
recovery closes as no longer needed, without inventing a recovery receipt or
sending a turn. Claimed or uncertain delivery still requires its own receipt.
Never rerun original commands, respond to security prompts, change settings or
identities, edit source, dispatch workers, review a mission, Play, Resume, merge,
reset usage or alter schedules. Native approval retains its separate active-run
and exact owner gates. Play and dispatch Resume are fenced while recovery is
pending; Pause stays available.

## One-shot and rollout boundaries

The existing notifier commits its claim before the existing owned bridge resumes
and starts a turn. It sends a fixed pointer, never the original instruction.
The same retained connection rechecks the original and current ledger before
resume and again before start. The final check-to-native-call gap is cooperative,
not atomic native cancellation. Preserve the original receipt, payload,
notification and timestamps.

Any saved recovery attempt, even unavailable or uncertain, prevents a second
attempt for that original request. Historical confirmations only recover
receipts, even after expiry; they never notify again.
Before separately authorized rollout, quiesce older writers, back up private
state and install exact compatible source. Do not rebind a host, reset credentials,
clear the legacy stop or change a standard run merely to enable this control.
Live receipt recovery and approval-relay qualification remain separate steps;
fixture results are not live acceptance.

## Local verification

Run the full Python discovery suite and local JavaScript suites. Focused safety
coverage is in `tests/test_reply_recovery.py`; UI interaction assertions are in
`tests/test_conversation_ui.js`. They cover exact signed scope, metadata privacy,
unknown/changing reads, one-shot claims, same-connection send checks, Stop after
resume, no generic draining, late original replies and development fences.

For rendered desktop/mobile QA, run
`PYTHONPATH=.:tests python3 tests/manual_reply_recovery_fixture.py`.
Its private `session.json` belongs to a temporary fixture and must not be
published. Every native read/send is mocked; confirmation simulates a separate
receipt and retained reply on the original message. End it with Ctrl+C to close
the fixture and remove its temporary state. Never substitute a live ledger or
host for these fixture inputs.
