# Managed workspace cycle (WSP-05D / WSP-04D6)

Read this for `meta.runAuthority`, schema v3, immutable task contracts or an
admission-managed worker. It replaces the legacy reserve/begin/bind/transition/
runner/complete/pilot sequence for that scope. A refusal never permits fallback
to those commands or removal of a marker.

This is reusable source guidance for a **separately authorized rollout**, not
permission to install, activate Play, initialize admission or migrate live state.
An absent allocation, maintenance fence or unavailable qualified host evidence is
a setup boundary, not an invitation to manufacture it. The designated brain is
the only scheduler; no background Python loop or second inference agent.

## Enter or recover one bounded cycle

Use the installed wrapper with explicit `--platform` and `--workspace`, never
browser selection or cwd. Verify this task is the registered brain, read `inbox`,
acquire its controller normally and keep the token private. Use `operations.md`
for typed control receipts and safe Pause. Read the relevant protocol document
from the installed tooling checkout before a handoff; use CLI `--help` for exact
arguments. Do not substitute guessed JSON schemas.

Process the current typed inbox before ordinary work. A stop takes priority:
preserve task/descendant checkpoints, reconcile in-flight effects and follow the
workspace Pause procedure. A stale wake cannot resume a parked brain. Only the
exact newer owner Resume can do that; it does not re-arm an old run.

Read `brain-cycle-inspect`. Recover retained intents and receipts before choosing
new work. Candidates, workers, budget and blockers are bounded recorded context,
not fresh native truth or executable arguments. A final reply is not acceptance.

If the latest choice is `wait`, read `brain-cycle-wait-state DECISION_HASH` before
repeating planning. For `unchanged` with `quietEligible: true`, reuse the original
named resume event. Do not append another decision, manufacture a new checkpoint
artifact, refresh evidence times or send an unchanged summary. Release the normal
controller and end the turn. This read does not itself suppress a native wake or
change a schedule. Reconcile an existing authorized heartbeat through the native
app tool only under `operations.md` scheduling policy; preserve explicit idle
listening and recheck inbox for racing input before ending.

`changed` means inspect those categories and decide again, not approved/ready.
`supervision_required` means outstanding ownership, receipts, answers, follow-up
planning, eligible work or explicit idle listening still needs normal handling.
`stopped` routes to safe Pause. `superseded` uses the latest decision. `unbound`
is an older wait without event hashes: inspect and record a bound wait once,
never assume unchanged. Corrupt/oversized inventories require investigation,
not an empty-inventory assumption or SQL repair.

## Make the brain's decision

Use a fresh inspection revision/context for `brain-cycle-decide`. The brain
chooses with rationale and reuse reason; Python does not rank tasks or call models.

- **Create:** choose an eligible bounded packet where an owned task cannot serve
  the scope. Exact-owner mode needs owner task approval. Phase-delegated mode may
  compose approval only inside the existing owner grant, reviewed phase, operations,
  limits and checkpoints. Use `brain-cycle-reserve DECISION_HASH` and retain its
  worker identity. Neither a candidate nor reservation is a native send permit.
- **Continue:** reuse the exact confirmed owned task for same-run edit correction
  before terminal settlement. Bind retained findings and a reuse rationale. After
  two no-progress corrections, budget/quality concerns or scope change, stop at the
  appropriate checkpoint; do not open a replacement to bypass a bound.
  New-generation correction/rereview is not yet implemented.
- **Handle:** bounded authorized planning/review in the brain, with no new product
  edit, publication, target-access or acceptance authority.
- **Wait:** name concrete owner input or externally delivered evidence. Questions
  and unapproved proposals alone do not justify periodic model checks. A new
  unchanged wait ID refuses; reuse the receipt. Pending work still needs supervision.

## Compose the handoffs

Read the corresponding `docs/` document from the installed tooling checkout.

| Situation | Protocol |
| --- | --- |
| Reserved creation | `native-create-begin`, fresh `native-create-check`, one native `create_thread` using only emitted arguments, then `native-create-record`. See `NATIVE-CREATION-HANDOFF.md`. |
| Pending/uncertain creation | `native-create-state` / `native-create-recover`; reconcile existing identities, never create again. A client ID is not a task ID. |
| Task supervision | `native-task-plan`, native read-only tool call, `native-task-record` / `native-task-state`. Preserve original times/cursors. See `NATIVE-SUPERVISION.md`. |
| Account/phase usage | `native-account-state` / record and `phase-usage-state` / record on the existing allocation. Percentages are not lifetime counters. See `PHASE-USAGE.md`. |
| Same-task correction | `correction-handoff-prepare`, fresh one-shot check, one native message, then record; state/recover after uncertainty. See `CORRECTION-HANDOFF.md`. |
| Declared standard runner | `runner-handoff-acquire`, prepare/check, one native message, delivery/process observation and release after proven full-process cleanup. See `RUNNER-HANDOFF.md`. |
| Terminal ownership | For standard local tasks, use `terminal-handoff-state`, retain exact root/descendant checkpoint proofs with `terminal-handoff-proof-add`, then `terminal-handoff-settle`; use `terminal-handoff-recover` only for a committed receipt. Explicit `--outcome confirmed` requires qualified complete inactivity, inventory, cleanup and cumulative usage; `not_created` requires conclusive final attempt reconciliation and explicit zero task usage. See `TERMINAL-HANDOFF.md` and its linked evidence schemas. No qualified evidence means keep ownership and expose the blocker, not fabricate facts. |
| Settled result | `result-handoff-state`; collect measured source/GitHub/preservation, retain supplemental and independent-review proofs, then review. See `RESULT-HANDOFF.md`. Never self-review or promote one evidence axis into another. |
| Accepted result | Inspect for the next eligible same-phase packet. Keep task history; acceptance is not merge, archive or phase-release authority. |
| Owner archive | `archive-handoff-state/prepare/check/record` only with exact owner cleanup acknowledgment, measured preservation and fresh root-only safety evidence. See `ARCHIVE-HANDOFF.md`; delegated/descendant archival remains gated. |
| Phase/budget/plan boundary | Reach safe Pause, then `phase-checkpoint-prepare` and expose the retained report. See `PHASE-CHECKPOINTS.md`; the brain cannot review/release its own next phase or reset usage/attempts. |

Creation/correction/runner/archive checks consume one send boundary. Call the
native tool once only when the current check explicitly permits it. Historical
receipts never permit another send. After interruption at a consumed check,
reconcile without retry; retain uncertainty, ownership and charges. Re-read inbox
before/after each bounded step. Pause after check is cooperative in-flight work,
not an atomic cancellation guarantee.

Native defaults remain the default. For an exact owner-reviewed adaptive policy,
follow `MODEL-POLICY.md`: fresh destination capability binding, allowed model/effort,
quality/token floors and bounded escalation. Forward only emitted model/thinking
fields. Do not invent speed/Ultra, change global settings, lower quality to fit a
budget, or equate requested settings with observed application.

`NATIVE-EVIDENCE-COLLECTION.md` remains diagnostic: public metadata cannot prove
complete ephemeral descendants, full-process cleanup, non-resetting lifetime
counters or per-turn applied settings. Never promote that report into handoff
inputs. Harness also needs its trusted execution/evidence adapter; standard
runner/terminal/result paths cannot replace it. Terminal state reads are historical
and never recover automatically. Settlement is permanent ownership accounting,
not packet acceptance, retry, archive or a new send permit. Proof text stays inert;
do not turn an LLM conclusion or a final message into completeness/cleanup facts.

## Leave a useful, quiet handoff

Save outcomes and the next owner/external event once. Link retained artifacts and
the selected-workspace dashboard; no tokens or credential-bearing URLs. Notify
only on meaningful progress, completion, failure or required owner input. Normal
controller release remains required, but does not justify another evidence
artifact or repeated “no actionable changes” reply. On a real event, reacquire
and revalidate every boundary. Do not loop, sleep, self-message or create another
polling automation to get past missing input.
