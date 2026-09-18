# Actionable follow-ups and event-driven waiting

The Decision inbox keeps blocked outcomes visible under **Next steps for blocked
work**. The original answer and outcome are immutable evidence, not an executable
instruction. A designated-brain planning pass must produce one of:

- a retained proposal linked to a genuinely new owner decision;
- a retained proposal linked to an exact prepared but unapproved packet;
- an explicit external dependency and the event that permits reconsideration.

`continuation-publish` is a local controller operation, not an HTTP control.
Its closed schema and examples are in the bundled skill's operations reference.
It checks designated-brain ownership, cooperative stop intent, source outcome,
artifact repository/freshness, current version, and exact linked decision/seed
bindings. These checks do not independently verify the proposal's claims.
Publications are versioned immutable documents. Revisions retain older versions.
Legacy blocked decisions project as **Proposal needed** without a data rewrite.

| State | Meaning | Next action |
|---|---|---|
| Proposal needed | No retained next step | Brain performs one bounded planning pass |
| Proposal links changed | A linked question or seed was replaced | Brain revises the proposal against current versions |
| Next step published | Exact next decisions/packets are linked | Owner reviews the linked decision or packet; not a completion claim |
| Waiting for an external event | No authorized next action now | Resume on the named event or request a deliberate review |

## Scheduling

Event-driven waiting is the default for new installations. Existing saved idle
polling preferences are preserved until the owner changes them. **Use event-driven
waiting** saves that choice and notifies the same brain; it does not hard-stop a
turn or change dispatch permission. The brain pauses the existing native heartbeat
only after there are no active workers/runner, unpaused approved work, pending
receipts, or follow-ups needing a planning pass. Owner questions and unapproved
proposals alone do not require recurring model calls. **Enable periodic idle
checks** explicitly opts back into their usage.

Dashboard answers, exact approvals, holds, priorities, listening preferences and
typed controls notify the existing brain through the installed fixed CLI bridge.
Locally applied controls are **saved**, but separately await a brain receipt.
Receiving them never reapplies older policy over a newer change. No background
dispatcher, arbitrary browser prompt, private API or additional model is added.

The dashboard distinguishes policy from observed schedule: **native pause
pending** does not mean scheduling has stopped. Only the native automation tool
can pause it. The brain records the observed result and rechecks the inbox after
schedule changes to reconcile races. A paused heartbeat is different from
**Stop brain**: the former can wake on new input, the latter preserves ordinary
inputs until explicit **Resume brain**.

If immediate notification fails or is uncertain, the request remains saved and
the UI offers the existing brain. With its heartbeat paused, manual recovery is
required; do not claim automatic retry or silently enable idle polling.

## Authority

Planning does not provision a machine, inspect a target, approve a packet, create
a worker, run acceptance or merge. Original decisions retain their scope. A new
resource choice narrows the next proposal; execution remains separately gated.
Repeated polling cannot create missing authority or missing infrastructure.
