# Roadmap & Play: the project development loop

## Why this changes

The previous Mission view repeated run evidence, budgets, optional brain handoff
and configuration before the user reached the next action. A disabled capability
button described an internal dependency without explaining how to proceed.

The main path is now **Plan → Review & Play → Develop → Checkpoint**. Roadmap &
Play is the default landing page for a project; existing deep links and browser
history remain valid. The session map is still the dedicated activity monitor.

## How to use it

1. Select the project, then open **Roadmap & Play**.
2. Choose **Prepare next phase**. This fills a message in **Brain conversation**;
   edit it, select the send confirmation and choose **Send to brain**. An existing
   draft or uncertain request is preserved instead of overwritten.
3. When the brain retains a proposal, open **Phase plan & limits**. Review the
   goal, success criteria, repositories/paths, budget, parallel-task limit, merge
   policy and stopping checkpoint. Saving a plan and reviewing it are separate.
4. Return to **Roadmap & Play**. If requested, choose **Check Codex readiness**;
   it asks the existing brain to retain available models and efforts. Inspect the
   delivery result. It neither starts work nor automatically approves Play.
5. Choose **Review Play**, read the exact control preview, select the unchecked
   confirmation and choose **Confirm play**. The preview expires after five
   minutes. An old project context, lost connection or expired preview cannot be
   confirmed from this view; the server also revalidates the signed request.
6. Use **Follow sessions** to see observed activity. **Pause at safe checkpoint**
   remains available even while Play awaits the brain's receipt. Pause has its
   own short review and confirmation; a request is not a completed checkpoint.
7. At a saved pause, **Review Resume** continues the same phase and its consumed
   budget. At completion, **Review phase results**, then **Prepare next phase**.
   A completed phase is never restarted to reset usage or task attempts.

An active phase does not prove the brain or every task is currently executing.
Session-map freshness and task evidence remain separate from control state.

## Guidance by recorded state

| State | Main action | What it means |
| --- | --- | --- |
| No plan | Prepare next phase | Draft an owner message; no automatic send |
| Unsaved/draft/changed plan | Continue or review phase plan | Preserve edits and review current scope |
| Missing Codex catalog | Check Codex readiness | Fixed capability request, not worker creation |
| Request awaiting receipt | Inspect request delivery | Show the saved request and notification separately |
| Reviewed and eligible | Review Play | Signed preview, then explicit owner confirmation |
| Active phase | Follow sessions | Monitor observed activity; Pause remains available |
| Decision needed | Review decisions | Answer inside existing authority |
| Pause requested | Follow sessions or inspect delivery | New work fenced; checkpoint not yet saved |
| Paused and resumable | Review Resume | Same phase, same consumed budget |
| Expired/blocked pause | Prepare checkpoint follow-up | Explain the blocker before proposing more work |
| Completed/blocked phase | Prepare next phase | Read retained results; new review required |
| Unresolved handoff | Review handoff progress | Optional recovery must finish before continuation |
| Harness/mixed/unconfigured policy | Review approved queue | No entry into standard phase Play |
| Disconnected | Reconnect | Saved state may be stale; no new control approval |

## Information architecture

- **Roadmap & Play:** next action, short phase facts, exact control preview and
  collapsed source documents. Source filtering and refresh are under **Source
  freshness & repository filter**; private proposals remain explicitly private.
- **Phase plan & limits:** outcome and constraints only. Model settings, exact
  receipts and previous versions are secondary to the current review.
- **Tasks & evidence:** retained task results and merge evidence, not policy forms.
- **Token usage:** measurements and reservations remain separate. Unknown measured
  remaining is displayed as unknown; new-plan facts never relabel old-phase usage.
- **Advanced controls:** optional brain replacement, history and local diagnostics.
  Disclosure choices survive refresh within the project and browser tab.
- **Brain conversation:** owner input and retained replies, not a complete Codex
  transcript. The advisory assistant remains a separate service and pane.

All three panes keep their existing collapse and keyboard/drag resize behavior.
The phase steps reflow to two columns in a narrow workspace. Themes retain the
existing local fonts and colors; no new dependencies or external assets are used.

## Safety and verification

This is a presentation/navigation change. It reuses the existing signed standard
control endpoints, conversation submission and capability request protocol. It
does not create a scheduler, change approval/merge/budget policy, issue a native
task, install a skill, activate a project or replace a live brain.

Automated coverage includes the phase-state matrix, pending/old requests,
disconnected and stale controls, Harness isolation, draft preservation, source
staleness, bounded source choices, unknown usage, and per-project disclosures.
Existing browser-history, session-map, task, authority and backend suites remain
part of regression verification.

The repeatable browser fixture is `python3 tests/manual_journey_fixture.py --port
8797`. It creates only temporary repositories/ledgers, with synthetic ready,
running, paused, completed, missing-catalog and missing-plan projects. It has no
native notifier, inference credentials, scheduler or live-project connection.
Use the printed local link. Play/Pause writes affect only that disposable ledger.
Its synthetic source card is display-only, not citation or native-run evidence.

Source delivery, PR merge, live installation and live project qualification remain
separate. No GitHub Actions or paid services are needed for these checks.

### Local verification — September 24, 2026

- Complete Python discovery: **1,723 tests, OK, one skip**. The skipped test is
  the opt-in real Graphify executable integration; no dependency was installed.
- **24 JavaScript UI suites passed**, including the new journey state matrix.
  Every `web/*.js` file passed Node syntax checking; `git diff --check` passed.
- Rendered disposable dashboard: confirmed Play and Pause, inspected the retained
  delivery request, checked separate Resume confirmation, prepared but did not
  send the next-phase message, and inspected the simplified plan view.
- Light/dark layouts, collapsed/expanded assistant and keyboard resizing to a
  narrow workspace were checked. Browser inspection reported no JavaScript
  warnings or errors during the tested flow.
- The live dashboard, project bindings, brain, installed skill and native tasks
  were not changed by this verification. Runtime rollout is not claimed.
