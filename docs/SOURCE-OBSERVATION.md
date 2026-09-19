# WSP-04C3e — exact local source observation

Plan saved before implementation, continuing merged PR #29 (`02152fa`).

## Implementation plan

- [x] Add a bounded, explicit standard-policy local Git observer. Derive the
  repository path, branch, base and pinned common-directory resource identity from
  the existing exact task/settlement; accept no browser paths or arbitrary argv.
- [x] Inspect only existing local commit/tree metadata using a temporary,
  configuration-isolated Git view. Disable replacements, helpers, optional writes
  and all transport; never fetch, run hooks, filters, packet commands or tests.
  Refuse ambiguous/symlinked metadata, external object alternates, shallow history
  and unsupported formats instead of guessing completeness.
- [x] Verify exact commit objects, base ancestry, branch tip and full base-to-result
  changed paths (including both sides of renames). Pin/recheck repository identity
  and branch across the observation. Record out-of-scope changes as findings, not
  permission. Do not read checked-out source or claim a clean worktree.
- [x] Retain a bounded source artifact plus immutable observation receipt only
  after rechecking authority/state following I/O. Exact request replay returns the
  original receipt without Git reads or refreshed timestamps. No shared owner,
  budget, completion, native activity or run state changes.
- [x] Make result review recognize collector-owned source proof and reject a
  mismatched commit/path set or forged/missing collector receipt. Preserve the
  explicit caller-supplied evidence boundary of earlier unlabelled proof artifacts.
- [x] Verify with real temporary Git repositories, worktrees, packed refs, safety
  controls, stale/state-race cases, atomic retention and all regressions.

## Boundary

This increment collects local source structure, not semantic correctness, remote
push/PR/CI status, required-check policy, preservation, deployment, runtime, native
inactivity, reviewer identity or tenant acceptance. Source review stays separate.
The local Git executable/filesystem are trusted; this is not an OS sandbox or a
defense against a malicious process rewriting objects concurrently. Read intervals
are observed and rechecked, not an external repository lock or signature.

Internal designated-brain source calls and isolated fixtures only. No CLI, HTTP,
assistant action, installed skill update, live collection/migration, product
repository inspection, schedule change, native transport or Play activation.
Harness is refused before filesystem inspection; its clean-room/trusted-runner
rules cannot be implemented by a generic Git observer. No live state is touched
merely to deliver this source change.

## Internal API and authority

Construct `SourceObserver` from an existing `DispatchAdmission` instance and call
`observe(controller_token, worker_id, request)`. This is not exposed by the CLI,
dashboard or assistant. Do not invoke it against live state to upgrade tooling.

The request has exactly four fields:

| Field | Binding |
| --- | --- |
| `id` | Immutable request identifier, 1–100 ASCII identifier characters |
| `expectedRevision` | Exact workspace revision for new collection |
| `settlementHash` | Shared and locally attached confirmed-terminal settlement |
| `commit` | Exact 40-character lowercase SHA-1 result commit |

The registered repository path, approved branch/base, allowed paths and local
common-directory identity are derived from the bound intent/allocation/seed, not
accepted from the request. Exactly one `repo-local:` resource key must be pinned
in the existing allocation. Remote-only resource identity is insufficient. No
identity is inferred, allocation opened or repository registered by this helper.

The designated brain must hold its current controller. New observations require
unpaused/unexpired current run and task authority, standard repository policy,
an unrevised task binding and the exact settlement review hold. Pending worker
controls, unreconciled local runners, maintenance fences, detached settlement,
non-creation and previously reviewed results refuse. Read-only Git collection
runs outside ledger locks. On return the same authority, shared journal, revision
and binding are rechecked before any observation/artifact/event is retained.
Pause during collection discards the result; it never finishes a stale write.

## Local Git observation

Only the installed `/usr/bin/git` is used, with fixed direct argv and no shell.
The private temporary bare view supplies its own config/HEAD/refs and points only
to the pinned local object store. Original repository config, hooks, filters,
remotes, replace refs and inherited Git environment are not passed through.
System/global config and attributes, external diff/text conversion, optional
writes, interactive prompts and transport are disabled. Missing objects fail;
there is no fetch, checkout, test command, network or inference call.

Normal checkouts and conventional linked worktrees, loose/packed refs and
loose/packed objects are supported. Metadata files are bounded regular reads
without symlink traversal. The resource key pins the common directory's device
and inode; layout and exact approved branch tip are checked before and after
collection. Object inventory is metadata-only, rejects filesystem indirection,
and is checked on both sides. Shallow history, grafts, local/HTTP alternates,
unsupported ref layouts, symbolic result refs and SHA-256 commit IDs refuse.

Both commit objects are rehashed against their requested SHA-1 IDs. Base ancestry
must hold. The raw recursive base-to-result tree diff disables rename detection,
so a rename includes deletion and addition. Ordinary file additions, modifications,
deletions and executable-mode changes are supported. Changed symlinks or gitlinks
require a separate adapter. Empty diffs and ambiguous, non-UTF-8, noncanonical or
duplicate paths refuse. No changed path is silently truncated or excluded by scope.
Out-of-scope paths are retained explicitly as failure findings.

Bounds: four seconds and 65,536 output bytes per Git call; at most 50,000 object
inventory entries and three seconds per inventory traversal; packed refs up to
1 MB; 200 paths up to 500 characters each; final retained proof at most 16,000
UTF-8 bytes. The overall proof-size bound can refuse fewer than 200 long paths.
Bounds assume responsive local filesystem calls, not adversarial/network storage.

This measures committed structural metadata. It does not read the working-tree
contents or inspect the index, prove a clean checkout, collect blob contents,
validate semantics, preserve a patch, attest the entire object store or establish
the remote repository/PR relationship. The temporary view is configuration
isolation, not OS isolation. A hostile filesystem/Git binary or concurrent
object replacement/ABA is outside this adapter's trust boundary. Observed layout
and branch stability is not an acquired repository lock.

## Retention and result review

The canonical JSON artifact records the exact request, task/intent/settlement,
repository/resource identity, branch/base/result commit and tree IDs, complete
changed paths with modes/object IDs, out-of-scope findings and collection interval.
It explicitly records `worktreeInspected`, `remoteObserved` and
`semanticReviewPerformed` as false. No absolute checkout path, source file content,
Git stderr, remote URL or credentials are included.

One workspace transaction retains the hash-addressed observation, a versioned
`source-observation.json` artifact with `local_source_observer_v1` provenance,
the exact request receipt and a `source_observed` event. Worker/queue completion,
preservation, pilot, native identities, shared owners, budgets and run settings
stay unchanged. Concurrent identical requests have one durable receipt. Failure
before commit leaves no partial proof; failure after commit needs only replay.

Exact replay verifies the retained bytes, collector journal, request binding and
receipt. It does not inspect Git or refresh time, and may return the historical
observation after Pause, expiry or a maintenance fence. A new request is a new
explicit collection, not a retry of native work; it must pass current authority.
Missing/corrupt history requires explicit investigation, never deletion to rearm.

To use the artifact in a separate `ResultReview`, retain a source proof pointing
to its artifact ID and use a new current workspace revision. Proof review time
must follow artifact retention. The collected commit/base/branch/full path set,
task/settlement, canonical bytes, metadata provenance, observation journal and
request receipt must agree. The measurement's original observation time is also
checked for freshness: a later review timestamp cannot refresh an old collection.
Collected out-of-scope changes cannot carry verified source status, but can
support a `changes_required` result with failed source status.

The collector itself never marks source verified. Source semantics, acceptance
criteria, CI/preservation and the separately bound independent review still need
their own evidence. Collector source bytes cannot masquerade as CI proof. Older
unlabelled proof artifacts retain their explicit caller-supplied trust boundary;
they are not silently promoted to measured Git facts. A metadata provenance label
or collector report kind opts into all collector checks; missing provenance or
history then refuses rather than falling back to generic evidence.

See [verification](SOURCE-OBSERVATION-VERIFICATION.md),
[result review](RESULT-REVIEW.md) and [remaining activation gates](ROADMAP.md).
