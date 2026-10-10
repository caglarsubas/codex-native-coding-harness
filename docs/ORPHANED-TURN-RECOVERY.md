# Recover one stranded standard brain turn

## Problem and user outcome

An owned approval observer can end while its native turn or controller remains
unresolved. The approval text existed only on that connection: a new connection
cannot reconstruct it, answer it, or replay the original Play. A completed ledger
receipt also does not prove that the native turn ended. Previously the UI described
this gap but provided no bounded way to recover the abandoned controller.

In Brain chat, **Review turn recovery** now prepares the exact target without
writing state. After one unchecked, signed **Confirm turn recovery**, the server
cancels that one turn only if it is still active, then checks its end. If it was
already ended, no cancellation is sent. The confirmation includes conditional
controller recovery, so the owner does not need another approval for that local
completion. Unknown results offer **Check this existing turn again**, never a
second cancellation. The recorded result opens the existing phase checkpoint
review; it does not create a checkpoint or resume development.

## Closed scope and native boundary

This exception is limited to an empty `standard_cooperative_v1` run that remains
running/stopping with local dispatch paused and an exact brain controller belonging
to the latest received request. Require no tasks, workers, packets, runner, merges,
managed admission, pending controls, replacement or Brain Stop. The original owned
notification must retain its exact run, native turn, reviewed host binding and
acknowledged workspace-write/on-request/Code Mode-off resume profile. Its observer
must have ended with no witnessed child threads. This is registered standard
scope, not complete descendant or OS process-tree qualification.

The controller owner must explicitly end with that original request ID and use
the designated brain prefix. A legacy lease without this exact request link is
not guessed from activity, timing or a matching checkout; it needs its separate
operator recovery procedure.

The configured owned host must have no live subscription or native approval
request. Pin the original endpoint and both project identities, current catalog,
registered ledger identity and checkout's Git common repository. Repeated
`project/read`, metadata-only `thread/read`, latest `thread/turns/list` without
items and bounded `thread/backgroundTerminals/list` must agree on the exact turn
and no tracked terminals. Unsupported, changing, active or incomplete terminal
metadata remains unknown; no empty-page or desktop-host substitution is allowed.

The signed review is session-, workspace-, controller-, revision-, catalog-,
host- and turn-bound, expires after five minutes and is refreshable by an explicit
click. Confirmation repeats identity and metadata checks. Under registry → ledger
locks it commits the private one-shot claim and fences the run as `stopping`
before any native cancellation. It rechecks those pins at the send boundary and
can issue only the documented [`turn/interrupt`](https://learn.chatgpt.com/docs/app-server)
request with this exact `threadId` and `turnId`. The permit is consumed before
the frame is attempted. No resume, start, steer, approval response, terminal
cleanup, arbitrary method or browser-supplied target is possible.

The `{}` interrupt acknowledgment is not an ended turn. Fresh, repeated exact
ended-turn and inactive-thread reads, plus known-empty tracked terminals, are
required before clearing only the originally hashed controller. New activity,
controller replacement, registry maintenance or identity drift refuses release.
No checkpoint, effect outcome, usage coverage, task settlement or pilot acceptance
is manufactured. Cancellation delivery and conditional controller recovery are
distinct saved facts.

## Failure, progress and rollout

`GET /api/workspaces/ID/turn-recovery` reads saved metadata only. Polling never
collects evidence or confirms recovery. The three POST suffixes are `/preview`,
`/confirm` and `/reconcile`, using normal owner authentication, project-scoped CSRF
and the same serialization lock as native permissions. They accept no query
parameters, arbitrary native arguments or unsaved reconciliation target.

The claim lives under the original notification's `turnRecovery` journal. An
identical confirmed HTTP retry returns its existing receipt without native I/O,
including after expiry. A crash, blocked send or lost response keeps the claim
consumed and ownership retained. Explicit reconciliation reads only the same
turn on the same binding; it cannot resend cancellation or restore the old
observer. Every old notification, receipt, phase deadline, consumption and gap
remains intact. Raw prompts, transcripts, native error bodies and endpoint paths
are not copied into this journal or inference history.

An unavailable original host is an operator repair boundary, not permission to
start or silently rebind another host. A replacement endpoint needs a separately
reviewed continuity design; this version refuses it. After controller recovery,
the run stays stopping and dispatch stays paused. A designated-brain safe
checkpoint, applicable closeout and a newly reviewed successor Play remain
separate operations. Nothing here extends an expired phase or grants the lost
permission.

Quiesce older writers and back up private state before installing. Source merge,
installation, exact live confirmation, native results and pilot acceptance are
separate steps. The source tests and disposable rendered rehearsal use synthetic
native responses; they neither repair an existing host nor complete the pilot.

## Source verification

The final local qualification passed 2,188 Python tests (one existing skip), all
35 JavaScript suites, syntax checks for all 31 web scripts including `web/app.js`,
Python compilation and diff checks. The 23 focused recovery tests cover exact
one-shot cancellation, already-ended turns, lost responses, idempotent receipts,
host/catalog/controller drift, concurrent confirmations and maintenance races,
strict/managed/Pause fences, owner authentication and project-scoped CSRF.

A disposable rendered fixture verified desktop and 320px reflow, keyboard
disclosures, an unchecked confirmation, the recorded recovery result and direct
preparation of the existing safe-checkpoint review without confirming it. Its
native responses were synthetic. No live pilot state, host binding, original
request, phase deadline or native permission was changed. No GitHub Actions or
paid CI execution was added or invoked.
