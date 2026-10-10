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
and no tracked terminals. Ended-turn activity must be loaded-idle; `notLoaded`
does not prove zero tracked terminals. Unsupported, changing, active or incomplete terminal
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
start or silently rebind another host. The separately reviewed ended-turn
continuity path below can inspect an already qualified replacement. After controller recovery,
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

## Separately reviewed replacement host: ended turns only

The original host can exit before the signed recovery is used. Do not keep
asking for a review that needs a dead endpoint. An operator may separately
review and qualify a replacement host and dashboard binding, back up private
state, stop older dashboard writers, and supply:

```text
--brain-app-server-binding PRIVATE_REVIEWED_CANDIDATE.json
--turn-recovery-prior-binding PRIVATE_PRESERVED_ORIGINAL.json
--turn-recovery-retired-host PRIVATE_REVIEWED_RETIREMENT.json
```

The original binding is historical evidence only: its complete hash must equal
the original notification/profile. It is never validated against an obsolete
socket, connected to, resumed, or used as a fallback. Require exactly one
identical brain mapping in both bindings, including workspace, canonical
checkout, both distinct project IDs and workspace-write/on-request/Code Mode-off
policy. Only endpoint pins may differ. The registered catalog, database identity
and Git common repository checks remain unchanged.

Retirement configuration has exactly `version: 1`, `bindingHash`, `processId`
and `launchClaimHash`. Before separately reviewing it, the operator must verify
the PID against the original binding's retained host inspection and one-shot
launch journal; the hash is provenance, not independent authentication or proof
by itself. Never guess a PID from a name, socket file or process listing. A
current, fixed `/bin/ps -p PID -o pid=` metadata read must prove exact absence
before and after native inspection and before conditional controller release.
A live/reused PID, unreadable process metadata or missing historical provenance
refuses. No process is killed and no host is started by this path. This rules out
releasing an original in-memory turn merely because a different host reports a
persisted ended turn. It does not prove process-tree cleanup.

On the already reviewed candidate, repeated project/thread/turn reads must
identify the exact original latest turn as ended, with matching completion
metadata, **loaded-idle** activity and complete known-empty tracked terminals.
Identity reads bracket the terminal inspection. `notLoaded` is unknown, not zero
terminals; the path never calls `thread/resume` to manufacture an idle observation.
The explicitly signed inspection-loading extension below is the sole exception
to the no-loading rule; no read or old confirmation authorizes it.
Unknown/unsupported terminal APIs, active/new/changing turns, pending approvals,
observed children, tasks, packets, managed ownership and Brain Stop all remain
fenced. If the candidate cannot supply this evidence, host qualification is
still incomplete and no recovery claim is created.

The same unchecked **Confirm turn recovery** signs the exact old/new binding
hashes, retirement record, catalog/ledger/controller/run context and ended turn.
Unsafe-range socket/ledger identity integers travel as canonical decimal strings;
verify the envelope signature/session before decoding, and preserve their exact
integers in the private journal. Only read RPCs are possible in this mode: no
interrupt, load, turn start, permission response or replay. Record native
delivery as `not_needed`, separately from conditional controller recovery.

A claim is pinned to its selected binding and retirement record. Neither a
previous original-host cancellation claim nor a replacement claim can migrate
to another endpoint or obtain another attempt. Historical HTTP replay returns
only its receipt, even after the host disappears. Explicit checks of an unresolved
claim repeat only its own metadata observations and original-PID absence; polling
does not collect them. Preserve the original notification/profile and every
usage gap/deadline/receipt. Effect outcome and task-tree completeness remain
unknown, and development stays stopped without a fabricated checkpoint.

Host launch, binding review, loaded-thread qualification, safe phase checkpoint,
closeout/successor review and actual native permission response are still separate
observed outcomes. Source merge and synthetic tests do not complete this pilot.

## Break the dead-host / unloaded-thread recovery cycle

A fresh replacement host can correctly return the original persisted turn as
`interrupted` while its runtime status is `notLoaded`. Its terminal API is then
unavailable. Requiring loaded-idle evidence before permitting any loading makes
recovery impossible. Bypassing the terminal check or replaying Play would conceal
uncertainty or duplicate work. The fix separates loading for inspection from
starting a turn and from controller recovery.

On this separately reviewed replacement only, **Review turn recovery** can now
offer `load_for_inspection_then_reconcile`. The preview performs repeated exact
project/brain/latest-ended-turn reads, checks original-PID absence and reports
`trackedTerminals: null`, `terminalCoverage: unknown`. It does not query an
unloaded terminal tracker or write/load anything. The same unchanged original
notification, receipt, controller, run, catalog and both host bindings are pinned.
Active, different or changing turns cannot obtain this exception. Existing
original-host recovery still refuses `notLoaded`.

One explicit unchecked **Confirm turn recovery** includes exactly one inspection
load and conditional local controller recovery. The private journal first commits
the consumed claim and `stopping` fence, then commits an issued marker before the
native frame. Under the serialization locks it repeats original-host retirement,
registered/endpoint/context identity and ended-turn checks immediately before
the sole documented [`thread/resume`](https://learn.chatgpt.com/docs/app-server)
request. The request has only the exact brain ID, `excludeTurns: true`,
workspace-write/on-request, `approvalsReviewer: user` and Code Mode disabled.
No history, path, instructions, model/effort, runtime roots, permission profile
or arbitrary target can be supplied. **This is native thread loading, not
standard phase Resume.** `turn/start`, `turn/steer`, approval responses and
creation remain impossible on the recovery client. Loading may initialize native
runtime/MCP components; it is an explicit native action, not a read-only check.

The acknowledgment contains no terminal safety proof. Reconciliation still needs
fresh repeated loaded-idle metadata for the exact unchanged ended turn plus
complete known-empty **current-host** tracked-terminal pages, with bracketing
identity and retirement checks. Unsupported, partial, active or changing reads
retain the controller. A fresh empty tracker is not a reconstruction of the lost
host's terminal inventory or OS process-tree cleanup. The journal preserves the
unloaded pre-observation and `historicalTerminalCoverage: unknown`; effect outcome
remains unknown and task-tree completeness remains false, even after local
controller recovery. No native ownership is released or safe checkpoint created.
The run remains stopping, usage/allowances/gaps/deadline remain unchanged, and
the existing separate safe-checkpoint controls govern further pilot progress.

Controller recovery also retires its exact private credential, rather than leaving
`standard-controller.json` behind to block the next brain acquisition. The signed
preview pins its bytes and filesystem identity without exposing the token. Only
after the same native inactivity checks pass, an exclusive hard link retains those
bytes in a private hash-addressed archive before removing the active filename.
A changed owner, bytes, inode, permissions, symlink, foreign hard link or archive
collision refuses recovery; nothing is overwritten. Interrupted linking/unlinking
can reconcile only the exact retained pair under the original consumed claim.
The database controller remains owned until retirement and the local recovery
commit succeed. This is credential retirement, not native/process cleanup, a new
controller acquisition or permission to start work. The private archive must never
be committed, exposed through a transcript or copied into inference history.

Interrupted claims, failed sends and lost load responses never obtain another
load, even when no frame was sent. The existing **Check this existing turn again**
is read-only reconciliation against the same pinned host/turn. An identical
confirmed HTTP retry reads only its retained receipt. Another turn, controller,
host, catalog, maintenance fence, Brain Stop or registered effect prevents
recovery. Current native policy reports are retained separately from requested
settings; Code Mode acknowledgment is not observed execution qualification.

Rollout must first merge compatible source, quiesce older writers and back up
private state. Review/install the qualified replacement binding separately; the
old binding is historical only. Old launch approvals, prior read-only recovery
reviews and source delivery do not confirm this new native action. No automatic
load, reconnect, host launch, phase extension, Play or pilot acceptance follows.

### Prior source verification (PR #136, 2026-10-10)

The complete local suite passed: 2,201 Python tests (one existing skip), all 35
JavaScript suites, all 31 web JavaScript syntax checks and `git diff --check`.
The 36 focused recovery tests include lossless browser round trips, exact
registered HTTP routing, original-PID absence and drift, historical-endpoint
non-use, unknown/active/unloaded refusal, preservation of the original request
and replay without native I/O. A disposable rendered desktop/320px rehearsal
confirmed the replacement review, recorded recovery and separate safe-checkpoint
preview. Native reads and retirement were synthetic; the original live pilot
ledger, binding, usage, controller and deadline were unchanged. These checks
qualify source behavior, not a replacement host or live pilot acceptance.

### Inspection-load and credential-retirement source verification (2026-10-10)

The updated full local suite passed **2,225 Python tests** (one existing skip),
all **35 JavaScript suites**, all **31 web syntax checks**, including
`node --check web/app.js`, and `git diff --check`. The **60 focused recovery
tests** include 24 new cases for inspection loading and credential retirement:
read-only unknown projections, exact native policy, durable pre-frame claims,
lost acknowledgments, concurrent confirmations, active/foreign turns, unsupported
or partial trackers, retirement/identity drift, maintenance and Brain Stop,
HTTP authentication/CSRF/idempotency, archive collisions, credential replacement
and crashes before/after unlink. The next designated-brain acquisition succeeds
only after the old matching credential has been preserved and retired.

`PYTHONPATH=tests:. python3 tests/manual_turn_recovery_fixture.py --inspection-load`
provides a disposable synthetic rendered rehearsal. Desktop and 320px sheet
checks passed, including keyboard disclosures, unchecked confirmation, no
horizontal overflow, recorded recovery and the separate safe-checkpoint action.
It does not connect to Codex, approve a live control or qualify the pilot.

An explicit live **read-only** qualification on the existing rebuilt host still
observed the exact original interrupted turn as `notLoaded`, with current
terminal coverage **unknown** and no thread load or turn start. Both private
database logical fingerprints, the original binding, controller, request, expiry
and recorded usage of 719,893 remained unchanged. Source delivery is separate
from merge, backed-up installation, replacement-binding review, exact inspection
confirmation, actual terminal evidence, checkpoint retention and pilot acceptance.
No GitHub Actions or paid CI service was added or invoked.
