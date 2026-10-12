# Read-only historical cleanup collector

Source implementation and explicit native read qualification. Not installation,
executed-effect disposition, terminal closeout, a safe checkpoint or pilot acceptance.

The operator no longer needs a private one-off audit script to identify which
cleanup evidence the current source can provide. `historical-cleanup-plan` pins
one existing empty stopping standard run and its original Play/Pause/consumed
recovery; `historical-cleanup-collect` reads the exact bound history and current
terminal inventory. Neither command changes the ledger or sends a brain message.

## Operator interface

Use only the already reviewed current binding and, for retired request hosts,
the separately reviewed history-only chain described in
[historical effect closeout](HISTORICAL-EFFECT-CLOSEOUT.md). There is no discovery,
old-endpoint fallback, launch or rebind. Both native project identities, checkout,
brain, workspace, ledger identity/revision, native policy and original command
hashes stay pinned. Retired-host launch artifacts and fixed PID absence are
checked before and after collection; neither proves child cleanup.

```sh
python3 -m orchestrator.cli --platform PRIVATE_REGISTRY --workspace EXACT_WORKSPACE historical-cleanup-plan CURRENT_BINDING --historical-host-chain REVIEWED_CHAIN
python3 -m orchestrator.cli --platform PRIVATE_REGISTRY --workspace EXACT_WORKSPACE historical-cleanup-collect CURRENT_BINDING PRIVATE_PLAN --historical-host-chain REVIEWED_CHAIN
```

The optional chain is omitted only for unchanged original-host inspection already
permitted by the historical contract. Save the plan as an owner-only canonical
regular file. The closed request has exactly `version`, `workspaceId`, `brainId`,
`runId`, `expectedRevision`, `contextHash`, `runHash`, `originalCommandHashes`,
`bindingHash`, `scopeHash`, `hostChainHash`. It contains no target overrides,
native methods, commands, attestation flags or confirmation. Plan reads no native
endpoint. Its hashes are read-scope bindings, not signed execution authority;
there is no approval countdown or automatic collection on polling/Help.

Collect returns bounded JSON for private operator retention outside the ledger.
Do not commit it or publish its native IDs. Saving output is not retaining a brain
receipt or confirming either historical owner control. There is deliberately no
HTTP, assistant, dispatcher, scheduler, accounting or settlement consumer for this
new report. A later explicit collection is another read, not a replayed native
effect; saved reports never renew their original observation times.

## Actual collection and qualification

`CleanupProxy` permits only identity-checked initialization, exact `project/read`,
metadata-only `thread/read`, latest-turn metadata, the existing complete bounded
persisted turn/item range and cursor-linked current `backgroundTerminals/list`.
No load/resume, start/interrupt, command, process control, permission response,
subscribe/reconnect or cleanup method is available. The proxy process is the only
owned child the existing read transport disposes of; it never kills native work.

Collection brackets two independently stable history/call-inventory reads with
repeated exact project/brain/latest-turn/current-terminal observations. It requires
the exact latest completed recovery and original Pause inside the Play-to-recovery
range. Membership, current activity, terminal pages, run, original requests,
usage/gaps, expiry, controller/runner and host provenance must remain unchanged.
Drift refuses the report. Strict Harness and nonempty/unknown ownership refuse
before a native call. No controller acquisition, SQLite transition or schema
upgrade is performed.

The current terminal inventory is collected only for a loaded-idle brain. An
unloaded brain is `unknown`, with `rows: null`; no query/load is attempted.
Unsupported native reads retain their sanitized reason/reserved RPC code, never
the error body. Missing cursors, repeated/empty intermediate pages, duplicate
handles/items, partial failures and bounds refuse instead of truncating or
discarding already observed identities. The complete current inventory is read
twice; running identities remain visible and are never terminated or settled.

Each historical effect retains its exact turn/item hash, native handle hash,
separate optional OS PID hash, named native field types, current tracker linkage
and explicit missing historical requirements. Command bodies, outputs, cwd,
transcripts and raw error text are never retained. An item/handle disagreement
refuses correlation: process handles and reused PIDs cannot establish continuity.
The existing missing-call/result, typed-link, completion-time, compaction and
inventory gaps are copied without alteration, not replaced by cleanup diagnostics.

Qualification names the fixed supported source:
`documented_app_server_v2_metadata`. Its documented terminal method lists running
terminals for a loaded thread; it does not provide a retrospective lifecycle or
descendant-cleanup contract. See the
[official App Server reference](https://learn.chatgpt.com/docs/app-server).
Therefore this source's `completeProcessLifecycleSource` and
`completeDescendantCleanupSource` remain false, even if an item includes an
OS PID, extra birth/descendant fields, a successful exit code or caller/model
"clean" flags. Unknown future fields do not silently enlarge a qualified protocol.
Hash agreement is consistency, not runtime attestation.

`historicalCleanup` is `unqualified` for executed/unsupported/unresolved effects.
Only an independently correlated complete historical non-execution report can
say `not_required_non_execution`; even then this collector authorizes no closeout.
The existing separately signed non-execution closeout remains unchanged.
An empty replacement-host tracker, absent old host, ended turn or command exit
never proves old cleanup. `executedEffectDispositionAvailable` stays false.

Bounds remain 64 turns, 512 items/effects, the existing exact configured rollout
file limits and native response/deadline limits. Current terminals permit up to
8 pages/512 rows per pass; total source observations permit 128 reads. Existing
historical reports must still fit 20 KiB. This separate private operator report
must fit 64 KiB, or refuse whole; no signed HTTP limit is increased. Bounds are
ceilings, not promises that every combination fits.

## Qualification result and remaining boundary

The explicit read-only qualification on 2026-10-12 successfully collected the
unchanged pilot's persisted range: six executed commands and one unsupported
effect. All 34 historical requirements stayed intact. The current brain was
`notLoaded`, so terminal coverage remained unknown; historical cleanup remained
unqualified. Independent before/after checks verified unchanged database logical
hashes, original commands, run, usage/gaps/expiry and reviewed process identity.
Recorded usage remained 719,893. Native writes and ledger writes were zero.
Private evidence and native IDs were not committed. This qualifies collection
behavior on that runtime, not the missing cleanup evidence or the pilot.

The final CLI qualified at 14:10 local time. The machine rebooted at 14:15;
subsequent explicit checks found both reviewed foreground processes absent and
no dashboard listener. Repeated ledger reads and logical database hashes still
matched the original records; inodes remained identical but device numbers
changed. Those are stale live bindings, not permission to repair them silently.
The retained pre-reboot qualification is historical evidence, not a claim of
current connectivity. No host was relaunched or binding rewritten.

Local verification passed 2,355 Python tests (one skipped), including 27 collector
tests, all 35 JavaScript suites, syntax checks for the 31 web scripts, Python
compilation and diff checks. Fixtures cover identity/provenance and metadata
drift, incomplete pagination, interrupted partial inventories, running trackers,
PID/handle confusion, private request parsing, stale usage/expiry/ownership,
multi-host continuity and refusal of native mutation methods. No GitHub Actions
or paid service was added or run. These checks do not establish live acceptance.

To qualify executed cleanup, a separately supported source must independently
retain effect-to-process birth/epoch linkage, complete from-first-effect lifecycle
coverage and scoped descendant/terminal cleanup for the original effects.
A future observer cannot backfill lost historical facts. No owner-uploaded
attestation, private Codex database/API, vendor patch, fresh command or second
recovery can substitute. Such a source and any executed-effect disposition need
their own implementation and independent qualification. Cooperative registered-task
observations remain distinct from unrelated legacy whole-system-tree requirements.

Source merge, installation and live authority remain separate. Do not restart
the running dashboard or install this code during source delivery. No Play or
recovery replay, usage reset, safe-status inference, clock extension, brain receipt,
ownership release or pilot acceptance follows this report.
