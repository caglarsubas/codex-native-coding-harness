# Historical effects and terminal closeout

**Source and disposable-fixture implementation. Not installed or qualified on
the live pilot. No host launch, binding change, native load or wake is included.**

An exhausted ended-Pause receipt recovery cannot be replayed. Its missing brain
receipt must not be manufactured by another native turn or an owner record.
These two signed assistant controls extend the non-waking
[inspection record](ENDED-RECOVERY-RECORD.md), without changing that older control:

1. **Review historical effects** / `confirm historical effects` reads and retains
   evidence, including unknown outcomes. It leaves the entire run unchanged.
2. **Review terminal closeout** / `confirm terminal closeout` separately closes an
   eligible empty expired/duration-stopped run as **blocked · unqualified**. It
   requires conclusive historical non-execution and fresh complete current
   tracked-terminal evidence. It does not retain a safe brain checkpoint.

Both use authenticated, CSRF-protected, session/project-bound, signed, expiring,
revision-bound previews. The server repeats the read-only inspection at confirmation
and checks expiry again inside the local transaction. A lost response can retrieve
the exact durable local receipt, even after expiry, without another native read,
write or notification. Polling reads only saved state and never confirms anything.

## Closed eligibility and continuity

Only the exact empty stopping standard run with one accepted original Play,
one accepted completed Pause and one consumed completed receipt recovery qualifies.
Pin all original command/notification/observer bytes, original native turn IDs,
run/phase, unchanged usage/gaps/expiry, checkout, workspace and both project IDs.
The original Pause must appear in the observed Play-to-recovery turn range.
No tasks, packets, runner, controller, native decision claim, observed descendant,
Brain Stop, handoff, maintenance fence or other pending control is allowed.
Strict Harness is excluded.

Use the unchanged reviewed host, or the independently operator-reviewed
replacement with the existing complete continuity and original-PID retirement
proof. The old endpoint is historical hash evidence only. Original launch provenance
and repeated PID-absence checks are mandatory; no name/path identity substitution,
binding migration of the consumed recovery or direct fallback connection exists.

## Read-only historical collection

The dedicated `HistoryProxy` allows only fixed project/thread metadata reads,
current tracked-terminal reads, and cursor-linked `thread/turns/list` with full
persisted items for the exact designated brain. It has no write or load permit.
No `thread/resume`, `turn/start`, `turn/interrupt`, command execution, discovery,
permission response or observer reconnect is available. Host support for the
experimental full persisted history is required; unsupported or truncated responses
are a refusal, not empty evidence.

Read the complete bounded newest-recovery-to-original-Play range twice, bracketing
it with repeated exact current metadata reads. Require ended turns, full item
arrays, unique IDs, stable status/completion/items and the exact latest recovery.
Cross-check it against two stable reads of the single exact configured local
rollout's call inventory, with matching session, checkout and ordered turn contexts.
The configured log cannot be inferred from directories, titles or a supplied transcript.
Retain hashes and bounded effect metadata only, never message text, tool arguments,
command bodies or outputs. Hash the full inspected file and native items.

Require the explicit full-items view; a missing historical completion time is
retained as a gap, never replaced by the current clock or an inferred deadline.
Nested completed native items, compaction, unsupported records/events, unmatched
calls and missing results remain gaps. Code Mode's arbitrary outer `exec` program
is not interpreted or executed to reconstruct inner commands. A missing saved
result or listing entry is not a denial, non-creation or cleanup attestation.

Bounds are 64 turns, 512 items/effects/calls, one historical turn per page,
32 MiB per configured log, 16 MiB per line and a 12 KiB report. Preserve the native
client's existing response/time bounds. The complete signed browser submission
must fit within 30 KiB (below the HTTP 32 KiB limit). Oversize or growing evidence
is refused rather than silently truncated. Records stay private in the ledger.

## What this evidence can establish

| Evidence | Recorded historical outcome | Closeout |
| --- | --- | --- |
| Native typed `commandExecution: declined`, no exit code, independently matching exact call ID and command hash | `not_executed` | Possible after the separate fresh current-terminal check |
| Complete correlated history with no effects or calls | `not_executed` | Same separate terminal check required |
| Completed/failed command with exit code | Execution observed; historical terminal coverage unknown | Refused |
| Missing/mismatched/unsupported effect, nested unreconciled command or compaction | Unknown | Refused |
| Unloaded brain / missing or truncated current terminal tracker | Current terminal coverage unknown | Refused |

This version qualifies **historical non-execution only**. It does not implement an
executed-effect cleanup attestor, OS process-tree settlement or a permission-denial
pilot acceptance evaluator. A command exit code is not proof of descendant cleanup;
an empty tracker on a replacement host is not historical cleanup proof. Arbitrary
executed effects need a separately implemented independent evidence path. Retaining
their unknown outcome is useful diagnosis, not permission to move on.

Reconciliation can record an unloaded brain as unknown without loading it. Closeout
always requires repeated exact loaded-idle, latest-completed-recovery and complete
known-empty current tracked-terminal observations. Loading acknowledgment alone
would not suffice; this adapter does not perform loading at all.

## Atomic records and successor preparation

`standard_historical_effects` retains the full reviewed evidence, confirmation
evidence and original Play/Pause/recovery/run in a hash-addressed owner snapshot.
It is local-completed and never notifiable. Its outcome is blocked/unqualified even
when historical non-execution is known.

`standard_terminal_closeout` pins that reconciliation snapshot and freshly identical
historical report/host continuity, then atomically retains its own local receipt,
sets the run to blocked and adds an owner-closeout sidecar. Preserve the old
checkpoint verbatim, every original command/permit/receipt, actual usage and gaps,
and the original expiry. No controller or resource ownership is released.

The validated sidecar marks only the exact old Pause/recovery commands as historical
for subsequent pending-control checks. Their original queued status and missing
brain receipts remain unchanged and visible. The notifier refuses them; later
standard receive cannot backfill them. Corrupt or changed originals/sidecars refuse
operation. Only future catalog preparation can pass the old recovery's receive-only
fence after that exact validated closeout; old recovery receipt/checkpoint operations
remain fenced. No new run, usage epoch or authority is created.

The graph shows the non-waking historical review, then the separate closeout review.
Saved outcomes stay ahead of collapsed Details, with plain-language missing-evidence
labels. Closeout exposes **Next: Help me continue development**; that prepares a
successor and is not Review, Play, Resume or pilot acceptance. Source merge,
installation, evidence qualification and live owner controls remain separate steps.

## Verification and rollout

Focused tests exercise known/unknown histories, nested effects, compaction,
identity and turn boundaries, loaded/unloaded/truncated trackers, usage/expiry and
ownership races, request size, expiry during inspection, signatures/session/CSRF,
atomic rollback, duplicate receipt recovery, original-record preservation, inert
polling, catalog-only preparation and refusal of all native writes. Run the full
Python suite, JavaScript suites/syntax checks and disposable desktop/mobile UI checks.
No hosted CI or paid service is added.

Before any separately authorized installation, quiesce older writers and back up
private state. Do not apply source adapters to the live ledger during delivery.
No installation can supply a missing historical result or make unknown status safe.
If the pilot's old diagnostic cannot be independently reconciled, it remains
unqualified and fenced; do not claim completion or silently run a fresh attempt.
