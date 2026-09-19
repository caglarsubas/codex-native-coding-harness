# WSP-03B3 verification — phase-bound task contracts

Verified on 2026-09-19 against PR #21's merged base
`963b262fbadb2066c7c616a981bdf74902fd8a86`. This report records source and
isolated-fixture evidence, not live activation or tenant acceptance.

## Automated checks

| Check | Result |
| --- | --- |
| Python 3.12 `-m unittest discover -s tests -v` | 459 tests passed, 35.011 seconds |
| Task contract tests within the full suite | 34 passed |
| Task contract, Run readiness, workspace Pause, decision, workspace, mission and pane JavaScript suites | All seven passed |
| `node --check web/app.js` and `node --check web/task-contracts.js` | Passed |
| `git diff --check` | Passed |

Tests use temporary ledgers/repositories and synthetic identities. They cover:

- Exact workspace, designated brain, reviewed mission, repository policy,
  packet and inheritance binding; revoked/replaced reviews and seed revisions.
- Closed operation/settings fields, phase path containment, checkpoint reserve,
  manual-merge refusal and Harness's exact-owner approval boundary.
- Requested settings remaining unverified and unapplied; no native calls,
  notification, admission reservation or execution authority from a proposal.
- Immutable linked versions, same-request replay, conflicting request IDs,
  concurrent proposals and transaction rollback including the format marker.
- Invalid/missing/oversized declarations and malformed pointers remaining
  blocked; foreign-workspace documents suppressed from the current declaration.
- Prior legacy approval/preflight invalidation; legacy approval, reservation and
  begin-creation refusals; reprepare retaining the declaration and its fence.
- Registered-workspace-only CLI/API, authenticated reads, strict query shape,
  no browser write route, and discarded late responses after a workspace switch.
- The first v1-to-v2 proposal requiring paused dispatch and no retained active
  worker/runner; ordinary reads leaving the metadata format unchanged.

An additional isolated compatibility probe executed the exact PR #21 `core.py`
against a fixture ledger containing a declaration. That older helper refused to
reopen it with `Unsupported ledger version`. This does **not** prove an already
running old process will stop: it may have cached a ledger object. Stop and
upgrade all older processes before live use, as documented in
[the rollout boundary](TASK-CONTRACTS.md#format-compatibility-and-rollout).

## Browser verification

Used `tests/manual_task_contract_fixture.py`, an ephemeral authenticated local
dashboard with two synthetic workspaces, no configured inference service and no
native notification bridge. No user dashboard or live ledger was used.

- At 1280 × 720, **Approved queue → Review** showed the bound/not-activated
  declaration, operations, token estimate, rationale and version history. The
  seed-only approval control was absent for the declared packet.
- Requested model/effort/speed defaults were distinct from **Not applied /
  unknown**. Host support and owner policy remained explicitly unverified.
- Expanding the exact JSON/history disclosure survived ordinary five-second
  polling without collapsing the user's reading position.
- At 390 × 844, the workspace and document widths were 390 pixels without
  horizontal page overflow. Long hashes wrapped; the exact JSON remained
  scrollable. The temporary viewport override was reset afterward.
- **Run readiness → Inspect** recognized the declaration and removed the
  missing-declaration blocker, while retaining run-authority, native settings
  and legacy-dispatch blockers. The diagnostic did not authorize execution.
- Switching to the second workspace showed its empty queue, with no first-
  workspace declaration or review content. Browser warning/error logs were empty.

The fixture server and verification tab were closed after testing.

## Delivery and remaining boundary

Impeccable guidance kept the feature within the existing typography, colors and
three-pane layout. Details/history use progressive disclosure; no dependencies,
external assets or new design system were introduced.

No live state-format upgrade, installed skill update, heartbeat change, inference
request, product source edit, task creation or permission change was performed.
GitHub checks, merge state and running revision must be verified independently of
these local results.

Autonomous Play is still unavailable. The next integration must bind exact owner
activation/run generations and version-bound approvals to shared admission and
native-effect checks. Neither an owner-reviewed mission nor this task declaration
may become executable permission merely because new source is installed.
