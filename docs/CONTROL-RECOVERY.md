# Guided recovery from a standard phase policy or safety stop

## One-click preparation

Use **Help me continue development** in the assistant. Its visible summary and
collapsed exact instruction form a signed preparation preview; the Help click is
the owner's confirmation. The existing brain investigates all current conditions
and prepares the next safe decision without requiring a handwritten prompt.
Follow saved / notified / received / replied progress in the same panel. The
reply reports checks completed, changes prepared, remaining blockers and the next
owner decision. A missing confirmed identity remains missing, never a retry permit.

If evidence or a decision is still required, enter only that missing item in the
follow-up field. The platform prepares the exact instruction for confirmation.
It does not automatically resend the original request or apply policy changes.
See [assistant-led workflow](ASSISTANT-LED-WORKFLOW.md) for boundaries.

The dashboard projects a deterministic, read-only explanation of a stopped or
blocked cooperative phase into Roadmap & Play and the assistant. Conditions can
involve usage evidence or budget, duration, reviewed mission/authority, task
limits, registered effects, merge ownership, catalog, repository identity,
external prerequisites or an owner decision. It shows each condition's source:
platform observation, optional brain-reported checkpoint code, or an explicitly
unclassified stop. A brain code is a lead, not independent verification. An
unknown stop is never converted into a guessed budget increase. The card needs
no model call, background poll or assistant-service connection.

When usage is relevant, the projection distinguishes observed tokens, reviewed
budget and reserve, cached versus uncached input, output, observation time and
coverage gaps. A missing sample is not zero; a gap leaves measured remaining
budget unknown. Arbitrary exception strings, checkpoint prose and native IDs
are not forwarded to inference. The phase retains its exact checkpoint summary
locally for the designated brain's investigation.

For a terminal blocked phase, **Prepare recovery proposal** opens a signed,
session-bound preview of an exact brain instruction. The owner confirms the
preview before it is saved and notified through the existing one-shot bridge.
The instruction asks the designated brain to inspect the exact policy,
checkpoint, evidence and native-effect receipts, then classify each condition.
It may refresh read-only evidence inside existing authority. If more development
needs changed limits, scope or authority, it proposes the *minimal exact change*
in a genuinely new bounded mission phase for owner review. It does not assume
more tokens are the remedy. It forbids reusing the stopped phase, waiving any
control, native retry, worker effects, mission review and Play. Receipt and brain
reply remain separate from notification delivery. An uncertain notification is
not resent blindly.

This is a general *diagnosis and owner-reviewed proposal* path, not an automatic
policy-repair engine. A confirmed recovery request starts an investigation, not
an authority change. The owner
must still review the exact new phase. Confirming that signed review applies its
proposed scope and limits through the existing mission control; the assistant then
shows the next prerequisite, including a separate signed Play preview when ready.
The owner must separately confirm Play under the standard-project contract. The
app must not calculate a supposedly safe new limit from incomplete evidence,
reset prior consumption, revive a terminal
run, or infer permission to cross a public-contract, tenant, billing, licensing,
credential or destructive-data boundary. Once exact evidence and a new phase
exist, the normal conversation-first signed controls guide those confirmations.
Strict Harness controls are unchanged.

## Open phase with unresolved work

A phase can still be recorded as `running` after its controller is released:
checkpoint settlement refuses while a native creation or merge is unresolved.
The dashboard must not describe this as healthy progress. Its read-only recovery
projection covers pending/issued creation identities, uncertain merges, released
controllers with unsettled confirmed tasks, and existing policy/evidence blockers.
It never changes the recorded run status, marks a worker absent, releases its
ownership, or infers current native inactivity from stale observations.

Session map, Roadmap & Play, the status header and the assistant expose this
attention state. Visible bullets explain identity, budget and coverage conditions;
measurements and the original saved brain checkpoint remain under Details.
Completed Play receipts say received, not phase-completed. A pending recovery
reply does not hide the warning. Reloading reconstructs guidance from the ledger.

**Reconcile this phase** opens a server-generated, signed conversation preview
for the exact existing run. **Confirm reconcile** (or its Confirm button) submits
one normal brain-bound message, not a new dispatcher. The request permits only
inspection/reconciliation of existing effects and a retained diagnosis. It forbids
implementation, worker creation or continuation, merge retry, policy changes,
usage reset and Resume/Play. Missing identity asks for precise supporting evidence,
not a guessed match. Missing evidence and exhausted budget remain separate blockers.

The normal session/project/signature/expiry/revision checks and immutable receipt
replay apply. A pending phase control or conversation, brain handoff, stopped
brain or stopping/paused run keeps its existing fence. A new phase remains
unavailable until the existing owned effects settle. Recovery never increases
limits automatically; subsequent review and Play are separate owner controls.
No scheduler, native task discovery on read, inference call or live migration is
introduced. Native final-answer text is not imported as a dashboard receipt.

Local tests use synthetic blocked runs and no native task or paid service. A
source merge, installation and live qualification are separate observations.

### Recovery guidance qualification

`tests/test_recovery.py` covers open/stopping/paused/blocked runs, initial
`nativeStatus: not_created` versus unsettled lifecycle, independent usage gaps and
overrun, uncertain merges, controller release, and healthy owned tasks. The
projection leaves its input unchanged and excludes native IDs.

`tests/test_assistant_journey.py` covers signed/session/project bindings, tampering,
expiry, a Pause race, pending requests, handoff/stop/strict fences, unchanged run
ownership and usage, and receipt replay without another notification. The UI
suites cover the header, received-versus-completed notice, Session map warning,
assistant recovery action, retained details/focus during unchanged map polling,
disconnection, and duplicate/stopped-brain guidance.

For a rendered rehearsal, run:

```sh
python3 tests/manual_progress_fixture.py --port 8774 --recovery
```

Open the emitted disposable URL. Verify **Recovery required**, inspect the
worker/budget/coverage bullets, and choose **Reconcile this phase**. Type
**confirm reconcile** only after reading the preview. Enter `reply` in the
fixture terminal, then reload the dashboard: the retained reply appears and
unresolved conditions remain visible. Enter `quit` to dispose of the fixture.
This rehearsal uses neither inference nor a native notifier. It qualifies the
rendered owner interaction, not live task reconciliation or resumed development.
