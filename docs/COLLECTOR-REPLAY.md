# Issue #41 — concurrent collector receipt replay

Plan saved before implementation on PR #40's verified merged commit
`5589ae5ea0687d4b38643247c3abca29daf7e377`. Issue #38 is closed; this increment
addresses the separately recorded collector race, not inference or Play activation.

## Plan

- [x] Inspect GitHub, source and local-preservation collectors for the split-lock
  receipt lookup. All three have the same pre-I/O gap.
- [x] Reproduce the gap with event-controlled fixture interleavings: pause one
  request after its read-only lookup, then let an identical request retain first.
- [x] Recheck the exact retained receipt inside each pre-I/O ownership transaction,
  before applying new-work context and revision checks.
- [x] Verify immutable conflicts, missing/corrupt evidence, unrelated revision
  changes, Pause and maintenance boundaries without retries or renewed timestamps.
- [x] Run focused and full Python regressions, JavaScript UI/syntax checks and
  whitespace validation locally; record results and prepare a manual-merge PR.

## Boundaries

The initial read-only replay path stays available. The second lock retains its
existing controller/identity and ownership-maintenance checks; a fence arriving
between the two transactions can still refuse that in-flight call. A subsequent
explicit exact replay can use the initial historical-read path. No lock is held
during Git/network collection, and the existing post-I/O recheck remains intact.

Only an exact, fully validated retained receipt bypasses new-observation
checks. New or conflicting requests gain no stale-revision, authority, maintenance
or Pause bypass. Receipt recovery never recollects, changes original evidence time,
accepts a task, releases ownership or authorizes dispatch.

Tests use disposable ledgers/Git repositories and synthetic GitHub responses. No
live collector, native task, account/budget change, installed skill, schedule,
dashboard restart, runtime upgrade, maintenance release or Play activation is in
scope. All checks run locally. No Actions workflows/jobs/runners or paid services.

## Implementation and reproduction

An initial receipt lookup and the new-observation context check use separate
transactions. Another identical request can commit its receipt in between them,
advancing the workspace revision. Previously, the delayed request then failed its
new-work revision check instead of returning the result that had just been saved.

Each collector now invokes its existing immutable receipt validator again under
the second transaction, before building new-work context. The change is three
lines per collector. It adds no retry, schema, route, dependency or external effect;
the final post-I/O receipt/authority check is unchanged.

The adjacent result-handoff supplemental-proof writer already rechecks its
receipt in its second transaction; inspection required no change there.

The regression harness uses thread events, not sleeps: the delayed call has really
exited its first transaction before the competing writer proceeds. Against the
unmodified merged source, the first 18 tests produced six errors for exact and
post-Pause replay plus three failures for the expected immutable-conflict reason.
The other nine guard cases passed. The expanded suite covers eight interleavings
for each of the three collectors (24 cases), including corrupt artifact bytes and
Pause without any matching receipt. Tests prohibit another collection call and
compare full logical local/shared state after the competing operation, so replay
cannot renew evidence, duplicate artifacts/events or change capacity accounting.

## Local verification — 2026-09-20

Python 3.12.11 focused verification passed **156 tests**: the new race matrix plus
the existing GitHub, source, preservation and result-handoff suites. All **7
JavaScript UI regression files** passed, as did JavaScript syntax and Git whitespace
checks. The complete final-code Python suite passed **1,103 tests in 191.145
seconds**, with no failures, errors or skips. This includes all 1,079 baseline
tests and the 24 deterministic race cases. Only this verification text changed
after that full run; production and test source were unchanged.

```sh
PYTHONPATH=tests python3.12 -m unittest test_collector_replay test_github_evidence test_source_observation test_local_preservation test_result_handoff -v
python3.12 -m unittest discover -s tests -v
node --check web/app.js
node --test tests/test_*_ui.js
git diff --check
```

Read-only GitHub inspection found zero configured Actions workflows and zero
Actions runs; the source tree contains no workflow. Nothing is added or enabled.
These are local fixture results, not hosted CI, live rollout, worker acceptance
or autonomous-workspace qualification. The fix is intended for manual merge;
the installed dashboard and live workspace state are unchanged.
