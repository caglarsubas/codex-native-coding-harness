# Workspace device recovery verification

Date: 2026-10-04. Scope: source-only trusted local operator recovery for an
unchanged ledger inode and brain with a changed filesystem device number.
The operating contract is in [Workspace operations](WORKSPACES.md#device-number-drift-after-a-local-reboot).

## Outcome

- Added read-only exact-scope preview and separately confirmed recovery commands.
- Recovery compares the complete ledger schema and logical contents against a
  separately retained private reference backup, then verifies fresh backups of
  both databases before changing the registry pin and its unchanged catalog link.
- Preserved the ledger, native identities, evidence times, expired run, usage,
  gaps, receipts and all execution controls. No automatic adoption or raw SQL
  recovery shortcut was added.

## Local verification

- `python3 -m unittest discover -s tests -v`: 1,995 tests completed in 407.096
  seconds; 1,994 passed and one existing optional Graphify executable test skipped.
- All 30 JavaScript suites passed using `node --test tests/test_*.js`.
- `node --check web/app.js`, Python compilation and `git diff --check` passed.
- The 24 new Python cases cover exact owner hash/confirmation, stopped-writer
  acknowledgment, private files, aliases/hard links, missing/corrupt reference,
  schema/data drift, unchanged inode/brain, catalog isolation, enrollment and
  Harness refusal, paused/expired accounting, pending native/control ownership,
  dashboard exclusion, post-backup drift, failed backup retention, concurrent
  confirmations, lock retention through registry commit, historical replay and
  corrupt history.
- An explicit read-only preview on the disposable pilot matched its complete
  current ledger schema and logical contents to the last separately retained
  verified backup. Neither that preview nor testing applied a private repair.
- Local tracked files and the complete remote main tree contained no GitHub
  Actions workflows. None were added or invoked; absent checks are not passing CI.

## Separate rollout boundaries

This delivery does not install the new command, modify a private identity,
change an app-server binding, notify/resume a brain, renew a phase, start Play,
answer a native permission prompt or qualify strict Harness. The private pilot
databases were independently checked after preparation and remained unchanged.

The dedicated native host was explicitly restored as an operator runtime repair;
metadata-only public reads verified its exact existing project/brain and tool
discovery. Those reads are not an in-turn capability receipt, approval-result
proof, current native inactivity or completed end-to-end pilot acceptance.

After manual source merge, installation, exact private infrastructure review,
and guarded recovery remain separate. Any expired standard phase still needs the
existing recovery-only preparation flow and separately reviewed successor mission
and Play. Native permission handling, Pause/checkpoint/restart/reconciliation,
and rendered durable progress remain pilot acceptance work. No live product
project was activated and no UI acceptance is claimed from unit tests.

## Pending-Play preservation (2026-10-07)

An operator read found a changed filesystem device number with an unchanged
ledger inode and brain. Both the complete ledger and registry matched the
separately retained, verified pre-recovery backups. The original owner-confirmed
Play remained queued with its accepted native turn and an unconfirmed, incomplete
outcome; no registered workers or controller had appeared. Normal device recovery
correctly refused pending work, but this also prevented the brain from reading
the registry to retain its receipt. No physical reboot or missing native effects
are inferred from that metadata.

The new **explicit** `--preserve-pending-play` preview binds this limited empty-run
case under a distinct review kind and hash. Confirmation retains the same backup
and lock protocol and changes only the registry/project device pin. The full
ledger, unknown usage, expiry, owner receipt, original one-shot notification and
unresolved native outcome remain unchanged. Normal recovery keeps its existing
pending-work refusal. Tasks, packets, approvals, descendants, merges, recovery,
controller/runner ownership, changed reference, strict Harness and managed
ownership cannot use the exception. The original notification cannot resend
after the device repair.

A read-only preview against the disposable pilot matched the exact existing
request; it was not confirmed. All private ledger and registry logical contents
still match the original backups. Source delivery installs nothing, applies no
identity repair, launches no host, changes no binding and qualifies no pilot.

Local source verification after the final refusal audit:

- `python3 -m unittest discover -s tests -v`: **2,064 tests, one existing skip**.
- Focused identity recovery: **38 tests**, including 14 new pending-Play cases.
- `node --test tests/test_*.js`: **31 JavaScript test files passed**.
- `python3 -m compileall -q orchestrator`, `node --check web/app.js`, all other
  `web/*.js` syntax checks and `git diff --check` passed.

These are local source/fixture results, not remote CI, rendered UI acceptance,
native inactivity, host restart qualification or completed pilot evidence. No
GitHub Actions workflow or paid verification service was added or triggered.
