# WSP-03B1 verification — 2026-09-19

Result: selected-workspace safe Pause implemented and locally verified. No live
workspace was paused, resumed, enrolled, adopted or activated during this run.

Base: PR #19 merged at `415e47598bc3dacd9d20100da84d8341958ba5ca`.
Branch: `codex/wsp-03-workspace-pause`.
Implementation and operator contract: [Workspace Pause](WORKSPACE-PAUSE.md).

## Automated checks

Python 3.12: `python3.12 -m unittest discover -s tests -q` — **397 tests passed**
in 31.796 seconds. The pause-specific suite includes 23 tests; an additional HTTP
test verifies workspace routing, inbox/assistant awareness and refusal before
notification. Existing legacy brain-control and platform-admission tests remain green.

All five JavaScript suites passed:

```sh
node tests/test_workspace_pause_ui.js
node tests/test_decision_ui.js
node tests/test_workspace_ui.js
node tests/test_mission_ui.js
node tests/test_panes_ui.js
```

Syntax checks passed for `web/app.js`, `web/activity.js` and
`web/workspace-pause.js`. The Skill Creator validator accepted the updated source
skill. `git diff --check` passed. No dependencies were installed or downloaded.

Coverage includes exact stop/workspace identity, retained owners completed or
deleted after Pause, changed native bindings, descendants that cannot disappear,
foreign/cyclic ancestry, per-task artifact/session/repository/time checks,
stale/future/partial evidence, owned runners, uncertain creation, processing
worker controls, fresh heartbeat evidence, duplicate concurrent observations,
transaction rollback, controller handoff, immutable retries, early-resume refusal,
Pause superseding pending Resume, raw-state compatibility and bounded CLI input.

## Rendered browser rehearsal

Used `tests/manual_pause_fixture.py` with two disposable workspaces, synthetic
worker evidence, no inference and no native notification bridge.

- Alpha's primary **Pause workspace** saved a stop and showed **Pausing safely**,
  retained-worker count, missing brain receipt and missing inventory.
- Beta remained unchanged when selected. Returning to Alpha retained its state.
- A synthetic checkpoint enabled **Resume brain from checkpoint**, but unknown
  native brain activity still displayed **Checkpoint saved · activity not confirmed**.
- Resume preserved paused worker dispatch and explicitly stated it was not Play.
- Another Pause superseded that pending Resume and required a new checkpoint.
  The older artifact was labeled **Previous checkpoint · does not complete this Pause**.
- The 390 × 844 viewport rendered readable progress, links and keyboard focus.
  Document client width and scroll width were both 390 pixels: no page overflow.

Restored the viewport, closed the disposable tab and stopped its fixture server.
Only temporary fixture state was removed; no user or live workspace data changed.

## Evidence and rollout limits

These are local test and rendered-fixture results, not hosted CI, a real native
worker pilot, installed-skill verification or a running-dashboard revision claim.
No API credential, live ledger, transcript or runtime configuration is included.

The helper validates retained assertions; it is not an independent native
inventory collector or process attestation. Actual native idle/coverage evidence
must come from supported tools. Worker and runner ownership is not released by
parking. Unknown or expired evidence remains visible and blocks fresh pause claims.

The source skill updates the brain's checkpoint procedure; the existing design
system informed the flat progress panel, primary action and narrow layout. The
installed skill and live dashboard are unchanged. A coordinated helper/assets/
skill rollout and a separately scoped native pilot remain required. Autonomous
Play, versioned runs, authority activation, phase release and token admission
remain incomplete and are not enabled by this PR.
