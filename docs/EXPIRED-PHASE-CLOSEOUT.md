# Close an expired empty phase without losing its history

Recovery can finish correctly while its old phase stays paused: a reply is not
permission to retire a phase or restart it. Previously, the UI then offered
only “Inspect saved controls.” Resume refused the expired duration, ordinary
messages stayed held, and the owner had no usable transition.

## One-page owner flow

1. After the recovery reply and controller release, the graph and advisory guide
   offer **Review stopped-phase closeout** when the narrow eligibility checks hold.
2. The explicit preview reads metadata from the reviewed owned host. It displays
   the expired phase, **blocked · unqualified** outcome, preserved records and
   the fact that no brain wake or development is included. Details retain the
   exact ended-turn observation. Confirm the displayed button or type
   **confirm close stopped phase**.
3. The closeout receipt appears in the same inspector with **Next: Help me continue
   development**. This uses the existing signed, server-generated preparation
   request; no prompt writing or page navigation is needed. Loading that preview
   never sends it. Help is preparation only; the new mission needs its own Review
   and Play. A successor must have a genuinely new phase ID.

## Boundaries

This is an owner outcome, not a designated-brain terminal settlement or a
successful pilot. The adapter is deliberately limited to an expired, empty
`standard_cooperative_v1` run with its exact recovery received and replied.
There must be no registered tasks, legacy workers/packets, merges, runner,
controller, pending controls/messages, Brain Stop, handoff or maintenance/managed
fence. Even a terminal worker cannot be dropped through this path. Other phases
still need their existing brain checkpoint/reconciliation controls.

Before signing and again before confirmation, bounded `thread/read` and latest
`thread/turns/list` metadata reads bracket the exact recovery turn. Its ID must
be the latest completed turn, with stable completion time and idle/notLoaded
brain state. Bind the native project and checkout to the reviewed host, keeping
its desktop-catalog ID separate. Active, missing, changed, unknown or later
turns refuse closeout. These reads do not resume, subscribe, approve native
prompts, fetch turn items or inspect command/transcript bodies. Completed here
means the turn ended, not that its commands or permission relay were successful.
The read-to-local-commit gap remains cooperative; these observations are not a
native lock or atomic cancellation of a future turn.

The signed five-minute preview binds browser session, selected workspace, ledger,
brain, exact revision/run hash, recovery ID, reply hash and owned-host observation.
The confirmation rechecks local guards under registry → ledger locks. It retains
one completed `standard_closeout` receipt and an `ownerCloseout` record containing
the previous checkpoint and unqualified outcome. All budgets, cumulative usage,
allowances, coverage gaps, observation times, expiry, task counts, recovery and
historical native-effect records remain unchanged. The old run cannot be
reopened/relabelled through a later brain checkpoint.

Closeout is not a notification kind. Exact signed replay returns its original
receipt, even after expiry or later state changes; it never recollects evidence,
reapplies the outcome or sends a wake. Concurrent tabs cannot close twice. A lost
response is recovered with the same preview, not a new action.

## Rollout

Source, merge, backup/quiesced installation and live qualification remain separate.
Do not restart a dashboard, change a host binding, close the pilot, notify Help or
confirm Review/Play merely because the source is merged. No runtime dependency,
background dispatcher, paid service or GitHub Actions is introduced.

Disposable verification covers read-only Help polling, exact preview/confirmation,
native metadata drift, identity/fence/ownership races, preserved gapped usage,
same-ID replay, reload, one-page next-step visibility, and successor draft → Review
→ separate Play preview. Synthetic observations qualify local behavior only, not
real native permission handling, restart persistence or pilot acceptance.

Local source verification: 2,009 Python tests passed (one optional test skipped),
all 30 JavaScript UI suites passed, all web JavaScript syntax checks and the diff
check passed. The disposable rendered rehearsal covered desktop and 320px reflow,
keyboard confirmation/sheet dismissal, light/dark themes, receipt visibility,
pending-request replacement, reload, and sign-out/reconnection with an embedded
guide. Its host responses and delivery receipts were synthetic. No live pilot
closeout, wake, Review or Play was performed during this verification.
