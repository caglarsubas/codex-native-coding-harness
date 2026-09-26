# Conversation as the main project control surface

The owner directs development through the AI assistant. Project pages are optional
inspection surfaces. A routine standard-project cycle stays in the conversation:

1. “Help me continue development.” The assistant reads the current project snapshot
   and presents its first available prerequisite.
2. “Prepare the next phase.” Confirm the exact instruction once. Its delivery,
   receipt and retained brain reply appear in the conversation.
3. Review the proposed outcome, budget, concurrency, merge policy and stopping point.
   Expand scope, success criteria and exclusions when needed. Type **confirm review**.
4. If native capabilities need refreshing, confirm that request here and follow its
   receipt. When ready, request Play, then type **confirm play** for that exact preview.
5. Ask for progress or request **Pause** or **Resume**. These use the registered
   standard phase and preserve its consumed budget and checkpoint requirements.
   If usage needs measuring first, confirm the local usage check in chat. Missing
   coverage remains unknown and blocks further effects; it is never treated as zero.

When a standard phase stops on a control blocker, Roadmap & Play and the assistant
show a deterministic explanation before the owner asks the model. Confirming
**Prepare recovery proposal** sends one exact, bounded investigation/draft request
to the existing brain. It does not change a budget, review a new mission or Play.
See [guided control recovery](CONTROL-RECOVERY.md).

The assistant can also send an explicitly requested, verbatim instruction to the
project brain, such as a requested phase revision. It never invents the owner's
answer. A short confirmation phrase is handled directly by the browser, without
an inference call, and applies only to one current preview in this project.
“Yes,” a model reply, or old conversation text does not submit a control.

### Keep control and native conversation independent of inference

The product's exact **Help me continue development**, **Pause the project safely**
and **Resume the project** starter phrases prepare the existing signed standard
control preview directly. They do not wait for an advisory model, interpret vague
assent, apply a control, or enter strict Harness. A pending request is inspected
instead of duplicated. Review and Play remain separate confirmations.

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
