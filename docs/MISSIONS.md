# Mission and authority configuration — WSP-03A

This increment implements **configuration and owner review, not activation**.
The existing exact packet queue, brain controls, pilot limit and native scheduling
are unchanged. A reviewed configuration is not packet approval, delegation or a
token reservation. No configuration operation sends a brain notification.

## Dashboard workflow

1. Select a development workspace, then **Mission & authority** below Overview.
2. Create a draft with the mission goal, measurable success criteria, exclusions,
   one phase objective and the mandatory owner checkpoint. Describe earlier stop
   conditions, such as a material plan change or a required budget revision.
3. Select repositories, repository-relative allowed paths and proposed operations.
   Nothing is selected implicitly. Manual-merge repositories cannot include merge;
   any Harness scope prohibits phase-delegated approval. Product instructions,
   approved packet boundaries and trusted execution contracts always take precedence.
4. Choose a proposed approval mode and explicit total/parallel task limits, phase
   token allocation and included checkpoint reserve. These values are not currently
   enforced, account observations, billing figures or provider hard limits.
5. **Save draft**, inspect the complete rendered contract and its SHA-256, then
   explicitly **Record owner review**. Each change creates a new immutable version
   requiring fresh review. **Revoke this review** withdraws only the configuration
   review; it does not stop a running task or alter an existing packet approval.

Alternatively, open Roadmap and choose **Prepare draft** on one current action
of an observed published source. The browser opens one unsaved workspace-local
draft with the action as its initial goal and an explicit source reference in
the phase objective. It starts in `prepare_only` mode with no repositories,
paths, operations or numeric allowances selected. Fill every required field,
inspect the saved version and use the same separate owner-review step above.
Existing unsaved drafts are retained rather than replaced. Old source buttons
fail closed after a workspace or observation change. This handoff has no backend
write or authority effect until the owner separately saves the Mission draft;
save itself still grants no execution authority.

The screen explains why Play is unavailable. WSP-03B/C and WSP-04 must implement
run generations, delegated packet admission, mandatory phase release and shared
resource/budget safeguards before activation. Cooperative workspace Pause is
implemented separately in [WSP-03B1](WORKSPACE-PAUSE.md), without Play. Future
activation must require a **new explicit owner action** bound to the exact contract;
upgrading must not turn any existing `reviewed` configuration into a running mission.
Model/effort/speed choices are deliberately not simulated by this form.

Use **Run readiness → Inspect run readiness** to inspect the current exact review,
prepared packet paths and retained platform evidence together. The diagnostic
separates actions for the owner, brain/operator and platform developer. A satisfied
check or candidate binding is not authority; see [the inspection contract](RUN-READINESS.md).

Unsubmitted edits are kept separately per workspace in the current browser tab.
Switching or navigating away and back retains them; reloading the page clears them.
Saved versions and receipts persist privately in the workspace ledger. Polling does
not overwrite an active editor. Stale writes are refused, with the local draft retained.
An uncertain request can be retried manually with the same ID; no automatic retry.
An old retry returns its original receipt and the latest state, never restores an
old draft or a revoked review. Review checkboxes are never inferred from chat.

## Contract and persistence

`GET /api/workspaces/{id}/mission` returns current configuration, binding issues,
activation blockers, the latest 20 immutable versions and an earlier-document
pointer. Exact documents and receipts use the existing authenticated document
reader. Older documents remain linked by `previousHash`; events retain review
receipts. Text is rendered as text, never as HTML or executable instructions.

`POST` to that same route accepts one closed shape:

```json
{
  "id": "unique-retry-stable-id",
  "operation": "save",
  "expectedRevision": 0,
  "spec": {
    "goal": "Deliver an offline fixture milestone",
    "successCriteria": ["Independent fixture checks pass"],
    "exclusions": ["No live infrastructure"],
    "phase": {
      "id": "phase-one",
      "title": "Fixture foundation",
      "objective": "Implement a bounded offline fixture",
      "checkpoint": "Owner reviews independent evidence before phase two",
      "stopConditions": ["Material plan change", "Budget revision needed"],
      "scope": [{
        "repository": "registered-repository-id",
        "allowedPaths": ["src/fixture/**", "tests/test_fixture.py"],
        "operations": ["edit", "test", "commit", "open_pr"]
      }]
    },
    "authority": {
      "approvalMode": "exact_owner",
      "maxParallelTasks": 1,
      "maxTasks": 2,
      "tokenBudget": 100000,
      "checkpointReserveTokens": 10000
    }
  }
}
```

The numeric example is synthetic, not an allowance for any real workspace.
Modes are `prepare_only`, `exact_owner`, `phase_delegated`. Supported operation
labels are `edit`, `test`, `commit`, `push`, `open_pr`, `merge`; none execute argv.
Allowed paths must have an explicit relative prefix; whole-repository wildcard,
absolute, traversal and ambiguous path spellings are refused. A draft is limited
to 32 KiB, 20 repositories, 40 paths per repository and bounded text/list sizes.

Review/revoke replace `spec` with `documentHash` and `confirmed: true`, using
`operation: review|revoke` and the current mission revision. Version counts saved
contracts; revision also counts review/revoke. Unrelated metrics/checkpoint events
do not invalidate review, but a repository identity/mapping/policy change does.
The server pins workspace, brain, version, scope and repository mapping hashes.
Stale configuration remains readable, not silently rebound or reapproved.

Writes use the workspace ledger's SQLite transaction, immutable snapshots and an
optimistic mission revision. Replay fingerprints include workspace, actor and the
entire request. Sessions and CSRF are scoped as for other workspace mutations.
Unknown fields, model/native arguments, cross-workspace document hashes, reused
IDs with different content, stale writes and absent confirmation are refused.
No new database table, background scheduler, external service or secret is needed.

## Brain procedure

Use explicit registry routing:

```sh
python3 -m orchestrator.cli --platform /absolute/private/.platform --workspace example mission-state
python3 -m orchestrator.cli --platform /absolute/private/.platform --workspace example mission-draft /absolute/private/mission.json --revision 0 --id stable-proposal-id
```

`mission-draft` requires the active designated-brain controller token through the
existing environment mechanism. A stopping/parked brain cannot draft. The CLI has
no owner review/revoke command. The local owner controls the files/processes on
this machine: this protocol is not an OS security boundary against that owner.
Propose only within the owner's requested planning scope; do not use drafting to
silently expand a mission. Dashboard owners may prepare/review while a brain is
stopped because these operations grant no execution authority and do not wake it.

The compact inbox and assistant know that the configuration is inactive. Assistant
context includes only status, proposed numeric limits, bounded phase/checkpoint
text and activation blockers, not mission document bodies, paths or receipts.
Chat has no mission mutation capability; direct the owner to the review screen.

## Verification and rollout boundary

Tests cover immutable versions, exact-hash review/revocation, uncertain retries,
concurrent edits, stale mapping detection, Harness/manual-merge restrictions,
invalid/empty scopes, numeric limits, brain identity/stop gates, workspace/CSRF
isolation and no notification/dispatch effects. Browser checks use disposable
workspaces with no native notification bridge. No live workspace authority or
budget is configured by implementing or testing this increment.

Local validation on 2026-09-18: 248 Python tests passed; mission retry/isolation,
workspace routing, brain-control presentation and pane JavaScript suites passed;
JavaScript syntax and skill validation passed. The isolated two-workspace browser
rehearsal covered save, review, revoke, new-version history, draft retention across
workspace switching, visible invalid-budget feedback and a 390-pixel form with no
horizontal overflow. These are local/fixture checks, not hosted CI, a native-worker
pilot or proof that the live dashboard is running this revision.

## Optional standard merge capability

The authority object may include `mergeMode: manual` (also the omitted default),
or `brain_exact_pr_v1`. The latter requires `phase_delegated`, all-standard scope,
exactly one repository with the `merge` operation, and its existing
`required_checks` repository policy. Manual repository policy still refuses it.
The dashboard makes this a deliberate draft selection; owner review and separate
Play remain required. It does not grant a merge from a configuration review.
See [STANDARD-MERGE.md](STANDARD-MERGE.md). Before future merge-enabled Play, update
the installed launcher from its stale schema-1-only source to the exact compatible
merged source. This enabling phase remains manual-merge and stops at an open PR.
