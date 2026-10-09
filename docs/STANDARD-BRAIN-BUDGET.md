# Paused standard-phase brain allowance review

Resume used to accept a `brainAllowance` preview field but retained the original
run allowance. Editing that value did not authorize a change. This repair adds a
separate exact owner review, not a new meaning for Resume or a waiver for budgets.

## Owner workflow

For an eligible budget-stopped phase the graph's next action is **Review brain
allowance**. It opens Token details in the same inspector. Enter the proposed
whole-token amount, review the signed old → new allocation, select the unchecked
confirmation and choose **Confirm brain allowance**. Editing requires another
review. The advisory conversation exposes the same `brain_budget` adapter and a
server-generated suggestion; **confirm brain allowance** applies only its single
current displayed preview. It does not call inference or notify the brain.

The total phase budget, reserve, task/concurrency limits, repository scope,
expiry, original Play receipt, checkpoint, observations, high-water counters,
coverage gaps and prior controls stay unchanged. Only the brain reservation
increases, reducing still-unreserved task capacity inside the same total. A
suggestion is not authority or a provider billing cap. Zero/unknown usage is not
invented; displayed counters are recorded, not final or automatically refreshed.

After confirmation the phase remains **paused**. Explicitly refresh registered
usage and resolve host/evidence prerequisites before a separate exact Resume.
Reallocation cannot renew an expired phase, increase its total/reserve, permit
another native attempt, release ownership or claim pilot success. If the total
has no headroom, prepare a genuinely new reviewed phase instead.

## Closed eligibility and records

This first adapter supports only an empty, paused `standard_cooperative_v1` run
with its exact unchanged reviewed mission/limits, retained checkpoint, released
controller and a completed latest owned-host turn. No tasks, packets, merge
effects, runner, pending controls/messages/recovery, Brain Stop, brain handoff,
unresolved recorded native approval/delivery or managed/strict maintenance may
use it. Retained ended-turn metadata is not independent native inactivity proof;
because this control makes no native action it does not collect such proof.
The ordinary native/effect/Resume guards remain authoritative later.

The private preview is session-, workspace-, ledger-device/inode-, brain-,
mission-, revision/context- and run-bound. It expires after at most five minutes
and never beyond the original run expiry. Both preview and confirmation recheck
the same guards under registry → ledger locks. Closed fields accept only run ID,
context hash and the increased amount, bounded below the total minus reserve.
No model-authored command or host target is accepted.

Confirmation appends `standardRun.budgetReviews` and an immutable
`standard_brain_budget` signed-review snapshot, advances the ordinary audit/run
revision and records a completed local command. This kind is not notifiable and
needs no brain receipt. Exact replay returns only its original durable receipt,
even after expiry or a later change; it cannot reapply an older allocation.
Prior usage evidence and original observation clocks are never rewritten.

## Rollout and verification

Source, manual PR merge, installation and live qualification stay separate.
Quiesce older dashboard/CLI writers and back up the private registry and ledger
before installing compatible source. Do not mix cached older helpers with the
new allowance journal. No source upgrade automatically adjusts a live allowance,
rebounds a host, collects evidence, wakes a brain or confirms Resume. Historical
failed host-inspection claims remain immutable. New notifications alone use the
new sandbox-safe handoff described in [host evidence](STANDARD-HOST-EVIDENCE.md).

Backend tests cover signatures, sessions, stale context, unknown/gapped usage,
exact receipt replay, unchanged scope/expiry/reserve, pending ownership/delivery,
strict fences and HTTP authentication/CSRF. UI tests cover editing, confirmation,
expiry, project isolation and non-mutating render. For disposable rendered QA:

```sh
python3 tests/manual_brain_budget_fixture.py --port 8802
```

This fixture creates only temporary repositories/ledgers and synthetic ended-turn
metadata. It has no native transport, inference credentials or live project.
Browser acceptance here is not native denial-pilot acceptance.
