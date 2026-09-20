# WSP-04C3f — exact GitHub result evidence

Plan saved before implementation, following PR #34 merged at
`5b307232bf0941904e51221a6d8ec53fb6b9db02`.

## Plan

- [x] Collect bounded, read-only GitHub PR, branch protection, effective branch
  rules, exact-head check suites/runs and combined statuses using existing `gh`
  authentication. No arbitrary endpoint, command, credential or repository input.
- [x] Bind the request URL to an allocation-pinned conventional GitHub remote,
  exact approved branch/base/result and confirmed terminal settlement. Refuse
  Harness before network access; recheck authority after collection.
- [x] Preserve unknown/incomplete policy and check coverage. Empty requirements,
  ambiguous checks, unsupported rules and unavailable endpoints cannot verify CI.
  Repeat bounded observations to detect change; never claim an atomic GitHub lock.
- [x] Retain a redacted, provenance-bound artifact and immutable receipt without
  changing worker completion, shared ownership, budget or native state.
- [x] Bind separate result review to collected PR/CI projections and original
  collection time. Prevent forged collector labels and unrelated evidence axes.
- [x] Verify fixture transport, completeness, identity, policy drift, replay,
  tampering, transaction failures and all regressions; update roadmap/docs.

## Boundary

The WSP-04C3f kernel was internal-only. The later [result handoff](RESULT-HANDOFF.md)
adds a designated-brain CLI under stricter owner-approved standard-policy scope.
No live workspace collection, HTTP/assistant control, installation, runtime restart
or Play activation follows from source delivery.
This measures remote metadata, not source semantics, workflow trustworthiness,
deployment, runtime, preservation, host cleanup, tokens or tenant acceptance.
The brain remains the scheduler and independent review remains required.

## Internal contract

Construct `GitHubObserver` from the existing `DispatchAdmission` bridge. Its
`observe(controller_token, worker_id, request)` method requires the designated
brain and a settled, unaccepted standard-policy task in the current approved run.
The closed request contains:

| Field | Binding |
| --- | --- |
| `id` | Immutable per-worker request identifier |
| `expectedRevision` | Current workspace revision |
| `settlementHash` | Exact shared terminal settlement and attached local receipt |
| `commit` | Exact full result Git object ID; never a branch/ref expression |
| `prUrl` | Canonical credential-free `https://github.com/OWNER/REPO/pull/NUMBER` |

The PR remote must match a `repo-remote:` identity in the original task intent and
allocation. Head repository, head branch, head commit and base commit must match
the approved result/seed. Forks, renamed repositories, Enterprise hosts and moved
bases are unsupported, not silently accepted. A moved base needs a separately
reviewed contract; the collector cannot expand the result-review schema. No local
repository is read, no fetch occurs, and no identity is inferred from the working
directory. Harness refuses before network access.

The trusted local operator supplies installed `gh` and existing authentication.
Direct argv uses explicit `GET`, hostname `github.com`, JSON Accept header and
pinned REST version `2022-11-28`. No login flow, new key, shell or caller-selected
endpoint is added. The environment contains only CLI/auth, certificate and proxy
settings; debug, alternate host, inference keys and prompts are not propagated.

## Observation and coverage

Each of two consecutive rounds reads the PR, classic base-branch protection,
effective active branch rules, exact-head check suites, exact-head check runs
(`filter=all`) and combined commit statuses. Both normalized projections and all
raw response hashes must match across rounds; observed drift refuses retention.
This is drift detection, not an atomic snapshot, lease or merge-time guard.
Raw PR text, check output, details URLs and error bodies are discarded. Only
identity/state metadata, policy/check identifiers, issue codes and response hashes
are retained. Open PR test-merge SHAs do not count as actual merge commits.

The classic/effective required-check union preserves provider IDs. Result check
names include context plus provider, preventing different providers' requirements
from collapsing. Wrong-app runs cannot satisfy pinned requirements. Legacy
statuses cannot prove app identity: a matching legacy context with a pinned app
leaves CI unverified. Same-name reruns from one app are ambiguous; the collector
does not guess which is latest. Unpinned requirements consider every matching
provider and legacy status.

Only completed `success` verifies a required check. Pending, skipped and neutral
are not passing in this conservative observer. Failures are retained; missing
checks or unknown coverage keep CI unverified. Empty requirements are never green.
Unsupported rules such as required workflows, code scanning, merge queues or
future rule types also prevent verification. Non-CI requirements (reviews,
signatures, deployments, etc.) are not merge-eligibility checks here; verified CI
does not mean the PR is mergeable or authorized to merge.

Unavailable optional endpoints produce named unknown-coverage issues. A classic
protection 404 cannot distinguish absent from inaccessible policy and stays unknown,
even if other endpoints succeed. An unprotected repository can have passing runs
without qualifying verified CI here. Requirements are not invented from its runs.

Each response is bounded to 512,000 bytes and five seconds; total collection is
bounded to 30 seconds. Inventory requests ask for 100 entries but accept at most
40, requiring declared total counts to equal returned lists. Effective rules use
the same stricter bound, avoiding an unseen second page. Malformed, duplicate-field,
incomplete or oversized responses cannot become green. Independent suite coverage
keeps the observer below the check-runs endpoint's suite truncation limit. Reports
over 16,000 bytes refuse retention. There is no pagination loop or automatic retry.

## Retention, replay and review

Network I/O runs outside registry/workspace/admission locks. Authority, settlement,
allocation, worker projection, run state and revision are rechecked afterwards.
Pause, maintenance, changed approval or stale evidence refuses new retention.
Snapshot, artifact, request receipt and event commit atomically; no shared state,
worker status, queue, ownership or token accounting is changed.

Artifacts carry `github_result_observer_v1` provenance, observation hash and exact
task/intent/commit references for CI and merge. Result review rechecks canonical
bytes, journal, request receipt and exact PR/CI/base/branch/commit/settlement
projections. It cannot promote CI, claim an unmerged PR merged, or use this metadata
for semantics, preservation, acceptance criteria, runtime or another evidence axis.
Removing collector markers does not allow fallback to generic evidence. Older
unlabelled caller-supplied proofs retain the older explicit trusted-caller boundary;
this optional collector does not retroactively authenticate them.

Collection start is `observedAt`, not receipt/review time. It must follow settlement
and stay fresh at retention and new review. Repackaging old bytes cannot renew it.
Exact request replay returns the old integrity-checked receipt, even after Pause,
expiry or maintenance, without network calls, mutation or authority renewal.
Changed content under the same ID refuses. Concurrent identical requests may do
redundant GETs but retain one result. Failed local retention can be recollected
because no remote mutation or native effect occurred.

See [verification](GITHUB-EVIDENCE-VERIFICATION.md). Semantic/criterion/preservation
review, full native descendant/counter and host-cleanup evidence, trusted Harness
acceptance, continuation/rereview/archival, owner activation and a supervised live
pilot remain separate gates. No installed operator or dashboard process changes.

## API references

Checked against GitHub's official contracts:

- [PR identity and merge fields](https://docs.github.com/en/rest/pulls/pulls#get-a-pull-request).
- [Classic protection](https://docs.github.com/en/rest/branches/branch-protection#get-branch-protection)
  and [effective branch rules](https://docs.github.com/en/rest/repos/rules#get-rules-for-a-branch).
- [Check runs and suite limit](https://docs.github.com/en/rest/checks/runs#list-check-runs-for-a-git-reference)
  and [combined statuses](https://docs.github.com/en/rest/commits/statuses#get-the-combined-status-for-a-specific-reference).
- [REST versions](https://docs.github.com/en/rest/about-the-rest-api/api-versions):
  the pinned `2022-11-28` version remains supported through March 10, 2028.
