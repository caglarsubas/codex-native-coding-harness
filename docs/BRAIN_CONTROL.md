# Brain controls and safe checkpoints

Use **Overview → Designated brain** to wake/resume the existing brain or request
**Stop brain at safe checkpoint**. These are separate from **Resume worker
dispatch / Pause new workers** at the top of the page.

| Control | Immediate effect | Completion evidence |
| --- | --- | --- |
| Wake / Resume brain | Save intent and notify the existing native task | Brain receives the request and recovers retained state; native schedule is separately observed |
| Stop brain at safe checkpoint | Fence new worker creation and acceptance acquisition; notify brain | New retained checkpoint, reconciled workers, no owned acceptance runner, fresh paused heartbeat observation |
| Resume worker dispatch | Notify brain of the explicit resume request | Brain processes it; exact packet approval and preflight still gate every worker |
| Pause new workers | Fence the next creation boundary | Local ledger acknowledgement; existing work is not cancelled |
| Reconcile / worker checkpoint / archive | Notify brain immediately | Receipt and actual outcome, not native queue delivery |

Notification requires the opt-in installed `codex queue` bridge and Codex running.
It wakes an idle task, or waits behind an active turn. Stop is **cooperative**, not
a hard interrupt: the brain reads its inbox between bounded steps. An already
running tool or isolated acceptance process must finish safely. There is no fixed
stop deadline. Do not mistake an empty implementation-worker queue for an idle
brain: planning, reconciliation and a native active turn are separate work.

## State and recovery

`meta.brainControl` is additive for existing ledgers. Absence means running/ready.
It retains desired state, phase, commandId, requestedAt and the last checkpoint.

| Phase | Meaning |
| --- | --- |
| ready | Brain controls permit work; this is not a live activity claim |
| resume_requested | Resume intent saved, not yet received |
| stop_requested | New dispatch fenced, stop not yet received |
| checkpointing | Brain received stop; safety work is unfinished |
| parked | Safe checkpoint recorded; automatic brain work is stopped |

Stopping supersedes older pending brain controls and worker-dispatch resumes.
An explicit newer Resume brain supersedes an unfinished stop. It does not enable
worker dispatch. Other answers and controls remain durable while stopped and
are received after resume. Controller, worker and runner ownership never expires
merely because a browser, server or brain stopped. No archive/delete/reset occurs.

Only the designated brain controller can call `brain-park`. Its closed input is
`summary`, 1–8 retained `artifactIds` (at least one new version observed after
the stop), and exact `workerObservations`. Each active native worker requires
`workerId`, matching `threadId`, `status: "idle"`, `observedAt` and `reference`.
Observation time must follow this stop and be within 120 seconds. A configured
heartbeat needs the same fresh post-stop PAUSED evidence. An unconfigured
heartbeat is allowed. Reserved/unstarted workers keep their reservations.
In-flight creation/acceptance, owned runner or processing worker controls refuse
parking. Unresolved design responses can be checkpointed without fabricated
outcomes; they remain in the inbox for recovery.

The immutable checkpoint document contains the retained artifact references,
worker/queue records and pending command IDs. Artifacts are readable from the
brain panel and Artifact library; the document is in authenticated
`/api/documents/<documentHash>`. The dashboard cannot manufacture this receipt.
The helper validates scoped assertions and timestamps; the trusted brain must
verify the actual native evidence. It is not an independent process attestation.

After saving, the brain releases its controller and ends its turn. Until a later
native idle event is observed, UI says **Safe checkpoint saved**, not that the
native turn already ended. A later idle observation supports **Brain stopped at
checkpoint**. A stale idle event is labeled **Last observed idle**, never freshly
observed. With no evidence, UI says **Activity not observed**.

## Delivery failures and race boundaries

Notifications use a fixed allowlisted control kind and hash identifiers. Neither
answer text nor browser-supplied commands, target, model or effort enters argv.
Each attempt is claimed durably before sending. Lost HTTP replies retry the same
envelope; ambiguous native delivery is not automatically resent. Open the brain
or use Wake/Resume brain to recover saved requests, not duplicate answers.
The existing heartbeat remains a fallback until safely parked.

Ledger intent and native scheduling are not one transaction. Re-read intent
before pausing the heartbeat and before parking. A newer resume refuses a late
park and requires schedule restoration according to saved listener policy. A
crash after native pause leaves a visible unfinished stop; Resume brain can wake
the same task without that schedule. All native operations remain in the brain.
