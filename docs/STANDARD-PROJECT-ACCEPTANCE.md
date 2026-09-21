# Standard-project milestone acceptance — 2026-09-21

## Outcome and scope

The owner-approved cooperative standard-project path is implemented and exercised
with two disposable local Git projects, two designated native brains and two
real implementation tasks. This is a standard-project engineering milestone,
not strict Harness acceptance or a rollout into existing workspaces. The live
Harness dashboard, ledger, automations and installed skill were not changed.

The previous rolling iteration forecast is replaced by the finite
[completion contract](STANDARD-PROJECT-COMPLETION.md). Standard mode does not
require completing the remaining strict-assurance kernels first.

## Real native pilot

| Evidence | Alpha | Beta |
| --- | --- | --- |
| Bounded deliverable | Unicode-safe slug normalization | Numeric count, sum and mean with explicit empty input |
| Native tasks | One designated brain and one implementation task | One designated brain and one implementation task |
| Requested worker settings | gpt-5.6-sol / low | gpt-5.6-sol / low |
| Source commit | `68480f5f87277ce5879d8e50f40bcf0f9a025a89` | `ced0ebba9d0e66abb29f02ca050f9352d43a4ef3` |
| Independent local tests | 6 unittest cases passed | 3 unittest cases passed |
| Retained artifact | RESULT.md, v1 | RESULT.md, v1 |
| Artifact content SHA-256 | `aee1e1f0d898879c0b59309c92b183a1aacff92d6e9072414c603f404e2f6a06` | `98a7bc98dfd0cd347307c3f931c811764b6a032e979ae465314bb8236da3c3e9` |
| Final run/task state | Completed; controller released | Completed; controller released |
| Token observation | Unknown, not zero | Unknown, not zero |

These commits belong to local disposable repositories, not public delivery PRs.
Neither repository has a remote. Native task IDs, private registry paths and
authentication material remain in the local ledger, not this public report.
Alpha's final checkout was clean. Beta retains an untracked private `work/`
directory containing its brain's control request files; no whole-checkout cleanup
claim is made.

The actual browser/native sequence verified:

- Separate owner-confirmed Play for both workspaces and immediate fixed-message
  native delivery acknowledgements, without waiting for a heartbeat.
- Beta Pause before dispatch, followed by a parked checkpoint. Restarting the
  isolated dashboard retained its run, allowance and checkpoint. Explicit Resume
  continued that same phase.
- The two brains independently selected bounded tasks, retained inheritance,
  issued one native creation each, supervised the workers, inspected source and
  ran local verification before completing their phases.
- Preservation-only follow-ups exercised the new task-scoped `preserve`
  operation for both completed tasks. Re-preserving identical bytes retained v1
  rather than creating a duplicate. Old result records were retained as history.
- The rendered dashboard showed completed runs, no registered tasks in flight,
  explicit unknown usage, separate repository measurements and a combined 2/2
  cooperative completion count. The local code snapshot counted 74 Alpha lines
  and 61 Beta lines, 135 combined, under the existing counting method.
- Cross-workspace artifact links opened the originating workspace and its
  immutable reader. The Alpha result text and content hash were read in the UI;
  both artifact versions appeared in creation/reference order.

The live pilot used explicit local projectless mappings. Saved-project native
worktree creation was not exercised by these two pilot tasks. This is not a load
test or proof of simultaneous same-workspace execution.
Registered-capacity and same-repository exclusion were exercised by local
regression tests. Native API metadata does not attest actual per-turn settings.

## Defects found during the pilot

1. A shell-local controller token did not survive separate terminal calls.
   The brain correctly fenced and parked before creating a task. New private
   acquire/release helpers preserve the credential across bounded calls without
   printing it. The subsequent native Resume succeeded.
2. The initial pilot setup omitted artifact roots for the legacy importer.
   Setup now supplies explicit roots, and the standard protocol additionally
   retains only task-approved artifact paths inside the pinned Git repository or
   native worktree, without requiring a broad artifact root. Both real brains
   exercised that new path after completion. Artifact creation time remains
   unknown when unobserved; preservation time is not relabeled as creation time.
3. Final compatibility review found standard decision answers still pointed at
   the legacy receiver. The standard cycle now receives those exact version-bound
   inputs, with the existing outcome/artifact requirements. A regression verifies
   that free text never enters the fixed notification and that saved answers
   cannot wake or resume a stopping/paused brain.

## Verification and billing boundary

Local regressions cover the owner/session-bound controls, replay, stale reviews,
strict-mode fences, registered capacity, repository identity, uncertain creation,
pending native IDs, budget observations, checkpoint/resume persistence,
artifact versions and dashboard behavior. The skill validator and JavaScript
syntax checks are also required by the completion checklist.

Final verification on the complete implementation source:

- `python3 -m unittest discover -s tests -v`: **1,562 passed**, 294.755 seconds.
- All **16** `tests/test_*ui.js` Node suites passed.
- `node --check` passed for every `web/*.js` file.
- Source skill validation passed using the installed local validator.
- `git diff --check` passed. No runtime dependency was downloaded.

GitHub reported **zero Actions workflows and zero Actions runs** before this
branch was published. No workflow was added, enabled, dispatched or rerun; no
paid API was used. Native tasks used the owner's existing Codex allowance.
Local passing tests are not a claim of passing GitHub CI.

## Release and remaining boundaries

The single consolidated PR is for manual owner merge. Source merge and a live
rollout are separate: existing workspaces never opt in during upgrade. Follow
[standard onboarding](STANDARD-COOPERATIVE-RUNS.md) for a new standard workspace.
The isolated pilot dashboard is not the live Harness dashboard.

Standard mode promises registered-task coordination, partial observations,
conservative planning allowances and cooperative safe checkpoints. It does not
promise complete lifetime accounting, provider-enforced spending caps,
whole-process-tree cleanup, automatic merge/archive or native speed control.
Those are not silently included by a completed phase.

The separate Harness milestone retains its original evidence, isolation,
environment, runner and authority requirements. It remains unqualified by this
pilot and must not inherit a green acceptance state from standard mode.
