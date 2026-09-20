# Cumulative phase usage verification

Scope: WSP-04D3, based on merged PR #32 at exact commit
`e113e6fa9651b2813c28ce688e1f3cf6389a2da3`. Source integration and synthetic private
fixtures only. PR #32 was verified merged at 2026-09-20T01:59:44Z.

## Evidence boundaries

| Boundary | Result |
| --- | --- |
| Source | Brain-owned phase state/record CLI, immutable cumulative evidence journal, per-session/per-role readout and existing admission/effect checks |
| Counter collection | Not implemented; no available desktop tool was treated as a complete per-task counter source |
| Coverage | Supplied assertions are checked against owned roots, known descendants, previous samples and retained terminal evidence; not independent discovery of every native child |
| Accounting | Brain baseline deltas, full-lifetime task counters, sticky epochs/high-water marks, protected estimates and exact settlement incorporation |
| Live state | No live baseline, usage write, allocation, native task, schedule, model setting, installation or dashboard restart |
| Acceptance | No real native pilot, autonomous Play, trusted Harness execution or deployment claim |

The implementation follows the orchestration skill's designated-brain control
boundary and official documentation's distinction between thread usage events and
account summaries. No new app-server, SDK runtime, private native API, log scan,
inference call, goal reset, credit action or provider API credential is introduced.
All counters, task/account identifiers, epochs and evidence hashes in tests are
synthetic. No private conversation content is copied into this repository.

## Local verification

```sh
python3 -m unittest discover -s tests -v
node --check web/app.js
node --test tests/test_*_ui.js
git diff --check
```

Local Python 3.12: **914 tests passed**, including **35 new phase-usage tests**.
All **7 JavaScript UI test files passed**; JavaScript syntax and whitespace checks
passed. Hosted checks, merge, runtime and acceptance must be assessed separately.
This backend increment does not add a UI control; JavaScript regression checks are
not rendered-browser or live accounting acceptance evidence.

## Fixture coverage

- Real subprocess CLI state/record flow in a temporary private platform; explicit
  workspace selection, controller ownership and no read-side initialization.
- Nonzero long-lived brain baseline, full task lifetime usage, input/cache and
  output/reasoning subsets, per-session deltas and role totals without double count.
- Distinct workspace allocations/totals and request-ID namespaces under one shared
  account identity; foreign allocation/controller/brain and native identity refusal.
- Exact owned root role and ancestry; nested reviewers/descendants, cycles, missing
  parents, previously recorded sessions and newly retained Pause descendants.
- Creation before/after the one-use send check, pending native creation, confirmed
  identity changes and revalidation at the dispatch effect boundary.
- Missing, null, incomplete, future or stale samples; no replacement of known
  charges by zero and no envelope-time refresh of older constituent evidence.
- Immutable baseline, counter epoch and role/parent binding; cumulative regression,
  invalid delta subsets and older phase totals remain conservative blockers.
- Exact settled task-tree/epoch/counter incorporation, eliminating the separate
  unincorporated charge only with complete fresh evidence; mismatch or later growth
  stays blocked. Confirmed non-creation requires its actual retained zero receipt.
- Historic exact replay and conflicting IDs; concurrent optimistic versions have
  one winner. Shared-transaction failures roll back journal/projection/event together.
- After-Pause accounting retains stop state, worker records, resource holds and
  approval/evidence axes. Overruns are retained and checkpoint headroom protected.
- Private bounded closed input, invalid/nonfinite counters, duplicate sessions,
  journal tampering, missing pointers and legacy projection overwrite refusal.
- State/source drift between inspection and recording; old observations are not
  refreshed on read, replay or later report creation.

The tests establish consistency and failure behavior, not authenticity of arbitrary
caller-supplied source assertions. Complete flags still require real independently
qualified evidence. An absent child cannot be discovered by validating a supplied
list; local records, account percentages and best-effort dashboard totals cannot
prove otherwise. A healthy accounting receipt grants no execution authority.

## Remaining pilot gates

Qualify a complete native/descendant and cumulative-token observation source;
connect supervised runner and result evidence; provide explicit owner setup and
activation plus compatible brain operator installation; then retain evidence from
a small real standard-policy pilot. The native weekly-only account response still
needs a supported window-policy decision before live admission. This increment
does not relax that policy or any maintenance fence.

Continuous phase execution, preservation-backed archival, adaptive routing,
two-workspace live acceptance and trusted Harness execution remain separate gates.
