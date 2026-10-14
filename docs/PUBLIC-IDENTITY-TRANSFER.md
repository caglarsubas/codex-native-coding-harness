# Exact public-host identity and history transfer

`public_identity_transfer_v1` is a separately reviewed operator maintenance
path for **one existing brain**, not a new brain, a dispatcher or a same-run
continuation permit. Source delivery transfers no live state.

## Root cause and native extension

Stock `project/import` creates a new UUID. A matching name/root and an old
idempotency key cannot preserve the original app-server project identity in an
empty destination. Project membership is native database metadata, not part of
the conversation's JSONL. `thread/resume.history` is cloud-only and explicitly
not supported for this repair; editing native databases or copying a shared
Codex home is not an alternative.

The operator-reviewed source build adds experimental
`project/restoreMetadata`, version 1. It accepts the exact observed public
project record and restores its ID, name, root, metadata, position and public
creation/update timestamps through the native local store API. A single native
transaction refuses any existing project, thread or project idempotency record,
including a replay of the same restore. Remote/custom stores remain unsupported.
Recency remains derived from actual member threads, not an imported assertion.
No thread is loaded or turn started by this method.

This is an explicitly named **source-build extension**, not a claim that stock
Codex supports exact-ID import. There is no fallback to ordinary import,
desktop tools, a different identity or direct SQLite manipulation. The native
patch is delivered in `native-runtime/patches/public-host-identity.patch`;
its build and generated-schema instructions are in `native-runtime/README.md`.

## Snapshot and review

Both source and destination endpoints must already be separately reviewed,
live, privately pinned public app-server bindings. The source is the unchanged
original accepted Play's host, not an unavailable/retired endpoint or a fabricated
historical assertion. The destination is an application-owned source build with
the existing public task/policy contracts and this additional closed entry:

```json
"identityTransferEvidence": {
  "protocol": "public_identity_transfer_v1",
  "sourceCommit": "<exact native source commit>",
  "sourceTree": "<exact native source tree>"
}
```

Both pins must equal its public task backend pins. The original binding and
accepted Play acquire none of these capabilities by backfill. This source does
not qualify or launch either endpoint and never changes the vendor desktop
signature/peer checks.

An explicit preparation repeats source project/thread reads and checks the
original receipted Play's latest exact ended turn. It copies only that brain's
bounded, complete, self-contained JSONL, retaining byte hash and file epoch.
The source home must be private. Native 0644 JSONL beneath that private ancestor
is readable without chmodding the original; writable aliases, hard links,
symlinks, partial records and shared homes refuse. Exported archives are private.
Legacy root histories and complete zero-based contiguous paginated root histories
are supported without conversion. Fork/base-linked, segmented/compressed,
goal-bearing, dynamic-tool/plugin/capability-bearing, foreign-root and incomplete
histories need another qualified path and remain unsupported.

The destination must independently report empty projects and both active and
archived thread catalogs, a complete empty MCP inventory, its exact isolated
home and the byte-exact restricted public-host configuration. No credential,
plugin, session database, transcript from another brain or global home is copied.

The ledger must remain an empty unowned paused schema-v4 standard run, without
pending controls, workers, queue/merge ownership, Brain Stop or strict enrollment.
The immutable context pins original Play, run, commands, usage/gaps, expiry,
repository/catalog and both project IDs. Reading time does not expire a new
review; **any scope drift invalidates it**. No phase clock is extended.

Operator commands, always with an explicit registered platform/workspace:

```text
standard-public-transfer-prepare ORIGINAL_BINDING REVIEWED_DESTINATION_BINDING NEW_PRIVATE_DIRECTORY
standard-public-transfer-apply PRIVATE_TRANSFER_SPEC --confirm-hash EXACT_REVIEW_HASH
standard-public-transfer-status PRIVATE_DIRECTORY
```

Preparation is not submission or loading. The apply operation needs the exact
separately displayed owner hash, not generic assent, an old host approval or
model output. No dashboard route or ordinary Help/polling action consumes it.

## One-shot native stages

The private durable intent and canonical original-run/Play sidecar fence the
entire transfer. Changing review directories, usage snapshots or destination
endpoints cannot obtain another attempt. Retain that new local fence alongside
the unchanged original database/control records; never delete it to bypass a
refusal. Separate fsynced claims
precede exactly one native project restoration, one public `thread/resume.path`
inspection load and one native `thread/metadata/update` membership assignment.
The load pins the exact copied rollout and unchanged UUID/cwd, requests only
metadata, forces the restricted policy and disables Code Mode/goals/apps/plugins/
hooks. Repeated actual effective-policy reads precede assignment. Repeated native
thread reads must preserve the complete turn projection and original latest
ended turn. The original source bytes and copied history prefix must remain
unchanged, with fresh binding/run/source rechecks at every stage.

Interrupted claims, uncertain delivery, unexpected permission requests, policy
failure or source/Pause/configuration races permanently consume the attempt.
No load, restore or assignment is resent. Status reads only retained private
files; it neither connects nor renews/recollects anything. A missing result is
`outcome_unknown`, never success or terminal safety.

## What the result does not establish

`metadata_transferred` means exactly that. It does not install the dashboard's
binding, acquire/release a controller, clear the original policy guard, update
usage or expiry, fabricate a receipt/checkpoint, reconnect an old observer,
send Play/recovery/Resume, reconcile old effects or qualify the pilot. Source
current and historical terminal safety remain explicitly **unknown**. An empty
new host cannot establish old cleanup. The existing migration assessment still
returns `migrationQualified: false` until a separately reviewed same-run
transition/evidence contract is implemented and its prerequisites actually hold.

Source merge, installation, native package/launch qualification, exact transfer
review, dashboard cutover and continuation remain separate. Preserve the original
shared host and every original run/control/receipt/usage/gap/expiry record.

## Disposable qualification

`scripts/qualify_public_identity_transfer.py` uses two isolated temporary homes
and a loopback-only fake provider. Run it against an exact reviewed binary hash,
once for `--history-mode legacy` and once for `--history-mode paginated`.
Each fixture creates one receipt-only source turn, then restores the same project
ID and brain UUID/history in the other home through actual native methods.
It checks byte-prefix/turn-projection agreement, actual loaded policy and **zero
transfer turn starts/model requests**. No cloud request, credential, desktop
pipe, live host, live ledger or pilot result is involved.

## Source qualification record — October 14, 2026

The final source passed 2,552 local Python tests with one optional skip, all 39
focused identity/CLI/replay/drift/conservation tests, 36 JavaScript suites,
31 web syntax checks, 122 Python AST checks and diff checks. The native source
passed 226 store tests and 320 protocol tests; its one schema-generator test was
explicitly run for stable and experimental exports rather than treated as an
automatic pass. The source bundle/patch includes actual native state tests.

The exact compiled binary passed real legacy and paginated identity fixtures,
plus the restricted public-host task fixture with an actual native patch and
fixed successful command. The exact privately staged package passed the
paginated identity fixture again. Each identity fixture had one loopback-only
source receipt and zero transfer turns/model requests. No cloud model or
protected desktop pipe was used. Ad-hoc signature integrity verified; vendor
authorization is not claimed.

Only a new private package and a non-executing empty-home launch scope were
prepared. No live intent/exec claim, native transfer, binding installation or
control confirmation occurred. The existing dashboard remained on its installed
PR149/150 source. Its read-only audit retained the sole original Play, 1,049,625
local tokens, original expiry, usage gaps and receipts, with zero workers,
unverified original policy and unknown terminal safety. Source databases were
unchanged. GitHub Actions remains unconfigured and was not run.
