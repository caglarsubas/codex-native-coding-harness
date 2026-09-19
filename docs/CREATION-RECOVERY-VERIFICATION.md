# WSP-04C3c verification — reconciled non-creation recovery

Date: 2026-09-19. Base: merged PR #27,
`7b83a9dd24e7edcc7a35248441dbd133729c145c`.

## Results

| Check | Evidence |
| --- | --- |
| Full Python 3.12 regression suite | 719 tests passed in 47.612 seconds |
| New creation-recovery tests | 47 passed within the full suite |
| JavaScript regression suites | All seven passed: decisions, missions, panes, run readiness, task contracts, workspace Pause and workspace routing |
| JavaScript syntax | `node --check web/app.js` passed |
| Diff whitespace | `git diff --check` passed |

Commands: `python3.12 -m unittest discover -s tests -v`,
`node --check web/app.js`, `node --test tests/test_*_ui.js`, and
`git diff --check`. Installed runtimes only; no dependency downloads. The full
suite was rerun after the final source edits. Initial fixture issues involving
snapshot evaluation timestamps, same-tick test times and a control already
refused by the public API were corrected before the successful full run.

## Exercised behavior

- Explicit creation attempts can close from shared `starting`, exact local-first
  `creation_pending` with a still-reserved shared claim, pending client IDs and
  unconfirmed uncertainty. Inspection remains read-only and does not establish
  absence, release ownership or create a terminal table.
- Unattempted reservations, missing claims, detached shared/local receipts and
  confirmed or previously observed native work refuse. A confirmed task cannot
  become absent through a later unknown activity observation. Pending IDs and
  native history remain retained after settlement; another workspace cannot bind
  a resolved client ID as its task.
- Complete finality/absence/descendant/pending/effect assertions are all mandatory.
  Missing, false or integer-as-boolean flags, nonempty inventories, wrong host,
  omitted/substituted client ID and foreign attempt/usage bindings refuse.
- Usage must explicitly cover this attempt with complete zero task counters.
  Missing, partial, negative/subset-invalid or consumed tokens cannot become zero.
  Resource keys must match the owned repository set exactly with full exit/cleanup.
  Stale, future, non-finite and out-of-order evidence refuses.
- Artifact bytes, repository, exact worker/intent references, post-attempt time,
  ID/version/hash and size are checked. Missing/changed/foreign/old/oversized
  artifacts refuse. Missing reconciliation bytes after closure block local
  recovery and the special safe-Pause exception.
- Native observations invalidate old candidate hashes. Retained Pause tasks,
  pending clients observed as tasks and retained stop bindings contradict absence.
  The whole native chain is checked, including corruption deeper than the latest
  two entries; history loss does not reopen ownership.
- Closure releases the exact repository/slot/held-token reservation but leaves
  the immutable attempt, estimates, pending IDs and cumulative phase usage intact.
  A fixture with 1,234 already observed tokens retains that usage after the
  11,500-token reservation closes. Explicit later coverage incorporation does not
  reset counters or attempts. All old creation/native paths remain fenced.
- The packet is held with no retry authorized. Worker status is `settled`, not
  `complete`; evidence axes, pilot state and archival flags do not advance.
  Portfolio counts settlement separately from completed/accepted work.
- Concurrent conflicting closures have one winner and one terminal journal row.
  The confirmed-terminal and non-creation coordinators cannot substitute outcomes.
  Wrong controllers/workers, allocation drift, retained worker controls and local
  runners refuse. Revoked work approval, Pause and exhausted new-work budget do
  not suppress safety accounting; maintenance still blocks new release.
- Shared transaction failure rolls back all release/accounting changes. Local
  receipt or local audit-event failure leaves a committed shared outcome and a
  conservative local owner. A fixture subprocess exits with `os._exit(29)` after
  shared commit; receipt recovery behind a later maintenance fence does not
  repeat release. Another workspace may acquire the freed repository before the
  old local receipt attaches, and recovery preserves that newer owner.
- Exact replay remains receipt-only after evidence expiry; changed requests or
  corrupt terminal history/local identity refuse. Dedicated recovery does not
  unpause the brain, reset usage, resend creation or change model settings.
- Fresh Pause inventory recognizes a retained hash-bound non-creation receipt
  without requiring a nonexistent task checkpoint, while retaining the worker
  and pending ID. Empty inventory before settlement still blocks. Settlement
  invalidates an older inventory, missing proof blocks, and a contradictory later
  task observation becomes an explicit recovery conflict.

## Evidence boundary and follow-through

All native identities, creation outcomes, counters, inventories, resource cleanup
and crash cases are isolated fixtures. Supplied finality and absence are checked
for consistency, not independently collected/authenticated. An error, missing ID
or empty list alone never becomes proof. A future trusted native/operator adapter
must establish complete, final non-creation with no late effects before supplying
these assertions. The Orchestrator skill's ownership rules informed the permanent
attempt closure, no-retry boundary and separate cleanup/accounting evidence.

No native transport, automatic retry, CLI/HTTP/assistant recovery route, live
ledger setup, installed skill update, dashboard restart, schedule change, product
edit, credential use or model override is included. No new UI component changed;
JavaScript tests are regression evidence, not browser or real pilot acceptance.

See the [saved plan and internal contract](CREATION-RECOVERY.md) and
[roadmap](ROADMAP.md). Separate result acceptance, independently verified native/
resource observations, trusted Harness runner integration, new-generation
continuation, native transport, maintenance migration and exact owner Play
activation remain. Local tests, GitHub checks, source merge, installed/running
revision and real runtime acceptance are separate evidence states.
