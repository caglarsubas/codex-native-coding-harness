# Continuous foreground connection through planning review

`continuous_connection_handoff_v1` preserves one original foreground owning
connection while the owner reviews a prospective planning turn. It is an
operator-only, opt-in path for **unconsumed** canceled-attempt planning, not a
reload, recovery, new dispatcher, background keeper or same-run Resume.

## The lifecycle gap

A successful inspection load becomes historical when its connection closes.
The pinned native runtime may unload an idle thread with no subscribers; the
default native delay is 60 seconds. A host process remaining alive does not
keep an unsubscribed brain loaded. Extending an approval countdown or treating
an old loaded-idle observation as current does not fix that gap.

This path can subscribe only to a brain that is **already loaded and idle**.
It cannot resurrect the closed inspection connection, adopt a consumed load,
disable unloading, reload a stored thread, or rename a failed planning attempt.
A future permitted producer must retain ownership until the new subscription
is actually acknowledged. There is deliberately no load capability here.

## Exact scopes and one original process

First prepare the explicit version-2 prospective usage planning review in
[FORWARD-USAGE-EVIDENCE.md](FORWARD-USAGE-EVIDENCE.md). It must have no canonical
planning journal or mailbox, and all original disposition/database/sidecar,
source/client/interpreter/package/binding pins and budget/expiry gates must hold.

The separate handoff review pins that exact private request, its full context,
the implementation and a bounded foreground ownership window (1–86,400 seconds,
normally 86,400, always capped by the unchanged original phase expiry). Review
validity is `scope_changes`, not a short approval timer. A live connection's
lifetime, evidence freshness and the phase deadline are separate constraints;
no window is renewed automatically.

After exact new owner confirmation, quiesced writers and verified private
backups, commit a permanent canonical intent before opening one connection.
Its identity is the original database identity and Play command, independent of
directories, source versions, endpoints or a new request ID. A partial, failed,
stopped or closed owner permanently fences another open and standalone planning
fallback. An owner must not close the current process to install source.

On that connection, repeat latest original interrupted-turn, project/brain/cwd,
loaded-idle, actual restricted policy and complete empty current-tracker reads;
claim before one `thread/subscribe`. Keep the original process and pipe object.
No `thread/resume`, model keepalive, account refresh, native permission response,
cancel, reconnect or second subscription is supported.

## Review while subscribed, then hand off in-process

The ready record pins the exact process birth, a new owner nonce and the native
subscription observation. Its immutable file pin is retained separately. It is
historical evidence, not a persistent assertion of current activity or safety.
File-only status says `claimed_current_connection_unknown`, never "connected".

An explicit planning preview binds the new confirmation to that original ready
record, process/nonce, source and exact prospective planning hash. An owner
confirmation writes one private authorization into the protected registry-side
journal. It performs no native call itself; arbitrary commands, request text,
browser targets or sandbox-written approval files are not accepted.

The original foreground owner observes only its bounded private authorization
and passive native events. Periodic file/context checks and checks immediately
before every effect honor Stop, drift and expiry. No native metadata polling,
telemetry collection or model wake is used to keep a connection alive. Permission,
active/foreign-thread or close events fail closed without answering or canceling.

After that separate confirmation, the existing planning adapter claims its
original canonical planning journal once and collects actual usage **then**, not
while the owner is still reviewing. The new explicit handoff scope permits this
ordering on the already open read-only connection. The standalone version-2 path
still collects before connecting. Both retain the existing 120-second freshness,
monotone vectors, high-water amounts, allowances/reserve and original expiry.

A process-local, thread-bound, single-use object passes the very same proxy and
subscription into the planning adapter. It cannot be serialized or adopted by
another process. Repeat actual native state at handoff and turn-start boundaries.
Commit a new handoff claim; never subscribe or resume again. The same original
observer retains the explicit new receipt and inert proposal. Stop/drift during
that turn fences its service too; it sends no native cancel. The outer original
owner closes the connection after outcome, failure, interruption or expiry.

The old ledger, original missing Play receipt, usage/report time, claims, captured
effects, historical bindings and repository holds remain byte/epoch unchanged.
Current empty trackers are not historical cleanup or terminal-safety proof.
A planning result is not worker completion, phase success or pilot acceptance.

## Operator interface

Use exact private registry/workspace routing from the qualified source:

```text
python3 -B -m orchestrator.connection_handoff --platform PLATFORM --workspace WORKSPACE prepare PLANNING_REVIEW --max-hold-seconds 86400
python3 -B -m orchestrator.connection_handoff --platform PLATFORM --workspace WORKSPACE backup HANDOFF_REVIEW NEW_BACKUP --writers-stopped
python3 -B -m orchestrator.connection_handoff --platform PLATFORM --workspace WORKSPACE serve HANDOFF_REVIEW --confirm-hash EXACT_HANDOFF_HASH --writers-stopped --backup NEW_BACKUP
```

Save each closed `request`, not its wrapper. Keep `serve` in its original
foreground session. While that exact owner is present:

```text
python3 -B -m orchestrator.connection_handoff --platform PLATFORM --workspace WORKSPACE planning-review HANDOFF_REVIEW
python3 -B -m orchestrator.connection_handoff --platform PLATFORM --workspace WORKSPACE authorize HANDOFF_REVIEW PLANNING_CONFIRMATION --confirm-hash EXACT_NEW_CONFIRMATION_HASH
python3 -B -m orchestrator.connection_handoff --platform PLATFORM --workspace WORKSPACE status HANDOFF_REVIEW
python3 -B -m orchestrator.connection_handoff --platform PLATFORM --workspace WORKSPACE stop HANDOFF_REVIEW --confirm-hash EXACT_HANDOFF_HASH
```

Stop is a permanent local fence, not native cancellation or a retry permit.
Status is file-only and reconnects, loads, collects and renews nothing. Missing
close/outcome records stay unknown. A consumed original planning attempt cannot
obtain an executable handoff review. To retain its exact blockers without claiming
another operation, use:

```text
python3 -B -m orchestrator.connection_handoff --platform PLATFORM --workspace WORKSPACE assess HISTORICAL_PLANNING_REVIEW
```

An assessment hash is not an approval hash. In particular, a v3 attempt that
already consumed its original planning claim must retain that failure. Source
installation cannot rearm it, restore its earlier connection or fabricate a
usable review. Further live progress would require a separately designed and
authorized forward lineage or a genuinely different permitted target—not another
confirmation of this attempt. No such lineage is supplied by this component.

## Qualification and rollout

Disposable tests cover exact approvals and conservation; loaded/unknown state;
concurrent ownership; source/ready/backup drift; process-local and CLI type
identity; Stop before/during planning; native permissions; collection failure;
stale usage despite a longer ownership window; consumed/partial/closed claims;
and file-only status without renewed evidence.

The compiled fixture explicitly sets a **disposable** one-second native idle
unload delay, subscribes the new original owner, closes every other subscriber,
then waits 1.5 seconds before preparing and confirming planning. It proves one
owning connection, one subscription, one new turn, actual sandboxed receipt and
inert proposal, with no reload/reconnect/resubscribe. Its original ledger and
numeric usage are labelled synthetic; all three model responses are loopback
fakes. No credential, live host, paid service, Action or runtime download is used.

```text
python3 -B scripts/qualify_canceled_continuation.py --package EXACT_PACKAGE --evidence NEW_PRIVATE_EMPTY_DIRECTORY --continuous-handoff
```

Source, local qualification, manual merge, safe installation, actual eligibility,
exact live review/application and pilot acceptance remain separate. This source
does not change or qualify the running dashboard or live v3 host.
