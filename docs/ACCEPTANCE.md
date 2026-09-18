# Acceptance and operational boundaries

## Reproducible local checks

```sh
python3 -m unittest discover -s tests -v
node --check web/app.js
node --check web/observations.js
node --check web/inference.js
node --check web/readiness.js
node --check web/provenance.js
node --check web/activity.js
node --check web/decisions.js
```

The tests use temporary local repositories and ledgers, not a product checkout or
trusted runner. They cover approval, immutable seed changes, stale revisions,
idempotency, concurrent duplicate reservations, single-controller ownership,
uncertain/pending native identities, pause races, post-pilot concurrency, shared
runner exclusion, crash recovery, bounded corrections, exact changed paths,
completion evidence, archival acknowledgment, policy downgrade refusal, Unicode
metrics, missing repositories, authentication, Host/Origin checks and CSRF.

Optional inference tests use fake transport responses and temporary credentials:
no real endpoint is called by the suite. They cover local-model allowlisting,
owner-only configuration, redirect refusal, aggregate-only projection, sanitized
errors, complete JSON answers, evidence IDs, cached snapshots, artifact versions,
concurrent requests, unchanged controller state, and authenticated fixed-shape
requests. Live endpoint/model behavior and rendered UI must be checked separately;
schema/evidence-ID validation does not prove narrative accuracy. See
[inference boundaries](INFERENCE.md).

Readiness tests cover metadata-only inspection, exact native identity/path/host,
freshness, private inventory scoping, unchanged controller state, mapping-change
approval invalidation, active ownership, shared packet gates and isolated fixture
rehearsal. The real native pilot remains a separate acceptance gate; see
[readiness and first-drive requirements](READINESS.md).

Runtime-provenance tests cover immutable startup observations, same-HEAD source
edits, dirty/untracked/deleted source, ignored credentials, symlink refusal,
unstable/stale snapshots, fixed GitHub GETs, changed origins and failed refreshes.
State polling never inspects source or calls GitHub. This does not attest loaded
memory, dependencies or deployment; see [runtime boundaries](RUNTIME.md).

## Native integration acceptance

Decision tests cover version/hash binding, authenticated HTTP receipts, artifact
resolution, single-answer races, supersession, interruption, compact inbox and
independent listening/dispatch state. For rendered interaction checks,
`scripts/bootstrap_fixture.py` creates a labeled temporary fixture; never submit
test answers into the live portfolio. Synthetic checks do not qualify as a pilot.

For free-text UI regression, submit an answer with no option selected and verify
its exact text through receipt and artifact-bound history. Reject blank and
whitespace-only answers. Select an option, then use **Use my own answer instead**:
text must survive, all options must clear and confirmation must reset. In-page
Refresh must retain a draft. Also verify an option with no required note still
submits, required notes are enforced, and HTML-looking answer text renders inert.

Before enabling dispatch, verify in the actual designated brain:

1. Installed skill loads and the private workspace resolves.
2. `status`, acquire, inbox processing and release work with no product mutation.
3. Native task/project discovery works; existing work is reconciled, not duplicated.
4. The 15-minute heartbeat is attached to the correct existing brain. With explicit
   idle listening enabled, it stays active for decisions even while dispatch is
   paused. Otherwise it parks once approved/active work and pending controls drain.
5. A single explicitly approved real packet completes in a fresh native worktree,
   with scope, acceptance, native identity and exact evidence independently checked.
6. Only then record pilot success to enable two workers.

Unit tests or a read-only onboarding turn do not establish item 5. Missing
projects, packet authority, runner/backend, or consequential design decisions are
blockers, not permission to synthesize a demonstration product task.

## Deliberate limits

- Codex tool calls are performed by the brain, not the dashboard process.
- No immediate page-to-brain wake API is assumed. Initial activation or explicit
  idle-listener reactivation requires the native brain once; queued requests are
  durable while it is inactive. Active scheduling consumes model usage.
- Native creation and SQLite cannot be committed atomically. A one-shot outbox
  boundary prevents blind retries but may require manual recovery of uncertainty.
- Controller recovery is a trusted operator action, never a time-based takeover.
- Runner exclusion applies to this ledger; the brain checks unmanaged work too.
- Evidence is independently reviewed by the brain; references are not a standalone
  cryptographic proof system.
- Token/cache/model/effort and task/message counts cover configured retained local
  logs only. Counter/fork/continuation diagnostics and limits are described in
  [observation contracts](OBSERVATIONS.md); they are not billing records.
- Artifact discovery covers scoped local file links and explicit registration,
  not all native attachments or overwritten historical bytes.
- Roadmap checkboxes are recorded source claims, not independently verified gates.
- No cloud deployment, hosted CI, product launcher modification or OpenClaw.

## Public-repository hygiene

Before publishing, inspect `git diff --cached` and `git ls-files`. Never include
`.state/`, `reports/`, installed `installation.json`, session artifacts, private
configuration, `.env`, endpoint credentials, personal absolute paths or task IDs. No license is inferred merely
from repository visibility; the owner can select a license separately.
