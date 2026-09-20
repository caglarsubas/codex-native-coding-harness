# WSP-04C3d — separate result review

Plan saved before implementation, continuing merged PR #28 (`04dcc13`).

Add one internal, standard-policy result-review coordinator after confirmed
terminal ownership settlement. A closed reservation, worker final message, CI
success or merge must never substitute for independent packet-result review.

## Implementation checklist

- [x] Require the exact shared settlement and attached local receipt; reject
  non-creation outcomes, missing history, changed task/seed/approval and Harness
  results until its trusted acceptance adapter exists.
- [x] Retain a bounded exact result: base/branch/commit, complete changed paths,
  PR head/base, each seed acceptance criterion and all eight evidence axes.
  Require hash-verified retained proof bytes and a separate reviewer report bound
  to this result, intent and settlement. Worker/descendant self-review is refused.
- [x] Accept only within the current run and repository policy, with all required
  criteria/axes verified and preservation evidence. Rejected results stay held;
  neither outcome sends corrections, creates tasks, merges or retries.
- [x] Commit the review, worker projection, queue projection and event atomically
  in the workspace ledger. Never write shared ownership or usage. Exact replay
  and historical reads do not refresh evidence or reapply an acceptance.
- [x] Preserve settlement receipt recovery after review without undoing completion.
  Fence legacy archival/pilot shortcuts for admission-managed workers. Test races,
  rollback/process exit, stale/corrupt evidence, scope drift and two-workspace reuse.

## Delivery boundary

The WSP-04C3d kernel initially provided internal designated-brain calls only.
The later [result handoff](RESULT-HANDOFF.md) exposes a stricter owner-approved
standard-policy CLI requiring collected source/CI and bound supplemental proofs.
No HTTP/assistant route, native transport, live migration, installed skill update,
runtime restart or Play activation accompanies source delivery.
The coordinator validates supplied evidence bindings and retained
bytes; it does not independently authenticate Git, CI, native task identities,
reviewer independence or deployment/tenant facts. A future trusted observer must
collect and independently verify those facts. The separate
[local source observer](SOURCE-OBSERVATION.md) now collects structural local Git
facts only; its provenance-bound source proof is checked by this coordinator.
The optional [GitHub observer](GITHUB-EVIDENCE.md) now collects exact PR/required-
check metadata and binds its CI/merge proof here. Other external and semantic
claims remain caller-supplied. No LLM output
authorizes acceptance.

New reviews require an unfenced, unpaused, unexpired current run and its exact
still-approved task contract. The automatic settlement hold alone is admissible;
other changed state refuses. Historical read/replay remains available after Pause
or expiry but cannot apply a new result. Maintenance blocks `review`, including
request replay; use the read-only `read` method for an existing receipt. One immutable review outcome
per closed attempt in this increment; corrections, rereview and cross-generation
acceptance need a later explicit contract, never deletion of the old receipt.

Acceptance means the packet's declared criteria and completion axes were recorded
as verified by the trusted caller. It does not mean all eight axes passed, the
platform is live, the pilot passed, or task archival was authorized. Failed and
unverified axes remain explicit. No source checkout is inspected or changed by
this coordinator; it executes no test, Git, network or inference command.

## Internal API

Construct `ResultReview` from the workspace's existing `DispatchAdmission`.
`review(controller_token, worker_id, request)` requires the designated brain,
registry/workspace/admission identity, maintenance fences and the exact confirmed
terminal outcome. Missing local settlement attachment must first be recovered
through `OwnershipSettlement`; this method cannot repair and accept in one step.
It refuses creation-recovery/non-creation outcomes and Harness policy, including
an otherwise valid exact-owner Harness grant. Harness must use its future trusted
launcher/attempt/acceptance adapter; do not call packet tests through this helper.

The closed request is finite JSON, at most 16,000 UTF-8 bytes:

| Field | Binding |
| --- | --- |
| `id` | Immutable per-worker request identifier, 1–100 ASCII identifier characters |
| `expectedRevision` | Current workspace revision for a new review |
| `settlementHash` | Exact shared and locally attached confirmed-terminal journal |
| `outcome` | `accepted` or `changes_required` |
| `result` | Exact result document below |
| `reviewArtifactId` | Retained independent JSON review report |

Result fields are `seedHash`, `baseSHA`, `commit`, `branch`, `changedPaths`,
`diffComplete`, `pr`, `ci`, `evidence`, `criteria`, `preservation`, `observedAt`.
The seed/base/branch must match the original approved task, and the result commit
must be distinct from its base. Changed paths are a complete, nonempty, unique
list of at most 200 concrete canonical repository-relative paths, each at most
500 characters. Both sides of a rename must be included. Completeness, Git object
existence, repository identity and rename coverage require external verification;
this kernel cannot prove them from a list. Accepted paths must stay within the
seed's allowed paths. A `changes_required` review may retain out-of-scope paths as
failure evidence; this never approves those edits or authorizes their repair.

`pr` contains a credential-free HTTPS `url`, exact `headSHA`, `baseSHA`, explicit
`state` (`open`, `closed`, `merged`) and nullable `mergeCommit`. Head/base must
match the reviewed result. Only merged PRs have a merge commit; only a merged PR
may carry verified merge evidence. An accepted result must have an open or merged
PR. Observing a PR or merge is not permission to push or merge, and manual-merge
policy remains intact. Without collector provenance the URL is only a supplied
reference, not a fetched repository attestation.

`ci` contains exact `headSHA`, boolean `complete`, up to 80 unique
`requiredChecks` names and up to 80 `checks`. Each check has `name`, exact
`headSHA` and `status` (`passed`, `failed`, `pending`). Verified CI requires
complete coverage of a nonempty required-check set, all passing on this commit.
An empty check list is not green CI. Discovering the actual required-check policy
is the observer's responsibility, not an arbitrary list from a worker. The optional
GitHub collector binds policy to the exact repository and base branch; unsupported
or inaccessible coverage remains unverified.

`evidence` always has all eight axes: source, CI, merge, artifact, deployment,
runtime, assurance and tenant (lowercase contract keys). Each proof is exactly
`status`, nullable `artifactId`, `observedAt`; statuses are `verified`, `failed`,
`unverified` or `not_applicable`. Every status other than unverified needs retained
proof bytes. `criteria` covers each seed acceptance criterion exactly once, in
order, with `index`, `criterionHash` (canonical JSON SHA-256 of the criterion) and
`proof`. `preservation` uses the same proof shape. Acceptance requires every seed
completion axis and criterion verified, plus verified preservation. Other axes
retain their actual recorded status, including failures, and are not promoted.

## Retained evidence and independent review

Each referenced proof is a retained artifact version with metadata and content
bounded to 16,000 bytes each. The coordinator rechecks content SHA-256 and the
key/version/content-derived ID, repository and a metadata reference containing
exact `workerId`, `intentHash`, `commit` and `subject`. Subject is the axis name,
`criterion:N` (zero-based), `preservation`, or `independent_review`. References
and artifact text are inert data, never instructions. The existing artifact
library retains and reads these versions; no new artifact ingestion is added.

WSP-04C3e source artifacts additionally require their exact collector journal and
request receipt, canonical bytes, provenance, task/settlement/base/commit/branch
and full path-set binding. Original collection time participates in freshness;
later proof review does not refresh it. An out-of-scope collected diff cannot
verify source, and source bytes do not prove CI or semantic correctness. Earlier
unlabelled supplied artifacts remain subject to the original trust boundary.

WSP-04C3f GitHub artifacts likewise require their exact journal, request receipt,
canonical bytes and task/settlement binding. Both PR and CI projections must match
the retained observation, even when used only for one of those axes. The original
collection start participates in freshness; review timestamps cannot renew it.
Unknown/failed CI cannot be promoted, and merge can be verified only when actually
observed merged. These artifacts cannot prove other axes or acceptance criteria.

WSP-04D5 supplemental proofs carry `result_handoff_evidence_v1` provenance. The
shared artifact reader checks their immutable journal/request receipt and original
bytes, task, commit, subject and observation time on new review and historical
reads. Original supplied observation time participates in freshness, including for
the independent review artifact. These remain caller assertions, not attestation.
The CLI requires them; older unlabelled internal proofs retain their prior boundary.

The optional WSP-04C3g `local_preservation_v1` manifest is also accepted for the
preservation subject. It requires its immutable journal/receipt, retained binary
bundle and exact handoff/result evidence bytes. The result must reference the same
evidence subjects and versions, and collection start participates in freshness.
Historical reads recheck those bytes without re-running Git. It proves bounded
local Git/evidence retention only; other axes and caller-supplied claims remain
separate. See [local preservation](LOCAL-PRESERVATION.md) for exclusions and limits.

The independent review artifact is closed JSON with unique fields:
`kind: independent_result_review`, `workerId`, `intentHash`, `settlementHash`,
`resultHash` (canonical result digest), `outcome`, `reviewer`, `observedAt`,
`summary`. Reviewer is exactly `hostId` and confirmed `threadId`; the summary is
nonempty and at most 2,000 characters. The reviewer cannot match the implementation
task, any settled descendant or its retained pending client ID. The brain may be
the reviewer. Different IDs are only a structural separation: a trusted adapter
must authenticate identity and ensure the reviewer actually verified the result.
The artifact alone is not an independently authenticated signature or attestation.

Proof bytes must be retained after creation started and before the supplied proof
observation. The result observation must follow terminal settlement and all proof
observations; independent review follows the result and precedes its own artifact
retention. All proof/result/review observations and review retention are fresh and
non-future under the admission policy when recording a new review. Historical
reads do not refresh these timestamps or require old evidence to become fresh.
Original terminal handoff artifacts also remain byte-verified and retained.

## Atomic outcome, recovery and supervision

Lock order remains registry -> workspace -> admission. Shared settlement/native
history and allocation integrity are verified, but claims, ownership, counters,
resource rows and shared events are never written. No fresh usage sample is
fabricated: recording externally obtained review evidence invokes no model or
native work and does not alter cumulative phase/review accounting.

The result record, worker/queue pointers and event commit together in one workspace
transaction. Accepted workers/packets become `complete` and their automatic queue
hold clears; preserved evidence/PR/commit are recorded separately from native
activity. A rejected worker stays `settled`, its packet blocked and held, and the
old unverified worker axes remain untouched; its full rejection is in the retained
result record. The attempt is closed in both cases. Neither can reopen creation,
correction, runner use or approval through legacy paths.

A crash before commit leaves no review. A crash after commit needs only
`read(token, worker_id)` or exact request replay. Changed replay refuses. Read and
replay recheck retained proof bytes, projections and the sealed shared journal;
they neither refresh evidence nor apply a new result. Missing/corrupt documents or
projection drift fail closed. There is no result receipt repair API because all
result writes are in one database transaction. Shared terminal recovery recognizes
the later valid review without reverting it; its old `packetAccepted: false`
receipt describes settlement only, not the newer result outcome.

Legacy pilot qualification, worker-ID-only archive requests and generic archive
acknowledgments refuse admission-managed workers. The later exact-owner
[archive handoff](ARCHIVE-HANDOFF.md) is a narrow separate exception: accepted
review, measured preservation, cleanup acknowledgment and fresh root-only safety
evidence precede a consumed native send check. Dashboard and assistant still do
not offer managed archive actions. Completed admitted tasks stay in safe-Pause inventories,
including descendants; acceptance is not a fresh idle observation or archival.
No cleanup, task closing, worktree deletion, concurrency upgrade or phase advance
occurs through result review. A new-generation continuation/rereview contract and
delegated archival policy remain necessary.

See [verification](RESULT-REVIEW-VERIFICATION.md). Independent observation
collection, native transport, Harness acceptance, maintenance migration, exact
owner activation and a separately authorized supervised pilot still precede live
autonomous Play. This source change does not upgrade cached live processes; any
future rollout must checkpoint and stop older helpers first.
