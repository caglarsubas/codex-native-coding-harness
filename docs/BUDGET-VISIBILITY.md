# Workspace budget visibility — WSP-04D7

Plan saved before implementation, after verified PR #51 merge
`ad3706347d4c1678cc591a06f11f740efe2980f4`.

## Scope and acceptance

- [x] Explicit authenticated selected-workspace inspection of the existing shared
  admission ledger, using bounded read-only SQLite connections. Missing stores
  remain missing; no controller, schema initialization or accounting write.
- [x] Reuse the kernel's arithmetic: recorded cumulative usage, held estimates,
  settled actual tokens not yet incorporated, checkpoint reserve and balance.
  Never turn missing/incomplete/stale counters into zero or available headroom.
- [x] Separate shared account windows and recorded global reservation counts
  from workspace phase allowances, historical log analytics and billing.
  Keep other workspace identities, paths, native IDs and proof content private.
- [x] Token usage page with explicit inspection, per-phase breakdown, freshness,
  blockers and next steps; cached overview/assistant metadata only. No inspection
  during polling or chat, no automatic retry, no public write control.
- [x] Local backend/API/UI regressions and disposable browser checks across
  populated, missing, stale and switched workspaces in the existing three-pane UI.
- [x] Update the roadmap and convergence evidence; retain live qualification,
  owner release/Play and no-extra-Actions-billing boundaries.

## Design

Use the existing editorial operations-ledger design context: assured, precise,
composed, with explicit unknown states. Start the Token usage page with the
phase-budget inspection, then keep local log analytics as a separate section.
Use readable accounting rows and progressive disclosure rather than a fabricated
utilization chart. Preserve both themes, keyboard focus and narrow-pane access.
The action reads saved accounting only; it neither measures native usage nor
requests a new sample. A valid snapshot never grants execution authority.

## Evidence boundary

Phase accounting is caller-supplied cumulative evidence, not independently
qualified native telemetry. Budget arithmetic may conservatively overlap partial
observed usage and reservations until a complete sample incorporates settlement.
Do not add cached-input or reasoning subsets twice. Account percentages cannot be
converted to tokens or distributed as workspace wallets. Phase allowances are
not an account bill, and balances from separate phases are not one shared wallet.

Inspection is a historical shared-store snapshot, not a lock, a readiness decision
or a cross-database transaction. Local revision and expiry are visible; ordinary
dashboard refresh must not silently refresh shared evidence. Host evidence,
maintenance rollout, public phase releases and real autonomous acceptance remain
separate milestones. No live state, installed skill or dashboard restart is part
of this source increment.

## Owner workflow and protocol

1. Select the workspace and open **Token usage** (or the overview's budget link).
2. Choose **Inspect saved accounting**. This explicit authenticated GET reads
   `/api/workspaces/<id>/budget`; it accepts no parameters or write operations.
3. Read the phase rows separately. Expand accounting interpretation for limits
   and the formula. A negative balance is retained, not clamped to zero.
4. Unknown balance means missing/incomplete/old/changed evidence, not permission
   to proceed. Ask the designated brain/operator to reconcile via the existing
   evidence procedures. Missing platform/host capabilities still require their
   separately reviewed implementation and qualification, not another approval.
5. Download the inspected JSON snapshot if needed. This is a private browser
   download with original times, not a retained proof, bill or acceptance report.

The reader verifies private regular database identities around each read, checks
registered workspace/brain identity and existing journal/projection bindings, and
fails closed on malformed, missing-pointer or oversized evidence. It reads at
most 4,096 rows / 4 MB per selected table, 128 selected-workspace allocations and
the existing bounded current journal records; each database has a five-second
query deadline. An invalid inspection replaces an older good cache, never reuses
its balance. No writer-store constructor, controller lease or schema setup is used.

Inspections expire for display after 60 seconds; the oldest constituent sample's
policy expiry or a changed local workspace revision can suppress the balance
sooner. Refresh/poll/chat does not re-read shared accounting. A fresh display
still describes only the saved snapshot: source effect context, native state,
enrollment, legacy owners and external activity are not re-qualified. Assistant
context has at most eight anonymous phase rows with omitted counts, numeric
account/capacity facts, original times and explicit historical boundaries; it
does not receive phase/task IDs, paths, proofs or foreign workspace details.

## Reproducible local checks

Run the full standard-library Python suite and all `tests/test_*_ui.js` suites.
For disposable browser QA, run
`PYTHONPATH=tests:. python3 tests/manual_budget_fixture.py` and open its fixture
link. It creates temporary synthetic ledgers, disables the notifier and uses no
inference credentials or native calls; Ctrl-C cleans up the temporary ledgers.
Do not use the running portfolio dashboard or real admission store as a fixture.

Verified 2026-09-21: **1,372 Python tests** and **10 JavaScript UI suites** passed;
all web JavaScript syntax, Python compilation and whitespace checks passed.
Disposable two-workspace browser checks covered populated accounting, an empty
second workspace, the overview link, keyboard disclosure persistence, light/dark
themes, a 460-pixel viewport and automatic stale-snapshot balance suppression.
No browser console warnings/errors were observed. Missing-store/no-initialization,
corruption, size bounds, counter subsets, settlement charges, unknown/zero/negative
values and late workspace response rejection are covered by local regressions.
GitHub's workflow and run inventories were both empty at pre-push inspection.
No workflow, live install, native task, policy or running dashboard was changed.
