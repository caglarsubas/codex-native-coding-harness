# WSP-04C1 verification — recoverable dispatch admission

Date: 2026-09-19. Base: merged PR #23,
`f9614ae04fba383412f737752b31f84f89472f05`.

## Results

| Check | Evidence |
| --- | --- |
| Full Python 3.12 suite | 546 tests passed in 37.298 seconds |
| New bridge regression cases | 39 passed within the full suite |
| Admission-focused suites | 64 tests passed, including existing kernel and resource-audit cases |
| JavaScript regression suites | All seven passed: decisions, missions, panes, run readiness, task contracts, workspace Pause and workspace routing |
| JavaScript syntax | `node --check web/app.js` passed |
| Diff whitespace | `git diff --check` passed |

## What was exercised

- Exact run, task approval, contract, seed, workspace, brain, database and resource
  bindings. The shared claim fingerprints the immutable dispatch intent, so an
  unbound claim with a matching ID cannot be silently adopted.
- Positive work/review/handoff reservations, declaration estimate floor, complete
  cumulative usage coverage, checkpoint reserve, current account headroom and reset
  windows. Missing usage is not zero; stale evidence blocks advancement.
- Local pilot/concurrency limits, global slots, phase attempt counts and canonical
  repository exclusion. Two independent fixture brains can reserve different
  repositories concurrently; aliasing the same repository has one winner.
- Concurrent repeated reservation returns the same owner and claim; concurrent
  creation-intent calls have one winner. No returned value is a native permit.
- Exceptions before shared commit roll back the claim and resources but preserve
  the local intent. Exceptions after shared commit preserve the claim; a restarted
  bridge attaches it without making another reservation, including after Pause.
- A local creation boundary commits before shared advancement. If the latter fails,
  the worker stays in-flight, recovery cannot rewind it and a second begin refuses.
- A separate fixture Python process exits with `os._exit(17)` after the shared
  creation boundary and before the local receipt. SQLite reopening preserves both
  ownership records; recovery attaches the receipt without repeating the boundary.
- Pause at either cross-store gap stops further advancement. A partially attached
  creation intent blocks workspace parking as an in-flight effect. Revocation,
  expiry, held-task drift, stale preflight and changed repository bindings refuse.
- A real fixture checkpoint/release produces generation 2 while preserving the
  same phase allocation, 1,234 observed tokens, 11,500 held tokens and its claim.
  Changed limits/mappings change the binding, never the same-phase allocation ID.
- Database identity drift, missing claims/resources, enrollment metadata and each
  file-only workspace/adoption fence refuse. Recovery does not recreate missing
  ownership, reset counters, remove a fence or reactivate a workspace.
- Legacy local bind/transition/runner methods refuse admission-managed workers;
  the completion method has the same explicit coordination fence. Existing legacy
  behavior remains covered by the full regression suite.

## Delivery boundary and remaining work

This is source plus isolated-fixture evidence, **not live autonomous execution**.
The bridge has no public write route, native tool calls, effect argv, scheduler,
allocation initializer or maintenance-fence release. Native creation-result
binding (pending versus confirmed IDs), continuation, independently verified
native/resource evidence, ownership settlement/release and exact owner-facing
Play still need integration and qualification. The fixtures explicitly arrange
unpaused state and fresh synthetic evidence; production cannot infer these facts.

All existing enrollment/adoption fences remain in force. No live ledger, token
budget, dashboard process, installed skill, heartbeat, model configuration,
inference service, credential, product checkout or product authority was changed.
The Orchestrator skill's approval and ownership boundaries guided these limits.
No new UI was introduced, so no new browser-acceptance claim is made.

The [implementation plan and protocol](DISPATCH-ADMISSION.md) and
[roadmap](ROADMAP.md) identify the next integration. GitHub checks, merge,
running revision and a separately authorized supervised pilot remain separate
evidence states from the local tests above.
