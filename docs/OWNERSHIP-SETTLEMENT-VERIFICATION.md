# WSP-04C3a verification — terminal ownership settlement

Date: 2026-09-19. Base: merged PR #25,
`8318bf443ad0fb24b39b4c285f5c5f1dfa3f0f26`.

## Results

| Check | Evidence |
| --- | --- |
| Full Python 3.12 regression suite | 627 tests passed in 41.766 seconds |
| New ownership settlement cases | 42 passed within the full suite |
| JavaScript regression suites | All seven passed: decisions, missions, panes, run readiness, task contracts, workspace Pause and workspace routing |
| JavaScript syntax | `node --check web/app.js` passed |
| Diff whitespace | `git diff --check` passed |

Commands: `python3.12 -m unittest discover -s tests -v`,
`node --check web/app.js`, `node --test tests/test_*_ui.js`, and
`git diff --check`. The Python run used the installed Python 3.12 environment;
no dependencies were downloaded. Earlier fixture failures were corrected and
the complete suite above rerun after the final source edits.

## Exercised behavior

- Exact registered-brain controller, workspace/database/phase/dispatch binding
  and latest native receipt are required. Changed identity, stale/missing native
  attachment, resource drift and allocation drift refuse.
- Pending or uncertain creation, unknown/running activity, unmatched local
  continuation intent, acknowledged/uncertain sends, queued/processing worker
  controls and owned local/shared runners cannot release ownership.
- Full descendant ancestry, unique host/task identities, task-scoped retained
  artifact bytes/version/hash, repository cleanup and complete final usage are
  validated. Foreign claims/brains, client IDs used as tasks, duplicate/omitted
  coverage, incomplete counters and invalid token subsets refuse.
- Previously observed descendants cannot disappear from the final inventory,
  including a child whose root is missing from a partial earlier Pause report.
  Missing/foreign/old/oversized/changed handoff artifacts refuse.
- Freshness applies to every native, inventory, cleanup and usage observation.
  Evidence cannot predate the retained operation/journal, artifact or idle state;
  stale/future/non-finite times refuse. Reading never refreshes evidence.
- A successful synthetic settlement changes held tokens from 11,500 to zero and
  retains 1,000 actual tokens as unincorporated usage. A finished correction's
  12,650-token reservation is accounted once. Cached/reasoning subsets are not
  added twice, actual overruns remain charged and block subsequent admission,
  and later exact cumulative inclusion avoids double counting. Attempts persist.
- Worker status becomes `settled`, not `complete`; packet is held for separate
  review. Evidence axes, pilot state, preserved/archived flags and completion
  metrics are not promoted. Portfolio metadata separately counts settled tasks.
- Two fixture workspaces cannot reserve the same repository concurrently; after
  verified settlement the other may reserve it. Recovery of the old receipt
  neither removes nor changes that new owner's resource reservation. Settled
  descendant IDs cannot be rebound through the native lifecycle coordinator.
- Exact replay returns the original receipt after evidence expires; changed
  content refuses. Concurrent conflicting requests have one winner. Native
  creation/correction and legacy completion paths cannot reopen a settled claim.
- Failure after shared writes but before commit rolls back the journal, actual
  usage and release together. Failure during local attachment (including after
  its local audit event) leaves the shared settlement committed and local owner
  conservative, with explicit receipt-only recovery.
- A fixture subprocess exits with `os._exit(23)` after shared commit and before
  local receipt attachment. Restart/recovery and exact replay preserve one
  settlement and charge actual usage once without repeating release.
- Shared/native journal corruption, missing local receipts and divergent local
  identities refuse rather than silently resetting ownership. Construction and
  unsuccessful recovery do not create a settlement store.
- Pause, revoked work approval and unavailable new-work headroom do not conceal
  terminal accounting. Enrollment/adoption fences still prevent new settlement;
  recovery of an already committed receipt remains safe behind a later fence.
  Settlement invalidates old Pause inventory and never parks/resumes the brain.

## Evidence boundary and follow-through

All tasks, counters, native observations, cleanup observations and crash cases
are isolated fixtures. The coordinator checks supplied evidence consistency; it
does not independently observe native state, authenticate an external hash, stop
a task, archive it, run acceptance or prove that an external actor cannot wake it.
The Orchestrator skill's ownership and approval rules kept safe relinquishment
separate from work authorization and packet acceptance.

No CLI/HTTP/assistant settlement route, native transport, new-generation approval,
runner execution, not-created recovery, maintenance migration or public Play is
introduced. No dashboard process, installed skill, live ledger, schedule, native
task, model setting, credential, inference service or product repository changed.
No new UI component was added; JavaScript regressions are not browser acceptance.

See the [saved plan and internal contract](OWNERSHIP-SETTLEMENT.md) and
[roadmap](ROADMAP.md). Independently verified destination/resource evidence,
runner/result coordination, unresolved-creation recovery, new-generation
continuation, native transport and exact owner activation remain required before
a separately authorized real pilot. Local tests, GitHub checks, merge and live
runtime acceptance are separate evidence states.
