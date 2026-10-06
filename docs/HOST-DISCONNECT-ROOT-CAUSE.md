# Native host disconnection: lifecycle and observation

## Observed trigger, not a phase TTL

In the disposable pilot on October 6, 2026, desktop update metadata recorded
installation starting at **22:25:54 Asia/Shanghai**, shortly after the saved Play
request started. Window teardown followed and the replacement desktop process
started at **22:26:00**. The previous reviewed host process was absent; the CLI
proxy used by the dashboard remained alive. The native turn was later observed
interrupted, without a retained ledger receipt or confirmed effect outcome.
No host exit code or signal was recorded, so these observations do not prove a
particular kill signal or explain every historical disconnection.

The exec launch avoids the unsigned supervisor ancestry that previously failed
native trust checks, but still depends on the desktop-owned foreground execution
session and native-tool connection. It is not an independent service. Closing,
updating or restarting Codex can invalidate that lifetime and context. A running
dashboard, retained socket path or surviving proxy is not a running native host.
Increasing preview expiry, phase duration or a read deadline cannot fix this.

## Bridge defect and source correction

The turn observer previously waited on the proxy pipe for up to six active hours.
A surviving proxy with no EOF could therefore leave `streamStatus: open` and a
saved phase appearing running after the host had disappeared. It had no bounded
way to distinguish a quiet healthy turn from a blackholed transport.

The owned observer now watches its **existing** WebSocket connection. Every
15 seconds it verifies the original executable/socket metadata epoch and sends
one control ping with a random nonce; only the corresponding pong satisfies its
10-second response deadline. Healthy quiet turns continue, including native
approval waits. There is no model-idle timeout. EOF, a close frame, endpoint
replacement, failed write or missing pong ends that observer as connection lost.
These deadlines measure transport responsiveness, not proof the host process
died; a stalled host or suspended client can also leave the outcome unknown.

This is not a reconnect loop or native RPC: it sends no initialize, thread/read,
resume, turn/start, permission response or instruction. Read-only clients do not
start this heartbeat. Frame, byte, write and overall subscription bounds remain.
Pending approvals keep their original one-shot decision claim; a lost connection
cannot produce a second response. No native error body or transcript is retained.

The command keeps its start acknowledgment, original request, receipt and owned
effects. A separate `nativeConnectionLoss` records a bounded reason and original
observation time; the turn outcome and inventory remain unknown. The graph,
phase journey and conversation show **Connection lost · request unresolved**
instead of suggesting work is verified active. Pause retains priority. Retained
brain replies still take precedence in conversation history.

The saved-request action now opens the real control-request history in the same
inspector. Previously the standard workspace linked to a section omitted from
Advanced controls. Request cards preserve their IDs, original timestamps and
receipt/result alongside connection status, and reflow without a narrow table.

## Remaining native lifetime boundary

This source correction detects and explains the loss; it does not make a
desktop-owned host survive desktop replacement. Durable survival requires a
supported app-owned host/runtime lifecycle that preserves native trust and
explicitly reconciles its connection identity. Detaching the process, inheriting
stale pipe values, modifying vendor signatures or silently pinning a replacement
endpoint are not supported substitutes. There is no automatic restart or replay.

Before a deliberate desktop update, reach a safe checkpoint and preserve all
ownership and receipts. After loss, independently inspect the original request
and effects, repair the host through its existing reviewed launch/binding
workflow, and reconcile that same request. A handshake is not native-tool,
approval, usage, inactivity or pilot qualification. Do not repeat Play just to
test connectivity.

## Verification and rollout

Disposable tests exercise quiet healthy streams, exact pongs, blackholed open
pipes, EOF, close frames, endpoint drift, concurrent approval writes and missing
receipts. Synthetic desktop/mobile rendering verifies visible progress without
touching a native project. These tests do not qualify heartbeat behavior on a
live vendor host or certify a native host across an app update.

Source, manual merge, installation and live qualification remain separate.
Quiesce older writers and back up private state before installation. No live
binding, current phase, usage, controller, worker or uncertain native request is
changed by source delivery. See [host lifetime and review recovery](HOST-LIFETIME-AND-REVIEW-RECOVERY.md).
