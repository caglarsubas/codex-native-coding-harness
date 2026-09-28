# Conversation as the main project control surface

The owner directs development through the one-page project workspace. Select
the brain on its persistent graph for durable instructions and replies; choose
the separately labelled advisory guide for explanations and signed-control
previews. Roadmap and evidence open in the same inspector. A routine
standard-project cycle stays in this workspace:

1. Click **Help me continue development** below its preparation summary. This
   confirms the displayed, signed preparation request; no prompt writing is needed.
   The existing brain inspects blockers, refreshes permitted evidence, reconciles
   existing work and prepares a safe next step in one bounded turn.
2. Follow **Preparation progress** in the conversation: saved, notification,
   brain receipt and retained reply. Existing pending requests are followed, not
   duplicated. If a plan is already ready, the assistant offers its review directly.
3. Review the proposed outcome, budget, concurrency, merge policy and stopping point.
   Expand scope, success criteria and exclusions when needed. Type **confirm review**.
4. If native capabilities need refreshing, confirm that request here and follow its
   receipt. When ready, request Play, then type **confirm play** for that exact preview.
5. Ask for progress or request **Pause** or **Resume**. These use the registered
   standard phase and preserve its consumed budget and checkpoint requirements.
   If usage needs measuring first, confirm the local usage check in chat. Missing
   coverage remains unknown and blocks further effects; it is never treated as zero.

When a running standard phase stops on a control blocker, the workspace shows
a deterministic explanation before the owner asks the model. A paused phase
with unresolved limits/evidence is different: ordinary brain messages are held,
and phase Resume remains refused. **Help me continue development** or **Review
recovery preparation** shows a signed, exact recovery-only wake preview. One
owner confirmation may deliver a single bounded preparation turn through the
reviewed, bound Codex app-server host, reusing a held unsent message. The old
phase stays paused and its consumption and expiry are unchanged. The dashboard
then shows native delivery, brain receipt and reply separately. See
[checkpoint recovery wake](CHECKPOINT-RECOVERY-WAKE.md) and
[guided control recovery](CONTROL-RECOVERY.md).

The assistant can also send an explicitly requested, verbatim instruction to the
project brain, such as a requested phase revision. It never invents the owner's
answer. A short confirmation phrase is handled directly by the browser, without
an inference call, and applies only to one current preview in this project.
“Yes,” a model reply, or old conversation text does not submit a control.

### Keep control and native conversation independent of inference

**Help me continue development** uses a server-generated preparation instruction,
not an inference-generated prompt. The bounded scope and token-use notice are
visible before the Help button; the exact instruction is under Details. Clicking
it confirms that signed, project/session/revision-bound preparation only. The
exact typed starter can confirm this same displayed Help preview; it does not
invent or confirm an unseen plan. If no current preview is displayed, it first
loads one. **Pause the project safely** and **Resume the project** still prepare
their own separate signed previews. Vague assent is never confirmation.

The preparation request covers policy, scope, task limits, timing, readiness,
usage coverage and uncertain native effects. The brain must perform available
bounded checks before asking for missing evidence. It cannot waive a control,
start workers, change limits or replay effects. A returned unresolved condition
does not trigger another automatic request. A small evidence/decision field
prepares the follow-up wording, with an exact message preview before sending.
Review and Play remain separate confirmations. Strict Harness is unchanged.

The authenticated, project-scoped `GET /api/workspaces/<id>/assistant/help`
projects the next step and may sign the preparation preview. Reads and polls
never collect evidence or notify a brain. The existing `/assistant/confirm`
adapter saves the normal reconcile message; the existing one-shot notifier sends
its fixed pointer. There is no help scheduler or second dispatcher. Reloading
reconstructs progress from the same durable command and retained reply. Missing,
overdue or uncertain delivery stays visible without blind resend; a receipt is
not proof of current activity, and a preparation reply is not phase completion.

For any other instruction, type it and choose **Send to project brain…**. The
assistant shows the exact text and selected project; **confirm send** saves and
notifies it through the existing conversation adapter. No inference call is made.
**Ask assistant** remains available for advisory explanations using bounded
metadata, with no retained native replies included in its inference history.

The model prompt omits repeated action-impact prose while retaining the full
facts, restrictions, availability and limitation fields. Exact impacts remain
visible in the server-signed confirmation, never authored by the model.

### Desktop CLI updates

A missing legacy `/Applications/ChatGPT.app/Contents/Resources/codex` (or the
equivalent `Codex.app` path) can resolve the new nested `CodexCLI.app` layout only
after verifying the executable's Apple code signature, OpenAI team and `codex`
identifier. Arbitrary missing paths, symlinks and verification failures remain
unavailable. This is startup-only compatibility, not PATH discovery, installation
or a new transport. `codex queue` still sends once; acknowledgment and the brain's
retained receipt/reply remain separate observations. An unqualified owned host is
not silently adopted.

On macOS the local operator may also opt in to `--desktop-brain-wake` alongside
`--notify-brain`. For registered standard projects only, an exact queue
acknowledgment is followed once by `/usr/bin/open -g -a` against the verified
OpenAI-signed desktop bundle and `codex://threads/<designated-brain-id>`. Loading
the existing chat allows Codex to consume its saved queue; no second message is
sent, no task is created and no global model or app setting is changed. The
desktop may select that chat, but is requested not to take foreground focus.
The existing durable claim also covers this open step. Unknown queue delivery
never opens or resends; failed/uncertain opening keeps the accepted queue and
requires inspection of the same task. An open request is not a brain receipt.
Paused/stopping controls keep their existing priority and ordinary-input fences.
Strict Harness does not use this additional desktop-open behavior.

## Architecture

### Reply-to-next-step visibility

Delivery notices follow their exact project/request ID through polling instead of
retaining the original queued text. A retained conversation reply replaces the
waiting notice. A completed legacy request without a retained reply remains
explicitly incomplete; a missing record is never treated as successful delivery.
Unrelated errors and notices from another project are not overwritten.

Roadmap & Play and the assistant show the latest retained brain reply, its original
timestamp, and the current next action together. A short summary includes an
explicit next-action sentence when present; the complete unmodified reply remains
under Details. Reply prose never selects a control or supplies authority: next-step
buttons use the existing current-state projection and signed previews. Native
brain replies are labelled separately from advisory inference and remain outside
its conversation history. Replies received in an open assistant chat also expose
the current next-step preview directly beneath that reply.

A successor draft displays its own version and stopping checkpoint. The previous
run's blocked/completed status stays labelled as history, not the state of the new
plan. Previous usage gaps remain visible before Play. Review and Play are still
separate owner confirmations; receipt, reply and a new draft never start workers.

See [progress and interval-accounting verification](BRAIN-PROGRESS-VERIFICATION.md).

The model proposes keys from a server-generated catalog. `JourneyProposals`
creates signed, expiring previews bound to the selected ledger, browser session,
brain and existing mission/run request. Confirmation composes the existing
mission, conversation, capability and standard-run adapters. Native dispatch
continues to belong to the designated brain.

The exact mission is presented locally for review; inference receives bounded
metadata. Retained brain replies shown in chat are not appended to inference
history. Unconfirmed chat stays in the tab, while confirmed requests and replies
remain in the private ledger. Reloading recovers the latest brain reply and
pending-message state from that ledger. Signed request IDs survive uncertain
responses; replay returns the retained outcome without re-notification.

The assistant occupies the main work area by default for new layout preferences.
**Ask assistant** or **Focus conversation** restores that layout; selecting an inspection page can reopen the project
pane. Existing saved pane sizes and collapse choices are preserved.

## Coverage and boundaries

This delivery covers the standard-project phase loop, capability/usage refresh and exact
brain messages alongside existing decision/control previews. Strict Harness
activation, brain replacement, retention policies and advanced evidence inspection
retain their existing controls. No new native transport, scheduler, merge policy,
provider or billing integration is introduced.

Local verification uses disposable ledgers and mocked inference. Source delivery,
PR merge, installation and live inference/native task qualification are separate.
This change does not start the user's project phase.

## Local verification — 2026-09-25

- Full Python discovery: 1,733 tests, successful with one optional pinned Graphify
  subprocess integration test skipped (no reviewed executable configured).
- All 26 JavaScript suites, 30 browser-script syntax checks, Python compilation
  and Git whitespace checks passed. The 33 assistant tests also passed separately.
- Disposable browser QA with mocked inference: request a phase review, type
  `confirm review`, request Play, type `confirm play`, refresh usage, and request
  safe Pause without changing pages. Native delivery was deliberately unavailable
  and displayed as unavailable, never completed. No real Codex task was started.
- Rendered focused/default conversation layout, collapsed evidence, unknown usage
  when no samples exist, and pending-request recovery after reload were checked.
- Regression coverage includes project/session isolation, tampered and expired
  previews, exact receipt replay, invalid payloads, stale scope, strict-project
  exclusion, safe Pause after mission revocation, and Resume preserving usage and
  the original expiry. Missing coverage does not unlock Resume.

Merge, live installation and qualification with the configured inference service
remain separate rollout steps. No GitHub Actions workflow was added or invoked.

## Guided preparation verification — 2026-09-28

- Full local Python discovery: 1,795 tests, successful with one optional pinned
  Graphify subprocess test skipped. All 29 JavaScript UI suites, all 31 browser
  script syntax checks, Python compilation and Git whitespace checks passed.
- The 12 focused help tests cover signature/session/project/expiry checks,
  concurrent confirmations, exact receipt replay, paused/stopped/handoff races,
  missing replies, current-run correlation, strict-project exclusion and reads
  that neither notify nor mutate the ledger. No inference service is required.
- Rendered disposable recovery rehearsal: one Help click saves one request;
  unavailable notification remains honestly labelled; a synthetic retained reply
  survives reload and offers only a short missing-evidence field. Its generated
  follow-up is a separate exact message preview. Unconfirmed creation ownership,
  usage gaps and the budget overrun remain intact.
- Rendered disposable completed-phase rehearsal: Help, retained draft, exact
  Review confirmation, then **Next: Review Play** beside the saved review.
  The Play preview was inspected but not confirmed. Details stay collapsed by
  default and the initial Help button is visible at a 1280-by-720 viewport.
- Both rehearsals deliberately disabled native notification and used synthetic
  brain replies. They qualify local UI/ledger behavior, not live Codex delivery
  or model compliance. No live brain, task, budget or running service changed.

Installation and real native-turn qualification remain separate rollout steps.
No GitHub Actions workflow, paid service or automatic recovery loop was added.
