# GitHub result evidence verification

Scope: WSP-04C3f, based on PR #34 merged at exact commit
`5b307232bf0941904e51221a6d8ec53fb6b9db02`. PR #34 was independently verified merged
at `2026-09-20T03:38:02Z`; fetched `origin/main` matched that commit.

## Evidence boundaries

| Boundary | Result |
| --- | --- |
| Source | Internal exact GitHub PR/policy/check collector and provenance-aware result review |
| Remote observation | Explicit read-only GETs; no push, test execution, PR edit or merge permission |
| CI | Exact-head/provider-bound metadata only; inaccessible/empty/incomplete policy remains unverified |
| Acceptance | Independent criterion/semantic/preservation review is still required |
| Live state | No workspace ledger write, native task/message, usage baseline, allocation, installed skill, schedule or dashboard change |
| Rollout | No autonomous Play, real pilot, trusted Harness run, runtime or tenant-acceptance claim |

The orchestrator skill's designated-brain and approval boundaries shaped this
implementation: collection cannot schedule work, accept a packet or activate a
workspace. The source helper uses existing GitHub CLI authentication only. No
credential, private prompt, artifact body or live ledger is included in this PR.

## Local verification

```sh
python3 -m unittest discover -s tests -v
node --check web/app.js
node --test tests/test_*_ui.js
git diff --check
```

Python 3.12: **988 tests passed**, including **39 new GitHub-evidence tests**.
All **7 JavaScript UI test files passed**. Syntax and whitespace checks passed.
This increment changes no UI rendering; these results are not browser/runtime
acceptance. Hosted checks and the new PR's merge state remain separate evidence.

Fixture coverage includes:

- Exact remote/head/base/branch identity, fork/rename refusal, provider binding,
  classic/effective policy union and redaction of PR/check text.
- Empty requirements, unavailable endpoints, missing providers/checks, ambiguous
  reruns, unsupported workflows/merge queues/rules, skipped/neutral/pending/failure.
- Duplicate/incomplete/oversized inventory and JSON, malformed policy, exact suite
  coverage, raw policy/PR/check drift and independent CI-versus-merge state.
- Real subprocess transport fixtures: fixed GET/host/version, private environment,
  bounded output, timeout, safe error handling and no automatic transport retry.
- Current approved task/settlement/remote binding, actual Harness-policy refusal
  before I/O, Pause during I/O, concurrent observation and transaction rollback.
- Exact historic replay after Pause/expiry/fence without I/O or timestamp renewal;
  corrupt/missing journals, request receipts and artifact provenance.
- Collected proof supports separate review but cannot be promoted or used for an
  unrelated axis; failed CI supports rejection, never acceptance. Freshly written
  review timestamps cannot renew stale original collection time.

## Read-only remote smoke check

On 2026-09-20, the standalone projection helper queried this tooling repository's
already-merged PR #34 twice per endpoint, without constructing a workspace observer
or writing any ledger. Expected identity was fetched independently first:

- PR head: `5f4aea6fc6916136f1d2b06265185a12e229c902`.
- PR base: `2c1acc3478e950fece554f62c211223ae7825990`.
- Branch: `codex/wsp-04-runner-handoff`.

The collector observed `merged` with merge commit
`5b307232bf0941904e51221a6d8ec53fb6b9db02`. CI remained `unverified`, with issues
`classic_policy_unavailable` and `no_required_checks`; `mergeAuthorized` remained
false. This proves the current read-only transport/projection handled that public
PR, not that its CI passed or that a live workspace is ready. Authenticated passing
required-check coverage was exercised with fixtures, not claimed from this smoke.

Complete native descendant/counter/host evidence, broader workflow/preservation
qualification, trusted Harness acceptance, continuation/rereview/archival, exact
owner activation and separately authorized supervised pilots remain open gates.
