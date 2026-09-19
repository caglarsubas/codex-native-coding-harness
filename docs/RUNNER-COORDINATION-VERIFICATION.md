# WSP-04C3b verification — shared runner coordination

Date: 2026-09-19. Base: merged PR #26,
`9f5aa46fe8864ec4b45fd19aa7933dad85cc30b3`.

## Results

Final results after the last source edit:

| Check | Evidence |
| --- | --- |
| Full Python 3.12 regression suite | 672 tests passed in 43.462 seconds |
| Runner-specific cases | 45 passed within the full suite |
| JavaScript regression suites | All seven passed: decisions, missions, panes, run readiness, task contracts, workspace Pause and workspace routing |
| JavaScript syntax | `node --check web/app.js` passed |
| Diff whitespace | `git diff --check` passed |

Commands: `python3.12 -m unittest discover -s tests -v`,
`node --check web/app.js`, `node --test tests/test_*_ui.js`, and
`git diff --check`. Tests use the installed Python 3.12 and Node runtimes;
no dependencies or runtime tools were downloaded.

## Exercised behavior

- Runner keys must be pinned to the exact phase allocation. Current designated
  controller, run/approval, `test` operation, native idle, preflight, retained
  instruction bytes and execution hash are required. An actual edit-only fixture
  cannot reserve acceptance capacity. Harness policy explicitly refuses.
- Extra work/review/handoff estimates increase a fixture claim from 11,500 to
  12,650 held tokens without a second task/slot. Missing or stale evidence,
  invalid estimates, changed execution/artifact bytes and insufficient headroom
  cannot acquire. Expired/revoked work authority and maintenance fences refuse.
- Two workspaces concurrently compete for the same runner: one reservation wins
  and the other remains unmodified. An existing local owner also blocks admission.
- Launch is local-first and one-shot. Replays return receipts, not send permission.
  Concurrent launch requests have one winner. Changed local identity/stage or
  marker bytes refuse; Pause, preflight and budget changes between transactions
  retain the conservative pending marker. Generic native polling, correction and
  settlement cannot bypass an owned runner or unresolved launch.
- Unknown process outcome preserves ownership. Exact task/host/process identity
  is required and a known identity cannot disappear/change. Exit retains its code
  (including nonzero), but does not release the runner or promote acceptance.
  Observation/cleanup evidence must be fresh, finite and ordered after the journal.
- Release requires every idle/process-tree/cleanup flag, the exact reservation
  and reconciled exit (or no launch intent). Only the runner is released. Repository
  and estimated tokens stay held until full terminal settlement. Unlaunched
  cancellation does not replenish the one-attempt allowance.
- Safety observations and cleanup can proceed after Pause without resuming work.
  Maintenance allows observation/recovery but not new release. Exact committed
  release replay remains receipt-only behind a later fence and expired evidence.
  Owned/in-flight runners block parking; launch markers participate in Pause
  ownership binding. Historical no-runner Pause/settlement binding shapes remain
  unchanged.
- Shared rollback leaves reservation, ownership and tokens intact. Failure after
  shared commit but before local attachment recovers only the local receipt.
  Four fixture subprocesses call `os._exit(19)` at the post-commit boundary for
  acquisition, launch, process exit and release; reopen/recovery/replay preserve
  exactly one effect and the original token hold.
- Another workspace can reserve a runner after the first shared release commits,
  before its local receipt attaches. Recovery of that old receipt does not touch
  the newer shared owner. A historical released-runner observation likewise does
  not erase another local worker's runner ownership.
- After cleanup, a fresh scoped correction and terminal settlement remain valid.
  The fixture retains 13,800 estimated tokens across creation, runner and
  correction, then conservatively charges 1,000 supplied final actual tokens.
  This is accounting, not passing acceptance or a claim about measured live usage.

## Evidence boundary and remaining gates

Every task, process, account/usage sample, cleanup observation and crash case is
an isolated fixture. This coordinator validates supplied assertions and immutable
bindings; it does not independently observe a runner or authenticate evidence.
No acceptance process, native send, kill, archive or retry is performed. The
Orchestrator skill's ownership rules kept launch, cleanup release, terminal
settlement and packet acceptance separate.

No CLI/HTTP/assistant write route, installed-skill change, live ledger migration,
dashboard restart, schedule change, product edit, credential, inference request
or model-setting change is included. No UI component changed; JavaScript tests
are regression evidence, not new browser acceptance. GitHub checks, source merge,
installed/running revision and real runtime acceptance are separate claims.

See the [saved plan and API contract](RUNNER-COORDINATION.md) and
[roadmap](ROADMAP.md). Not-created recovery, independent result acceptance,
trusted host/native observations and transport, Harness execution-policy adapter,
new-generation continuation, migration and exact owner Play activation remain
before a separately authorized real pilot. This source increment does not enable
autonomous dashboard Play.
