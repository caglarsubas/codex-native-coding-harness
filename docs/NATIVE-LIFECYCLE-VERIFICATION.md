# WSP-04C2 verification — native lifecycle receipts

Date: 2026-09-19. Base: merged PR #24,
`9b76707e942974f7262af78115793e44469b8493`.

## Results

| Check | Evidence |
| --- | --- |
| Full Python 3.12 regression suite | 585 tests passed in 38.645 seconds |
| New native lifecycle cases | 39 passed within the full suite |
| JavaScript regression suites | All seven passed: decisions, missions, panes, run readiness, task contracts, workspace Pause and workspace routing |
| JavaScript syntax | `node --check web/app.js` passed |
| Diff whitespace | `git diff --check` passed |

## Exercised behavior

- Pending client IDs and confirmed host/task identities remain distinct. Pending
  IDs cannot be submitted as confirmed task IDs. Host/client/task bindings cannot
  be erased or replaced by later observations, including uncertain results.
- Another workspace's shared owner or any registered brain cannot be rebound as
  this worker. Exact designated-brain controller and workspace/database/intent
  bindings remain required; no authority leaks between two fixture workspaces.
- Result/activity observations are bounded, fresh and monotonic. Missing/stale,
  future, malformed, foreign and changed evidence refuse. Observations can be
  retained after Pause/expiry/maintenance fencing without restoring execution.
- Exact historical replay is receipt-only and never regresses newer state.
  Conflicting writes at one expected hash have one winner. Modified records,
  missing journal history/pointers, and divergent local identity/receipts require
  explicit recovery rather than silently resetting ownership or progress.
- Same-task edit-correction intents require current authority, exact approved
  contract, current preflight, confirmed idle evidence, fresh admission and a
  retained same-repository instruction artifact with verified bytes/version/hash.
  Unsupported operations, missing/foreign/oversized/changed artifacts, revoked
  approval, expired authority and stale capacity evidence refuse.
- A correction holds additional work/review/handoff tokens without a second task
  slot or a fresh phase allocation. The fixture increases held tokens from 11,500
  to 12,650. Idle, acknowledged, uncertain and finished receipts do not release
  those tokens or repository ownership.
- Acknowledgment is not turn completion. A finished-turn receipt requires prior
  acknowledged delivery, exact task and continuation identity, newer evidence,
  explicit idle activity and boolean progress. Unknown sends cannot be resent;
  idle polling cannot finish them or reset consecutive no-progress counters.
- Two finished no-progress corrections block another correction. Exact replay
  counts each result once. A later genuinely finished progress result can reset
  the consecutive counter; activity polling cannot.
- Exceptions before shared commit roll back journal and token writes while
  preserving the durable local in-flight marker. Exceptions after commit leave
  recoverable receipts. Pause or preflight drift between continuation commits
  prevents shared advancement without clearing the local marker.
- A separate fixture process exits with `os._exit(19)` after shared continuation
  commit and before local attachment. Reopening/recovery preserves ownership and
  the 12,650-token hold; replay does not repeat the reservation or any send.
- Native lifecycle/continuation hashes participate in workspace Pause inventory
  binding. A newer native observation invalidates an older retained pause report,
  even when worker status and task identity otherwise remain unchanged.
- Legacy kernel bind/block/runner/settlement and creation-only recovery cannot
  bypass the new coordinator or desynchronize admission-managed ownership.

## Evidence boundary

All tasks, observations, artifacts, token usage and failures above are isolated
fixtures. They prove local source behavior, not that a real native task was
created, messaged, paused, finished, accepted or archived. Evidence hashes and
activity fields are trusted caller assertions, not native attestation.

No native transport, public write route, scheduler, runner/settlement release,
maintenance-fence release, new-generation continuation approval or public Play is
introduced. The source upgrade does not initialize live journals or allocations.
No dashboard process, installed skill, live brain, heartbeat, model settings,
credential, inference service, product checkout or private portfolio state changed.
The Orchestrator skill's ownership and approval rules guided these boundaries.
No new UI component was added, so no new browser-acceptance claim is made.

The [saved plan and internal contract](NATIVE-LIFECYCLE.md) and [roadmap](ROADMAP.md)
retain the remaining work: coordinated runner/settlement and ownership release,
independent destination/resource evidence, new-generation continuation approval,
native transport, exact owner Play activation and a separately authorized pilot.
GitHub checks, merge and live runtime acceptance remain distinct from these tests.
