# Advisory guide in the one-page workspace

## The assistant remains advisory

The project brain's durable conversation is the primary place to ask the
project to continue. Select the brain node in the graph to open it in the
inspector. The on-prem assistant is a separately labelled **Advisory guide**
there: it explains recorded process state and can propose only supported
controls. It is not the project brain, and its messages are not brain replies.
See [the conversation workflow](ASSISTANT-LED-WORKFLOW.md) for preparation, review,
Play, Pause, Resume and direct project-brain instructions.
It can propose supported controls and free-text decision answers; only a separate
owner confirmation submits the exact preview through the existing control ledger.
It cannot approve packets, run shell commands, inspect arbitrary files, merge code,
provision infrastructure or directly operate native workers.

## Using it

1. Open the authenticated project workspace. Select **Advisory guide** in the
   inspector to ask about state; select the brain node for durable brain chat.
2. Ask, for example, “What needs my attention?” or “Why is work waiting?”
3. Choose **Send**, or Cmd/Ctrl+Enter. Enter alone adds a new line. Suggested
   questions populate the box without sending anything.
4. Review the proposed step directly in the conversation. Standard-project phase
   controls accept the displayed confirmation phrase (for example, **confirm play**)
   or the inline confirmation button. Contextual inspector sections remain optional inspection links. Decision links focus the exact
   version; artifact links open the retained version's inert reader. Check the
   evidence. For a requested supported action, review its inline preview: title,
   target, impact, exact payload/scope, state revision and five-minute expiry.
   Choose the displayed confirmation or dismiss it. Ordinary requests, navigation
   and model replies never confirm a control; only the exact confirmation does.
5. Open an answer's **Details** disclosure to inspect its source context, model,
   service-reported usage and time. Old answers do not update when state changes;
   ask again for a fresh snapshot. No monitoring is implied by chat.

The model uses the existing server-side `.env` and inference tenancy. The key is
not sent to the browser or included in prompts. **Context & privacy** previews the
bounded dashboard data; submitted messages are additionally sent. Never type
secrets. See [the exact inference contract](INFERENCE.md#assistant-chat-data-boundary).

Advisory history and drafts survive inspector changes within
the tab. They are deliberately not persisted across reloads, tabs, or server
reconnection that requires a page reload. **Clear chat** removes the local transcript
and draft, not upstream records. Failed requests retain the question for manual
retry and cannot dispatch work. There is no automatic resend after uncertainty.

## What the assistant knows and can do

Each question gets a fresh, bounded projection from the **same snapshot builder
as the workspace**: observed brain activity and freshness, control intent, heartbeat,
controller/runner ownership, pending controls and notification receipts, workers
and evidence axes, queue eligibility, follow-ups, per-repository size/Git/readiness,
roadmap checklists, model/effort usage, recent PRs and artifact versions. A capability
catalog explains every dashboard view, available controls, restrictions and next
review locations. Counts show included/omitted records; it does not know every
process or file, and old evidence does not become current merely because chat ran.

Supported confirmation-backed actions:

- Stop the brain at a safe checkpoint; resume/wake that same brain.
- Pause or request resume of worker dispatch, separately from brain activity.
- Request reconciliation; switch periodic idle checks/event-driven waiting.
- Hold/release one prepared packet; request checkpoint or archive an eligible,
  completed and preserved worker.
- Record a free-text answer for one open decision version. The saved text must
  be an exact excerpt of your latest message, shown before confirmation. The
  assistant cannot invent an answer or select a suggested option for you.

Examples: “Prepare the next phase”, “Pause this phase”, or
“For the open design question, record this answer: …”. Standard projects use
their phase Pause/Resume; ambiguous legacy brain/dispatch requests need clarification. Model mistakes remain
possible: verify the preview rather than treating its wording as authority.

Packet approval/priority changes, advanced diagnostics and new executive briefs
retain their review screens. Standard native-capability/usage refresh and phase controls
are available inline. Each phase keeps its separately reviewed stopping point.

Confirmation uses a server-signed, session-bound preview; the browser/model cannot
change its target, command or payload. Changed state, a changed decision version,
expiry or server restart requires a new preview. The existing transactional control
checks still apply. One command ID survives retries: a lost confirmation response
can recover its receipt, but does not resend an uncertain native notification.

The card follows actual command state from dashboard polling: saved/notified,
received/processing, completed or rejected. **Sent to Codex is not completed**;
**stop requested is not checkpointed**. If notification is unavailable, the control
is recorded but the brain has not been woken. Opening another tab/reloading loses
chat but not the confirmed command: its pending state and latest brain reply remain
in the conversation's current-project summary, with full history in Control requests.

## Workspace layout

The graph stays visible on desktop while its contextual inspector holds the
brain conversation, advisory guide, roadmap, decisions and evidence. Select a
node or use **Explore project** to change inspector context without opening a
separate project page. On narrow screens, the inspector becomes a dismissible
sheet; the graph and searchable task list remain available beneath it. Old
project links select the corresponding inspector section. Exact control previews
and confirmation gates are unchanged. See [one-page workspace](ONE-PAGE-WORKSPACE.md).

## Verification

Run the Python suite and frontend checks without a network/model dependency:

```sh
python3 -m unittest discover -s tests -v
node tests/test_decision_ui.js
node tests/test_panes_ui.js
node --check web/assistant.js
node --check web/panes.js
node --check web/routing.js
```

For isolated browser QA, run:

```sh
PYTHONPATH=.:tests python3 tests/manual_assistant_fixture.py
```

The fixture binds port 8769 with a temporary ledger and mocked inference. Open
the private URL from `session.json` inside the printed temporary directory.
Never publish that URL. It shares the browser's loopback cookie name with a
live dashboard on another port; reconnect the live dashboard afterward.
The phrase `fixture failure` deliberately returns a recoverable chat error.
“Please stop the brain” returns a fixture-only stop preview; “Answer: [text]”
returns a fixture decision-answer preview. Confirming changes only the disposable
fixture ledger; its native notification bridge is disabled.
Stop the fixture with Ctrl+C. It never contacts the live inference service or brain.

Acceptance remains separate: unit/fixture checks do not qualify the local model's
factual accuracy or prove native-worker acceptance. A successful live chat verifies
this transport path and rendering only; links and narrative still need review.
