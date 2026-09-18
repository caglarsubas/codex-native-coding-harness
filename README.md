# Codex Native Coding Harness

A local operations ledger and dashboard for an existing Codex task acting as the
brain of a multi-repository development workflow. The brain prepares bounded
inheritance packets, creates native implementation tasks inside an approved queue,
supervises them, and independently verifies completion.

**The webpage is not an agent scheduler.** It records typed requests in SQLite;
the brain performs native Codex actions. No private desktop API, runtime download
or external telemetry is used. Orchestration needs no model API key. An optional,
user-configured inference service can draft advisory briefs on explicit request;
it has no controller authority.

## What is included

- Portfolio-neutral controller, with `standard` and stricter `harness` policies.
- Versioned, immutable seeds and completion envelopes; digest-bound approvals.
- Single-controller ownership, one worker per repository, and serialized managed
  acceptance. One worker initially; two only after a verified real pilot.
- Safe handling of uncertain creation, pending native IDs, process interruption,
  stale approval, pause races and retained ownership.
- Loopback dashboard with queue, workers/evidence, knowledge, events, metrics and
  Markdown report export. Local authentication, Host/Origin checks and CSRF guard.
- Personal Codex skill and a runbook for native tool operations and recovery.
- Read-only Git metrics: aggregate and per-repository snapshots at exact commits.
- Optional evidence-linked executive brief on Overview, using an allowlisted
  on-prem model through `llm-inference-engine`. Versioned output, freshness,
  service-reported usage, and a preview of the exact aggregate data sent.

AI briefs are unverified drafts. Initial live trials exposed occasional narrative
errors; factual-accuracy qualification remains open. Deterministic metrics and
independent evidence remain authoritative.

This coordinates native tasks; it does not replace repository policy, a trusted
runner, OS isolation, independent review or human authorization. The local owner
and the brain are trusted. Ledger evidence references are checked for structure,
not cryptographically certified by the controller.

## Quick start

Use Python 3.11+; the controller and tests use only the standard library. The
optional YAML packet importer additionally requires an **already installed**
PyYAML. Do not install dependencies during a restricted execution run.

1. Copy `config/portfolio.example.json` into `.state/portfolio.json`. Fill in an
   existing brain task ID, repository paths, actual saved Codex project IDs,
   authoritative refs, and merge policies. `null` project IDs block dispatch.
2. Initialize and test:

   ```sh
   python3 -m orchestrator.cli init .state/portfolio.json
   python3 -m unittest discover -s tests -v
   node --check web/app.js
   python3 scripts/install_skill.py
   ```

3. Start the dashboard:

   ```sh
   python3 -m orchestrator.cli serve
   ```

   Open the private URL in `.state/dashboard-session.json` in a Codex browser
   panel. It uses a local bootstrap token in the fragment, clears that fragment,
   and establishes an HttpOnly, SameSite session. Never publish the private URL.
   The server binds only `127.0.0.1`; it is not a network-deployment server.
4. In the designated brain, invoke `$codex-orchestrator` for **read-only onboarding**.
   Keep dispatch paused until a real packet is explicitly approved and verified.

Closing the browser does not stop a brain or worker. Stopping the local server
does not cancel tasks. Restarting it rotates dashboard authentication, not ledger
state. Keep the computer and Codex app running for local scheduled work.

## Control semantics

| Action | Immediate effect | Native effect |
|---|---|---|
| Approve / hold / prioritize | Update reviewed ledger state | No task creation by itself |
| Pause | Block the next creation boundary; supersede queued resumes | Does not cancel running or already-starting tasks |
| Resume / reconcile | Queue a request | Brain processes it on its next active cycle |
| Checkpoint worker | Queue a request | Brain sends a cooperative checkpoint request |
| Archive completed task | Queue after preservation checks | Brain verifies inactivity and uses native archive |
| Answer a decision | Bind an answer to an immutable question version | Brain continues authorized design and records an artifact-backed outcome |
| Keep listening between jobs | Save the owner's listener preference | Brain keeps the existing native heartbeat active independently of dispatch |

The [Decision inbox](docs/DECISIONS.md) separates recorded answers, brain receipt,
design outcomes and implementation approval. With idle listening enabled and its
native heartbeat active, dashboard answers do not need a chat “continue”. Initial
activation or reactivation after deliberately stopping idle listening needs the
brain once; the webpage cannot wake a paused native schedule. Local scheduled
checks require the computer/app running and consume model usage. Immediate task
interruption stays in native Codex controls.

Never blindly retry a `starting` worker or `processing` native action. Reconcile
its unique dispatch/request identity against actual native state first.

## Reuse with another project

The Harness portfolio is a private configuration, not hard-coded into this repo.
For another portfolio, create a separate private configuration and state directory:

```sh
python3 -m orchestrator.cli --state .state/another-portfolio init .state/another-portfolio.json
python3 -m orchestrator.cli --state .state/another-portfolio serve --port 8769
```

Use the `standard` profile for ordinary repositories, with their own AGENTS.md,
execution requirements and manual/required-checks merge policy. Use `harness`
only when its deny-all-outbound trusted execution contract applies. The controller
refuses an in-place policy downgrade. No product source changes are needed merely
to install this tool. OpenClaw and other agent interfaces are out of scope.

## Prepare the first supervised drive

Open **Readiness** to inspect checkout/native-mapping gaps, packet launch blockers,
brain freshness and the separate real-pilot gate. Run the isolated lifecycle
rehearsal to test ledger transitions without touching product work. Its report is
synthetic and cannot enable dispatch or two-worker concurrency.

Read the [readiness runbook](docs/READINESS.md) and [first-pilot proposal](docs/FIRST_PILOT.md).
Project registration, safe worktree setup, a valid CI evidence route, exact packet
approval and a live brain cycle remain required. The webpage cannot wake a paused
native heartbeat or silently register projects.

The [runtime provenance view](docs/RUNTIME.md) distinguishes the server-start
checkout from the current source tree and explicitly observed GitHub revision.
It flags dirty/changed/stale evidence and recommends manual restart when needed;
it never pulls code, restarts the process or treats a merge as deployment.

## Metrics and privacy

```sh
python3 -m orchestrator.cli scan
python3 -m orchestrator.cli export
```

Counts cover tracked UTF-8 text including blank/comment lines, grouped as source,
tests, docs and config/data. Exclusions and exact commit IDs are recorded. They are
not executable SLOC or test coverage. Worktrees are not counted multiple times.
Missing measurements are unavailable, not zero. Delivery metrics cover only tasks
managed by this ledger. Historical messages/tasks, model/effort, token and cache
observations can be imported from configured local Codex logs. The dashboard
includes Token usage, Git & delivery, Artifact library and Roadmap views. See
[observation setup and limits](docs/OBSERVATIONS.md). Missing sources remain
unavailable; retained local logs are not account-wide billing records.

Do not infer subscription charges from API token prices, or causal model effects
from unmatched tasks. Reports and the entire `.state/` directory are private and
Git-ignored. The public repository must contain no personal paths, native task IDs,
approvals, tokens, live databases or conversation transcripts.

## Documentation

- [Operator runbook](skills/codex-orchestrator/references/operations.md)
- [Record contracts](docs/RECORDS.md)
- [Acceptance and known boundaries](docs/ACCEPTANCE.md)
- [Inference setup, privacy and future uses](docs/INFERENCE.md)
- [Official scheduled-task documentation](https://learn.chatgpt.com/docs/automations)
- [Official worktree lifecycle](https://learn.chatgpt.com/docs/environments/git-worktrees)

No hosted CI workflow is installed. Run the local checks above; product-specific
acceptance and required self-hosted checks remain owned by each product repository.
