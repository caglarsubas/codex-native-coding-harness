# Admission evidence reconciliation — WSP-04B3

Implemented: compare quarantined ownership with bounded external observations and retain
an exact owner-reviewed, account-bound usage baseline. This is an evidence
reconciliation step, not a native collector, ownership release or run activation.

## Scope

- [x] Validate exact account, native inventory, claim, resource, runner and
  per-task cumulative usage observations; reject arbitrary text/commands.
- [x] Report stale/incomplete coverage, unresolved pending creation, duplicate or
  unadopted tasks, missing checkpoints, busy runners and mapping gaps explicitly.
- [x] Preserve counter epochs, subsets and per-task coverage across reviewed
  baselines; never silently reset usage, switch accounts or discount cached tokens.
- [x] Retain versioned exact-hash review receipts with optimistic concurrency and
  idempotence. Preview/status must not create an evidence store or mutate claims.
- [x] Re-evaluate freshness/source drift separately from the historical receipt.
- [x] Keep all enrollment/adoption fences, ownership and allocations unchanged.

Native observations and evidence hashes are assertions supplied by the trusted
local operator/brain after using supported native and operator tools. Schema
validation is not independent proof of those observations. A consistent report
must not be presented as activation authority or live pilot acceptance.

## Operator workflow

Complete [maintenance enrollment](ENROLLMENT.md) and [quarantined ownership
adoption](OWNERSHIP-ADOPTION.md) only when explicitly requested by the owner.
This feature does not perform either operation automatically. For an already
adopted portfolio, gather fresh supported native-tool observations, independent
runner/operator evidence and complete cumulative per-task token observations.
Do not gather these by probing private Codex APIs or treating worker prose as
execution evidence. The dashboard's historical usage aggregates are not a
complete admission baseline: missing samples and counter resets remain gaps.

Save the bounded observation document privately. It must contain no credentials,
transcripts, commands, raw source paths, artifact bodies or account email/address.
Account identity is an opaque SHA-256 identity binding, not a login credential.
Evidence hashes refer to separately retained observations; they do not authenticate
their source. Never set a coverage flag true merely to get a consistent report.

```sh
python3 -m orchestrator.cli --platform /absolute/private/.platform platform-reconciliation-preview /absolute/private/evidence.json
```

Preview requires intact enrollment/adoption fences, the exact imported kernel
identity, paused dispatch and released controllers. It locks recorded source state
while inspecting it; it never observes native tasks, collects token logs, changes
workspaces/claims, initializes evidence tables or sends notifications.

Inspect the returned report and save its exact JSON privately. Missing evidence
is reported with machine-readable codes and claim/task/resource scopes. Only for
the owner's explicit review of that exact document:

```sh
python3 -m orchestrator.cli --platform /absolute/private/.platform platform-reconciliation-record /absolute/private/review.json --id exact-review-id --confirm
python3 -m orchestrator.cli --platform /absolute/private/.platform platform-reconciliation-status
```

All commands are platform-wide; omit `--workspace` and `--state`. There is no
browser/chat mutation route. A request to develop this feature is not permission
to collect or record a live baseline. No live baseline was recorded in this release.

## Closed evidence contract

The top-level fields are exactly `schemaVersion: 1`, `adoptionHash`, `account`,
`inventory`, `claims`, `resources`, `runners` and `usage`. `adoptionHash` pins the
completed import's `bundleHash`. Timestamps are finite positive Unix seconds;
evidence, identity, checkpoint and epoch hashes are 64-character SHA-256 hex.
Observation freshness uses the adopted policy's age limit (at most 300 seconds),
and observations must not predate the recorded adoption completion.

| Section | Required fields and interpretation |
|---|---|
| `account` | `identityHash`, `observedAt`, `evidenceHash`, `windows` with exact `short` and `long` entries; each has `usedPercent` and `resetsAt`. Null window values mean unknown, never zero. |
| `inventory` | `accountIdentityHash`, `observedAt`, `evidenceHash`, explicit booleans `complete`, `includesDescendants`, `includesUnmanaged`, exact `workspaceIds`, covered `hostIds`, `tasks`, `pending`. Missing or bounded/incomplete native coverage must be marked incomplete. |
| `inventory.tasks[]` | `hostId`, `threadId`, `workspaceId` (nullable for unmanaged work), `role` (`brain`, `worker`, `reviewer`, `nested`, `external`), `parent` (null or host/task pair), `state` (`idle`, `running`, `unknown`), `checkpointHash` (nullable), `observedAt`, `evidenceHash`. |
| `inventory.pending[]` | `hostId`, `clientThreadId`, `outcome` (`resolved`, `not_created`, `unknown`), `threadId` (only non-null for resolved), `observedAt`, `evidenceHash`. A client ID is never a task ID. |
| `claims[]` | Exact `claimId`, `outcome` (`quiescent`, `not_created`, `unknown`), `native` host/task pairs, `observedAt`, `evidenceHash`. All retained native bindings must be covered. Negative creation evidence cannot discard a known native task. |
| `resources[]` | Canonical `key`, explicit `verified` boolean, `observedAt`, `evidenceHash`. Verification is an operator assertion; missing imported mappings remain migration gaps. |
| `runners[]` | Canonical runner `key`, `state` (`idle`, `busy`, `unknown`), explicit `cleanupObserved`, `observedAt`, `evidenceHash`. Idle without observed cleanup is insufficient. |
| `usage` | `accountIdentityHash`, `observedAt`, `evidenceHash`, explicit `complete`, `sessions`. This must cover exactly the supplied native inventory, including brains, reviews and nested tasks. |
| `usage.sessions[]` | `hostId`, `threadId`, `counterEpoch`, `counters` (nullable), explicit `complete`, `observedAt`, `evidenceHash`. Exact counters are `inputTokens`, `cachedInputTokens`, `outputTokens`, `reasoningOutputTokens`. |

See the `evidence()` fixture in [the regression suite](../tests/test_reconciliation.py)
for a complete synthetic example. Fixture identities and hashes are not live
evidence. Lists, document bytes and native IDs are bounded; duplicate identities,
extra fields, non-finite/negative counters and invalid subsets are rejected.

## Meaning of a report

`consistent` means the supplied assertions are fresh, structurally complete and
consistent with the locked records and prior baseline. It does **not** mean that
Codex or an operator cryptographically attested them. The report explicitly emits
`trustBoundary: caller_supplied_external_evidence_not_native_attestation`,
`executionAuthorized: false`, `ownershipReleased: false` and
`activationAvailable: false`.

Every configured brain must be represented exactly once. Observed tasks must be
idle with a checkpoint hash. This is a quiescence observation, not task completion
or permanent termination. Unmanaged/unadopted tasks, nested/review ancestry gaps,
cross-workspace parent links, cycles, unresolved pending creation, shared native
ownership, resource conflicts and orphaned runner records remain blocking issues.
New ledger owners or changed resource bindings cannot disappear behind an old
adoption receipt. No report removes imported ownership or its reserved slots.

`needs_evidence` can still be reviewed and retained as a diagnostic. It never
establishes or replaces the baseline. Account window resets, insufficient account
headroom, stale/future observations and incomplete usage are explicit issues;
there is no default unlimited state.

## Baseline and review durability

Raw cumulative tokens are **input + output**. Cached input is a subset of input;
reasoning is a subset of output. Neither is added again, discounted as a bill or
converted from an account-usage percentage. `knownCumulativeTokens` describes
the supplied samples; it is not a phase charge or an enforced token allowance.

Only a consistent reviewed record becomes the baseline anchor. Subsequent
consistent records must preserve its account identity, every prior host/task
counter epoch and nondecreasing counters/observation times. A missing session,
epoch change or lower counter requires explicit correction/migration, not a fresh
empty allocation. Invalid diagnostic records cannot replace or launder the last
consistent anchor, even after it leaves the displayed 20-record history window.

Reviews expire after five minutes, but underlying evidence can expire sooner.
Recording re-evaluates the approved conclusions; if age/reset gates changed, a
new preview is required. Exact source/kernel fingerprints, prior-version hashes
and baseline hashes are rechecked under registry → workspace → kernel lock order.
Only the registry receives a new versioned record, containing the exact preview,
evidence and receipt hashes. A crash after commit is recovered by retrying the
same request ID/content, which returns the historical receipt without replay.
Competing versions refuse, transaction failure rolls back, and history hash
corruption is detected without automatic repair. History is bounded to 10,000
reviews pending an explicit archival migration.

Status separates `reviewedReport` from `currentEvaluation`. It re-evaluates saved
evidence age and current recorded-state bindings, not native activity. Source
drift makes the current evaluation incomplete; missing fences, changed identities
or unavailable state cannot look ready. No stored observation timestamp is
refreshed just because the owner reopens the report.

## Still required before Play

The trusted brain/operator must supply actual supported observations; this release
does not implement a native collector. The run controller must still connect exact
owner/phase activation, packet authority, budget admission, native-operation
receipts and cooperative Pause/checkpoints at every effect/continuation boundary.
It must consume fresh revalidated evidence rather than treating this historical
baseline as a permanent clearance. No automatic migration, live execution,
ownership release or budget grant was introduced here.

## Verification

Local verification on 2026-09-19 with Python 3.12: **373 Python tests passed**,
including 35 reconciliation tests. All four JavaScript regression suites
(mission, workspace, decision and panes), syntax checks for `web/app.js`,
`web/missions.js` and `web/workspaces.js`, and `git diff --check` passed.

The new fixtures cover two-workspace ownership, pending/native mismatches,
changed pending creation, conflicting resources, nested/review coverage,
quiescence and runner evidence, incomplete/stale usage, counter continuity,
history integrity, concurrent/exact retry, rollback and a hard child-process
exit after receipt commit. Cross-process hash-seed tests check deterministic
review comparisons. All observations and identities are synthetic.

No live private baseline, native task, heartbeat, installed skill or dashboard
process was changed. This increment adds no frontend component; JavaScript
regressions are not browser acceptance. Local tests are separate from CI,
merge, deployed runtime and real two-workspace pilot acceptance.
