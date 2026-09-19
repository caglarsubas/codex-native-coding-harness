# Run readiness verification — WSP-03B2

Date: 2026-09-19. Source base: PR #20 merge
`1376b6a422084699ba0831b51f73e9e27df21801`.

## Delivered scope

An explicit, read-only selected-workspace inspection joins exact mission/review
bindings, conservative prepared-packet path scope and retained platform evidence.
The dashboard separates owner setup, evidence/coordination and missing software
controls. CLI JSON and bounded historical assistant context use the same contract.
The [plan and inspection contract](RUN-READINESS.md) records the semantics.

Every report remains blocked for autonomous execution. Diagnostic candidate and
report hashes do not create a run or grant authority. No database migration is
required; the dashboard keeps only a workspace-specific in-memory report cache.

## Automated verification

- **424 Python tests passed**, including 25 run-readiness tests and scoped HTTP
  regression coverage. Command: `python3 -m unittest discover -s tests -v`.
  Local interpreter: Python 3.12.
- **Six JavaScript suites passed**: run readiness, workspace Pause, decisions,
  workspace routing, missions and panes.
- Syntax checks passed for `web/app.js`, `web/run-readiness.js` and
  `web/missions.js`; `git diff --check` passed.

Readiness tests cover exact review identity and hashes, draft/revoked/stale
configuration, policy/mapping drift, conservative glob comparison, seed integrity
and size bounds, packet coverage limits, legacy eligibility versus phase authority,
expired/invalid platform evidence, concurrent source changes, and foreign registry
refusal. Ledger/registry fingerprints and admission-file checks verify no retained
state mutation, owner release or implicit admission initialization.

HTTP tests verify authentication, explicit workspace routing, no POST activation,
per-workspace concurrent-request refusal, historical cache isolation and no
inspection on ordinary polling/chat context reads. Frontend tests cover changed
revisions, old/future timestamps, discarded late workspace-switch responses and
captured-report export serialization/filename/cleanup.

## Rendered browser checks

Used `tests/manual_run_readiness_fixture.py` with two disposable workspace ledgers,
no notifier, no inference and no native task operations. The fixture contains one
reviewed phase and one proposed packet in Project A; the second workspace has no
mission. Both the fixture server and temporary browser tab were closed afterward.

- Desktop at 1280 × 720: inspected the existing three-pane layout and grouped
  report. Satisfied checks use expandable details; blockers remain visible.
- Opening Run readiness does not inspect automatically. Reload clears the tab's
  captured report; inspection requires the explicit button again.
- Switching to the second workspace initially shows no report. Its explicit
  inspection reports missing configuration without Project A's mission/packet.
  Returning to Project A retains its own captured report and labels it historical.
- Expanded packet details distinguish contained paths from blocked legacy checks
  and missing operation authority. The related readiness button navigates to
  Operational readiness.
- At 390 × 844, pane controls remain available and the report is readable. Expanded
  hashes wrap and the workspace pane's scroll/client widths both measured 390 px.
  The JSON document is available in an expandable, scrollable region.
- No browser console errors or warnings were recorded during these checks.

The inspection-download button was exercised without a console error, but the
in-app browser did not expose a download-completion event. Actual OS file delivery
is **not browser-accepted by this report**. Serialization is tested; the complete
JSON remains readable in the dashboard and available through the CLI/API.

The design pass preserved the existing palette/type system and reduced initial
detail by collapsing satisfied checks. No redesign or dependency was introduced.

## Explicitly not accepted

No live dashboard restart, skill installation, ledger enrollment, owner adoption,
evidence collection, notification, heartbeat change or inference call was performed.
No product repository or real development task was changed by this increment.

This is source/test/UI evidence, not deployed-runtime or autonomous-development
acceptance. Native run activation, effect/continuation fences, phase release,
operation/settings contracts, admission integration and a real two-workspace
Play/Pause pilot remain separate work. Required GitHub checks and merge status must
be observed on the resulting PR; these local results do not imply either.
