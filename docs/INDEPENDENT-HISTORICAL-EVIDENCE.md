# Independent original-effect capture and correlation

Source implementation, not a live installation, executed-effect cleanup attestor,
terminal closeout or pilot acceptance. It changes no original Play/recovery, usage,
expiry, host binding or safe-status requirement.

## What is independent

The existing owned notification observer can retain a second, hash-only item record
from the native event stream, independently of later persisted-history and rollout
reads. `nativeEffectCapture` is anchored in the **original sending command** before
`turn/start`. It uses the same already owner-reviewed connection; it does not add a
connection, subscription, RPC, scheduler, native permission response or effect.
Only future fully retained `owned_observer_v1` standard Play/Pause/Resume and the
existing narrowly authorized Pause recoveries use this capture. Legacy sends
without that original host handoff stay unchanged and have no capture. Their
original authority and one-shot guards remain.

`effect_capture.begin` refuses an accepted old request, changed run/binding/brain,
unknown protocol and an existing file or anchor. There is no CLI/HTTP method for
creating, backfilling, replacing, resealing or migrating a historical capture.
The importer has no arbitrary path, supplied cleanup flag or owner attestation.
It reads only the deterministic private file anchored by that original command.

This is a separate observation vantage point, **not independent OS attestation**.
Hash agreement establishes record consistency, not developer identity or complete
process lifecycle. The supported native source does not promise that a turn stream
enumerates all ephemeral effects, descendants or background processes.

## Private original records

One exclusive owner-only JSONL file is created in the original ledger directory.
Its header pins source implementation hash, command ID, immutable request hash,
brain/run/binding and original start time. The command pins its header hash and
file inode before the turn boundary. Each projected event has a sequence number,
previous-record hash and original observation time. A seal pins the complete file
hash, final chain head, exact native turn and event count. File/directory flushes
precede use. Interrupted, changed, unsealed, unsupported-producer or oversized
records remain incomplete or refuse; they can never re-arm the notification.

Only bounded `item/started`, `item/completed` and `turn/completed` metadata from the
exact brain is captured, including events before the turn-start reply and during
an existing permission wait. Message text, command bodies, paths, arguments,
outputs, approval prompts, credentials and raw errors are dropped. Native handles
and optional OS PIDs are separately hashed; neither is process-birth proof.
Unknown item types retain a hash and `unsupported`, never a guessed result.
The observation clock never substitutes for a missing native completion time.

Maximum capture: 512 events, 2 MiB, 16 KiB per record. An overflow or write error
retains a coverage gap. It does not retry a command, reconnect the observer or
change a native permission decision. A failed seal keeps the original open anchor;
no later writer can silently repair it as complete.

## Explicit read-only operator interface

Use the already reviewed current binding and the separately reviewed history-only
retired-host chain from [historical effect closeout](HISTORICAL-EFFECT-CLOSEOUT.md).
Never connect to an old endpoint or migrate its consumed recovery.

```text
python3 -m orchestrator.cli --platform PRIVATE_REGISTRY --workspace EXACT_WORKSPACE historical-independent-plan CURRENT_BINDING --historical-host-chain REVIEWED_CHAIN
python3 -m orchestrator.cli --platform PRIVATE_REGISTRY --workspace EXACT_WORKSPACE historical-independent-collect CURRENT_BINDING PRIVATE_PLAN --historical-host-chain REVIEWED_CHAIN
```

The plan pins the existing cleanup read scope, exact original capture hashes and
source hash. It collects no native evidence and creates no capture. Store it as a
canonical private regular file. Collection repeats the existing bounded native
history/current-tracker checks and brackets them with stable original capture,
request, usage/expiry, revision, identity and host-provenance reads. There is no
controller acquisition or SQLite write.

The private operator report contains the unchanged primary collection plus
`independentEvidence`: capture availability for each original command, exact
positive item/result matches and every missing or contradictory link. A known
typed command completion must agree on turn/item ID, full item hash, status,
command/cwd hashes and exit code. Duplicate/conflicting completions, changed
start-to-completion scope, foreign turns and changed private files refuse.
Captured effects missing from persisted history stay visible, not discarded.

All primary missing-evidence requirements remain intact. A positive command
result proves neither descendant cleanup nor a permission-denial outcome. The
report's complete inventory, process lifecycle, descendant cleanup, disposition,
ownership release, execution and pilot acceptance flags stay false. Reports are
bounded to 64 KiB and are never truncated. Native IDs and records stay private.

## Existing pilot and continuation boundary

The existing pilot's original requests predate this producer. An absent anchor
returns `capture_absent_at_original_effect`; it is not a known-empty effect set.
No new observer, host restart, confirmation or another pilot turn can recreate
the missing original facts. Its six executed effects, unsupported effect and
historical cleanup requirements therefore stay fenced.

This path can corroborate original facts where an original capture actually
exists. It deliberately does **not** claim a qualified retrospective cleanup
source, remove gaps or enlarge the existing non-execution-only closeout gate.
An executed-effect disposition still needs a separately supported, independently
qualified original process-birth/epoch, from-first-effect lifecycle and scoped
descendant/terminal cleanup source. The documented running-terminal API does not
provide that contract. No private Codex database/API, vendor patch, model prose,
owner-uploaded clean assertion or replay is an alternative.

Source merge, installation and live qualification remain separate. Quiesce older
writers and back up private state before a separately authorized rollout. Never
run an older cached helper against new captures or assume a changed producer hash
is compatible. Polling/Help import nothing and confirm nothing. The installed
pilot and running dashboard are not changed by source delivery.

## Verification

Local verification on October 13, 2026 passed 2,402 Python tests (one optional
executable test skipped), including 26 new evidence tests, all 35 JavaScript
suites, 31 web script syntax checks, Python compilation and diff checks. The
53 legacy Pause/continuity tests also passed after preserving their unanchored
send contract; they do not qualify a new capture or a replay.

Explicit source-only read qualification on the already reviewed pilot host
observed all three original captures absent and retained six executed effects,
one unsupported effect and all 34 historical requirements. Terminal coverage
stayed unknown. Database logical hashes and identities, original request and
reconciliation records, usage 719,893, revision 219, expiry, installed source and
protected host configuration stayed unchanged. Native and ledger writes were
zero. This qualifies the reader's fail-closed behavior, not a live positive
capture producer, historical cleanup, installation or pilot acceptance.
