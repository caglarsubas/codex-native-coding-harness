# Owner-requested archive handoff verification

Scope: WSP-05A, starting from PR #37 independently verified merged at
`cc2abdee9229b680bd3505c6fc486743b5310eca`. Fetched `origin/main` and a later
read-only remote check matched that exact revision. Changes and tests used an
isolated tooling worktree and disposable fixtures, not live product checkouts.

## Delivered boundary

- Separate explicit owner request binds the accepted review, measured local
  preservation manifest and managed-worktree cleanup acknowledgment.
- Designated-brain state/prepare/check/record CLI for a confirmed local root with
  no descendants; existing worker-ID-only managed archive and generic ack refuse.
- Fresh complete native inactivity/worktree assertions before preparation and a
  single consumed send check. The brain, not Python, calls the existing native
  archive tool; no private API, filesystem cleanup or transport is introduced.
- Atomic local handoff/check/outcome journals, command/worker projections and
  events. Unknown delivery never permits a resend or an unsent cancellation.
- Historical reads, exact receipt replay and late observations survive Pause and
  maintenance without resuming the workspace. Archived accepted tasks remain in
  subsequent safe-Pause supervision; shared ownership and usage do not change.

The orchestrator skill's explicit owner approval, preservation and recovery rules
shaped this implementation. The native worktree cleanup boundary was checked
against [official documentation](https://developers.openai.com/es-419/docs/environments/git-worktrees).
Evidence hashes and complete/idle/preserved assertions remain caller-supplied,
not independently authenticated host or native observations.

## Local verification

```sh
python3 -m unittest discover -s tests -v
node --check web/app.js
node --test tests/test_*_ui.js
git diff --check
```

Python 3.12: **1,071 tests passed**, including **28 new archival tests**.
All **7 JavaScript UI regression files passed**. Syntax and whitespace checks
passed. UI source is unchanged; this is not new browser QA or a live pilot.

Fixtures cover:

- Full subprocess CLI owner/request/prepare/check/observation/state round trip,
  exact target arguments, separate accepted result, unchanged shared counters,
  no native call and no pilot promotion.
- Wrong controller/workspace, missing registration, exact owner/review/proof
  bindings, cleanup acknowledgment, refused brain self-approval and duplicates.
- Supplied preservation note refusal, terminal descendant tree refusal and newly
  known descendants; missing coverage, running/unknown task, worktree uncertainty,
  wrong target, stale/future observations and pre-boundary timestamps.
- Owner receipt required before preparation; queued-but-unprepared receipt is
  not in-flight native work. New check evidence cannot reuse the prepare sample.
- One permit under concurrent send checks; duplicate checks never send again.
  Preparation/check/result event failures roll back all local projections.
- Pause/maintenance block new sends but allow late observation. Unsent prepared
  cancellation is final; consumed uncertainty cannot be cancelled as unsent.
- Unknown-to-confirmed outcome with historical unknown replay that cannot undo
  confirmation. Concurrent identical result recording retains one observation;
  changed replay, wrong expected hash/host/task and unsupported outcomes refuse.
- Read/replay after expiry and maintenance with process execution forbidden.
  Missing slot/receipt, changed owner command, forged archived status and corrupt
  preserved bundle invalidate historical results and block new sends.
- Archive handoff/check/outcome changes invalidate older Pause bindings; accepted
  archived tasks remain supervised because they can later be unarchived.

## Cost and delivery

Read-only GitHub metadata checks before publication found **0 configured Actions
workflows and 0 Actions runs**. No workflow was added/enabled/dispatched/rerun, no
runner provisioned, and no paid service or dependency introduced. The existing
repository no-Actions-workflow regression test remains passing. Local results are
not relabelled as GitHub CI; absent remote checks are not green CI.

No live task was archived, messaged or created. No live ledger, installed skill,
dashboard process, native schedule, maintenance fence, allocation or budget was
changed. The dashboard and assistant still do not offer managed archive actions.
The PR remains for manual review/merge; merge is separate from installation and
runtime acceptance.

## Remaining gates

This completes the first explicit-owner archival handoff only. Automatic delegated
retention policy/UI, descendant archival, new-generation continuation/rereview,
trusted host/native evidence, Harness acceptance and supervised two-workspace
Play/Pause rollout remain open. Local preservation is not an off-device backup,
uncommitted/external-object backup or native transcript guarantee. Operators must
quiesce older helpers before any separately authorized rollout; no mixed-version
or downgrade compatibility is claimed.
