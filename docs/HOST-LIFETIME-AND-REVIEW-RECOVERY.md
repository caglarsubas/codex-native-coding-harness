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
guarded host launcher. **Foreground `run` is the ancestry-preserving option for
a persistent Codex-owned terminal.** The supervisor remains in that terminal's
process ancestry until the guarded host exits; it does not detach or return while
the host is running. Keep the terminal and Codex app open. Running it from a
temporary command request does not turn that request into a persistent terminal.
Actual destination native tools must still be observed separately.

Legacy detached `start` is process supervision only, independent of the command's
foreground lifetime. It must not be presented as a native connectivity repair:
on the disposable host observed on October 6, 2026, the host stayed alive and its
handshake passed, but desktop rejection metadata recorded
`untrusted-process-ancestry` during failed native app-tool discovery. Inherited
connection environment and signed host bytes did not prove a trusted detached
process chain. The log does not identify a rejected PID; the correlated rejection
and failed destination catalog are not grounds to blame or alter a particular
vendor component. No signature, ancestry check or native trust policy is bypassed.
Process metadata separately showed the detached supervisor parented by the OS,
not retained under the app. Preserving the caller is a necessary design correction,
not proof that a particular foreground host will pass native trust or tool discovery.

Neither mode has a process timeout or automatic restart. Private intent,
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

Prepare a **mode-bound** foreground review, then separately confirm its exact
`reviewHash` in the persistent, qualified Codex-owned terminal:

```text
python3 -m orchestrator.host_lifecycle preview PRIVATE_MANIFEST --mode foreground
python3 -m orchestrator.host_lifecycle run PRIVATE_MANIFEST NEW_PRIVATE_ATTEMPT_DIR --confirm-hash EXACT_FOREGROUND_REVIEW_HASH
python3 -m orchestrator.host_lifecycle status PRIVATE_ATTEMPT_DIR
```

The foreground review binds both the original manifest hash and the supervision
mode. An old detached approval cannot authorize foreground `run`, or vice versa.
Legacy `preview --mode detached` / `start` remain available for explicit
process-only supervision and historical receipts; their manifest hash is not
native tool qualification. A foreground intent cannot be consumed by the
detached internal monitor. The same attempt is permanently one-shot across modes.

Preview/status start nothing. Exclusive intent precedes supervisor launch;
intent/monitor claim permanently fences the same attempt, even on failure or
unknown outcome. The current environment is inherited, not persisted; pipe
presence is merely a refusal guard, not authentication/qualification. The guarded
launcher must refuse unavailable context. Native process output is discarded.
Supervisor death/reboot may leave historical status; never infer permission to
relaunch. An interrupted foreground wait retains unknown process outcome and its
consumed claim, not permission to launch again, kill tasks or clear ownership.
This is not a boot service or guaranteed connectivity after desktop exit.

## Rollout boundary

Source delivery installs/starts nothing. Quiesce older writers and back up private
state before installation. A newly started listener may change canonical socket
identity and requires the existing exact binding review; never silently repin or
reuse old approvals. Never replay wakes or automatically Resume, Review or Play.

Disposable tests cover one-shot intent across both modes, mode-bound reviews,
foreground caller lifetime, interrupted monitoring, legacy intent compatibility,
detached exit records, identity drift,
HTTP auth/isolation, cached health, refresh and original receipt recovery.
Rendered checks use synthetic native responses. They do not qualify a real host
across turns/reboot, prove native tool connectivity, or accept/repair the pilot.
The foreground alternative is source-delivered only: it has not been installed
or launched on the pilot, and no changed binding or phase control is authorized.
