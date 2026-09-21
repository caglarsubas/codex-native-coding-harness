# WSP-04H — owner native observation setup and saved reports

Plan saved before implementation against verified PR #58 merge
`19a99de3b5b7e9351ecba2dec4e5179db4a1e76f`.

- [x] Add explicit selected-workspace inspection of endpoint reviews, eligible
  existing standard-policy allocations and bounded saved collection metadata.
  Reads never connect, start a process or initialize shared accounting.
- [x] Add authenticated, signed owner endpoint review/revoke previews and exact
  confirmation. Bind browser session, workspace/registry/ledger/shared-store
  identities, revision, phase allocation and endpoint fingerprints. Recheck files
  without executing them; revoke remains possible if files/shared state disappear.
- [x] Expose setup under Run readiness with blank explicit inputs, clear read-only
  scope, unchecked confirmation, workspace-isolated drafts and original report times.
  No collection, server startup, discovery or native-task controls in this UI.
- [x] Keep polling/assistant projections to cached bounded status/counts only.
  Test filesystem replacement, allocation drift, concurrency, rollback, historical
  retries, HTTP authentication and disposable browser interaction locally.

The owner approves a future bounded metadata-read endpoint, not execution, tokens,
account access, source collection or Play. Only the designated brain's existing
explicit collector may subsequently connect. No model calls, native mutation,
provider fallback, installation, schedule change or live state is authorized.
Complete ephemeral membership, lifetime counters, OS cleanup and per-turn settings
telemetry remain unavailable; saved metadata cannot satisfy those gates.

## Owner workflow

1. Select the workspace and open **Run readiness → Inspect observer setup**.
   This reads existing local records only. It does not initialize the shared store,
   check a connection, observe native activity or renew any saved report timestamp.
2. During paused setup, choose **Configure observation endpoint**. Select an exact
   existing open standard-policy phase allocation. Harness is excluded before
   endpoint file access. This page does not create an allocation or authorize a run.
3. Supply the canonical path to a separately trusted installed executable, its
   existing private local socket and the SHA-256 of the independently observed
   server initialization identity described in [the collector contract](NATIVE-EVIDENCE-COLLECTION.md).
   The fields start empty; no credentials, URLs, command arguments or guessed
   identities are accepted. Normal socket replacement requires new owner review.
4. **Preview endpoint access** checks file ownership, permissions, executable
   bytes and socket identity without execution or connection. Review the exact
   workspace/allocation, paths and hashes. The confirmation checkbox starts unchecked.
5. **Record endpoint review** saves a versioned endpoint permit for the designated
   brain's existing bounded metadata collector. It does not call that collector,
   notify the brain, start a server/task/model, update usage or enable Play.
6. **Preview endpoint revocation → Revoke endpoint access** blocks later
   collection for that exact review. It cannot cancel an in-flight read, stop
   native work or delete evidence. Intact reviews remain revocable when endpoint
   files, saved reports or shared accounting disappear or become unavailable.

Endpoint versions are newest first; saved collection reports show original times,
sample/activity counts, tracked-terminal counts, endpoint-review matching and
explicitly incomplete coverage. No raw native IDs, terminal commands, transcripts,
model names, errors or proof bodies are included in report summaries. A recent
timestamp is not a fresh validation of the report's effect context. Zero tracked
terminals are not process cleanup; an idle sample is not complete task-tree proof.
The label ages from the original collection time and cannot become fresh on reopen.

Inspection expires after 60 seconds or a local revision change. Reinspect before
preparing a new preview. Forms remain private to the current tab, keyed by workspace,
with generation guards against late responses after switching away and back.
An uncertain confirmation is never retried automatically. A manual identical retry
can recover only its original receipt; it cannot restore revoked endpoint access.

## Authenticated surface and concurrency

Only the selected-workspace routes exist:

| Route | Effect |
| --- | --- |
| `GET /api/workspaces/{id}/native-observer-controls` | Explicit read of existing endpoint/allocation/report records |
| `POST /api/workspaces/{id}/native-observer-controls/preview` | Non-connecting review/revoke preview |
| `POST /api/workspaces/{id}/native-observer-controls/confirm` | Exact confirmed owner review/revoke receipt |

Host, origin, authenticated session, scoped CSRF and workspace registration checks
apply. Strict JSON rejects duplicate keys, non-finite numbers, surplus fields and
bodies over 32 KiB. There is no unscoped route, direct review/revoke shortcut,
collection/discovery/start/connect/Play route, owner CLI or assistant action.

The server signs a five-minute preview bound to its process key, browser session,
workspace, registration/brain, registry/local/shared database identities, exact
revision/context, allocation fingerprint and endpoint fingerprint. Shared inode
and socket identity values use lossless decimal strings in browser JSON; nanosecond
timestamps must never round through JavaScript numbers. Confirmation verifies the
signature before restoring those integers and revalidating the endpoint.

Lock order is registry → local ledger → existing shared allocation store. The
shared allocation remains write-locked until the local endpoint receipt is durable;
a concurrently closed allocation cannot slip through. The shared transaction does
not mutate accounting. Revocation deliberately needs neither the shared store nor
endpoint files. Historical replay precedes freshness checks but follows authenticated
scope/signature/storage identity checks and never reapplies the prior write.

Explicit read bounds precede decoding: at most 1,000 endpoint versions / 2 MB,
1,000 saved reports / 8 MB, 128 shared allocation rows after the existing 4 MB
bounded object reader, 64 samples per report. Return only the newest 20 endpoint
versions and 20 reports, disclose omissions, cap inspection at 128 KB and signed
preview at 28 KB. Damaged/excessive records require operator recovery, not an older
healthy fallback. Saved report history is diagnostic, not latest-pointer authority.
Polling and assistant fact F39 expose cached closed counts/status/original times
only, never endpoint paths, IDs, hashes, raw reports or implicit inspection.

## Verification and rollout boundary

Focused regressions cover no process/connection, filesystem identity and permission
drift, unsafe paths, allocation closure, workspace/brain/session/storage replacement,
signature/TTL/confirmation checks, lossless browser number transport, local rollback,
concurrent review/revoke, historical replay, bounds, redacted I/O failures, missing
shared storage, report privacy, HTTP/CSRF and workspace-generation races.

Disposable browser QA used fake executable/socket metadata and a synthetic report:
blank choices, unchecked confirmation, successful versioned review and revocation,
historical evidence, empty second-workspace isolation, light/dark themes and narrow
workspace rendering. No native endpoint was connected. The initial browser test
caught nanosecond rounding; the fix is regression-covered and the flow was rerun.

Final local verification: all 1,542 Python tests (including 29 focused owner
backend/HTTP tests), all fifteen JavaScript UI suites, all web JavaScript syntax,
Python compilation and diff whitespace checks passed. GitHub read-only inventory
showed zero configured workflows and zero workflow runs before publication.

Source delivery is not live installation, native qualification or operational
acceptance. Do not update the installed skill/dashboard, private ledgers, .env,
native schedules or maintenance/dispatch state as part of this PR. No hosted
workflow, paid API or GitHub Actions execution is needed. Milestone 3 remains
externally capability-gated; this closes owner setup/visibility, not complete Play.
