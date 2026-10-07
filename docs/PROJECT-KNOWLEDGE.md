# Durable project knowledge and bounded brain context

The operational ledger, reviewed mission, repository revisions and preserved
artifacts remain authoritative. The knowledge index is a private, rebuildable
search aid. Search results carry project/repository, source path, revision or
document hash, observation time, and extracted versus inferred provenance.
They never grant approval, acceptance, merge or native task authority.

## Implementation sequence

1. Measure only registered brain and worker sessions, retain coverage gaps and
   immutable observations, and charge cumulative high-water usage. Fresh,
   complete evidence is required before a new standard effect. A checkpoint
   can always be recorded; post-checkpoint closeout is labeled separately.
2. Build one index per registered project and repository from bounded,
   allowlisted source files. Graphify is an optional pinned code-only subprocess
   provider. Copy only eligible tracked code into a private staging directory
   before extraction; no repository hook, global configuration or automatic
   runtime installation. The provider adapter emits a bounded graph file and
   provenance metadata; core search and the ledger depend on neither Graphify
   imports nor its storage layout. Record a content manifest and Git revision.
3. Offer project-scoped status, explicit refresh, search and source reading in
   the dashboard and brain CLI. Return at most ten results and 24 KiB of
   excerpts. Missing/stale graph data falls back to bounded direct source
   inspection, labeled as such. Inference receives metadata and links only.
4. Preserve an immutable checkpoint package: mission/review hashes, authority,
   tasks/results, unresolved effects, usage and knowledge references. Prepare
   and confirm replacement through an expiring owner preview only after Pause,
   safe settlement and controller release. Verify the new native task and its
   package receipt before rebinding. Never reset usage, approvals or authority.
5. Evaluate 20 fixed real questions; at least 18 must retrieve the expected
   manually verified source in the top ten. Verify stale/missing evidence,
   cross-project isolation, replay, receipt uncertainty and rendered controls.

## Boundaries

The existing standard cooperative contract applies only to registered standard
projects. Strict Harness work cannot consume an index containing forbidden warm
source material. The plan adds no scheduler, paid API, telemetry, GitHub Actions
workflow or automatic brain rotation. The optional provider is not installed by
source delivery. A running service or brain is not replaced by merging code.
Graft comparison and semantic/model enrichment remain deferred.

## Private setup and activation boundary

Keep `knowledge.json` in the selected project's private ledger directory, not
in a source repository. An example is in `config/knowledge.example.json`.
Each repository key must be an existing registered **standard** repository ID;
each prefix must be a specific repository-relative directory. A null Graphify
setting uses bounded direct Git-source search. To enable the optional provider,
install Graphify 0.9.66 separately under an owner-reviewed local path, record
the exact executable SHA-256 and set the absolute executable, version and hash
in the private file. Refresh the index explicitly. The application never
downloads it, installs hooks, changes repository instructions or sends source
to the inference service. Local code-only extraction is not a claim of
OS-enforced network isolation.

The adapter invokes `extract` with `--code-only --no-cluster --max-workers 2`
against a private staging tree containing only eligible tracked Git blobs. It
passes no inherited model credentials to either the version probe or extraction.
This is a structural/no-model path, not a proof that arbitrary third-party code
cannot open a network connection. The executable hash and version check pin the
entrypoint observed by the app; they are not a complete attestation of every
installed Python dependency. Keep the installation review separate from Play.

The Knowledge view and `knowledge-status`, `knowledge-refresh`,
`knowledge-search`, `knowledge-records`, `knowledge-related` and source CLI
operations require an explicit project. Code results are at most ten distinct
files and 24 KiB of excerpts. Roadmap, decision and artifact results are
metadata links to existing retained versions, not duplicate source bodies.
When a standard brain claims a task, its immutable inheritance seed receives
at most ten versioned source references matching exact requested task paths.
It never receives the parent conversation, entire graph or source excerpts;
missing knowledge does not block an otherwise authorized task.
If the index is missing or the HEAD/config/allowlisted checkout changes, search
falls back to bounded HEAD inspection and visibly labels that limit. It never
claims to search uncommitted content. Historical indexed citations remain
readable at their recorded Git blob, provided that blob is retained locally.

New standard Play can opt into the measured-usage guard in its signed review.
The guard requires a fresh, complete local observation before further effects;
missing samples mean unknown remaining measured budget, not zero. Older runs
are not silently enrolled. Terminal closeout samples are retained separately
from phase totals. Reservations, account limits and provider billing remain
distinct. The graph cannot enforce a provider billing cap.

Recent native response journals also include compaction consumption. The
[compaction-aware collector](COMPACTION-USAGE.md) charges those exact-session
records once and reconciles the older context-display stream without counting
its context estimate as a model call. Missing or conflicting response records
remain gaps; source delivery never rewrites saved usage or Resumes a phase.

Brain handoff is a two-review, owner-confirmed operation. The old task may
prepare one native replacement only after a saved paused/completed/blocked
checkpoint and controller release. A candidate task and its package receipt are then checked before
the owner confirms the actual binding change. Neither review starts Play,
resumes a phase, resets usage, installs a skill or restarts a service. Uncertain
native creation must be reconciled, never retried blindly.
The replacement must read the retained package and emit the exact standalone
`CODEX_ORCHESTRATOR_HANDOFF_RECEIPT_V1` line in a final Codex reply. Build that
line with `orchestrator.brain_handoff.receipt_marker(receipt_body)`, where the
marker input contains the prepared handoff ID, package hash and a bounded
summary. Only after that final reply is in the local native session log should
the old brain submit `brain-handoff-receipt` with those exact fields plus the
candidate's native task ID. The reader checks the
task ID, reviewed Git checkout identity, post-preparation final reply and exact
package/summary marker; it retains the native record hash and observation time, not the
transcript. The native project membership is still a brain-observed claim in
the candidate record. Before final rebinding, the old brain must also retain
a fresh exact native task/project observation. It may import a bounded native
`list_threads` result containing exactly one matching Codex task, project ID
and host ID:

```sh
python3 -m orchestrator.cli --platform /private/platform --workspace EXACT_PROJECT brain-handoff-native-observation /private/list-threads.json --observed-at ORIGINAL_UNIX_SECONDS
```

When an existing reviewed owned app-server binding is available, the old brain
may instead read only the candidate's exact `thread/read` metadata on that host:

```sh
python3 -m orchestrator.cli --platform /private/platform --workspace EXACT_PROJECT brain-handoff-native-exact-read /private/brain-wake.json
```

This read revalidates the old brain, both separately pinned project IDs, native
project root, candidate UUID, non-ephemeral local checkout and native activity
before retaining a bounded metadata hash. It never starts/resumes a task or
changes the binding. An unassigned, foreign, forked, active-at-final-review or
unavailable candidate fails closed. The bound host read is an alternative to a
truncated global list, **not** a complete native task/descendant inventory or a
cryptographic host attestation.

Call this after the replacement's final reply, while the old brain owns the
controller, then release the controller before final owner review. A result
showing the replacement still active may be retained, but final review waits
for a fresh result showing it idle (or `notLoaded` on the bound exact-read
path). This stores only exact membership and
status, the result hash and observation time; titles,
summaries and unrelated task rows are discarded. The observation must follow
the candidate, be no older than one hour at final review, and agree with the
reviewed project binding. The imported list remains a brain-observed tool
result, **not** a cryptographic Codex-host attestation. The owner must review
that boundary; missing native membership, native log or marker blocks rebinding.
A bounded current `list_threads` result may omit an older candidate. That omission
proves neither that the candidate is absent nor that it belongs to the reviewed
project. Keep the recorded candidate and final reply receipt; native creation is
one-shot and must not be retried or replaced to fill the evidence gap. Refresh,
Resume and pinning/unpinning do not provide the required fresh, exact, inactive
membership. The final reply proves the package receipt, while the
separate native observation provides project/host membership and current
inactive status. Owner rebinding requires both in the signed final review; it
does not activate the selected project or start Play.
The ledger commits the binding first; if the second database commit is
interrupted, project opening fails closed on its identity check. The explicit
`brain-handoff-recover HANDOFF_ID --confirm` CLI operation repairs only that
exact ledger-committed registry binding after owner inspection. It performs no
native task operation and cannot change an uncommitted or foreign handoff.
The dashboard and `brain-handoff-status` CLI show a read-only readiness summary
for preparation and final review, including the specific missing checkpoint,
project or native evidence. This is guidance from the current local observation,
not a durable authorization: the server repeats every gate in the separately
signed, expiring owner preview and again at confirmation.

## Evidence and current qualification

A saved standard Pause with a closed pre-turn failure may have a separately
signed **Recover saved Pause** control in the same graph-centered workspace.
It prepares the exact checkpoint-only preview without prompt writing. Durable
progress follows that new recovery, not the old failed delivery. Only an empty,
stopping standard run with stable bound-host completed-turn metadata is eligible;
uncertain effects, task ownership and strict Harness remain fenced. A paused
checkpoint is not pilot acceptance or permission for Play. Source, installation
and live qualification remain separate. See [failed-Pause recovery](FAILED-PAUSE-RECOVERY.md).

The fixed 20-question evaluation in `tests/test_knowledge_eval.py` checks
top-ten retrieval against manually reviewed owner modules and two deliberately
missing-evidence identifiers. Local tests provide source qualification only.
Graphify extraction with an installed binary, a rendered live dashboard,
disposable-project native handoff, merged source, installed backend and selected
standard-project activation remain separate evidence states until observed.
