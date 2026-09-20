# WSP-04D5 — brain-owned result evidence and review handoff

Update: [WSP-05C](BRAIN-COORDINATOR.md) also supports valid owner-delegated
standard-policy approvals, including local result preservation. This supersedes
the initial exact-owner-only scope below, not settlement, proof provenance,
independent review, Pause or current authority requirements. No live acceptance.

Plan saved before implementation, following PR #35 merged at
`e8839dcf10d05d5536f0fa041b315f3f4d81f31b`.

## Plan

- [x] Expose selected-workspace, designated-brain CLI operations for result state,
  existing local/GitHub collection, supplemental proof retention/reading and
  separate result review. No dashboard/assistant action or native transport.
- [x] Restrict the first handoff to exact owner-approved standard-policy tasks
  with confirmed terminal settlement. Preserve all current authority, Pause,
  maintenance, freshness, resource and replay checks; never initialize admission.
- [x] Retain bounded caller-supplied criterion/preservation/other-axis and independent
  review text as inert, task-bound artifacts with immutable request receipts.
  Original observation time, bytes and provenance must survive replay/review.
- [x] Require measured local source and GitHub CI proofs through this CLI;
  supplemental claims cannot impersonate collectors or prove themselves. Independent
  review is supplied by the brain, not generated or automatically accepted.
- [x] State/proof reads are historical and integrity-checked, without collection,
  writes or renewed freshness. Rejected results stay held; accepted results do not
  merge, archive, retry, advance phase or enable Play.
- [x] Verify a real subprocess CLI round trip in isolated fixtures, source/GitHub
  collector composition, proof tampering, concurrency, rollback, stale evidence,
  owner/Harness boundaries and regressions. Update roadmap and operator docs.

## Delivery boundary

Source implementation only. No live workspace collection, result acceptance,
native task/message, installed skill update, accounting change, allocation,
maintenance release, dashboard restart or Play activation is part of this run.
Native/host/usage qualification, preservation truth, rereview/continuation/archival,
owner rollout and supervised pilot remain separate work.

The later optional [local preservation collector](LOCAL-PRESERVATION.md) measures
bounded local Git/evidence retention. External/off-device preservation and archive
qualification remain separate; supplied notes are not promoted into collector proof.

## Brain procedure

Use an already admitted, exact **owner-approved standard-policy** task with its
confirmed terminal settlement attached locally. The current controller belongs
to the selected registered workspace brain. These commands cannot create a run,
initialize admission, settle native work, approve a packet or enable delegation.
Harness remains blocked before source/network inspection; its trusted acceptance
adapter is separate. First-handoff support for delegated task approvals also needs
separate qualification, matching the creation and runner handoff boundaries.

Commands share this prefix:

```text
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace EXACT_WORKSPACE
```

Keep `ORCHESTRATOR_CONTROLLER_TOKEN`, input files, artifact contents and receipts
private. Each JSON request is a bounded regular UTF-8 file (at most 16,000 bytes),
not a symlink or FIFO. Duplicate fields and non-finite JSON are refused. No default
workspace or legacy `--state` fallback is permitted.

| Command suffix | Purpose |
| --- | --- |
| `result-handoff-state WORKER` | Read exact settlement, task requirements, current revision and any recorded review |
| `result-handoff-collect-source WORKER REQUEST_JSON` | Explicit local Git collection under the existing isolated source observer |
| `result-handoff-collect-github WORKER REQUEST_JSON` | Explicit read-only exact PR/policy/check collection |
| `result-handoff-collect-preservation WORKER REQUEST_JSON` | Retain a bounded locally restored Git bundle and exact handoff/evidence manifest |
| `result-handoff-proof-add WORKER REQUEST_JSON` | Retain task-bound supplemental proof text; never mark it verified or accepted |
| `result-handoff-proof-read WORKER REQUEST_JSON` | Read exact retained proof, provenance and original/retention timestamps |
| `result-handoff-review WORKER REQUEST_JSON` | Apply one separate acceptance or changes-required review under current authority |

1. Read state. It contains the exact intent/seed/settlement, approved base/branch,
   allowed paths, required evidence axes and criterion indices/text/hashes. Missing
   settlement refuses rather than repairing it. This is historical state, not fresh
   native activity, run readiness or permission to proceed.
2. Collect source with `{id, expectedRevision, settlementHash, commit}`. Collect
   GitHub with the same shape plus `prUrl`. Use the current workspace revision for
   each new write. All existing collector identity, freshness, I/O bounds and
   before/after authority checks remain enforced. Preserve returned artifact IDs.
3. Read each proof with `{artifactId, commit, subject}`. Source uses `source`;
   GitHub uses `ci` or `merge`. Verify the measured result and limitations. Do not
   turn unavailable CI into passing or a source-path diff into semantic correctness.
4. Independently examine semantics, every acceptance criterion, required extra
   axes and preservation. Retain the supporting material using `proof-add` below.
   This CLI neither performs that review nor attests a supplied claim's truth.
   Optionally use `collect-preservation` after the other result proofs; its exact
   request schema, inventory/version binding and local-only limits are documented
   in [local preservation](LOCAL-PRESERVATION.md).
5. Build the exact result document from [result review](RESULT-REVIEW.md), using
   the collected source path set and GitHub PR/CI projection unchanged. Supply all
   eight axes, exact criteria and preservation proof. Source and CI artifacts must
   come from their collectors even for a changes-required outcome; a mere worker
   message or manually labelled artifact is insufficient on this CLI.
6. Retain a separate `independent_result_review` JSON report as an
   `independent_review` supplemental artifact. The brain must actually review the
   result and bind its exact canonical hash, outcome, task and settlement. A worker
   or descendant cannot review itself. No report/summary is generated automatically.
7. Submit the closed review request from `RESULT-REVIEW.md`, including the current
   revision and independent report artifact ID. Acceptance changes only the local
   worker/queue/review record. Changes-required leaves the settled attempt held.
   Neither outcome retries, sends a correction, archives, merges or advances phase.

## Supplemental proof contract

`proof-add` takes exactly these fields:

| Field | Meaning |
| --- | --- |
| `id` | Immutable per-worker evidence request ID |
| `expectedRevision` | Current workspace revision for a new write |
| `settlementHash` | Exact confirmed terminal settlement |
| `commit` | Full result commit |
| `subject` | `criterion:N`, `preservation`, `independent_review`, or a non-source/CI/merge evidence axis |
| `observedAt` | Actual original observation time, fresh and not before settlement or in the future |
| `content` | Nonempty inert UTF-8 text, at most 8,000 bytes |

The canonical request is additionally bounded to 12,000 bytes; the retained
journal is at most 16,000 bytes. `criterion:N` must be an exact current seed index,
not a padded or guessed number. Supplemental `source`, `ci` and `merge` are refused:
those subjects must use the collectors. Other-axis text remains a supplied claim,
not a new runtime/tenant capability or permission to perform a live action.

Content may be a review note, small test-evidence excerpt, preservation verification
or independent-review JSON. Never include credentials, private keys or unrelated
conversation material. It is stored byte-for-byte and never executed, sent to an
LLM, interpreted as authorization, or used as a shell/native-tool argument. Invalid
independent-review JSON may be retained as text but cannot pass the subsequent
strict review contract; retention is not validation or acceptance of its claims.

The artifact has `result_handoff_evidence_v1` provenance, exact worker/intent/commit/
subject references, original time and a journal hash. An immutable request receipt
binds the artifact to the original request. The shared artifact reader validates
this provenance on all later result reads, including the internal review kernel.
Missing journal/receipt, changed bytes or stripped labels cannot fall back to generic
proof. The CLI requires these typed supplemental artifacts for all supplied proofs
and the independent report; unlabelled proofs are not accepted through this handoff.
Earlier internal caller-supplied evidence retains its documented trust boundary.

## Freshness, recovery and safety

Proof observations must follow terminal settlement and precede retention. Result
proof timestamps must follow artifact retention; independent review follows the
result and precedes its own retention. Original collector and supplied observation
times participate in new-review freshness. Repackaging old bytes with new review
timestamps cannot make them fresh. Observation and retention times stay distinct
in proof-read output.

Registry -> workspace -> admission lock ordering is unchanged. New supplemental
proofs require current run/task authority, exact revision, attached settlement,
unchanged allocation and no Pause/maintenance/worker-control fence. Journal,
artifact, receipt and event commit in one local transaction. Concurrent identical
adds retain one outcome; failure before commit leaves no partial proof. No shared
usage, resource ownership or native state is changed.

An exact proof-add replay returns the original integrity-checked receipt without
refreshing time, even after Pause, expiry or maintenance. Changed content under
the same ID refuses. Source/GitHub exact replay keeps its existing no-I/O behavior.
State and proof reads are also historical and non-mutating. They never call Git,
GitHub, native tools or inference. State output is bounded to 128,000 bytes.

Review keeps its existing one-outcome-per-attempt transaction and replay rules.
Maintenance fences even review replay; use `state` for the existing outcome.
Rejected attempts cannot add new proof, recollect or rereview through this path.
Do not delete old history to rearm one. Fresh source/CI collection and acceptance
are not safe-Pause, host cleanup, archival, pilot qualification or execution authority.

No installed skill/helper is upgraded by this source delivery. Before future
live use, quiesce older writers, back up private state and perform an explicitly
approved compatible rollout. Do not run an older cached helper against the new
proof records: older versions do not enforce their provenance/freshness contract.
This release provides no mixed-version or downgrade compatibility contract.

See [verification](RESULT-HANDOFF-VERIFICATION.md) and [remaining gates](ROADMAP.md).
