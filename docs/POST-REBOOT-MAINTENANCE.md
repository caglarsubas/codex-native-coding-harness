# Forward-only post-reboot maintenance epoch

`post_reboot_maintenance_epoch_v2` is a separate operator-only, read-only
maintenance migration. It recognizes an unchanged admitted ledger across a
macOS volume device-number change, retaining an exact new certificate outside
the old records. It is **not** an identity override for ordinary operation.

The registry, project/native bindings, database rows, original snapshots,
requests, consumed claims, old pins, usage/gaps, clocks and startup fences remain
unchanged. Normal registry/effect routes continue to refuse their old device
pins. Only this explicit maintenance reader can use the certificate. It never
reconstructs the queued readiness receipt, changes its outcome or manufactures
native/historical cleanup evidence.

## Exact supported lineage

Require an empty, paused, unowned schema-7 standard target and its one original
queued readiness request with the exact positive authentication-check deadline
diagnostic: neither resume nor turn start was attempted. Require the canonical
separately approved new preparation to have completed with its positive receipt,
closed original observer, unchanged mailbox and both permanent startup markers.
The completed preparation and original readiness are different requests.

The evidence anchor is a complete **pre-reboot** PR-190 worker-readiness
observation, with its original intent/report/seal. It is an immutable historical
reference, never current readiness. An arbitrary evidence file, owner cleanup
assertion, newer capture, incomplete observation or another source version is
not supported. Read no historical Python as executable code. Its full bytes and
file epochs are hashed against the exact qualified PR-189/PR-187 sources.

The fixed macOS boot-session UUID identifies the reviewed boot, with repeated
reads bracketing the inspection. The original reviewed boot timestamp remains
the upper bound for the old observation and every retained record's change time.
`kern.boottime` is calendar-adjustable, not immutable boot identity. Revalidation
uses the earlier of that original cutoff and the current reported boot time;
it never rounds, applies a tolerance, refreshes the cutoff or ignores a newer
boot with the same device number. Missing/malformed/changing boot-session identity
refuses. Across all registered databases require identical SQL
schema, complete logical contents and inode; exactly one old device maps to one
new current device. Historical private-file comparisons admit only that device
component: hash, inode, size, owner, mode/link count and applicable original
change times stay pinned. Historical source epoch hashes are reconstructed only
for this closed comparison and retained alongside the real current epoch hash.
No generic recursive rewriting or live-pin normalization is installed.

Unknown delivery, another command/turn, changed database/brain/repository,
partial/Stop/permission records, missing claims, changed source or timestamps,
another device transition and an existing old socket refuse. The retired socket
is never connected, recreated, unlinked or adopted. Process absence and device
continuity prove no terminal safety.

## Prepare, back up, confirm, inspect

Use a clean qualified source and explicitly select the exact target:

```text
python3 -B -m orchestrator.post_reboot_maintenance prepare PRIVATE_PLATFORM WORKSPACE ORIGINAL_WORKER_EVIDENCE_DIRECTORY
python3 -B -m orchestrator.post_reboot_maintenance backup PRIVATE_REQUEST_JSON NEW_DISJOINT_PRIVATE_BACKUP --writers-stopped
python3 -B -m orchestrator.post_reboot_maintenance confirm PRIVATE_REQUEST_JSON PRIVATE_BACKUP --writers-stopped --confirm-hash EXACT_NEW_REVIEW_HASH
python3 -B -m orchestrator.post_reboot_maintenance status PRIVATE_REQUEST_JSON
```

Retain the preview's `request` as the private request JSON. The exact new
owner-reviewed scope hash has no reading-time countdown; changed scope
invalidates it. Generic assent, source/merge permission and prior startup or
host approvals do not confirm this control. Preparation reads only local SQL,
private files, Git metadata and fixed OS boot metadata. It exports no native
schemas, opens no native client and writes no operational state.

Legacy version-1 previews/approvals/certificates are never converted or repaired
in place. Preserve them verbatim. This version requires a separate exact review
with its boot-session pin. The permanent canonical owner and target fence are
unchanged across versions: an existing completed or partial claim still prohibits
another attempt. Source installation cannot apply either review.

Independently stop older writers before confirmation. Back up all registered
databases as verified self-contained SQLite copies, plus the entire explicitly
pinned historical input inventory, into a new private disjoint directory. These
are fresh preservation copies, never substituted for the pre-reboot reference.
Aliases, hard links, unsafe paths, credentials, omitted inputs, corrupt copies
and changed originals refuse.

Confirmation locks locally, verifies the exact unchanged context and backup,
then commits one canonical intent and a matching target-side maintenance claim
before the completion certificate. The canonical owner uses the original startup
hash and ledger inode, not the new device, request ID or source version. A
partial or failed write is permanently consumed: preserve it as unknown; never
retry, move, delete, adopt or rearm it. A second reboot needs a separate future
contract, not a successor directory. The pre-existing startup write fence is
never removed or relaxed.

Status is local read-only inspection and never confirms a control, reconnects a
host, renews the historical native observation time or repairs partial output.
Successful status means only `maintenanceIdentityRecognized`, with normal writes
blocked. Full context and backups are revalidated; stale native evidence does
not become fresh.

## Remaining runtime boundary

This certificate restores only the **explicit maintenance inspection path**.
It deliberately does not make the ordinary dashboard/execution identity check
accept the old registry pin. A live dashboard cutover, new host process/socket,
binding review and any permitted load still need their separate supported
contracts. It grants no launcher, subscription, thread load, turn, permission
response, cancellation, readiness/Play/recovery replay, usage reset, ownership
release, worker-phase activation or pilot acceptance. The current no-reload and
unchanged-binding limits remain effective; current and historical policy/terminal
safety stay unknown.

Source delivery stops at an open PR for manual merge. It installs/applies no
live migration or host repair. Disposable qualification uses real temporary
SQLite/Git lineage and explicitly simulated boot/device metadata, with synthetic
predecessor native observations. There is no OS reboot, live native connection,
download, provider request, GitHub Actions or paid CI. Run complete local Python
discovery, JavaScript suites, syntax checks and source/diff verification.
