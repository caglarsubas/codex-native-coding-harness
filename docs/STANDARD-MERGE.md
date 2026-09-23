# Exact PR merge handoff for standard projects

Manual merge remains the default. A future phase can opt in with
`authority.mergeMode: brain_exact_pr_v1`, phase delegation, and exactly one
standard-policy repository with `merge` in its reviewed operations. That repository
must already have `mergePolicy: required_checks`. A manual repository policy is
still a refusal; this feature neither edits it nor creates a migration route.
Missing `mergeMode`, or `manual`, grants no merge capability. Mission review alone
does not activate Play. Harness, strict/enrolled workspaces and legacy owners
retain their existing restrictions.

**Rollout prerequisite:** before any future merge-enabled Play, stop older writers
and update the installed launcher from its stale schema-1-only source to the exact
compatible merged source. Verify the launcher resolves that revision and supports
the standard schema-v4 protocol. Old prepared handoffs must be quiesced; their
source records lack the new local layout binding and cannot be promoted to
issuance. Already issued boundaries remain one-shot and require outcome
reconciliation. Source delivery does not install anything, update live state,
change repository policy, restart the dashboard or activate a phase.
This enabling phase itself stops at an open PR for manual owner merge.

## Authority and evidence

Only the existing designated brain can use the `standard-brain` operations below.
The helper never executes a merge. It takes the normal registry/ledger locks,
checks current authority, releases them for bounded read-only collection, and
rechecks the exact revision, owner review, mission, run, repository identity and
registered-task state before committing a handoff. The exact branch tip, origin and
retained common-directory/layout binding are checked again under these locks after
remote I/O, immediately before durable issuance. Pause can commit during I/O.
A stopped/expired/completed run, brain stop, changed binding, failed independent
review or unresolved registered task refuses new permission. A pending merge
blocks another task claim in that phase and claims on that repository in other
registered workspaces. Existing PR bindings cannot be reused in the registry.

The registered task must be completed with an immutable `standard_result` whose
`evidence.headSHA` is the exact result commit. `headSHA` is an optional addition to
standard `finish` evidence; old results without it remain valid results but cannot
be merged by this handoff. The brain must independently cross-check source, test
results and preservation. A worker reply alone is insufficient.

Preparation retains a content-addressed binding of workspace, run, completed task,
result, repository mapping/identity, PR URL/number, base/head branches and SHAs,
mission/review hashes, independent evidence, source preservation and one immutable
request ID. Only one PR request may be prepared per run, permanently consuming
that slot even if the PR closes without merging. A later phase cannot rebind that
PR with a new request. Historical receipts never issue fresh permission.

Local inspection uses the existing configuration-isolated Git object view. It
requires a canonical GitHub origin, exact local result branch, available base/head
objects and an ancestor base; it refuses out-of-task changes, shallow/alternate
storage, changed symlinks/submodules and incomplete bounded output. It retains
complete changed-file blob bytes, binary patch bytes, object identities and path inventory in the
private ledger. This is local result preservation, not an off-device backup of
all history, LFS objects or external submodules. It runs no checkout, hooks, filters,
tests or workflow. The immutable result, review and retained patch all bind the
same exact head.

GitHub inspection uses existing credentials through the bounded installed `gh api`
GET reader, plus one fixed bounded public GraphQL query per round for effective
queue and PR auto-merge state. This query covers classic protection as well as
rulesets; REST classic protection alone omits the queue setting. Missing, null,
unsupported, errored or enabled queue state, queue membership, and existing
auto-merge requests refuse permission. Two matching rounds verify repository/PR
identity, open/non-draft state, exact base/head, mergeability, base branch policy,
effective rules, complete
check suites/runs/statuses and workflow inventory. Unknown protection, unsupported
rules, missing/pending/failed checks, provider/rerun ambiguity, truncated inventory
or drift refuse permission. No endpoint failure means no policy. Only a positive
unprotected-branch observation can establish absence of classic protection;
effective rules must still be available. Canonical hashes bind the entire bounded
branch, classic-protection and effective-rule responses, including review counts,
strictness, restrictions, bypass metadata and unknown fields; availability and
unsupported-policy issues remain explicit. Check response hashes are compared too.
Duplicate context names across any runs/providers/statuses refuse before required
check selection, including optional successful reruns in the no-workflow path.
The complete bounded status history must agree with combined status; a full history
page (or full effective-rule page) refuses because those endpoints have no total
count. No raw API bodies are retained.

When no required checks are configured, permission requires a positive empty
GitHub workflow inventory and no workflow paths in either exact base or head,
plus complete local Python, JavaScript, syntax and diff evidence. The journal
records `noWorkflowObservation: true`; CI remains unverified, never fabricated as
passing. Local test results and semantic review are designated-brain assertions,
not independently authenticated process/CI attestation. The helper validates their
coverage, identity, outcome and freshness, and measures the source/diff itself.

## Typed operations

All requests include `operation`, `runId`, `taskId` and `requestId`. Send them only
through the private standard controller. No HTTP merge-effect or assistant action
exists. State/dashboard reads only project retained history; they never collect,
connect, refresh observation clocks or issue permission.

- `merge_prepare`: add `binding` and `evidence`. Retains one immutable proposal;
  emits no command. Identical retry returns its existing record without collection.
- `merge_check`: add fresh `evidence`. Recollects source and GitHub data, validates
  the retained source and current authority, then atomically records **issued**.
  Only this first successful response can include the fixed argv below. A competing
  check, lost response or historical replay cannot get another argv.
- `merge_receipt`: add `delivery`, one of `acknowledged`, `unknown`, `failed`.
  Records **uncertain** for all three. Command exit/acknowledgment alone does not
  establish the exact remote outcome. The first delivery receipt is immutable.
- `merge_reconcile`: no additional fields. Performs fresh read-only PR observation,
  never emits argv. A matching merged PR becomes **merged**; a matching closed,
  unmerged PR becomes **not-merged**. Open after issue remains **uncertain**, since
  delayed delivery can still execute. Terminal replay keeps its original time.

`binding` has exactly `prUrl`, `number`, `baseBranch`, `headBranch`, `baseSHA`,
`headSHA`. Only canonical github.com same-repository PRs and `codex/*` local head
branches are supported. Enterprise hosts, forks and merge queues need a separate
adapter. There is no arbitrary host, command, merge method or admin/force option.

`evidence` has exactly:

- `headSHA`, `resultHash`, `reviewer` (designated brain ID), `verdict: passed`,
  and a bounded `summary` of its independent review.
- `native: {observedAt, tasks}`. `tasks` must cover every registered confirmed
  task exactly once, each with `threadId`, `status` (`idle` or `completed`), and
  `trackedTerminals: none`. This is the cooperative registered-task guarantee,
  not whole-host process-tree assurance.
- `local: {observedAt, headSHA, complete: true, python, javascript, syntax, diff}`.
  Each category is an ordered array of `{argv, exitCode: 0, output}` with retained
  bounded nonempty evidence. Python requires
  `python3 -m unittest discover -s tests -v`; JavaScript requires `node PATH` for
  every committed `tests/**/*.js` file, sorted lexically. Syntax requires
  `python3 -m compileall -q orchestrator tests`, then `node --check PATH` for every
  committed JavaScript file, sorted lexically. Diff requires
  `git diff --check BASE_SHA HEAD_SHA`. The helper never executes these test arrays.

Changed-file blobs are rehashed against their exact Git object IDs and bounded to
two megabytes in total. Unchanged files remain in the retained task repository.
Observation timestamps must be original and less than five minutes old. Complete
coverage is required even in the required-checks path. Brain-supplied reports fit
the existing 64 KiB standard request bound. Collection bounds refuse oversized
source/inventories rather than silently truncating them. Never relabel an older
sample or summarize a partial test run as complete.

The sole issued argv is:

```text
gh api --hostname github.com --method PUT -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" repos/OWNER/REPO/pulls/NUMBER/merge -f sha=EXACT_HEAD_SHA -f merge_method=merge
```

This is the [synchronous merge endpoint](https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request),
with an exact server-enforced head SHA. It cannot request enqueueing or enable
auto-merge. If effective queue protection races the check, GitHub must refuse the
direct merge under its enforced protections; no fallback or asynchronous merge
endpoint is permitted. The former `gh pr merge` argv is unqualified because
[the CLI can enqueue or enable auto-merge](https://cli.github.com/manual/gh_pr_merge)
for queue-protected branches without an explicit `--auto` flag. A local fixture
verifies command selection and refusal/no-resend handling, not live GitHub policy
enforcement. Existing server-side actor exemptions are not changed or overridden.

Immediately before the one external call, the brain checks the latest state for
Pause/review changes and verifies the request still owns the issued boundary. It
executes the returned argv exactly once without a shell, added flags, or a retry.
If the response was lost, the brain stops before executing and reconciles. If a
stop arrives after issuance, it records uncertainty and does not send. A native
send cannot be made atomic with a local ledger transaction: head matching is
server-enforced, while base/policy verification has a cooperative check-to-effect
gap. GitHub remains responsible for enforcing server merge protections. This
feature does not claim a remote lock or eliminate concurrent external mutation.

## Outcomes and recovery

The dashboard and immutable run versions preserve **prepared**, **issued**,
**uncertain**, **merged** and **not-merged** independently from semantic correctness,
CI, deployment, runtime behavior, archival and phase acceptance. Observing an
already-merged exact PR records that fact with no command and no claim that this
brain caused it. Observation after Pause/revocation remains possible for an
existing journal; it never resumes work.

An issued/uncertain merge prevents Resume and closing/replacing its run until
reconciled. A safe paused checkpoint can retain the uncertainty. A prepared request
can be resumed only under its unchanged authority; there is no cancellation or
replacement API to regain a slot. An open prepared PR cannot close its phase through
this API; hold it for owner handling. Never delete a journal, reset a request ID,
replay a merge, infer non-delivery from timeout, or promote merge state into phase
acceptance.
