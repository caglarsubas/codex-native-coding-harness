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

Brain handoff is a two-review, owner-confirmed operation. The old task may
prepare one native replacement only after a saved paused/completed/blocked
checkpoint and controller release. A candidate task and its package receipt are then checked before
the owner confirms the actual binding change. Neither review starts Play,
resumes a phase, resets usage, installs a skill or restarts a service. Uncertain
native creation must be reconciled, never retried blindly.
The ledger commits the binding first; if the second database commit is
interrupted, project opening fails closed on its identity check. The explicit
`brain-handoff-recover HANDOFF_ID --confirm` CLI operation repairs only that
exact ledger-committed registry binding after owner inspection. It performs no
native task operation and cannot change an uncommitted or foreign handoff.

## Evidence and current qualification

The fixed 20-question evaluation in `tests/test_knowledge_eval.py` checks
top-ten retrieval against manually reviewed owner modules and two deliberately
missing-evidence identifiers. Local tests provide source qualification only.
Graphify extraction with an installed binary, a rendered live dashboard,
disposable-project native handoff, merged source, installed backend and selected
standard-project activation remain separate evidence states until observed.
