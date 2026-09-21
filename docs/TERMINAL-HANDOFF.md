# Terminal ownership handoff — WSP-04D6

## Saved implementation plan

Close the source command-path gap between managed native supervision and result
review. Reuse the existing confirmed-terminal and reconciled non-creation
journals; do not introduce a scheduler, new release protocol or native collector.

- [x] Designated-brain, explicit workspace/outcome CLI for state, checkpoint
  proof retention, settlement and interrupted local-receipt recovery.
- [x] Standard-policy scope checked under the existing registry/workspace locks;
  closed, bounded input and exact worker/attempt/artifact binding.
- [x] Read-only state even across the shared-commit/local-receipt gap. Settlement
  retains complete inventory, descendant, cleanup and cumulative-usage gates.
  Safety accounting remains possible after Pause or expired work authority.
- [x] Disposable CLI regression fixtures, including interrupted receipts,
  non-creation, negative evidence, and terminal-to-result-review composition.
- [x] Update managed-cycle source guidance and milestone status; local full suite
  and existing UI regressions. No GitHub Actions execution or additional billing.

This increment does not qualify a host evidence source. An idle task, a final
reply, account percentages or a public metadata collection report cannot prove
complete descendants, full-process cleanup or lifetime counters. Missing facts
remain blockers, not zero/default evidence. Terminal settlement releases owned
resources and records actual usage; it never accepts a packet or authorizes retry,
merge, archive, new workers or Play. Harness needs its separate trusted adapter.

No live ledger, schedule, installed skill, dashboard process or runtime is changed
by this source increment. A separately authorized rollout remains necessary.

## Brain command path

After separately authorized installation, use the installed wrapper with explicit
`--platform <private-registry> --workspace <id>` and its private designated-brain
controller token. No HTTP, assistant action, public Play or initializer is added.
Commands take an exact managed worker ID and a required
`--outcome confirmed|not_created`; never guess the outcome from missing IDs.

1. `terminal-handoff-state WORKER --outcome OUTCOME` reads the historical scope,
   exact attempt/native hash, revision, resource keys and evidence lower boundary.
   It does not observe native activity, refresh times, recover a receipt or decide
   that settlement is safe. A detached native receipt must first be recovered
   using the original native handoff.
2. Obtain qualified external evidence. For confirmed work, retain each root and
   descendant checkpoint using `terminal-handoff-proof-add WORKER request.json
   --outcome confirmed`. For conclusively uncreated work, retain one final
   attempt-scoped reconciliation proof with `--outcome not_created`.
3. Submit the exact closed evidence contract with
   `terminal-handoff-settle WORKER request.json --outcome OUTCOME`.
   Confirmed work uses [OWNERSHIP-SETTLEMENT.md](OWNERSHIP-SETTLEMENT.md#internal-contract);
   non-creation uses [CREATION-RECOVERY.md](CREATION-RECOVERY.md#internal-api-and-exact-evidence).
   These schemas remain unchanged. Only proof IDs returned by this adapter are
   accepted; generic artifact text is not upgraded into a terminal handoff.
4. If the shared settlement committed but local attachment failed, state reports
   `recoveryRequired: true`. Use `terminal-handoff-recover WORKER --outcome OUTCOME`.
   Recovery validates the original proof bytes/bindings and attaches only that
   receipt, even after Pause, expiry or a later maintenance fence. It never
   re-releases a newer owner's resources. If no settlement committed, recovery
   refuses; inspect and reconcile rather than treating recovery as permission.
5. A confirmed settled packet remains held for `result-handoff-state` and separate
   independent result review. An uncreated attempt stays closed and held with no
   automatic retry. Neither outcome archives or deletes anything.

## Proof request

The strict request reader rejects duplicate JSON fields, non-finite values,
symlinks and files above 16,000 bytes. A proof request has exactly these fields:

| Field | Meaning |
| --- | --- |
| `id` | Bounded immutable request identifier, scoped to dispatch intent and outcome |
| `expectedRevision` | Current selected workspace revision from state |
| `expectedHash` | State's exact attached native journal hash (confirmed) or claim/local-attempt hash (not created) |
| `threadId` | Exact local root/descendant ID for confirmed; null for not created; never a pending client ID |
| `observedAt` | Actual external proof observation time, fresh and after `evidenceAfter` |
| `content` | Nonempty inert checkpoint/reconciliation text, at most 8,000 UTF-8 bytes; no credentials |

The full proof request is at most 12,000 bytes. Observe every confirmed task's
final inactivity **after** retaining its checkpoint artifact; inventory, cleanup
and usage ordering follows the linked terminal contracts. Read state again before
each new proof because retention changes the workspace revision. It does not
change the attempt hash or renew evidence. New proof IDs must represent new
evidence, not periodic timestamp refreshing. Unknown descendants remain blockers;
accepting a supplied descendant ID as inert proof does not establish membership.
The complete settlement must validate a closed ancestry reaching the exact root,
all known descendants and no foreign claim/registered brain identities.

Retention is atomic in the workspace: immutable proof document, artifact version,
original observation/retention times, exact worker/intent/session references,
request receipt and audit event. Exact replay returns the old artifact and time
without a write. Same ID/different request refuses. Evidence text is never parsed
as commands. New proofs and settlement preserve maintenance fences; neither
requires renewed work permission solely to record safe terminal accounting.

## Compatibility and evidence boundary

Only standard-policy local tasks in an owner-authorized run, with exact owner
task approval or phase-delegated approval, are supported. Scope is revalidated
inside registry/workspace transactions, including read/recovery. No new admission
policy, allocation or live state is initialized. Existing internal journal shapes
are unchanged. Older generic internal terminal artifacts are not silently
retagged; this adapter is not a live migration or a downgrade guarantee.

The shared journal still commits before the local receipt. `ownershipReleased`
inside a retained settlement is a **historical result**, not a current claim about
native inactivity or an action performed by the state read. `packetAccepted`,
`executionAuthorized` and `nativeCallMade` remain false. Task attempts, pending
identities, cumulative actual charges and prior evidence remain retained. No
counter sample is synthesized from account limits or dashboard totals.

## Verification

Disposable tests cover both outcomes through the CLI, wrong brain/worker/scope,
freshness and revision drift, partial evidence, omitted descendants, proof replay
and corruption, concurrent retention/settlement, maintenance, Pause/revocation,
interrupted local receipt, newer-owner preservation and non-creation accounting.
Composition fixtures continue through measured source/GitHub result review and
then reserve the next phase-delegated packet without another owner Continue.
Those use temporary Git and fake GitHub responses, not native tasks or live proof.

Verified locally on 2026-09-21: **1,356 Python tests passed** (25 new terminal
handoff tests), all nine JavaScript UI suites, JavaScript syntax, Python compile,
diff whitespace checks, skill validation and temporary-destination skill install
with all four command help paths. GitHub's read-only inventory showed zero Actions
workflows and zero runs before publication; no workflow was enabled or dispatched.
Live runtime and native acceptance were not exercised.
