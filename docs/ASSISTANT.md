# Dashboard assistant and three-pane workspace

The assistant is an adviser beside the workspace, not another orchestration brain.
It can explain recorded status and suggest where to review evidence. It cannot
approve packets, answer decisions, send native task messages, resume/stop the brain,
run commands, inspect arbitrary files or change the ledger.

## Using it

1. Open the authenticated dashboard. Use **AI assistant** at the top to expand it.
2. Ask, for example, “What needs my attention?” or “Why is work waiting?”
3. Choose **Send**, or Cmd/Ctrl+Enter. Enter alone adds a new line. Suggested
   questions populate the box without sending anything.
4. Follow an answer's links into the workspace. Decision links focus the exact
   version; artifact links open the retained version's inert reader. Check the
   evidence and then use the existing explicit form/control if appropriate.
5. Open an answer's **Snapshot** disclosure to inspect its source context, model,
   service-reported usage and time. Old answers do not update when state changes;
   ask again for a fresh snapshot. No monitoring is implied by chat.

The model uses the existing server-side `.env` and inference tenancy. The key is
not sent to the browser or included in prompts. **Context & privacy** previews the
bounded dashboard data; submitted messages are additionally sent. Never type
secrets. See [the exact inference contract](INFERENCE.md#assistant-chat-data-boundary).

Conversation history and drafts survive view changes and pane collapse within
the tab. They are deliberately not persisted across reloads, tabs, or server
reconnection that requires a page reload. **Clear chat** removes the local transcript
and draft, not upstream records. Failed requests retain the question for manual
retry and cannot dispatch work. There is no automatic resend after uncertainty.

## Pane layout

- **Navigation / Workspace / AI assistant** at the top toggle each pane; collapsed
  desktop rails also have expand buttons. These controls remain accessible.
- Drag a vertical divider. The navigation divider adjusts navigation/workspace;
  the assistant divider adjusts workspace/assistant. Minimum widths keep content
  usable. Collapsed panes do not have an active adjacent resizing surface unless
  it can transfer space to an expanded pane.
- Keyboard: Tab to a divider, then Left/Right. Shift changes by a larger step;
  Home/End selects its minimum/maximum. Focus indicators and ARIA sizes are present.
- Widths and visibility are saved in this browser's localStorage. **Reset layout**
  restores defaults. No layout preference is synchronized between browsers.
- Narrow layouts automatically fit panes without overwriting saved widths.
  Below 720 CSS pixels one pane is shown at a time. Top controls switch panes;
  a chat link brings the workspace forward. This also supports narrow Codex panels.
- Each expanded pane scrolls independently. The middle workspace responds to its
  own width, so tables remain scrollable and section layouts stack when needed.

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
Stop the fixture with Ctrl+C. It never contacts the live inference service or brain.

Acceptance remains separate: unit/fixture checks do not qualify the local model's
factual accuracy or prove native-worker acceptance. A successful live chat verifies
this transport path and rendering only; links and narrative still need review.
