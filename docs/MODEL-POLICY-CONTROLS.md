# WSP-04G — owner model/effort policy controls

Plan saved before implementation against verified PR #57 merge
`90e969273481eb941392863944f714edc2621bdc`.

- [x] Add explicit read-only inspection of retained capability observations,
  reviewed mission, policy versions, revocation and eligibility. Missing/stale
  capabilities are a blocker; no model names or rankings are invented.
- [x] Add authenticated signed review/revoke previews and atomic confirmation
  through the existing policy kernel. Bind workspace/session/ledger/revision,
  exact mission/capability and owner-selected profiles, quality/token floors and
  escalation ceiling; historical retries must not restore revoked policy.
- [x] Add structured controls under Mission & authority, with workspace-isolated
  drafts, explicit choices, unchecked confirmation and visible policy history.
  Explain native defaults, caller-supplied observations and quality judgments.
- [x] Keep polling/chat to cached closed metadata. Verify API/kernel/UI races,
  disposable browser flows and the full local regression suite.

Policy review is not run authorization or a model call. Review/revocation fences
existing run authority but does not kill tasks, notify the brain, start Play,
release maintenance, reset usage or modify global settings. Use safe Pause for
active work; policy review requires paused setup. Speed and Ultra stay gated.
The dashboard cannot record capabilities or choose profiles on the brain's behalf.

No live state, installed tooling, model provider, native task, schedule, runner or
Actions configuration changes. Use only local/disposable fixtures and preserve
the existing editorial design. Native counter/cleanup qualification and rollout
remain separate; this increment closes the remaining owner model-policy surface.

## Owner workflow

1. Select a workspace, open **Mission & authority**, and choose **Inspect model
   policy**. This reads saved evidence only, without a provider/native call or
   shared-admission initialization. An empty workspace does not inherit a catalog.
2. Before review, pause dispatch and review the exact mission. The designated
   brain must separately record the actual destination model/effort schema using
   WSP-04E; this page cannot collect or refresh it. Observations expire after five
   minutes and remain caller-supplied, not host attestation. Missing, stale or
   damaged evidence explains the blocker without inventing supported settings.
3. Choose **Configure profiles**, then add one or more explicit profiles. Model,
   supported effort, owner-assessed quality tier, work-token floor, complexity
   floors and escalation ceiling start unset. At most 16 unique profile IDs and
   model/effort combinations are allowed. Quality is 1–4, work tokens 1–1 billion,
   and escalations 0–2; complexity floors cannot decrease. At least one profile
   must meet the highest floor. These are judgments/estimates, not benchmarks,
   monetary pricing or spending caps. Speed is null and Ultra is refused.
4. Preview the exact workspace, phase, profiles, limits and capability observation.
   Read the fence warning and explicitly check the confirmation. Recording review
   replaces the current policy and fences any existing run; it never re-arms it.
5. Revoke an intact current policy by giving a non-secret reason, previewing and
   explicitly confirming. A stale or damaged catalog does not prevent revocation.
   For active work, use safe Pause separately: this control is not a process kill
   or a claim that the brain/worker has reached a checkpoint.
6. Expand **Policy versions** for newest-first immutable review documents, original
   times, hashes and choices. Revocation is a retained receipt plus the current
   denial flag, not a rewritten policy document or a new review version. Old
   versions cannot become authority by viewing or retrying them.

Drafts are private to this browser tab and workspace, not persistent settings.
Closing the editor or a failed submission preserves them; a changed mission needs
explicit draft rebinding. Copying a recorded policy is an explicit action, not a
default. A model change clears its effort choice; catalog order never remaps a
saved model name. Workspace generations reject late responses and invalidate old
confirmation screens. An uncertain response keeps the identical signed request
for manual retry; there is no automatic resend. After a dashboard restart, inspect
saved state before preparing a new request because prior signing keys are gone.

## API and validation boundaries

Selected-workspace routes only:

- `GET /api/workspaces/{id}/model-policy-controls`: explicit read-only inspection.
- `POST /api/workspaces/{id}/model-policy-controls/preview`: `review` or `revoke`.
- `POST /api/workspaces/{id}/model-policy-controls/confirm`: exact signed proposal
  with literal `confirmed: true`.

Existing loopback host/session authentication, same-origin and scoped CSRF checks
apply. Writes reject duplicate JSON keys, non-finite values, extra fields, query
parameters and bodies above 32 KiB. A workspace lock rejects simultaneous HTTP
operations. Five-minute previews bind session, workspace, ledger path/inode,
revision/context and exact mission/capability/policy. The server derives bindings;
the browser cannot supply an actor, approval receipt or replacement catalog.

The existing policy kernel is shared by preview and confirmation. Confirmation
rechecks context and writes the review/revocation, run fence and receipt in one
transaction. Competing changes have one winner; failures roll back. Exact receipt
replays validate retained policy integrity but do not renew timestamps, reset
usage or undo later revocation. Changed catalog/mission/pause state, replaced
ledger, expired preview or restart refuses a new effect.

History is bounded before decoding to 128 versions / 2 MB retained bytes;
inspection output is at most 128 KB and signed preview at most 28 KB. Bounds or
broken hash chains/pointers require explicit operator recovery or migration, never
pruning history or treating it as a new empty setup. Revocation/catalog status
markers must remain present for an existing policy.

Polling and assistant chat receive only cached, closed numeric/status metadata
with original inspection time, revision, expiry and historical labels. No model
names, profiles, mission documents, hashes or revocation rationale enter that
projection. There is no owner-policy CLI, assistant action, legacy unscoped route,
capability-write route, run-release route or Play endpoint. Existing native
handoff, quality, admission, Pause, maintenance and Harness gates are unchanged.

## Verification and rollout

Local verification: `python3 -m unittest discover -s tests -v` passed all 1,513
tests. All fourteen JavaScript UI suites, syntax checks for every web script,
Python compilation and `git diff --check` passed. Remote workflow/run inventory
was empty before publication; no Actions workflow was added or executed.

The new kernel/HTTP tests cover authenticated scope, exact confirmation, stale
catalog/mission/revision, damaged evidence, history bounds, signature/session/
ledger/restart binding, concurrency, rollback and receipt-only retry after
revocation. The UI suite covers empty choices, stable catalog identities,
mission rebinding, unchecked confirmation, draft isolation and late responses.

A disposable two-workspace browser exercise created and revoked a fixture policy,
read its retained history and checked the no-catalog workspace. Dark/light themes,
keyboard focus and the resized narrow workspace pane were visually verified;
no console errors or warnings were observed. The fixture used invented model
labels and no inference service, native task or live ledger, then was shut down.

This source delivery does not install/restart the dashboard or update the brain's
skill/schedule. A separate rollout must quiesce older writers and prepared
handoffs; no mixed-version or downgrade safety is claimed. Supported native
counter/cleanup evidence is still an external qualification gate for Play.
