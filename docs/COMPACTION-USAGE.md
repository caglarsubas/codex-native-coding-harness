# Compaction-aware cooperative usage

## Cause and repair

Recent native runtimes retain a `token_usage_record` for each response, including
compaction. Its `thread_token_usage` is the cumulative counter; `usage` is the
response's increment. The older `event_msg/token_count` stream can instead keep
its pre-compaction cumulative counter and publish an estimated context size in
`last_token_usage.total_tokens`, with zero input/output breakdown. Treating that
estimate as another model call produces a false gap, while simply ignoring it
would omit the separately recorded compaction consumption.

The cooperative collector now selects the exact-session response journal when
present. It checks response/session/thread/turn identities, valid token vectors,
per-response cumulative continuity, turn continuity and immutable response IDs.
It charges compaction from that journal exactly once. A matching `compacted`
marker's numeric record reconciles the old display counter and bounded context
estimate; neither adjacency nor an unchanged total is sufficient. History and
message text in the compaction marker are not retained or returned.

Missing prefixes/baselines, conflicting responses, invalid counters, unpaired
display samples, unproven compaction and regressions remain explicit gaps. A bad
new record cannot fall back to an older display counter. Duplicate archived
records retain their original sample time. Known cumulative consumption and
persisted high-water amounts cannot be refunded by missing or regressed samples.
Older logs without the new journal retain the existing collector and fences.

This concerns **registered-session cooperative telemetry only**. It does not
qualify strict Harness usage, complete descendants, OS cleanup, subscription
billing or a hard provider cap. Cached input remains included in input; reasoning
remains included in output; reported cache writes are not added a second time.
The separate portfolio/model-attribution importer is unchanged.

## Operator sequence

1. Keep the affected phase paused. Read-only comparison may calculate an exact
   historical interval but must not rewrite its saved report or sample time.
2. Deliver and merge the source separately. Before installing, quiesce older
   writers and back up private state. Source/tests alone install nothing.
3. After compatible installation, explicitly refresh the exact run's usage using
   the existing control. Its new receipt retains the corrected cumulative amount;
   original reports, controls, checkpoints and consumed usage remain historical.
4. Inspect remaining scope, review, duration, allowance, identity and evidence
   gates. A healthy measurement does not Resume: only the separately confirmed
   existing same-phase Resume may do so. Do not repeat Play or a native effect.

## Verification

`tests/test_token_records.py` uses synthetic records for compaction charging,
both counter streams, duplicate archives, unchanged observation times, missing
responses, conflicting IDs, foreign sessions, malformed vectors, invalid turn
continuity, baseline/prefix requirements, cutoff isolation, repeated compaction,
nonadditive cache-write subsets and paused refresh/replay/history preservation.
Existing legacy collector tests remain unchanged. No native task, log mutation,
private transcript, runtime download, Actions workflow or paid service is used.

Final local source verification on 2026-10-03:

- 1,971 Python tests: 1,970 passed; the optional Graphify executable test skipped.
- All 30 JavaScript test files, JavaScript syntax, Python compilation and diff
  whitespace checks passed. The 47 focused accounting/recovery tests passed.
- A read-only comparison at the saved pilot's original sample cutoff accounted
  for the separately recorded compaction increment with no interval gap. The
  ledger and platform logical database hashes were unchanged; the saved gapped
  report, paused run, released controller and zero-worker state were preserved.

These results qualify source accounting, not installation, Resume, native
approval handling or pilot completion. No rendered UI change is claimed.

The official [app-server documentation](https://learn.chatgpt.com/docs/app-server)
documents thread usage updates and the separate context-compaction lifecycle;
it does not specify this local rollout accounting format. The format diagnosis
here is based on local numeric records, not a claim about provider billing.
