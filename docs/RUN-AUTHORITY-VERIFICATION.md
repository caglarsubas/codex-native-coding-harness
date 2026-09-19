# WSP-03B4 verification — internal run authority

Date: 2026-09-19. Base: merged PR #22,
`9e0485fb72bfdc5e1df56876a8eeae8b38a5d5b0`.

## Results

| Check | Evidence |
| --- | --- |
| Full Python 3.12 suite | 507 tests passed in 35.182 seconds |
| New run-authority tests | 48 passed within the full suite |
| JavaScript regression suites | All seven passed: task contracts, run readiness, workspace Pause, decisions, workspace routing, missions and panes |
| JavaScript syntax | `node --check web/app.js` passed |
| Diff whitespace | `git diff --check` passed |
| Older helper compatibility | Exact merged PR #22 `core.py` refused reopening a fixture v3 ledger with `Unsupported ledger version` |

The compatibility probe used a disposable fixture, not a live ledger. The format
marker does not stop an already-running cached older helper. Stop/upgrade all old
processes and reconcile ownership before any separately authorized future rollout.

## Authority and recovery cases

- Exact mission/review/workspace/brain bindings, explicit owner confirmation,
  native-defaults-only policy and bounded expiry. Prepare-only mode refuses.
- Exact-owner approval, separately labeled delegated brain approval, and Harness
  exact-owner-only behavior. No inferred model/effort/speed fallback.
- Current run, task contract, approval hash, operation and actor are rechecked.
  Held/completed tasks, changed mappings/seeds/contracts, old generations and revoked
  approvals refuse; historical replay cannot restore authority.
- Pause, brain stop, mission revocation and controller recovery retain an atomic
  run fence. A committed Pause fences approval even when it races another request;
  a stale optimistic revision must be refreshed before submitting again.
- A brain stop reuses the cooperative workspace checkpoint procedure. The exact
  parked checkpoint must be released by a new owner intent; an ordinary brain
  wake does not restore the prior generation.
- Mandatory phase/plan/budget/evidence stop reasons survive an ordinary pause.
  They require a newly reviewed scope before release. A second safe stop records
  the newer checkpoint without resetting the generation or limits.
- Identical concurrent requests return one receipt; different requests sharing a
  revision have one winner. Simulated exceptions roll back grants, stop commands,
  format changes and state pointers together.
- A separate fixture Python process exited at the pre-commit event boundary.
  Reopening recovered the unchanged ledger; retry created generation 1 exactly
  once. This is a crash-recovery test, not a native task interruption.
- Missing/corrupt run pointers cannot reset generations or regain legacy
  dispatch. Corruption does not prevent an otherwise valid safety pause/park.
  Malformed/oversized replay records refuse without exposing their contents.
- No run-authorization write route was added to the HTTP server, CLI or assistant
  action catalog. No source upgrade or read automatically creates a run record.

## What these results do not prove

The kernel returns authority facts, not a native execution permit. Shared
admission, real cumulative usage, host capability verification, native creation
and continuation effects, uncertain-effect recovery and public Play remain
unconnected. No runtime task was created, resumed, archived or merged by these
tests. No token allocation/counter or ownership claim was reset.

No live ledger, dashboard process, installed skill, heartbeat, inference service,
credential, product checkout or product approval was changed. There is no new UI
control to visually qualify in this backend increment; existing JavaScript tests
cover regressions, not a new browser acceptance claim.

The plan and required adapter work are retained in [RUN-AUTHORITY.md](RUN-AUTHORITY.md).
GitHub checks, merge, deployed/running revision and a real supervised Play/Pause
pilot must be verified independently of these local source/fixture results.
