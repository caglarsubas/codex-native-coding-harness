# WSP-04E — owner-reviewed model and effort policy

Plan saved before implementation against PR #44 merge
`2f720dbb163634d07ead3d460f39eb43a77b50ce`.

- [x] Retain bounded, expiring local native-tool model/effort capability observations.
  They are designated-brain assertions, not independent host attestation.
- [x] Add an internal owner review/revocation kernel for exact mission-bound
  profiles, complexity quality floors, minimum work-token estimates and bounded
  same-task escalation. No HTTP/assistant activation route or preset approval.
- [x] Bind adaptive run authority to that exact reviewed policy; preserve native
  defaults unchanged. Changed capabilities, unsupported speed, stale policy and
  insufficient budget refuse without fallback or global configuration changes.
- [x] Retain brain selections and rationale; apply exact model/thinking arguments
  at the existing one-shot creation/correction boundaries. Runner messages inherit
  the observed task settings; no runner model override.
- [x] Keep requested, emitted, reported-applied and observed settings distinct.
  Missing, mismatched or stale observations block further adaptive task effects.
  Preserve historical reads and late facts after Pause without renewing authority.
- [x] Qualify selection, escalation, replay, races, budget/quality boundaries,
  foreign scopes, capability drift, Pause and regression behavior locally.

## Product and delivery boundaries

This is policy/handoff source work, not a live rollout. No task, model call,
installed skill, dashboard restart, schedule, allocation or maintenance release
is changed. No Actions workflow or job is enabled. Harness retains its trusted
adapter boundary. Public Play and the native brain operating loop remain separate.

The current native task tools expose per-task `model` and `thinking`; they do not
expose a speed parameter. This adapter therefore supports only null speed and
never substitutes an API service tier or changes global settings. Capabilities
must come from the actual destination tool schema, not a hard-coded model list.

Official [model guidance](https://learn.chatgpt.com/docs/models) describes effort
as a quality/latency/token tradeoff and notes that availability depends on client,
rollout and sign-in. It is guidance, not proof of this host's available models.
Profile quality levels and token floors are explicit owner judgments, not provider
benchmarks, prices, token caps or guarantees. Budget shortage is a stop/review
condition, never permission to drop below the selected complexity's quality floor.
Ultra is also refused by policy review in this increment: its automatic delegation
needs qualified descendant admission. A host can advertise it without this adapter
claiming permission to use it. No model names, prices or automatic rankings are
hard-coded in the implementation.

Owner policy review requires an authenticated trusted caller; the actor label
alone is not authentication. [WSP-04G owner controls](MODEL-POLICY-CONTROLS.md)
add a selected-workspace HTTP adapter with exact signed preview/confirmation in
Mission & authority. A controller CLI must never expose owner review/revoke as a
brain operation. No live activation follows from either source increment.

Before separate activation, quiesce older writers and regenerate prepared handoffs.
No mixed-version or downgrade compatibility is claimed. Source, merge, installed
tooling, native delivery, observed settings and live acceptance remain separate.

## Authority and lifecycle

1. The selected workspace brain records the actual local native tool schema's
   model/effort catalog, original observation time and source evidence hash.
   The closed adapter supports only `model` and `thinking` on existing native
   creation/message tools; a reported catalog cannot invent tool parameters.
2. The owner reviews exact profiles and quality floors for the current reviewed
   mission while dispatch is paused. Each profile contains `id`, `settings`
   (`model`, `effort`, null `speed`), `quality` (1–4), and `minimumWorkTokens`.
   Floors for `routine`, `standard`, `complex`, `critical` must be nondecreasing.
   `maxEscalations` is an explicit 0–2 per-task ceiling. Missing profiles for a
   requested complexity are a blocker, not fallback permission.
3. The internal owner run request chooses either the unchanged `native_defaults`
   string or exactly `{mode: "adaptive", policyHash: EXACT_REVIEW_HASH}`. Policy
   review alone never authorizes a run, releases maintenance or creates admission.
4. With an existing valid run/allocation, the brain selects an approved profile
   and explains task complexity. Initial selection must match the immutable task
   contract's requested settings and precede approval/ownership. The existing
   task approval, reservation and one-shot creation handoff then enforce it.
5. After a confirmed native task and consumed send boundary, the brain records
   settings actually returned/observed. Delivery alone proves neither field.
   `applied` and `observed` may each be null; they are never populated from the
   request automatically. Unknown or mismatching observations are retained but
   refuse subsequent corrections and runner effects. A contradictory non-null
   applied value also blocks. Refresh evidence honestly or stop for reconciliation.
6. A fresh idle task may retain its current profile or explicitly prepare a
   strictly higher-quality profile, without lowering its complexity classification.
   A change increments the task's escalation count; preparatory alternatives do
   not consume attempts or reset the count. A consumed continuation binds the
   chosen selection hash. Every new continuation, even one retaining the same
   profile, requires a new post-boundary settings observation before further work.
   Two no-progress corrections still stop work regardless of unused policy quota.

Quality/complexity judgments come from the owner/brain, not a semantic proof.
The original initial settings stay bound to the packet; an escalation is a
separately retained continuation decision under the same owner-authorized policy.
No in-flight task is silently switched. Runner messages inherit the freshly
observed settings without another override. Existing result/preservation handoffs
retain their historical authority boundaries and do not infer semantic acceptance
from a model choice.

## Brain CLI contract

All commands require explicit `--platform PRIVATE_PLATFORM --workspace EXACT_ID`
and the designated brain's environment controller token. Never include the token
in JSON, prompts, reports or the repository. Requests are regular UTF-8 JSON files
of at most 16,000 bytes; duplicate keys, non-finite values and symlinks refuse.

| Suffix | Input / outcome |
| --- | --- |
| `model-policy-capability REQUEST_JSON` | Retain the actual observed local model/effort schema; never query a provider |
| `model-policy-select REQUEST_JSON` | Select initial settings or prepare a bounded same-task escalation; no approval, reservation or native call |
| `model-policy-observe WORKER_ID REQUEST_JSON` | Retain exact post-send applied/observed facts, including unknown/mismatch |
| `model-policy-state [--worker-id ID]` | Read retained policy, capability freshness, initial selection and settings evidence; never refresh it |

Common fields are `id` (8–100 ASCII letters/digits/underscore/hyphen) and
`expectedRevision`. Additional exact request fields:

- Capability: `hostId` (`local`), `models` (1–32 unique `{model, efforts}` entries),
  `observedAt`, `evidenceHash`.
- Selection: `runHash`, `queueId`, `contractHash`, `workerId`, `expectedHash`,
  `profileId`, `complexity`, `rationale`, `capabilityHash`. Initial selection uses
  null worker/native hash. Escalation names the exact owned worker and attached
  current native journal hash. Initial approval cannot be silently overwritten;
  changing an already-approved initial choice needs separately reviewed scope.
- Observation: `selectionHash`, `boundaryHash`, `hostId`, `threadId`, `applied`,
  `observed`, `observedAt`, `evidenceHash`. Boundary is the consumed creation-check
  hash, or the consumed continuation-intent hash. Both setting fields use the exact
  `{model, effort, speed}` shape when non-null. Do not infer them from send arguments.

Adaptive correction preparation adds `modelSelectionHash` to the existing
correction request. Reusing the current selection keeps settings; a retained
escalation selection changes them. Native-default corrections retain their old
request shape and omit model/effort overrides. There is deliberately **no owner
review/revoke CLI or assistant route**. Owner methods `model_policy.review` and
`model_policy.revoke` now share an atomic transaction with the authenticated
WSP-04G dashboard adapter; browser actor strings are not authorization.

## Freshness, recovery and accounting

Capability evidence expires after 300 seconds; native settings observations after
60 seconds. Same-catalog capability refresh preserves an exact policy, but any
catalog change requires owner review, even if a later observation returns to the
original catalog. Policy replacement/revocation fences the
run; Pause, expiry, mission changes and all existing maintenance gates still apply.
Capabilities cap at 1,000 versions before explicit history maintenance. Native
availability remains a caller-supplied assertion until actual host collection is
qualified; no public documentation or catalog hash attests account access.

Initial admission's minimum work estimate is the larger of the task declaration
and selected profile floor. Selection checks current shared headroom against both;
bounded correction requests must meet their selected profile floor. Actual admission
still checks complete work/review/handoff reservations and checkpoint reserve. Existing
phase/task-attempt counters are never reset by a policy or model change. Cached
input remains part of consumed tokens. Estimates are not billing or provider caps.

Exact retries return historical receipts, including after Pause/revocation, without
renewing timestamps or restoring old pointers. Changed request content refuses.
Observations may record late safety facts after Pause but never resume the run.
Capability versions and observation pointer receipts prevent rollback from hiding
newer evidence. A selection or prepared correction is inert; a consumed send
boundary remains uncertain/owned after interruption and must never be resent.

Owner policy, capability, selection and observation documents are retained as
bounded metadata/hashes in the private ledger. Full source, prompts, native tool
responses and account credentials are not needed for this protocol. Generic
task-contract UI remains the declaration-only view; policy/application evidence
is currently exposed through the explicit model-policy CLI. Dashboard presentation
and live collection belong to their saved integration milestones.

## Local verification

- 34 new policy/handoff tests; 334 focused tests passed.
- Full Python regression suite: 1,199 tests passed in 174.427 seconds.
- All seven JavaScript UI test files and `node --check web/app.js` passed.
- Tests use isolated fixture ledgers/repos and fictitious model identifiers.
  No native tasks, inference calls, live observations or live settings changed.
- No Actions workflows or jobs were added or run. Local test success is not
  hosted CI, live model observation, deployment or autonomous acceptance.
