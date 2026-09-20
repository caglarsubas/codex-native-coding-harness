# Native supervision verification

Scope: WSP-04D2 on merged PR #31, exact baseline
`200cdca1346403079e25e7bcb5f2cc4f3c619790`. Source implementation and isolated
fixtures only; no live observation writes, task sends or activation.

## Evidence boundaries

| Boundary | Observed result |
| --- | --- |
| Baseline | GitHub PR #31 merged at 2026-09-20T01:09:40Z; exact baseline above |
| Native wait capability | Read-only single-target probe returned poll schema 1, current `notLoaded` and an older completed turn |
| Account capability | Read-only limits probe returned a weekly window in `primary`, null `secondary`; missing short coverage was not treated as unlimited |
| Observation integration | CLI plan/record/state flows exercised against private temporary ledgers with synthetic tool-shaped responses |
| Admission integration | New unknown/changed-account/exhausted evidence blocks reservation/creation checks; older healthy evidence and manual updates cannot bypass current journal checks |
| Native task send | Not run; the helper has no task transport or polling loop |
| Runtime / acceptance | Not run; dashboard, installed skill, live ledger, schedules, settings and product repositories unchanged |

The capability probes were read-only and were not retained in live admission or
workspace state. Public fixtures use fabricated task/account identifiers, text and
usage values. Private account IDs, conversations, tool inputs and credit data are
not copied into source or this report. The brain remains the native caller; no
additional app-server, model runtime, private API or inference call is introduced.

## Regression commands

```sh
python3 -m unittest discover -s tests -v
node --check web/app.js
node --test tests/test_*_ui.js
git diff --check
```

Local Python 3.12: **879 tests passed**, including **40 native-supervision tests**.
All **7 JavaScript UI test files passed**; JavaScript syntax and whitespace checks
passed. The existing readiness diagnostic copy is updated without enabling an
action or adding a UI route. These checks are not a new rendered-browser or live
task acceptance result. GitHub-hosted check status is a separate evidence state.

## New fixture coverage

- Subprocess CLI task plan/record/state and account record/state with explicit
  workspace selection and designated-brain authentication; no hidden initialization.
- Exact task/host/version binding, cursor scoping, missing/duplicate/foreign polls,
  unsupported statuses, current activity versus historical turns, and explicit
  unknown results for tool errors and unavailable state.
- Discarded assistant/tool/error content and credit details; private account
  identity retained only as a digest; bounded finite input.
- Duration-based short/weekly mapping, reversed slots, weekly-only responses,
  unsupported/duplicate durations, authoritative bucket selection, null/nonfinite/
  negative values, explicit usage/spend restrictions and exhausted headroom.
- Immutable native source provenance, monotonic time, stale/future refusal,
  conflicting request IDs, optimistic concurrency and historical exact replay.
- Shared account observations across workspace brains without sharing task
  authority; different account identity fences admission and does not reset phase
  counters. Two concurrent observations have at most one new current version.
- New incomplete evidence overrides old healthy readings, including clearing the
  legacy usable projection; journal/pointer/projection corruption and manual
  update attempts refuse. This does not qualify concurrent old-version writers.
- Limits change between creation handoff and pre-send check; no native permission
  is emitted on exhaustion, and the in-flight owner remains retained.
- Native account evidence never supplies absent brain/worker/reviewer cumulative
  counters or releases repository, runner, token or task ownership.
- Shared task journal commits followed by interrupted local attachment recover
  through exact replay after Pause. Account failures roll back the shared
  transaction. Reads/replay do not invent newer evidence or revive old health.
- Observations after Pause preserve the stop and existing owners. Idle does not
  mean terminal completion, cleanup, acceptance or safe archival.

These tests verify conservative interpretation and receipt integrity under the
existing trusted-brain/private-store boundary. They cannot authenticate arbitrary
caller-supplied native assertions. No claim of complete descendant inventory,
actual task token metering, trusted runner execution or live acceptance is made.

## Remaining pilot gates

Qualify complete task/descendant and cumulative phase-token observations; connect
supervised runner and result evidence; provide explicit owner setup/activation and
brain operator installation; run a tiny real standard-policy pilot with retained
acceptance evidence. The observed weekly-only account shape also requires a
separate supported-window policy decision before qualifying for live admission.
Do not infer a missing window's capacity or weaken policy in this source increment.

Maintenance release, adaptive model/effort/speed, automatic phase continuation,
preservation-backed archival, the two-workspace rollout and the trusted Harness
acceptance adapter remain independent gates. Merge is not activation or deployment.
