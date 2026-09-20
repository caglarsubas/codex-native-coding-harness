# WSP-04C3g — local result preservation

Plan saved before implementation, continuing PR #36 merged at
`3fb9bf9b77256a1e7cbcd1f8148d3ca8bffaaefd`.

## Plan

- [x] Add an explicit designated-brain result-handoff operation for an already
  settled, exact owner-approved standard-policy task. No Harness source access,
  public activation, automatic archival or native calls.
- [x] Produce a bounded, self-contained Git bundle of the approved base/result
  from the existing configuration-isolated local object view. Restore into a
  disposable empty object store and check connectivity and object integrity.
  Never read working files, fetch, push, run tests/hooks or modify the source repo.
- [x] Retain bundle bytes, exact task handoff/evidence inventory and a provenance
  manifest atomically in the private ledger. Check authority before/after I/O;
  preserve original times, immutable replay and fail-closed corruption handling.
- [x] Bind collected preservation to separate result review, including the exact
  evidence versions being reviewed. Historical reads validate retained bytes
  without touching Git or refreshing evidence. Supplied historical proofs stay
  explicitly supplied; no automatic promotion or live ledger migration.
- [x] Test real temporary Git restoration, CLI composition, missing objects,
  oversize/unsafe storage, drift, Pause, replay, corruption and atomic rollback.
  Run all verification locally and update roadmap/operator guidance.

## Cost and rollout boundary

The owner requires no extra GitHub Actions billing. This repository has no
Actions workflows at the start of this increment. Do not add or enable workflows,
dispatch/rerun Actions, provision runners or add paid services. Local tests and
read-only GitHub metadata checks are separate evidence; absent CI is not green CI.

This increment changes source only. No live collection, acceptance, native task,
archive, installation, schedule change, resource release or Play activation.
Local bundle retention is not an off-device backup, native transcript export,
semantic review, workflow-trust proof, or proof of current task inactivity.

## Operator procedure

Use the existing registered workspace, admission store and designated-brain
controller; this cannot initialize or activate them. The same exact owner-approved
standard-policy, unpaused current run, attached terminal settlement, maintenance,
revision and closed-attempt gates as [result handoff](RESULT-HANDOFF.md) apply.
Harness and delegated approvals refuse before filesystem inspection. No source
path, command, model, credential or remote URL is accepted from the request.

```text
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace EXACT_WORKSPACE result-handoff-collect-preservation WORKER REQUEST_JSON
```

The request has exactly `id`, `expectedRevision`, `settlementHash`, `commit` and
`evidence`. The first four fields follow source collection. `evidence` is a list
of 1–40 `{subject, artifactId}` entries, sorted by unique subject. List every
retained evidence-axis and criterion proof used by the forthcoming result, not
unverified axes with no artifact. Subjects are the eight axis names or exact
`criterion:N` indices. Source/CI/merge use collector artifacts; other subjects use
the result-handoff supplemental protocol. The same GitHub artifact may appear for
both CI and merge. A version ID is required, not a path or latest-version alias.

1. Collect source/GitHub evidence and retain criterion/other-axis proofs normally.
   Their claims do not become verified merely because their bytes are retained.
2. Collect preservation using the current revision and that exact evidence list.
   Task/descendant handoff artifacts from terminal settlement are included
   automatically. Bundle, manifest, receipt and event commit in one local transaction.
3. Read the returned `artifactId` with `result-handoff-proof-read`, subject
   `preservation`, and the exact commit. It exposes original observation/retention
   times, provenance, Git restore findings, bundle ID/hash/size and evidence inventory.
   The binary `bundleArtifactId` is available through the existing authenticated
   Artifact library download; it is not printed by this command or sent to inference.
4. Independently review the findings. Reference this manifest in the result's
   `preservation` proof, with a new observation time after its retention. Generate
   and retain the separate independent-review report **after** the exact result.
   Submit that separate review through the existing result-handoff command.
   Its preservation evidence set must exactly match the manifest, including versions.

Self-reference and independent-review artifacts are excluded from the inventory
to avoid a hash cycle: the independent review necessarily binds the resulting
manifest later. It remains separately byte-checked by result review. This is not
an archival package of all future reviews, notes, transcripts or native attachments.
Replacing or adding a result proof requires a new preservation request/manifest,
followed by a newly bound independent review; never modify an existing receipt.

Collection does not set `preserved`, accept a task, archive it, release capacity,
change accounting, advance the phase or start work. Those boundaries stay separate.
Existing supplied preservation notes remain available and explicitly labelled
`result_handoff_evidence_v1`; they are not retroactively measured. No dashboard
archive control or automatic preference for this proof is added.

## What is actually preserved

The bundle contains the approved base/result and their reachable **local Git
objects and ancestor history**, including committed blobs outside the changed
paths. It does not include uncommitted/ignored files, other branches' unrelated
history, remotes, configuration, credentials from the environment, native task
transcripts, submodule repositories or external Git LFS payloads. Committed secrets,
if any already exist in that history, would also be copied: keep the private ledger
and downloads private; this is not a secret scanner or permission to publish them.

The standard-policy source identity is pinned by the existing local Git common
directory resource. Git uses a disposable bare view without original configuration,
replacement refs, hooks, filters, worktree access, lazy fetch or network protocols.
The closed `bundle create` call exports only two fixed refs. A second empty object
store unbundles and checks full strict Git integrity, base/result trees and ancestry
without referencing the original objects. Branch/layout identity is checked again
afterward. The original checkout, refs, index and object store are never written.

The bundle is capped at **8 MiB**, the manifest at **16,000 bytes**, and the request
at **8,000 canonical bytes** within the existing 16,000-byte regular-file CLI limit.
Git subprocesses have bounded output and timeouts (up to 10 seconds per bundle/
restore step); the object inventory retains its existing entry/time bounds.
Oversized or unsupported repositories fail closed without partial retention; no
automatic upload, partial bundle, remote download or paid storage fallback.
This is a trusted local-host operation, not an OS-isolation or adversarial archive
sandbox claim. Large repositories need a separately designed storage adapter.

The evidence manifest pins immutable bytes already inside the same SQLite ledger;
it does not duplicate them into the Git bundle. Loss of that ledger loses both.
Normal secure backups remain an operator responsibility and require separate scope.

## Replay, recovery and rollout

Exact replay returns the original receipt after Pause, expiry or maintenance,
without reading the checkout or running Git. New collection remains fenced.
Changed replay, missing journals, altered bundle bytes, missing evidence/handoffs
or changed provenance refuse; there is no automatic repair or recollection.
Review and historical state validate bundle/inventory integrity; old collection
times cannot be renewed by a fresh proof timestamp. After a crash before commit
there is no retained result; after commit, retry the exact request or read its
manifest. Temporary restore directories are cleaned up by the collecting process.
An abrupt OS/process termination can leave private temporary files for operator
cleanup; no background cleanup or worktree deletion is introduced.

No installed helper or live dashboard is changed by source delivery. Quiesce older
writers before a separately authorized rollout: older cached result reviewers do
not enforce this proof protocol. No mixed-version/downgrade guarantee is provided.
Preservation is one prerequisite, not a release of the native inactivity,
continuation/rereview, safe archival, owner activation and real-pilot gates.
