# Phase-bound delegated retention — WSP-05E

Plan saved before implementation after PR #52 merged at
`ff3c0619a2ab228db0b58783016ba98df69d53a7`.

## Plan

- [x] Internal exact-owner retention review/revoke, default no delegation, bound
  to one reviewed phase/run/brain with an archive-attempt cap, minimum retention
  age and explicit managed-worktree cleanup acknowledgment.
- [x] Designated-brain command preparation for an accepted standard-policy local
  root, using existing measured preservation and terminal review. Retain exact
  rationale/policy/result binding atomically; this is not a native send permit.
- [x] Reuse the existing archive prepare/check/record lifecycle. Revalidate policy
  at effect boundaries; preserve expiry, revocation, Pause, maintenance, root-only
  safety and no-retry rules. Historical and late-result validation remains possible.
- [x] Keep attempt counts across policy revisions/cancellation and reject missing
  pointers, downgraded actors, changed receipts and duplicate concurrent requests.
- [x] Local policy/CLI/lifecycle regressions, full suite and roadmap evidence.

## Scope boundaries

This is source and disposable-fixture work only. Owner policy methods are trusted
authenticated-caller seams; [WSP-05F owner controls](RETENTION-CONTROLS.md) now expose
signed dashboard review/revoke, not an assistant approval route. A generic
phase task-approval grant does not delegate archival. No live policy, native call,
skill installation, process restart, scheduler, cleanup, billing or Play activation.

Only accepted local root tasks without known descendants are eligible. Git bundle
retention does not preserve untracked files, external payloads or native transcripts.
Fresh complete worktree/inactivity evidence remains mandatory at both archive
boundaries. Missing evidence or host capability blocks archival. Python never
archives or deletes; the brain remains the native caller. Descendant retention,
complete output preservation, qualified host evidence and live acceptance remain
separate work; this increment does not complete milestone 8.

## Owner policy — trusted kernel and signed dashboard adapter

`retention_policy.review(ledger, request, actor="dashboard_owner")` is a trusted
authenticated-owner adapter seam, not authentication by itself. WSP-05F supplies
the signed, same-session HTTP adapter; no assistant action or brain CLI exists.
Review happens while dispatch is paused, after
an exact `phase_delegated` run intent is authorized and before activation. It does
not unpause, alter task approval, fence unrelated work or grant native capability.
An `exact_owner` run cannot gain delegated retention without a newly reviewed
mission/run. The default is no policy, even for phase-delegated task approval.

The closed review request contains:

| Field | Meaning |
| --- | --- |
| `id`, `expectedRevision` | Unique request and exact current workspace revision |
| `runHash`, `expectedPolicyHash` | Exact current run; current retained policy hash, or null initially |
| `maxArchives` | Integer from 1 to the smaller of 64 and the run's `maxTasks` |
| `minimumRetentionSeconds` | Integer 0–86,400, measured from accepted result-review time |
| `allowManagedWorktreeCleanup`, `confirmed` | Both must be explicitly true |

The retained policy binds workspace, brain, mission, phase, run generation, owner,
creation time and previous policy version. It expires with its run. Review is not
inherited by a later generation, even within the same phase. A real Pause fences
the current run; subsequent activation still needs the existing checkpoint/release
protocol and a new exact-run retention policy. No new resume shortcut is added.

`retention_policy.revoke` takes exactly `id`, `expectedRevision`, `policyHash` and
a bounded non-empty `reason`, with the same owner actor. Revocation can block new
retention effects without pausing other work. Replaying an old review receipt does
not undo revocation or refresh time. Policy supersession also blocks old requests
at preparation/check; revocation cannot undo a consumed native send boundary.

## Brain request and existing archive lifecycle

Only the existing designated-brain controller for the explicitly selected workspace
may request delegation. Read `archive-handoff-state` first: its `retention` object
shows the matching policy, attempt count and any saved request. `reviewed_policy`
is historical configuration, **not present eligibility**. State performs no native
observation and always returns `currentSafetyChecked: false` and no send permit.

```sh
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace EXACT_WORKSPACE archive-handoff-request-delegated WORKER_ID PRIVATE_REQUEST_JSON
```

The closed request contains `id`, current `expectedRevision`, `policyHash`, exact
accepted `reviewHash`, `preservationArtifactId` and a non-empty `rationale` of at
most 2,000 characters. The controller token and request file remain private. No
review/revoke CLI is exposed to the brain.

The request checks the current run/policy, controller, Pause, maintenance, confirmed
terminal settlement, accepted result, measured preservation, root-only ownership,
minimum age and remaining archive allowance. It atomically saves an immutable
delegation, a received typed archive command, its attempt charge and an idempotent
receipt. Failure rolls all of these back. No native arguments or call are emitted;
shared token charges, reservations, settlement and result acceptance are unchanged.

Use the returned `commandId` in the existing
[archive prepare/check/record sequence](ARCHIVE-HANDOFF.md). Because the designated
brain made and received this request, another `process` pass is not required.
Both preparation and one-shot check must still obtain fresh complete idle-tree and
worktree-preservation evidence. They revalidate the exact active retention policy
and run. Only the successful one-shot check yields the existing native tool's
arguments; the Python helper still cannot archive or remove a worktree.

The coordinator's `archive-handoff-state` hint on a completed task is navigation,
not a decision, eligibility assessment or native instruction. Managed event-wait
hashes include the new retained metadata; no scheduler or automatic archive loop
is introduced. Existing explicit-owner requests remain usable without a policy.

## Attempt limits and recovery

The cap counts delegated **requests within the exact run**, not successful archives
or lifetime phase totals. Policy revisions do not reset that count. Cancellation,
revocation, rejection and unknown outcomes do not restore the allowance. Each
worker can have at most one delegated request, even with a different request ID.
A failed request before its atomic commit consumes nothing. A new run requires
new owner authority; it cannot reuse an older worker's run binding.

Exact request replays return their historical receipt after Pause or revocation,
without resubmitting or renewing time. The durable worker slot, request receipt,
actor, payload, command fingerprint, policy and accepted-result binding must all
agree. Missing/corrupt history refuses; relabeling the request as a direct owner
command is not a recovery path. An unrelated direct owner archive request cannot
bypass an existing delegated attempt. No retry/reversal protocol is added.

Before the send check, a prepared handoff may be recorded as unsent `cancelled`.
After the check is consumed, only `unknown` or observed `archived` outcomes are
allowed. Late outcome recording and retained accepted-result validation remain
possible after policy revocation, supersession, run expiry or Pause. They validate
historical authority, not current permission to send. The cooperative check-to-call
gap cannot atomically cancel an already-authorized native call.

## Verification and rollout

Disposable fixtures cover owner-only policy, defaults, phase-mode and scope gates,
age/cap limits, concurrent idempotence, transaction rollback, missing/malformed
history, actor downgrade refusal, revoked/superseded policies, unknown/late results,
unchanged shared accounting and the existing CLI lifecycle. No fixture invokes a
native archive tool. Local verification on 2026-09-21 passed:

- 1,399 Python tests, including 27 new retention tests.
- All ten JavaScript UI suites and syntax checks for all web JavaScript files.
- Python compile checks and `git diff --check`.

No frontend layout changed; no new browser-rendering acceptance is claimed.

The first full run exposed an existing race in the native-proxy refusal fixture:
context cleanup could terminate its disposable process before it logged the
one-way `initialized` notification. The unchanged test reproduced 5 failures in
50 repetitions. A permitted metadata round trip now drains that notification,
while an explicit RPC spy proves rejected operations never reach RPC. All 50
repetitions then passed; no production native client or transport was changed.

Quiesce all older writers and prepared handoffs before any separately authorized
rollout. New readers preserve legacy explicit-owner records; older writers do not
understand delegated authority. This is not mixed-writer or downgrade support.
No live policy was configured, skill installed, service restarted, task archived
or GitHub Actions workflow added. Owner-facing policy controls are delivered
separately in [WSP-05F](RETENTION-CONTROLS.md); complete descendant and non-Git output
preservation, qualified host evidence and supervised acceptance remain separate
gates. The conditional completion estimate is unchanged.
