# Phase-bound task contracts — WSP-03B3

Implementation plan for the next prerequisite to autonomous Play. Give the brain
a durable, exact declaration of a prepared task's operations and requested
execution settings. This is not run activation or delegated approval.

- [x] Define a closed, bounded contract bound to the workspace/brain, current
  owner-reviewed mission/phase, repository policy and exact packet/seed.
- [x] Enforce conservative path containment, operation subsets and a positive
  token estimate that leaves the configured checkpoint reserve intact.
- [x] Retain immutable versions and idempotent designated-brain proposals.
  Revisions invalidate earlier legacy approvals/preflight; no native effect.
- [x] Fence legacy approval/reservation/creation for contract-bearing packets,
  including after reprepare, so old paths cannot silently ignore the contract.
- [x] Expose the declaration, current binding and requested/not-applied settings
  in the queue, Run readiness, scoped API/CLI and bounded assistant metadata.
- [x] Verify stale/revoked versions, cross-workspace isolation, changed seeds,
  policy escalation, races, retry recovery and browser rendering in fixtures.

## Scope and non-goals

The existing v1 inheritance seed remains unchanged. A separately hashed task
contract binds its exact bytes to a reviewed phase and requested operations.
This avoids changing old approvals or silently upgrading existing work.

Only the designated brain with its current controller token may propose a
contract. No chat/browser write route, native notification, model call or task
creation is added. An accepted proposal means structurally bound preparation,
not authorized execution. Existing packets without contracts retain their legacy
workflow; opting a prepared packet into this contract requires future run-aware
approval/admission, and cannot be undone through legacy reprepare.

Requested model/effort/speed identifiers are bounded data, not a supported-model
catalog. Null means use the destination's existing default; it does not record
what that default is. Applied and observed settings remain unknown. Selecting an
adaptive policy, verifying host capabilities, enforcing budgets and applying
native settings belong to the later run/adapter integration. Unsupported requested
settings must block that integration, never trigger a silent fallback.

No live ledger, installed skill, dashboard process or product task is changed by
this coding increment. A new exact owner activation and native-effect enforcement
remain prerequisites for autonomous Play.

## Proposal workflow

1. Select an explicit registered workspace and acquire its designated-brain
   controller. Read the current ledger revision, exact packet/seed hashes and
   current mission/review receipt. A draft, revoked or mismatched mission refuses.
2. Prepare the private JSON spec described below. Do not put credentials, source
   bodies, command strings or transcripts in rationale or settings.
3. Call `task-contract-propose` with the spec file, exact current ledger revision
   and a new request ID. The normal controller token stays in its environment
   variable, never in a document or prompt.
4. Inspect `task-contract-state` or the packet's **Review** in **Approved queue**.
   The declaration is prepared and bound, not activated. The legacy approval
   button is absent because it cannot approve this new authority boundary.

```sh
python3 -m orchestrator.cli --platform /absolute/private/platform --workspace example task-contract-propose /absolute/private/task-contract.json --revision 42 --id task-proposal-example
python3 -m orchestrator.cli --platform /absolute/private/platform --workspace example task-contract-state repository:PACKET-001
```

The workspace/paths/revision/IDs above are illustrative, not live values. There
is no browser proposal or approval endpoint. Authenticated
`GET /api/workspaces/{id}/task-contract?queueId={encoded-queue-id}` is read-only.
Ordinary polling never proposes a declaration or upgrades the ledger.

### Closed JSON spec

| Field | Meaning |
| --- | --- |
| `queueId`, `seedHash`, `packetDigest` | Exact prepared queue item and v1 seed |
| `missionHash`, `reviewReceiptHash` | Exact currently reviewed mission and owner receipt |
| `operations` | Nonempty subset of the phase's `edit`, `test`, `commit`, `push`, `open_pr`, `merge` operations |
| `requestedSettings` | Exactly `model`, `effort`, `speed`; each a bounded identifier or null for native defaults |
| `estimatedTokens` | Positive integer estimate, no larger than phase allowance minus checkpoint reserve |
| `rationale` | Why these operations, settings and estimate are proposed |
| `reuseReason` | Why this prepared packet needs a new task instead of reuse |

No additional fields are accepted. The spec is at most 16,000 UTF-8 bytes; the
retained envelope at most 32,768. Rationale/reuse text is bounded to 2,000 characters
each; setting identifiers to 100 ASCII letters/digits/dot/underscore/colon/hyphen
characters beginning with a letter/digit. These identifiers never become argv.

The envelope adds workspace/brain identity, mission revision, phase ID, exact
repository mapping/policy binding, actor, timestamp, version and previous hash.
It retains `executionAuthorized: false`. Paths come only from the exact seed and
must be conservatively contained by the phase. Contract preparation reads retained
documents only; it never opens repository source or runs acceptance commands.

Operations are declarations of requested effects, not a semantic analysis of the
task prose or command contents. No undeclared operation is inferred. Manual-merge
policy cannot be overridden. A seed that requires merge completion must declare
merge within an eligible phase. Harness still requires exact owner-approved
packets and its isolated execution rules; a declaration grants neither approval
nor an exemption.

The estimate includes no cache discount and reserves nothing. It is not a price,
remaining account usage or a provider billing cap. Actual aggregate usage and
concurrency admission must be checked by the future run-aware adapter.

## Versioning and fail-closed behavior

A proposal is one SQLite transaction: immutable contract, queue pointer,
invalidated prior approval/preflight, format marker, event and request receipt.
Exact request retries return the historical receipt without applying it again;
the current state must still be read separately. Reusing a request ID with changed
content refuses. Concurrent distinct proposals using one revision have one winner.
No dispatched or owned packet can be replaced, even if its task appears finished.

New versions keep earlier bytes through linked hashes. Reads expose up to 20
history entries and the next older hash. Revocation, phase changes, repository
mapping/policy changes and seed revisions mark the existing declaration stale;
they do not rewrite historical bytes. Reprepare keeps the contract pointer and
its legacy fence. A missing, oversized or corrupt declaration is invalid, not a
legacy packet. There is no remove-contract or downgrade control in this increment.

The assistant receives only the presence of a declaration and its legacy-approval
block through queue metadata. It does not receive rationale, full contract/seed
bodies or hashes. Run readiness includes a bounded structural projection; it does
not turn declarations into permission or verify native configuration.

## Format compatibility and rollout

The first successful explicit proposal marks that workspace ledger's metadata
`schemaVersion: 2` in the same transaction. V1 inheritance seeds, existing tables
and other queue items remain unchanged. Updated helpers and registry inspection
read ledger v1/v2; older v1-only helpers refuse to reopen v2. Installing new source,
reading state and inspecting readiness do not change the marker.

Before any live proposal: retain a verified SQLite backup, reach a safe checkpoint,
stop every older helper/dashboard process, and upgrade the helper and matching
web assets together. The marker cannot stop an already-running older process that
cached a ledger object. Mixed-version operation is unsupported. Do not downgrade
the marker, delete declarations or restore an old backup over newer owner/history
state to regain dispatch. Recovery must retain every newer task/owner/receipt.

The initial v1-to-v2 proposal also refuses unless dispatch is paused and no active
worker or runner ownership is recorded. This is a local maintenance prerequisite,
not independent native-idle evidence or proof that old processes have stopped.

No live rollout was performed for this increment. See the
[verification report](TASK-CONTRACTS-VERIFICATION.md). Future work must add an
exact owner activation/run generation, version-bound packet approval and effect
checks coupled to shared admission. A reviewed configuration or task declaration
must never activate merely because a future release is installed.
