# WSP-04C3c — reconciled non-creation recovery

Plan saved before implementation, continuing merged PR #27 (`7b83a9d`).

Close exactly one admission-managed creation attempt only after explicit fresh
evidence proves its request is final and no native task, descendant, pending effect
or task usage exists. This is terminal ownership accounting, not a retry, packet
acceptance, native transport, maintenance migration or autonomous Play activation.

## Implementation checklist

- [x] Inspect and hash the exact shared claim, local creation boundary and retained
  native observations without changing state or evidence timestamps.
- [x] Support local-first creation gaps, shared creation intent, pending client IDs
  and unconfirmed uncertainty; refuse unattempted reservations, missing claims,
  confirmed/previously observed native tasks, continuations and runner ownership.
- [x] Require a retained attempt-scoped reconciliation artifact, final not-created
  result, complete attempt/descendant inventory, resolved pending/effects, exact
  resource cleanup and explicit complete zero task counters. Never infer these
  facts from an empty list, timeout, absent ID or model response.
- [x] Seal the attempt using the existing terminal settlement journal, retain
  client IDs/attempts/usage history, and commit shared release before its local
  receipt. Keep the packet held; no creation retry or approval reuse.
- [x] Recover only committed receipts after crashes, preserving newer owners and
  all maintenance fences. Allow safety accounting after Pause or expired work
  approval without resuming work.
- [x] Let fresh safe-Pause inventory recognize a valid non-creation receipt
  without requiring a nonexistent task checkpoint; contradictory task evidence
  remains a blocker. Preserve historical receipt shapes.
- [x] Test evidence contradictions, corruption, concurrent terminal attempts,
  two-workspace reuse, subprocess exits, budget continuity and all regressions.

## Delivery boundary

WSP-04D6 now exposes the scoped standard-local command adapter documented in
[TERMINAL-HANDOFF.md](TERMINAL-HANDOFF.md). It supersedes only the original
internal-only entry-point limitation below; absence evidence is still externally
supplied and live rollout remains separate.

The original increment exposed internal designated-brain methods and isolated
fixtures only; WSP-04D6 adds the scoped CLI. External proof is
caller-supplied evidence, not independently authenticated native attestation.
A future trusted transport/observer must prove finality, completeness and cleanup;
this increment does not collect or fabricate that evidence. No HTTP/assistant
write route, installed skill, live ledger, native task, dashboard process, schedule,
model configuration, credentials or product repository is changed.

No retry allowance is introduced. Failed attempts stay in cumulative task counts;
pending client IDs remain reserved against reuse. Brain/review/other-task usage
stays in the cumulative phase observation. Missing or nonzero usage cannot be
relabelled zero to fit a non-creation outcome. Unresolved correction/runner sends,
legacy quarantine and contradictory known native work need their own recovery.

## Internal API and exact evidence

Construct `CreationRecovery` with the registered workspace's `DispatchAdmission`.
All methods require the selected workspace's designated-brain controller token
and exact worker ID. Construction does not initialize allocations, policy or
tables. `inspect(token, workerId)` reads the current exact attempt and returns
`sourceHash`, `intentHash`, retained host/client ID and `reconciliationRequired`.
It is not an absence observation, approval or authority to retry. Inspection
does not retain evidence or refresh timestamps. A settled attempt returns its
committed outcome; use `recover` to attach an interrupted local receipt.

`settle(token, workerId, request)` accepts a closed, finite JSON request of at most
16,000 UTF-8 bytes. `expectedHash` must equal the current `sourceHash`, binding
the shared claim and exact local owner/receipt. Native changes invalidate it.

| Field | Required content |
| --- | --- |
| `id` | Bounded immutable request identifier |
| `expectedHash` | Exact inspected attempt hash, not a native permit |
| `reconciliationArtifactId` | Retained immutable artifact version with exact attempt references |
| `inventory` | `intentHash`, `hostId`, nullable retained `clientThreadId`, `outcome: not_created`, true `requestFinal`, `complete`, `includesDescendants`, `pendingResolved`, `effectsComplete`, empty `tasks`, `observedAt`, `evidenceHash` |
| `resources[]` | Exactly the claim's 1–4 repository keys, each with `key`, true `processesExited` and `cleanupObserved`, `observedAt`, `evidenceHash` |
| `usage` | Exact `intentHash`, `counterEpoch`, `counters`, true `complete`, `observedAt`, `evidenceHash` |

The inventory is **attempt-scoped**, not an assertion that the entire host is
empty. `requestFinal` means the transport's exact creation request is conclusively
finished and cannot complete later. `pendingResolved` covers the retained client
ID or the unknown-response case. `effectsComplete` covers setup/creation effects
and cleanup; `includesDescendants` means related child/review tasks were also
checked. A transient lookup failure, missing sidebar entry, timeout, native send
error or empty list is insufficient. No result from an LLM creates these facts.
The future trusted observer must independently obtain and verify them.

Counters retain `inputTokens`, `cachedInputTokens`, `outputTokens` and
`reasoningOutputTokens`, all explicitly zero for this uncreated task. Subset and
finite integer validation still apply. Nonzero/unknown task usage is a
contradiction requiring another reconciliation path, not a reason to discard
usage. This does not zero the brain, review or phase-account counters.

The reconciliation artifact must have matching retained bytes, ID/version/hash,
be at most 16,000 bytes, belong to the same repository and contain metadata
references binding `workerId` plus exact dispatch `intentHash`. It must be retained
after the latest attempt/local receipt/native observation and before the supplied
inventory. Artifact contents are inert data, never parsed as commands. Receipt
attachment/recovery and the Pause exception recheck that these bytes remain
available; a missing artifact is not silently treated as preserved evidence.

All new observations must be fresh and non-future under admission policy. The
inventory follows the retained boundary and artifact; each resource cleanup
follows inventory; usage follows all cleanup. An older native pending observation
may be reconciled by fresh final evidence without refreshing that old observation.

## Eligibility and contradictions

Eligible states are an attached shared creation boundary with no native result,
unconfirmed pending/uncertain native observations, or an exact local
`creation_pending` boundary whose shared claim remains `reserved`. The latter is
not treated as proof that nothing was sent: it requires the same final external
evidence. Unattempted `reserved` owners and missing shared claims refuse. A
detached shared creation/native receipt must first be recovered through its
original coordinator; this API does not silently repair it.

Any confirmed native identity, continuation, runner history/ownership or unmatched
local continuation/runner marker refuses. The entire native journal chain is
hash-checked for prior contradictory work, bounded to 1,000 records / 2 MB. All
retained Pause evidence is checked for task observations tied to this worker or
its pending ID, also bounded to 1,000 records / 2 MB. Larger histories require
explicit archival, not silently truncated coverage. Current retained stop bindings
cannot erase a known task. Native work needs confirmed-terminal settlement, not
a different outcome label.

Exact repository ownership/allocation fingerprints and all database/workspace
identities remain required. Queued/processing worker controls and local runner
ownership block release. Pause, expired/revoked work approval or exhausted new-work
budget do not prevent safety accounting. Workspace/registry/admission maintenance
fences still block a new ownership change; no migration/unfence is introduced.

## Durable closure, accounting and recovery

Lock order stays registry -> workspace -> admission. The coordinator uses the
existing `ownership_settlements` table with a distinct `creation_recovery` kind;
only one terminal outcome may exist for a claim. Confirmed-terminal and
non-creation coordinators reject each other's outcomes. Existing confirmed-terminal
records and their local binding shapes remain unchanged.

Shared journal, zero actual task counters, `settled` claim and exact repository
release commit together, followed by the local receipt. Worker status becomes
`settled`, never `complete`; its packet is held with an explicit no-retry reason.
The immutable creation intent, old native observations, pending client ID,
estimates and phase task-attempt count stay retained. Pending IDs cannot be rebound
as another claim's task. No slot, budget epoch, run generation or approval can be
reused to reopen this old attempt. No source/CI/merge/runtime/pilot/tenant evidence
axis is upgraded. Portfolio settlement counts represent closed reservations,
not a claim that those native tasks existed or were accepted.

`recover(token, workerId)` attaches only a hash-verified committed receipt,
including behind a later maintenance fence. It never releases resources again,
clears another workspace's newer owner, refreshes evidence, sends a task or
resumes dispatch. Exact request replay returns the original receipt; changed
evidence refuses. If maintenance now blocks `settle`, use the dedicated recovery
method for an already committed result. Missing/corrupt history or changed local
identity refuses. A crash before shared commit retains ownership unchanged; a
crash afterward leaves a conservative local owner until recovery.

Receipts explicitly report `creationOutcome: not_created`,
`ownershipReleased: true`, `actualTokens: 0`, `retryAuthorized: false`,
`packetAccepted: false`, `executionAuthorized: false`, `nativeCallMade: false`
and the caller-supplied external-evidence trust boundary. Zero is supplied and
validated task accounting, not a measurement of live account consumption.

## Safe Pause and remaining work

Pause derives the non-creation exception from the exact retained receipt and
artifact bytes, not an editable status flag or absent task ID. The worker remains
in the retained set, including its client ID, but does not need a nonexistent
native task checkpoint. Settlement invalidates previous Pause inventory: a fresh
complete inventory is still required, plus the ordinary brain checkpoint and
heartbeat gates. A later observed task contradicting this receipt blocks parking
and needs explicit incident reconciliation. Recovery never parks/resumes the brain.

See [verification](CREATION-RECOVERY-VERIFICATION.md) and [roadmap](ROADMAP.md).
Separate result acceptance, trusted host/native observers and transport, Harness
runner integration, new-generation continuation, maintenance migration and exact
owner Play activation remain before a separately authorized real pilot.
