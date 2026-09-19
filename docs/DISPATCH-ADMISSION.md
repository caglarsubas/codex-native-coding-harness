# WSP-04C1 — recoverable dispatch admission bridge

Plan saved before implementation, continuing merged PR #23 (`f9614ae`).

Connect the internal run-authority and capacity kernels without enabling native
execution. This increment owns reservation and the one-shot creation-intent
journal. Native calls, result binding/continuation, owner-facing Play, adoption
release and live rollout remain separate increments.

## Implementation checklist

- [x] Pin registered workspace/database identities and an existing admission
  store; never initialize policy, allocations or live state on construction.
- [x] Bind cumulative phase allocation to workspace, phase, reviewed repository
  bindings, canonical resources and limits, independent of run generation.
- [x] Retain exact task/run/estimate intent before shared reservation. Recover a
  partial commit using the same claim, never a second reservation.
- [x] Recheck current authority, preflight, pause, local concurrency, fresh usage,
  capacity and retained ownership at the one-shot creation-intent boundary.
- [x] Preserve uncertain ownership after any partial creation-intent commit;
  recovery may copy receipts but cannot retry creation or release resources.
- [x] Test races, restart, partial commits, stale evidence, changed bindings,
  checkpoint/generation budget continuity and all maintenance fences.

## Safety and delivery boundary

Internal Python integration only, with no CLI, HTTP, assistant or installed-skill
write route. Every result says `executionAuthorized: false` and provides no native
argv. A future native adapter must consume the boundary within its own checked
workflow, verify destination/resource identities and preserve pending/confirmed
IDs, uncertain results and continuation authority. An admission receipt alone must
never be used as a reusable native permit.

The bridge does not unpause dispatch. Authorization remains owner intent until a
future exact activation route exists. Successful tests explicitly configure
isolated fixtures; they are not native acceptance or live ownership evidence.

Existing enrollment/adoption fences remain absolute. There is no release path,
and neither an empty imported inventory nor a consistent external assertion opens
capacity. No changes to the running dashboard, installed skill, schedules, native
tasks, product repositories or private portfolio state are part of this delivery.

## Budget and transaction protocol

The caller must already have an explicitly initialized immutable allocation. Its
ID derives from workspace and phase ID, not run hash, generation or request ID.
Its binding includes exact limits and repository/resource mappings; changed limits
or mappings require a future explicit migration, not a new same-phase budget.
Closed allocations cannot be reopened. Counters and task-attempt history remain
cumulative. Work-token estimate must cover the task declaration, with additional
positive review and handoff reserves.

Lock order is registry, workspace, admission. Cross-store commits are **not**
atomic: first retain a workspace owner/immutable intent, then commit the shared
claim before its workspace attachment. An interrupted attachment is recovered by
the deterministic claim ID and exact fingerprint, including the immutable dispatch
intent hash (run, approval, contract, seed and database identities). A pre-existing
unbound claim cannot be adopted just because its ID and estimate match.
Recovery after pause/expiry is
receipt-only: it cannot make a missing reservation or advance creation.

Creation intent first commits a local `starting` owner (`creation_pending`), then
advances the shared claim to `starting` before attaching that receipt locally.
This prevents Pause from mistaking a partially attached creation boundary for an
unstarted reservation. Either committed side means no retry. Missing native identity is
unknown, never evidence of non-creation. Even if this increment cannot call native
tools, it conservatively retains that boundary for the future adapter. Settlement,
ownership release, native result binding and continuation are not exposed here.

## Internal methods

WSP-04C2 now provides [native lifecycle coordination](NATIVE-LIFECYCLE.md): result
observations and same-run correction-intent receipts. Native transport, ownership
release and activation remain unimplemented. Use that coordinator once a claim
has native observations; creation-only recovery refuses rather than rewinding it.

| Method | Retained effect; never native execution |
| --- | --- |
| `phase_allocation` | Pure deterministic allocation specification; no store writes or identity attestation |
| `DispatchAdmission.reserve` | Exact designated-brain intent, then shared slot/token/repository reservation and attached receipt |
| `DispatchAdmission.begin_creation` | One-shot local in-flight intent, repeated authority/admission checks, then shared boundary and receipt |
| `DispatchAdmission.recover` | Attach an existing exact claim after interruption, including after Pause/expiry; never advance creation |

The allocation's canonical repository keys and preflight checks remain trusted
caller assertions. Matching hashes prove consistency, not independent observation
of Git remotes, native worktrees or host capabilities. The future adapter must
independently verify these identities and coverage before any native effect.

`intent` means a workspace owner exists but shared reservation may be absent.
`reserved` means both receipt and claim are retained, not that a native task exists.
`creation_pending` means the local one-shot boundary committed; shared advancement
may be absent. `creation_intent` means both creation-intent records are retained.
Neither latter state proves native creation; both prohibit retry and block safe
parking until separately reconciled. Recovery never rolls them back to `reserved`.

No existing worker can be silently replaced with a new run, approval or estimate.
Legacy native binding, transition, runner and completion methods explicitly refuse
admission-managed workers so their local record cannot diverge from shared ownership.

See [verification evidence](DISPATCH-ADMISSION-VERIFICATION.md). WSP-04C2 adds
result/same-run correction coordination. Ownership settlement/release, independent
resource observations, new-generation continuation approval and native transport
remain before exact owner activation and a separately authorized real pilot.
No browser acceptance or live rollout is claimed by these backend increments.
