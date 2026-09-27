# Brain replies, next steps and interval accounting

## Reproduced causes

- Submission banners retained notification text after the exact command had a
  completed receipt and saved reply. The main header displayed only the old run.
- Short excerpts could omit the reply's final next action. In the assistant a
  retained brain reply was also labelled as an advisory AI explanation.
- A successor draft used the previous run's checkpoint fallback rather than its
  own stopping point. Its previous usage gap disappeared from immediate guidance.
- Phase collection validated the entire brain log's per-call breakdown before
  filtering the interval. An invalid historical breakdown poisoned every later
  phase even when its cumulative baseline and interval counters were valid.

## Implementation boundaries

Request-bound notices now follow retained receipts; the current plan, original
reply time, next signed preview and remaining measurement requirement are shown
together. Full replies remain inert, unchanged and collapsible. No native text is
sent to inference or interpreted as approval. Legacy received-without-reply and
uncertain delivery stay incomplete. No notification is resent.

Accounting validates cumulative counters independently of per-call breakdowns.
A validated pre-phase cumulative sample can serve as the baseline even when its
last-call breakdown is invalid. The measured interval still requires valid
breakdowns; invalid cumulative baseline records, missing prefixes, unplaceable
records and in-interval regressions remain gaps. Samples after the cutoff do not
alter historical coverage. Valid totals are retained even alongside an invalid
breakdown, and per-field high water prevents counter regressions from refunding
known consumption. Worker full-lifetime prefix checks remain mandatory.

This changes collection behavior, not historical evidence: it does not refresh or
rewrite either terminal run, waive a gap, reset usage, review Mission v11, start
Play, change the designated brain or relax strict Harness requirements.

## Read-only live diagnostic

Compared the retained stopped phase's exact measurement interval with the fixed
collector. Both returned **962,157 tokens**. The old retained report still has
`invalid_token_record`; the new read-only calculation has no interval gaps because
the malformed per-call records precede the phase. The complete retained run hash
was unchanged before/after. A later cutoff at the checkpoint includes additional
usage and is not presented as an identical measurement interval.

This is diagnostic evidence, not a newly retained measurement or a guarantee that
future measurements will be complete. Every future effect still needs the normal
fresh, phase-scoped measurement.

## Reproducible verification

- `tests/test_brain_memory.py`: malformed breakdown before/inside/after the phase,
  invalid cumulative baseline, known-total retention, regression high water,
  worker prefixes, duplicate observations, closeout and concurrent refresh.
- `tests/test_progress_ui.js`: exact-request receipt transitions, old queued text,
  blocked Play, unrelated errors, missing records and project isolation.
- Journey, assistant-workflow and summary suites: successor checkpoint/version,
  prior evidence gap, visible next action, inert full text and distinct brain labels.
- `python3 tests/manual_progress_fixture.py --port 8774`: disposable rendered
  message/receipt/reply rehearsal. Type `reply` in its terminal after confirming
  the fixture message; type `quit` to remove its temporary repositories/ledger.
  No native notifier, inference service or real worker is used.

## Local verification — 2026-09-27

- Full Python discovery: 1,777 tests, successful, one optional pinned Graphify
  integration skipped because no reviewed executable is configured (433.622s).
- All JavaScript suites, browser-script syntax, Python compilation and whitespace
  checks passed locally.
- Rendered disposable rehearsal: confirmed one brain message, explicitly retained
  its synthetic reply, observed polling replace pending text with Brain replied,
  followed the inline next action to its exact review preview, and reloaded to
  recover the retained reply/current next step. No real task or model call.
- Live selected-project inspection: Mission v11 remains draft, previous run remains
  blocked, no registered tasks or pending receipts/controller. The assistant opens
  its signed review preview without confirmation or starting Play. The new header,
  reply excerpts and actual successor checkpoint are rendered in Roadmap & Play.

No GitHub Actions or paid services were used; the read-only workflow inventory was
empty. Absent CI is not passing CI. Merge remains an owner decision. No live phase
was reviewed, replayed, resumed or started as part of this repair.
