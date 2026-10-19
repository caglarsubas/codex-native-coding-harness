# Transferred preparation usage and disjoint worker-phase admission

These are two separate, opt-in operator adapters. Neither installs a runtime,
loads a brain, changes a binding, releases a hold, replays a consumed request or
qualifies a pilot. The old canceled run and the consumed v5 preparation stay
immutable, including their unknown outcomes and historical terminal safety.

## Append-only actual usage

`transferred_preparation_usage_v1` accepts only the exact independently completed
v5 transfer described in [the observer contract](OBSERVER-HEARTBEAT-AND-RECONCILIATION.md).
It preserves both original numeric baselines and the original `usage.claim.json`.
An explicit collection creates a new private, disjoint intent/evidence directory;
status and admission do not collect or retimestamp anything.

The closed read-only native client repeats exact account (`refreshToken: false`),
project, brain and latest completed-turn reads on the original destination. The
original native-returned rollout must retain its transferred prefix and the
same dated, single new start/completion. Only that private, bounded, unaliased
file is parsed. Native response/compaction-aware counters use the existing
numeric parser; legacy display counters are not added to native counters. Copied
history is counted once. No transcript or credential is retained in the report.

The report must cover the original registered brain interval, both earlier
sample/collection/through times, every token component, calls and both high-water
amounts. Missing prefixes, counter regressions, unknown coverage, exhaustion,
changed identity/file epochs or authentication remain gapped/unknown. An error
retains a separate unknown result, never an old claim retry or zero-usage proof.
The conservative maximum for the *whole* proposed target phase is the smaller of:

- Original brain allowance minus newly observed cumulative brain consumption.
- Original phase allocation minus that consumption and the original checkpoint reserve.

These are local cooperative accounting observations, not provider billing caps or
descendant/process cleanup evidence. Completed-turn accounting remains historical
and immutable; it does not acquire a new timestamp on read. The optional fresh
check still uses the existing 120-second rule. Native policy, tracker, catalog,
new target Play and effect-boundary freshness checks are unchanged.

Current-source fixtures need no frozen-source argument. The installed PR-182
completion record can be validated only with its exact allowlisted frozen source
hash/epoch; the original PR-181 handoff proof remains required inside it. Neither
historical implementation is imported or executed.

```sh
python3 -B -m orchestrator.post_preparation_usage --platform PLATFORM --workspace SOURCE collect COMPLETION_DIR NEW_PRIVATE_USAGE_DIR --completion-source EXACT_FROZEN_PR182_SOURCE
python3 -B -m orchestrator.post_preparation_usage --platform PLATFORM --workspace SOURCE status NEW_PRIVATE_USAGE_DIR
```

## Exact new-target lineage, not activation

`post_preparation_worker_admission_v1` admits only an **already registered**, empty,
paused, unowned standard target with a different workspace and brain. It must have
its own exact owner-reviewed mission, actual catalog mapping and existing private
restricted native binding. No strict enrollment, pending work/control, controller,
runner, previous attempt or admission is eligible. Nothing creates/registers a
target or supplies a binding in this adapter.

The target must be genuinely disjoint from the source and all retained/active
registered owners: no shared/nested checkout, Git common directory or canonical
remote. Missing identity fails closed. The existing explicit `--local-only`
repository-identity review is available; it is not a remote-absence fallback.
Canceled and partially admitted predecessors retain their repository exclusion,
as do quarantined owners. A raw successor marker or retained successor slot is
also ownership, even without a committed snapshot/run or workers; neither a
missing marker nor empty task list releases it. This cannot admit the held v3
checkout by relabeling it.
The complete source registry/ledger proofs remain pinned; adding a target after
the original preparation is not silently treated as an unchanged registry.

Preparation is file/SQLite/Git-only and returns a scope-bound review with no timer
expiry. Its reviewed total token allocation must fit the conservative ceiling.
Confirmation requires its exact new hash, explicitly stopped writers and a fresh
verified private backup of **every registered database** plus exact original and
new sidecars. Backup copies alone use a normalized SQLite journal mode; originals
are read-only and compared by complete logical fingerprints and inode identity.
Bounded chunked manifests reject missing, changed, aliased or unlisted copies.

Under registry/target locks, confirmation writes the existing shared outgoing
source claim first, then an exclusive target marker and one immutable schema-7
target snapshot. Failure between the claims cannot retarget or retry the source.
It changes no source database row, usage receipt, clock or binding. An interrupted
commit preserves either/both claims and stays permanently fenced; never delete,
reconstruct or retry a partial admission. A repeated complete confirmation reads
only the same receipt and cannot create Play.

```sh
python3 -B -m orchestrator.worker_phase_admission --platform PLATFORM --workspace SOURCE prepare EXISTING_TARGET EXISTING_TARGET_BINDING NEW_PRIVATE_USAGE_DIR
# Save the exact request privately and obtain its separate exact owner review.
python3 -B -m orchestrator.worker_phase_admission --platform PLATFORM --workspace SOURCE backup PRIVATE_REQUEST NEW_PRIVATE_BACKUP --writers-stopped
python3 -B -m orchestrator.worker_phase_admission --platform PLATFORM --workspace SOURCE confirm PRIVATE_REQUEST --confirm-hash EXACT_REVIEW_HASH --backup NEW_PRIVATE_BACKUP --writers-stopped
python3 -B -m orchestrator.worker_phase_admission --platform PLATFORM --workspace EXISTING_TARGET status
```

The existing separate target Play creates one new run, not an old Play receipt or
Resume. Its existing loaded-only send checks repeat exact idle identity, current
known-empty tracked terminals and effective policy; they never resume/load an
unloaded brain. Old/current unknown safety remains unknown. Cross-workspace
exclusion is checked again at effect/send boundaries; a late foreign owner does
not prevent recording local Pause. Task claims, one-shot creation, usage checks,
checkpointing, manual merge and pilot acceptance retain their existing gates.

## Qualification and rollout

Unit fixtures exercise real SQLite/Git identities, append-only accounting,
two-baseline monotonicity, native response and legacy counters, exact scope,
backups, partial commits, disjointness, changed evidence, loaded-only preflight
and Pause races. `scripts/qualify_post_preparation_usage.py` additionally exercises
the compiled two-home transfer, actual unload/completion and the actual native
response journal against a loopback fake provider. Its old ledger/provenance and
short expiry are explicitly synthetic and aligned **before** any capture. It
reads no live home or credential and makes no external model request.

Source, manual merge, safe installation, actual evidence, target eligibility and
new owner reviews are separate states. Installation alone neither collects usage
nor admits workers. If the current registry has no eligible pre-existing disjoint
target, report that blocker; do not request a futile approval, invent one, weaken
the original registry proof or reuse held resources. This delivery changes no
live dashboard, host, run, request, claim, usage, binding or hold.
