# Native project assignment: review once, revalidate before use

This operator-only standard-project control assigns one existing brain's native
project metadata. It is not Play, a brain wake, native loading, host installation,
permission approval, worker dispatch, terminal reconciliation or pilot acceptance.

## Scope validity, not a five-minute human-response race

New `native-project-preview` output uses `native_project_assignment_scope_v2`.
Its `reviewValidity` is `until_scope_changes` and `expiresAt` is explicitly null.
Keep the original private preview and its exact hash; elapsed time alone does not
require another preview or confirmation. `createdAt` and `nativeStatus` describe
the original inspection, not current native evidence. Polling never confirms,
stores approval, renews a review or invokes native reads.

An explicit owner confirmation of the exact displayed hash is still mandatory.
The trusted operator must not interpret model text, a previous unconfirmed draft,
vague assent or source installation as that confirmation. Before every claim and
native write, the existing adapter rechecks the current paused standard ledger,
released controller/runner, settled brain control, native activity and all
unresolved-effect fences. It independently rereads the exact project and brain
on the unchanged reviewed host, with no conversation history or native load.

The reviewed workspace, brain, both project IDs, checkout, single native project
root, ledger identity and revision, complete catalog hash/location mapping,
endpoint and full binding hash must all remain identical. The binding hash also
pins native policy. An idle/not-loaded transition is allowed only for this
non-executing metadata assignment. It does not establish that terminals are
empty, that historical effects are safe or that the brain is ready to develop.
Unknown/unsupported activity and an active turn refuse the assignment.

Changing any reviewed binding or ledger revision requires a new exact owner
review. A dead or replaced host is not automatically substituted. The adapter
holds registry then ledger locks when rechecking and claiming, and again across
the bounded native write response. This is a cooperative fence, not a native
transaction or a lock on activity initiated independently in Codex.

## One-shot execution and uncertainty

The same private assignment journal retains the entire original reviewed preview,
its hash, review kind, fresh preflight time and whether legacy expiry was explicitly
revalidated. A committed intent permanently consumes the attempt before one
`thread/metadata/update`. Even a pre-send host failure cannot permit another claim.
Lost responses remain uncertain. `native-project-status` reads the saved intent;
`native-project-reconcile` only rereads the same bound project/brain and retains
the result. Neither repeats the metadata update or loads/starts a native turn.

## Already approved legacy review

Legacy `native_project_assignment_v1` documents keep their original `createdAt`,
five-minute `expiresAt`, preview bytes and hash. Normal confirmation still refuses
an expired legacy review. New previews, reads, Help, installation and restarts do
not silently revive it.

If the owner explicitly authorizes revalidation of the already reviewed exact
assignment after expiry, the trusted operator may use:

```text
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace EXACT_WORKSPACE \
  native-project-confirm PRIVATE_BINDING PRIVATE_ORIGINAL_PREVIEW.json \
  --confirm-hash EXACT_PREVIOUSLY_REVIEWED_HASH --confirm --revalidate-expired-review
```

This deliberate choice applies only to an expired, structurally intact legacy
assignment review with no existing intent. It is not automatic approval transfer:
the operator must have the owner's exact hash confirmation and explicit choice
to revalidate it after expiry. The complete original scope is compared against
fresh reads; no refreshed hash, clock rewrite or authority extension is generated.
The private claim labels `legacyExpiryRevalidated: true` and preserves the full
original review. A changed scope, wrong hash, malformed clock, prior claim or
unconfirmed/unknown native result fails closed. The option does not apply to v2
reviews, unexpired legacy documents, other controls, Play or recovery.

## Rollout and pilot boundary

Source review, manual merge, installation and disposable native qualification
remain separate steps. Quiesce only the selected writer and back up its private
state before separately authorized installation. Do not change a different
dashboard, host binding, brain, pending request or historical pilot. Old assignment
journals remain readable and one-shot; there is no automatic schema migration.

After verified metadata assignment, collect only explicitly authorized pilot
evidence and use the designated brain's existing protocol. Mission Review, new
Play and permission responses retain their separate exact owner controls. Never
replay old Play or recovery, reset consumed usage/gaps, extend a phase deadline,
load a thread to manufacture safety, backfill a receipt or infer empty terminals
from an unloaded brain. A metadata assignment is not a completed pilot.
