# Summary-first reading

Long narrative reports use one shared presentation component. The normal reading
path is outcome, next action, then optional **Details**. Native details/summary
elements support keyboard and screen readers; no text is discarded or sent to AI.

## Coverage

- Roadmap & Play: completed task bullets, phase outcome and stopping-point detail.
- Tasks & results / advanced controls: phase report and legacy worker updates.
- Brain conversation: phase/task outcomes and long messages/replies.
- Session map: task rationale; status, freshness and actions remain visible.
- Decisions: historical resolutions and recorded continuation outcomes.
- Brain activity: full saved checkpoints, replacing the old irreversible clipping.
- Project introduction: roadmap narrative.
- Advisory assistant and executive brief: long answers with existing warnings,
  source links and action confirmations kept separate.
- Knowledge, artifacts, roadmap source documents, phase-checkpoint evidence and
  raw result documents already require explicit opening; keep them complete.

## Evidence and consent

Structured phase highlights describe recorded task titles/statuses, not fabricated
feature adoption. At most three whole-sentence excerpts summarize legacy prose.
Excerpts remain labelled as selected, not comprehensive or independently verified.
No clipping/rewording of sentences, removal of negatives, inferred passing tests,
or stale PR state promoted to current facts. Long unsegmentable prose has an
explicit full-report fallback. The original text remains verbatim in Details.

Exact consent previews, mission review scope, exclusions, stop conditions, blockers,
errors and user-entered forms are deliberately NOT collapsed by a generic rule.
Reducing visual noise must never conceal what an action authorizes. Published
source readers are not summarized as a substitute for inspection.

Disclosure preferences are tab-local, bounded, and keyed to project plus exact
report. Polling preserves the open report; switching projects or receiving new
content starts closed. No backend contracts or stored evidence change.

## Verification

Use `node tests/test_summaries_ui.js` for excerpt integrity, disclosure isolation,
malicious text, long-line fallback and structured facts. Run all UI suites and
the full Python suite. Render the disposable journey fixture with long reports;
verify closed/open details, keyboard operation, narrow panes and both themes.
Source/PR delivery remains separate from live installation.

### Local verification — 2026-09-25

- Full Python suite: 1,723 tests, OK with one optional real-Graphify integration
  skip. No runtime dependency was downloaded. Existing ResourceWarnings remain.
- All 25 JavaScript UI suites, JavaScript syntax, Python compile and diff checks
  passed. The static helper route is covered by the 21-test server suite.
- Disposable rendered fixture: a 1,242-character phase report is closed by
  default; full text opens by keyboard and remains open after refresh/navigation.
  Conversation history uses the same component. Browser error/warning log empty.
- Dark desktop and light 390px layout inspected; page/content widths both 390px
  with the report open. No horizontal overflow.
- No paid inference, Actions workflows, live ledger mutation, Play, brain
  replacement, installation or live restart occurred. Live rollout remains open.
