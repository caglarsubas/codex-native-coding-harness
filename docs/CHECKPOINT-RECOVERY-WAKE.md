# Recovery-only preparation from a paused standard checkpoint

The old failure mode was a dead end: a paused phase correctly refused Resume
because its duration or usage evidence was blocked, while the ordinary message
saved by “Prepare checkpoint follow-up” was intentionally not notified or
receivable. The page implied a brain reply would arrive anyway. This path makes
the exception explicit and keeps it narrower than phase execution.

## Owner flow

The one-page workspace first shows the recorded stop reasons, old phase budget,
known usage lower bound, coverage gaps and held-message state. **Help me continue
development** or **Review recovery preparation** opens a server-signed preview
bound to workspace, ledger, browser session, current brain, run hash and revision.
It names the exact held message (or one new server-generated instruction), a
fixed 500,000-token additional cooperative brain allowance, and the rule
that this is one preparation turn rather than phase Resume. The maximum accepted
allowance in the server guard is 2,000,000 tokens; this interface does not expose
an allowance editor. No numeric field is inferred from missing usage.
The owner must explicitly confirm the displayed preview. Reads and polling do
not collect telemetry, save a command, wake a brain or confirm authority.

The confirm transaction preserves the old run status, expiry, phase limits,
charged allowances, observed usage, high-water mark and gaps. It creates one
`standard_recovery` command and, only when no message was already waiting, one
bounded conversation command. If a prior message has any attempted native
notification, its delivery must be reconciled first; it is never retried. The
recovery command can be notified only on the reviewed, exact bound local
Codex app-server host. The desktop queue alone is not qualified for this path.
The native notification is a fixed pointer and contains neither message text
nor arbitrary browser argv. A durable claim precedes the native boundary, so
an uncertain send is never automatically repeated.

## Brain scope and receipts

The designated brain verifies its identity and the exact run, acquires the
existing controller, then uses `standard-brain recovery_receive` with the
command ID. That operation has a one-hour receive deadline and receives only
the bound message. Generic `brain-message-receive` and ordinary `receive`
remain fenced while paused. The brain may inspect local usage and native facts,
reconcile existing effects, retain a safe terminal checkpoint when all ordinary
preconditions hold, prepare a successor mission draft and save a concise reply.
It may not create or continue workers, merge, retry an uncertain effect, change
policy, review a mission, Play or Resume. Existing source and native tools still
have their own authority gates; this permission does not override them.

Progress is distinct: preview, committed request, native send claim/result,
brain receipt, saved reply and any later terminal checkpoint/draft. Native
accepted is not a brain receipt. A received message is not a reply. Reply does
not complete a phase or approve its successor. The recovery allowance is a
cooperative one-turn planning limit, not a hard provider or billing cap. Old
phase usage and unknown coverage are not reset or subtracted; any later usage
refresh preserves the same cumulative high-water accounting.

When this reply leaves an expired empty phase paused, use the separate signed
[owner closeout](EXPIRED-PHASE-CLOSEOUT.md) after the exact recovery turn ends.
It records blocked/unqualified, preserves the previous checkpoint and sends no
wake. Help then prepares a successor draft with its own Review and Play. An
unresolved task/effect or a missing recovery receipt cannot use that transition.

## Rollout and qualification

Source delivery, merge, private-state backup, quiesced installation and live
qualification are separate. Do not install against mixed-version writers,
change the bound host, wake the live brain, Resume or Play merely because this
source exists. Qualify with a disposable standard project and bound test host:
held-message reuse, one-shot native send, exact brain receipt and reply, budget
and Pause races, stale/foreign previews, uncertain delivery and UI progress.
Strict Harness, missing app-server bindings and cross-project requests fail
closed. No background scheduler, paid service or GitHub Actions is added.
