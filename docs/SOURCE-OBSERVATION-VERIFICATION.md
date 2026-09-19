# WSP-04C3e verification — exact local source observation

Date: 2026-09-19. Base: merged PR #29,
`02152fa96c039c76a1ce5c9814e6e2ab362b67e1`.

## Delivered source

An internal standard-policy source observer for an exactly bound, settled task.
It measures existing local commit/tree structure against the approved base and
branch, retains a versioned source artifact and immutable collection/request
journals, and supplies provenance-checked evidence to separate result review.
Out-of-scope findings are retained, never approved automatically.

No command executes checked-out code. Git runs with fixed argv, isolated config
and environment, no transport/helpers, bounded output/time and pinned local
object identity. Collection is read-only against the repository; only the local
ledger retains its proof. No native task or token-budget state is changed.

## Executed verification

| Check | Result |
| --- | --- |
| `python3.12 -m unittest discover -s tests -p test_source_observation.py -v` | 38 passed, 9.416 seconds |
| `python3.12 -m unittest discover -s tests -v` | 806 passed, 58.946 seconds |
| `node --check web/app.js` | Passed |
| `node --test tests/test_*_ui.js` | All 7 test files passed |
| `git diff --check` | Passed |

Python used the installed Homebrew 3.12 runtime; Git was the installed Apple Git
2.39.2 at `/usr/bin/git`. All source inspection tests use real temporary Git
repositories and isolated synthetic ledgers. No live portfolio or product
checkout was inspected. JavaScript checks are automated regressions, not live
browser acceptance. No UI changes are included.

## Exercised boundaries

- Exact commit rehash, ancestry, branch tip, tree IDs and complete changed paths.
  Dirty working-tree content is not read; repository file hashes, inodes and
  modification times stay unchanged. Renames retain both added/deleted paths.
- Conventional linked worktrees, packed refs and packed objects. Original Git
  config, replacement refs and inherited targeting/configuration environment are
  ignored. Missing local objects fail without transport; shallow/grafted/alternate
  storage, symlinked object/ref metadata, changed symlinks/gitlinks, invalid branch
  identity and an unrelated base refuse. Moving the branch during inspection
  prevents proof retention.
- Command timeout/output limits, raw diff truncation, noncanonical/invalid paths,
  empty changes, duplicate paths and over-200-path inventories. No unbounded shell
  command, repository hook, filter, packet acceptance command or fetch is added.
- Wrong controller/task, stale revision, changed settlement, revoked/expired run,
  Pause before/during inspection, maintenance replay and accepted-result limits.
  Harness policy and remote-only identity refuse before source filesystem I/O.
- Atomic artifact/journal/request/event retention, concurrent identical-request
  replay, event failure and real process exit before/after commit. Failed reads
  leave no source artifact. Shared ownership/accounting and worker/queue state
  remain unchanged.
- Collector byte/provenance/commit/path-set/request/settlement binding, missing
  collector journal or request receipt, altered receipt and stripped provenance
  refuse. Every collector marker requires full validation. Generic older proof
  artifacts remain explicit caller-supplied assertions.
- Source evidence can support a separately verified result, but does not supply
  CI, required-check policy, preservation or semantic review. Out-of-scope source
  may support changes-required evidence, not verified source. The original
  measurement timestamp participates in freshness; replay never recollects or
  refreshes clocks, including after Pause/expiry/fencing.

## Evidence limits and rollout

This is structural local source evidence, not a hostile-filesystem sandbox,
remote/push/PR/CI attestation, preserved patch, semantic correctness, verified
native inactivity or tenant acceptance. Git and the local filesystem are trusted.
Before/after identity checks are observations, not a resource lock or protection
against malicious concurrent object rewrites/ABA. Blob availability, all object
contents and a clean worktree are not proven. See the contract for exact bounds.

No public source-observation/activation route, native worker, live allocation or
ledger, product repository, installed skill, heartbeat, dashboard process, model
setting, inference call or credential was changed. Source delivery, PR/merge,
runtime rollout and supervised acceptance remain separate. Autonomous Play is
not enabled by this increment.

Next prerequisites include trusted CI/remote/preservation and native/host
collection, transport integration, Harness-specific execution/acceptance,
new-generation continuation/rereview, maintenance migration, exact owner-bound
activation and a separately authorized supervised pilot.

See [saved plan and contract](SOURCE-OBSERVATION.md),
[result review](RESULT-REVIEW.md) and [roadmap](ROADMAP.md).
