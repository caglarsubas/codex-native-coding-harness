# Native creation handoff verification

Scope: WSP-04D1 on the merged PR #30 baseline (`7f758d2`). Source implementation
and isolated integration fixtures only; no real task creation or live activation.

## Evidence boundaries

| Boundary | Observed result |
| --- | --- |
| Baseline | GitHub PR #30 merged; exact merge commit `7f758d26b659892edcfceb6f2b699b9381adb566` |
| Native capability | Current host exposes saved-project listing and native task creation; read-only project inventory schema v2 observed |
| Notification CLI | Installed `codex queue --help` describes messages to an existing task, not task creation |
| Creation interface | CLI emits exact native-tool-shaped arguments, consumes a one-use send check, and retains returned identity projections |
| Actual native send | Not run; fixtures supply pending/confirmed/uncertain observations |
| Acceptance/runtime | Not run; dashboard, installed skill, live ledger, schedules and product repositories unchanged |

The implementation follows the installed orchestration skill's brain-owned native
control boundary. It does not introduce an app-server/SDK runtime, private app API,
background scheduler or inference-service call. Current capabilities were checked,
not inferred from an old screenshot. Private project inventory was not copied into
this repository or artifact.

## Regression commands

```sh
python3 -m unittest discover -s tests -v
node --check web/app.js
node --test tests/test_*_ui.js
git diff --check
```

Local Python 3.12 result: **839 tests passed**, including **33 new native-creation
tests**. All **7 JavaScript UI test files passed**; JavaScript syntax and whitespace
checks passed. No new UI behavior was introduced, so this is regression evidence,
not a new rendered-browser or live task acceptance claim. Repository-hosted CI
status must be checked separately from these local results.

## What the new fixtures cover

- Real temporary Git repositories, isolated metadata reads, exact base ref and
  unchanged repository bytes; bounded seed and operation-scoped native defaults.
- Subprocess CLI begin/check/record/state/recover path using a temporary private
  platform, admitted task and native-tool-shaped pending then confirmed results.
- Exact owner approval; Harness and delegated first-pilot rejection before
  repository inspection; local project ID/path/host/Git matching and rejection of
  remote-only resource identity.
- Stale/future project evidence, expired account evidence, stale revisions, wrong
  controller, missing objects and changed common-directory identity.
- Concurrent callers obtain at most one handoff and one consumed send check.
  Missing check pointers/receipts cannot conceal an already consumed check.
- Pause during base reads, between local/shared creation commits and before send;
  lost handoff retention leaves owned uncertainty, never a new creation attempt.
- Pending client IDs stay separate; task IDs cannot collide with the brain or
  overwrite retained identities. Result acknowledgment always leaves activity
  unknown rather than inventing running/idle evidence.
- Late observations after Pause, uncertain-to-confirmed reconciliation, exact
  result replay and shared-first/local-attachment interruption recovery without
  resource release, unpause or duplicate native call.
- Read-only state and safe-Pause inventory invalidation; missing workspace, bad
  controller, oversized files, symlink and FIFO CLI input refusals.

These tests validate the protocol under a trusted brain and private local ledger.
They do not prove that an arbitrary caller-supplied hash is an authentic native
observation or that the external tool obeys the one-shot protocol. The gap between
the consumed check and the brain's native call is explicitly cooperative and
in-flight, not a distributed transaction.

## Remaining pilot work

Qualify native task/descendant and usage observations; connect supervised runner
execution and result evidence; add explicit owner setup/activation and the brain
operator integration; then run a tiny standard-policy pilot and preserve its real
acceptance evidence. Maintenance migration/release, adaptive model/effort/speed,
automatic phase continuation, archival and Harness trusted execution remain
separate gates. Merging this increment does not enable dashboard Play.
