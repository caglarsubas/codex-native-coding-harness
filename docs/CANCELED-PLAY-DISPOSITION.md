# Canceled Play: forward-only disposition and continuation assessment

`canceled_play_disposition_v1` records a local **unqualified** outcome for one
accepted Play whose owner Cancel resolved, original turn was interrupted and
original observer closed without a brain receipt. It never replaces that receipt,
reopens the turn or marks the run paused, complete or safe. The original run's
`running` value is preserved as historical recorded state, not live activity.

This is the local disposition and planning portion of the requested continuation
repair. It is **not an executable native continuation adapter**. The current
pinned public host establishes its owning subscription through `thread/resume`.
Its `turn/start` does not subscribe a new connection. A new turn without an owned
observer would lose permission and lifecycle handling; calling `thread/resume`
would violate the no-reload instruction. Neither is an acceptable fallback.

The supplemental [subscribe-only transport](NO-RELOAD-TRANSPORT.md) now provides
the source-build component for an already-loaded idle runtime. It does not change
this original binding or supply an executable exact-owner continuation adapter.
An absent host or unloaded brain still cannot be continued under no reload; the
local disposition remains a separate non-waking unqualified record.

## Exact operator review, no countdown

Use explicit existing registry/workspace routing:

```text
canceled-play-preview PRIVATE_ORIGINAL_BINDING ORIGINAL_PLAY_ID
canceled-play-backup PRIVATE_REVIEW NEW_PRIVATE_BACKUP --writers-stopped
canceled-play-confirm PRIVATE_REVIEW --confirm-hash EXACT_HASH --writers-stopped --backup VERIFIED_BACKUP
canceled-play-status
canceled-play-continuation
```

The preview returns its closed `request`, exact `reviewHash` and
`validUntil: scope_changes`. Store the request in a canonical owner-only regular
file. Only a new exact owner confirmation of that hash can apply it. The previous
Cancel confirmation, source approval, broad assent and elapsed time grant no
disposition authority. There is no browser/inference/native permission route.
Preparing, reading and polling do not create a claim or send a native request.

Before applying, quiesce older ledger writers and retain verified private backups
of both databases, all existing target sidecars, the original binding and review.
Original database inodes, complete schema/table fingerprints, source bytes,
dual project/catalog mapping, binding bytes/full file epoch, every sidecar epoch,
original command/run and original sealed item-capture chain are pinned. No native
endpoint is opened, even to prepare the review. Changed state invalidates it.

## Narrow eligibility

Only an empty unowned schema-v4 cooperative standard attempt qualifies: legacy
dispatch remains paused, run status is `running`, and no checkpoint, recovery,
controller/private credential, runner, task, merge, queue, decision, Brain Stop,
handoff, enrollment, quarantine, successor or partial-admission ownership exists.
There must be one original Play, still queued/unreceived, matching its owner
receipt and exact unchanged reviewed mission. It must not already have a
prospective run mailbox or notification retry/history.

The original accepted owned notification must correlate the exact brain/run/
binding/turn, restricted original policy, sole resolved command-permission Cancel,
request hash, native resolution, interrupted turn and closed observer in their
retained order. Observed descendants, pending/uncertain responses and unknown
delivery refuse. Earlier readiness requests need their own correlated receipts
or validated disposition. No old readiness request is reinterpreted or replayed.
The original public backend and capture must match; all captured effects remain
preserved, including executed or unknown ones. Their presence is not a cleanup
claim and is not silently filtered from the review.

## Durable unqualified record and write fence

A flushed exclusive `standard-canceled-play.json` claim precedes insertion of one
immutable owner disposition snapshot. All original meta/run, commands, snapshots,
events, usage/high-water/gaps, expiry, claims, binding and sidecar bytes/epochs are
unchanged. No event/revision increment, controller acquisition, receipt, safe
checkpoint, ownership release, phase closeout or native notification is created.

Either the file or snapshot fences normal writes. A claim without a committed
snapshot, a snapshot without its claim, corruption or changed original rows stays
`incomplete_or_changed`; it is never retried, repaired by deletion or unfenced.
Exact repetition after a completed commit only reads the original local receipt,
including its original time. Older running helpers must be stopped before rollout;
this is not a downgrade/mixed-writer guarantee.

The UI labels the attempt **Canceled Play · unqualified**, keeps drafts/history
readable and shows continuation requirements instead of another cancellation or
Play prompt. Pending-receipt presentation excludes only this exactly disposed
command; its raw queued status and missing brain receipt remain in history.
All ordinary mutation, messaging, recovery, Resume and Play controls stay fenced.
Incomplete records are displayed as unavailable, never as a resolved cancellation
or authorized continuation.

## Continuation boundary

`canceled-play-continuation` is file/database-only planning. It reports
`executionAvailable: false` and the unsupported no-reload owned-subscription
boundary. It cannot make a native call, issue another instruction under a renamed
Play, attach a historical mailbox, load/subscribe a thread, change bindings, reset
usage or renew the original phase clock. No confirmation of this disposition can
turn those false values into permission.

A future native adapter must separately qualify a supported no-reload owning
subscription, exact new owner authority, unchanged run/scope/limits/expiry,
actual usage evidence and fresh current native policy/tracked-terminal evidence.
That is additional source/runtime qualification, not another Cancel confirmation.
Current and historical terminal safety remain unknown. This does not impose
legacy whole-process-tree qualification on the separate cooperative protocol or
weaken its existing registered-task/result evidence requirements.

## Qualification and rollout

Disposable tests exercise exact cancellation correlation, conservation, old
runs/claims, changed source/binding/usage/schema/sidecars, concurrency, interrupted
commit, lost reply, missing claim, immutable records and mutation fencing.
Desktop/320px reduced-motion rendering checks keyboard Details, no page overflow
and no confirmation/wake submission. These tests make no native/model calls.

Keep source, manual merge, quiesced/backed-up installation, exact live disposition
review/application and native pilot acceptance separate. Source delivery installs
or applies nothing, and does not complete the native continuation or pilot.
