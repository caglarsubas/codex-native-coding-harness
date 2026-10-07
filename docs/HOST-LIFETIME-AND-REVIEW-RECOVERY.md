# Host lifetime and review recovery

Preview expiry, native read deadlines and phase duration are different clocks.
None is a host-process TTL. Recovery cannot reset usage, extend phase authority
or retry an uncertain native send.

The [disconnect root-cause record](HOST-DISCONNECT-ROOT-CAUSE.md) separates the
observed desktop-update/session loss from the bridge's former silent six-hour
wait. Owned turn subscriptions now check transport responsiveness on the same
connection and retain loss as an unknown outcome, never a retry permission.
This does not turn a desktop-owned foreground host into a persistent service.

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

## Separate opt-in operator host lifetime

`python3 -m orchestrator.host_lifecycle` runs one existing, privately reviewed
guarded host launcher. **Foreground `exec` replaces the operator process instead
of retaining a Python supervisor in the native peer's ancestor chain.** Use a
qualified, persistent app-owned foreground context and keep Codex open. This is
not a boot service or a promise that a temporary tool request survives. The
guarded launcher must itself finally exec the reviewed signed host; spawning it
under another unsigned wrapper would reintroduce the problem. Independently
observe the actual process chain and destination tools after the launch.

Foreground `run` remains available for explicit process-only supervision. It
keeps the caller alive until the child exits, without detaching, but that is
**not native trust qualification**. On the October 6 disposable host, read-only
process sampling showed an OpenAI-signed Node peer under the signed host, with
an ad-hoc-signed Python supervisor as its grandparent. macOS signing metadata
showed that Python had no developer team identity. Inspection of the installed
native peer-authorizer showed identity checks at peer, parent and grandparent
depth; correlated rejection metadata reported `missing-code-signing-identity`.
The log did not provide a peer PID. These observations locate a concrete wrapper
defect without changing vendor code, substituting connection values, calling a
private app API or bypassing native security. Removing the wrapper still needs
fresh destination qualification; no fixture or launch record supplies that proof.

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

None of these modes has a process timeout or automatic restart. Private intent,
PID and timestamp records contain no environment or transcript. Supervised modes
also retain observed exit code/signal. Exec has no in-process exit monitor: its
`exec_boundary_issued` status records only the consumed boundary and original PID
and parent, not a running host, finished exec, exit, health or native capability.
The managed terminal/process observations remain separate facts. All status
records are historical. It creates no brain, binding, authority, schedule or
registry entry; it is not a dispatcher.

The owner-only manifest contains exactly `schemaVersion: 1`,
`profile: standard_owned_host_v1`, the canonical private `launcher` path, its
exact `launcherSha256`, and the canonical registered checkout `cwd`.
The guarded launcher must independently enforce signed vendor integrity, exact
checkout/paused rollout state, current app-owned context, workspace-write,
on-request approvals and Code Mode disabled. The manifest label does not verify
script semantics or native tools. Never use a generic script, copy pipe values
from another context, modify the signed vendor or assume a socket proves health.

Prepare a **mode-bound** exec review, then separately confirm its exact
`reviewHash` in the qualified app-owned foreground context. Use shell `exec`
when invoking the helper so the calling shell does not remain as an ancestor:

```text
python3 -m orchestrator.host_lifecycle preview PRIVATE_MANIFEST --mode exec
exec python3 -m orchestrator.host_lifecycle exec PRIVATE_MANIFEST NEW_PRIVATE_ATTEMPT_DIR --confirm-hash EXACT_EXEC_REVIEW_HASH
python3 -m orchestrator.host_lifecycle status PRIVATE_ATTEMPT_DIR
```

Each foreground review binds both the original manifest hash and its mode. All
three mode reviews are distinct: no old foreground/detached approval authorizes
exec, and no exec approval authorizes supervised launch. Legacy `preview --mode
foreground` / `run` and `preview --mode detached` / `start` remain process-only
options and historical receipts; their hashes are not native tool qualification.
Exec/foreground intents cannot be consumed by the detached internal monitor.
The same attempt is permanently one-shot across modes.

Preview/status start nothing. Exclusive intent precedes any launch boundary;
intent plus monitor/exec claim permanently fence the same attempt, even on failure
or unknown outcome. Journal writes and their parent directory are flushed before
the exec boundary. Exec replaces the operator with the exact `/bin/zsh` launcher
in the pinned checkout, preserving its PID, original parent and inherited
environment without a child, detach, timeout, restart or fallback. It suppresses
native output and never returns a successful host-ready response. An exec error
or interruption retains the consumed intent, not retry permission.
The current environment is inherited, not persisted; pipe
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

Check the registered ledger before requesting another host-launch review. A
filesystem device-number change can block the registry even while its inode,
brain and complete saved contents are unchanged. Requiring an original Play's
receipt before device-pin repair then prevents the brain from obtaining the
access needed to record that receipt. The separate, operator-only
[pending-Play device review](WORKSPACES.md#preserve-an-unreceipted-play-during-device-recovery)
can preserve that one unknown request while reviewing only the unchanged ledger's
device pin. It neither settles the request nor qualifies another host. If its
strict reference/empty-run/unknown-turn conditions fail, keep the refusal rather
than requesting approval for a launch that cannot unblock the workflow.

Disposable tests cover one-shot intent across all modes, mode-bound reviews,
foreground caller lifetime, interrupted monitoring, legacy intent compatibility,
detached exit records, persistence failure, same-PID/parent exec handoff and
no fork/environment substitution/fallback, identity drift,
HTTP auth/isolation, cached health, refresh and original receipt recovery.
Rendered checks use synthetic native responses. They do not qualify a real host
across turns/reboot, prove native tool connectivity, or accept/repair the pilot.
The exec alternative is source-delivered only: it has not been installed or
launched on the pilot. Earlier foreground approval remains consumed; it cannot
authorize this mode or retirement of a different host. No changed binding or
phase control is authorized by this source delivery.
