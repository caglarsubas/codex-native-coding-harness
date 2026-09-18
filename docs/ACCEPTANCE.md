# Acceptance and operational boundaries

## Reproducible local checks

```sh
python3 -m unittest discover -s tests -v
node --check web/app.js
node --check web/observations.js
node --check web/inference.js
node --check web/readiness.js
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

## Native integration acceptance

Before enabling dispatch, verify in the actual designated brain:

1. Installed skill loads and the private workspace resolves.
2. `status`, acquire, inbox processing and release work with no product mutation.
3. Native task/project discovery works; existing work is reconciled, not duplicated.
4. The 15-minute heartbeat is attached to the correct existing brain and stays
   paused when no approved queue exists.
5. A single explicitly approved real packet completes in a fresh native worktree,
   with scope, acceptance, native identity and exact evidence independently checked.
6. Only then record pilot success to enable two workers.

Unit tests or a read-only onboarding turn do not establish item 5. Missing
projects, packet authority, runner/backend, or consequential design decisions are
blockers, not permission to synthesize a demonstration product task.

## Deliberate limits

- Codex tool calls are performed by the brain, not the dashboard process.
- No immediate page-to-brain wake API is assumed. A paused heartbeat requires a
  user message to the brain; queued requests are durable while it is inactive.
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
