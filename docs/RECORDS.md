# Version 1 record contracts

The runtime validates these contracts explicitly in `orchestrator/core.py`.
Canonical JSON is UTF-8, sorted keys, compact separators, no NaN. Its SHA-256 is
the record identity; this encoding is local to this tool, not RFC 8785 signing.
SQLite uses WAL, synchronous FULL and BEGIN IMMEDIATE for serialized transitions.

## Portfolio

`schemaVersion: 1`, `brainId`, `repositories[]`. Each repository has exactly:
`id`, `path` (absolute local path or null), `projectId` (verified native ID or null),
`ref`, `mergePolicy` (`manual` or `required_checks`), `policyProfile` (`standard` or
`harness`). Configuration stays private. Adding a repo requires user scope approval;
the initializer is not a discovery or authorization tool.

Changing path/projectId/ref invalidates pending approvals and preflights; an
active worker blocks that change. Policy and brain changes still require explicit
migration. Read-only readiness observations cannot edit these bindings.

## Inheritance seed

Exact fields: `schemaVersion`, `repository`, `policyProfile`, `packetId`,
`packetDigest`, `packetPath`, `catalogCommit`, `baseSHA`, `branch`, `objective`,
`rationale`, `allowedPaths`, `contracts`, `predecessors`, `locks`, `execution`,
`acceptance`, `stopConditions`, `completionAxes`.

All source paths are repository-relative. Packet and locks use SHA-256; base and
catalog use full Git commits. Branch starts with `codex/`. Each predecessor has
repository, packetId, axis, evidenceSHA256, reference. Each lock has path, sha256.

Execution has wrapperArgv, prefetchCommands, offlineAcceptanceCommands (all direct
argv arrays), and isolation. Harness requires OS_ENFORCED_DENY_ALL_OUTBOUND;
standard uses REPOSITORY_POLICY. The helper never executes those arrays.

Minimum completion axes are source/ci, plus merge for required-checks policy.
Additional required axes can be selected but not removed after approval. Seed
changes invalidate approval; a seed cannot replace a packet already owning a task.

## Queue and dispatch

Queue identity is `repository:packetId`, unique even when digest or base changes.
Approval records the user action, time, seed hash and packet digest. Preflight
records explicit checks/evidence and expires after 300 seconds.

Worker states: reserved → starting → running → awaiting_acceptance → accepting →
verifying → complete. Blocked is recoverable but retains ownership. Starting is
uncertain until native identity is resolved; it must never auto-retry creation.
Client IDs are distinct from task IDs. There is no automatic ownership expiry.

## Control request

See [the machine-readable control schema](../schemas/control-request.schema.json).
Exactly `id`, `kind`, `expectedRevision`, `payload`. Reusing an ID with identical
content returns the previous result; changing its content is refused. A stale
revision refuses the action before any mutation.

Kinds and payloads:

| Kind | Payload |
|---|---|
| approve | queueId, seedHash, packetDigest |
| hold | queueId, held boolean |
| prioritize | queueId, priority integer 0–999 |
| pause / resume / reconcile | empty object |
| checkpoint / archive | workerId |

Only typed controls are accepted. There is no shell, prompt-execution, filesystem
write, repository-delete or native-tool proxy endpoint. The HTTP layer cannot
acquire the controller token, prepare packets, preflight, dispatch or certify work.

## Completion envelope

Exactly `schemaVersion`, `seedHash`, `commit`, `changedPaths`, `pr`, `evidence`,
`preserved`, `reviewReference`. Evidence has all eight axes: source, ci, merge,
artifact, deployment, runtime, assurance, tenant. Each has status (`verified`,
`unverified`, `not_applicable`, `failed`) and reference. Verified requires a
reference; every contract-required axis must be verified. The brain separately
checks that the evidence is authentic, fresh and bound to the exact result.

Archive is allowed only for complete, preserved work, followed by native inactive
state verification. No automatic deletion API is provided.

## HTTP

Static: GET `/`, `/app.js`, `/style.css`. Auth: POST `/api/login`, GET `/api/session`.
Authenticated reads: GET `/api/state`, `/api/documents/<sha256>`, `/api/export`.
Mutation: POST `/api/commands` with exact origin, authenticated cookie and CSRF token.
All state includes a ledger revision and server timestamp. `/api/state` exposes the
latest 100 audit events and full-history derived delivery totals. Snapshot reads
do not change revision and never disclose controller tokens.
