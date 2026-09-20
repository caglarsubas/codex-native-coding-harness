# WSP-04D3 — cumulative phase usage accounting

Update: [WSP-04F](NATIVE-EVIDENCE-COLLECTION.md) inspects available native metadata
but deliberately supplies no phase-counter evidence: current public reads do not
establish complete non-resetting lifetime counters. All accounting requirements
below remain unchanged, including explicit baselines and complete descendant scope.

Plan saved before implementation, from merged PR #32 (`e113e6f`). This is a
brain-owned accounting interface, not a native counter collector or Play rollout.

## Plan

- [x] Add explicitly scoped phase usage state/record CLI commands over an existing
  allocation, under the designated brain controller and normal lock order.
- [x] Bind supplied cumulative samples to the exact brain and owned task trees,
  account identity, immutable per-session baselines and counter epochs. Preserve
  task/phase scope across run generations; never create a new allocation.
- [x] Derive input/output and their cached/reasoning subsets without double counting.
  Retain session high-water marks, unknown coverage and historical replay; no reset
  or missing member can revive older healthy admission evidence.
- [x] Integrate the exact retained projection into budget checks, protecting held
  estimates, unincorporated settlement usage and checkpoint reserves. Keep Pause,
  resource ownership, approvals, account limits and token counters independent.
- [x] Test bounded CLI flows, cross-workspace/claim isolation, topology, continuity,
  stale/missing evidence, replay, concurrency, rollback and creation boundaries.
  Update roadmap and preserve full-suite verification.

## Source boundary

Available desktop tools expose current task status and account limits, not a
complete per-task cumulative token observation. The official
[App Server reference](https://learn.chatgpt.com/docs/app-server) describes active
thread token-usage events; it does not establish a retrospective desktop-tool
collector or authorize attaching another server to the brain. No new runtime,
private API, goal reset, inference service or model call is introduced here.

The caller must supply independently collected, complete task-scoped counters.
This interface checks their consistency, not their native authenticity. Dashboard
best-effort rollout aggregates and account percentages are not acceptable evidence
of complete phase accounting. No live baseline, allocation, observation, installed
skill, schedule, settings, worker or maintenance fence is changed by source delivery.

## Operator workflow

This interface requires an already initialized private admission store and phase
allocation, a registered workspace, and its designated brain controller token in
`ORCHESTRATOR_CONTROLLER_TOKEN`. Reads do not initialize anything. The allocation
ID is the stable existing workspace/phase accounting identity, not a run generation.
Use compatible installed helpers only after old writers have been quiesced and
private state preserved. Source delivery is not that installation authorization;
mixed-version writes and downgrade are unsupported.

```sh
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace WORKSPACE phase-usage-state ALLOCATION_ID
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace WORKSPACE phase-usage-record ALLOCATION_ID PRIVATE_REQUEST_JSON
```

Read state first. It reports the current `expectedHash`, exact `contextHash`,
required native identities, pinned private account identity hash, previously
retained baselines/counter epochs and known raw token totals by role. Baselines
can therefore be recovered without copying an old conversation. Read status is
`usage_observed` or `needs_evidence`, not an execution permit. A budget's recorded
coverage must be read alongside the current issues and evidence timestamps.

Collect new actual observations using a qualified source outside this helper.
Never fabricate a complete flag, zero counter, baseline or evidence hash. Missing
data should be supplied explicitly as incomplete/null, not filled from estimates.
Save the request as private JSON outside Git, then record it. The helper only
parses bounded data; it cannot execute instructions, collect logs or call Codex.

### Closed request contract

| Object | Exact fields |
| --- | --- |
| Request | `id`, `expectedHash` (null before first record), `contextHash`, `observedAt`, `evidence` |
| Evidence | `accountIdentityHash`, `complete`, `includesDescendants`, `evidenceHash`, `sessions` |
| Session | `hostId`, `threadId`, `claimId`, `role`, `parent`, `counterEpoch`, `baseline`, `observedAt`, `evidenceHash`, `counters`, `complete` |
| Baseline | `observedAt`, `evidenceHash`, `counters` |
| Counters | `inputTokens`, `cachedInputTokens`, `outputTokens`, `reasoningOutputTokens` |

`parent` is null for the brain and each owned root; otherwise it contains exactly
`hostId` and `threadId`. `role` is brain, worker, reviewer or nested. Only the
configured local brain has null `claimId`; all other sessions belong to an exact
existing admitted claim and a parent chain reaching its confirmed native root.
Pending client IDs, other registered brains, foreign roots, previously accounted
foreign descendants, duplicate identities and cycles refuse. No cwd/title-based
attribution is used. Supported scope is local native tasks only.

Timestamps are positive finite Unix seconds. Hashes and counter epochs are
SHA-256 strings; IDs are bounded admission identifiers. The request is limited
to 128,000 bytes and 64 sessions, with at most 64 phase claims. Records are bounded
to 256,000 bytes and 10,000 versions. Larger histories require explicit migration,
not silently truncated coverage. Input must be a regular nonsymlink file; keep
raw source material private. No credentials, text prompts, transcript bodies,
commands, account email, source paths or model output fields are accepted.

The evidence's account hash must match the native account identity pinned by
[native supervision](NATIVE-SUPERVISION.md). A new account cannot silently replace
that identity or reset a phase. Fresh account headroom remains an independent gate;
these counters do not relax the current two-window account policy.

## Baselines, coverage and accounting

The long-lived brain uses an explicitly observed baseline at or before allocation
creation. Its phase counters are cumulative counters minus that immutable baseline.
A later baseline cannot erase prior work. Workers and descendants use an explicit
zero origin and their full lifetime counters, not a subtraction that could hide
work. Copied/forked histories need a qualified counter source; this module cannot
infer or remove inherited usage. Missing origin evidence means incomplete coverage.

Every session's identity, role, parent, claim, epoch and baseline are pinned on
first retention. The last valid cumulative sample is a high-water mark. Missing
sessions, incomplete samples, changed epochs/baselines, negative deltas or regressed
counters block new work and preserve prior known charges. Partial valid increases
may still raise the known total. Existing allocation totals and incorporated
settlements are a floor; the first record cannot reset older accounting.

Raw tokens are **input + output**. Cached input and reasoning output remain
subsets, not additional charges, billing discounts or dollar estimates. The state
view separates cumulative session counters, phase deltas and known totals by role.
Known totals in an incomplete report are not a claim of full measurement.

Coverage must include the configured brain, every confirmed phase root, all
previously retained sessions and descendants found in retained Pause/terminal
evidence. The caller additionally asserts complete independently observed native
coverage: local records cannot discover an unreported child. Unbound reservations
remain fully estimated capacity, not invented zero-usage tasks. After the one-use
native send check is consumed, an unobserved result invalidates the effect context;
pending/uncertain creation must be reconciled, never silently omitted.

The accounting projection uses the **oldest constituent sample time**, not merely
the newer report time. A new envelope cannot renew stale samples. Missing or
invalid coverage clears the usable coverage flags while preserving known counters;
there is no fallback to an older healthy report. Complete later evidence may
restore coverage only with the original bindings and nondecreasing counters.

Held work/review/handoff estimates and checkpoint reserves remain protected even
when partial active usage is counted; this deliberately over-counts until closure.
For a settled claim, the observed session set, counter epochs and counters must
exactly match its retained terminal record, with fresh observations after settlement.
Only then can that settlement be incorporated into the phase total to remove its
separate unincorporated charge. Confirmed non-creation uses the exact retained
zero-usage terminal receipt and never invents a task. Later growth or changed
settled evidence is a blocker, not a silent adjustment of terminal acceptance.

## Durability and effect boundaries

Record order is registry → workspace → shared admission. A single shared
transaction retains an immutable version, its predecessor, evidence/request hashes,
session high-water marks, exact allocation projection and event. There is no
second local receipt or partial cross-store usage update. Interruption before
commit rolls back; exact replay returns the original receipt without new charges,
timestamp changes or replacing newer evidence. Changed content under the same ID
refuses. Missing/corrupt journal or projection pointers fail closed.

Direct legacy allocation usage updates refuse after this journal is enabled by
the first explicit record. Shared budget checks revalidate membership, account
binding and the exact projection. The dispatch bridge also rechecks the current
workspace/native/Pause context at effect boundaries, so a newly known descendant,
consumed send check or terminal change requires refreshed evidence. Reservations,
new task IDs and settlement can invalidate earlier scope; refresh before the next
permitted boundary. A successful usage record alone never authorizes that boundary.

Accounting remains available after Pause or a stopped run, but never unpauses it,
changes approvals, cancels a task, releases a resource, accepts a result or archives
a task. Overruns are retained and block later admission; this is not a provider-side
hard cap or a mid-call kill switch. All existing maintenance fences remain intact.

## Verification and remaining integration

See [verification evidence](PHASE-USAGE-VERIFICATION.md). Fixture-qualified
accounting is now connected to existing admission/effect checks. Complete live
native/descendant and cumulative counter collection remains unqualified, as do
supervised runner/result integration, explicit owner setup/activation and the real
standard-policy pilot. No automatic phase loop, model/effort/speed change, installed
skill update, HTTP/assistant mutation route or dashboard Play activation ships here.
