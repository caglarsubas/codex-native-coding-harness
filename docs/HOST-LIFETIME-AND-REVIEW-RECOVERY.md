# Host lifetime and review recovery

Preview expiry, native read deadlines and phase duration are different clocks.
None is a host-process TTL. Recovery cannot reset usage, extend phase authority
or retry an uncertain native send.

## One-page recovery

An expired/refused workflow keeps its scope visible with **Refresh review** and
a visible countdown. Refresh requests only a new signed preview of that workflow
using current server-side scope/prerequisites. Verbatim brain messages retain
their exact draft. Failed refresh keeps the old review; changed scope needs its
own confirmation. Submitted, uncertain, recorded, dismissed and foreign previews
cannot become new requests. Original receipt recovery keeps its original ID.
Polling never renews or confirms. Dashboard restart still invalidates signatures;
a refused confirmation exposes Refresh review. No signatures are persisted.

The five-minute workflow review and two-minute native permission limits are unchanged. Closeout's clock
starts after native inspection; embedded standard-control expiry cannot be
extended by the outer chat preview. Phase duration and usage remain untouched.

**Check host connection** is an explicit authenticated/CSRF-protected action
on one registered standard project. It performs one five-second bounded
WebSocket initialization on the pinned endpoint, rechecks identity, then closes.
No task RPC, subscription, resume, turn, permission, discovery or ledger write.
Strict Harness, changed bindings, foreign targets and concurrent checks refuse.
Private native error bodies are never returned. State polling reads the cached
result, which becomes stale after 30 seconds, without reconnecting or refreshing
timestamps. Success proves a host handshake, not native tools, approvals,
descendant coverage, usage or phase readiness. Dashboard `/healthz` means only
the dashboard is available.

## Separate opt-in operator supervision

`python3 -m orchestrator.host_lifecycle` runs one existing, privately reviewed
guarded host launcher under a detached supervisor, independent of the command's
foreground lifetime. No process timeout or automatic restart. Private intent,
PID, observed exit code/signal and timestamp records contain no environment or
transcript. Running records are historical, not current health. It creates no
brain, binding, authority, schedule or registry entry; it is not a dispatcher.

The owner-only manifest contains exactly `schemaVersion: 1`,
`profile: standard_owned_host_v1`, the canonical private `launcher` path, its
exact `launcherSha256`, and the canonical registered checkout `cwd`.
The guarded launcher must independently enforce signed vendor integrity, exact
checkout/paused rollout state, current app-owned context, workspace-write,
on-request approvals and Code Mode disabled. The manifest label does not verify
script semantics or native tools. Never use a generic script, copy pipe values
from another context, modify the signed vendor or assume a socket proves health.

After separate exact operator review, in the qualified Codex execution context:

```text
python3 -m orchestrator.host_lifecycle preview PRIVATE_MANIFEST
python3 -m orchestrator.host_lifecycle start PRIVATE_MANIFEST NEW_PRIVATE_ATTEMPT_DIR --confirm-hash EXACT_MANIFEST_HASH
python3 -m orchestrator.host_lifecycle status PRIVATE_ATTEMPT_DIR
```

Preview/status start nothing. Exclusive intent precedes supervisor launch;
intent/monitor claim permanently fences the same attempt, even on failure or
unknown outcome. The current environment is inherited, not persisted; pipe
presence is merely a refusal guard, not authentication/qualification. The guarded
launcher must refuse unavailable context. Native process output is discarded.
Supervisor death/reboot may leave historical status; never infer permission to
relaunch. This is not a boot service or guaranteed connectivity after desktop exit.

## Rollout boundary

Source delivery installs/starts nothing. Quiesce older writers and back up private
state before installation. A newly started listener may change canonical socket
identity and requires the existing exact binding review; never silently repin or
reuse old approvals. Never replay wakes or automatically Resume, Review or Play.

Disposable tests cover one-shot detached intent, exit records, identity drift,
HTTP auth/isolation, cached health, refresh and original receipt recovery.
Rendered checks use synthetic native responses. They do not qualify a real host
across turns/reboot, prove native tool connectivity, or accept/repair the pilot.
