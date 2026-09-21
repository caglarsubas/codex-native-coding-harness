# WSP-03D — inspect saved phase checkpoints

Source baseline: PR #48, `be66adadeac0952c0cc44fcf019a194f222215e0`.
This bounded increment advances completion-plan milestones 5/6; it does not
complete either milestone or enable autonomous Play.

## Scope and acceptance

- [x] Authenticated, explicit, workspace-scoped read-only report history and
  inspection. No report creation, controller lease, native calls, scans, shared
  accounting initialization, approvals or release on GET or polling.
- [x] Creation-ordered versions, original checkpoint/report times, retained
  proof integrity, current/superseded/changed/unavailable context, and explicit
  missing/invalid evidence. Refuse oversized history rather than truncate it.
- [x] Dashboard checkpoint view, Overview entry point and artifact navigation;
  keep recorded task results, evidence axes, phase acceptance and measured usage
  distinct. Discard asynchronous responses after workspace changes.
- [x] Assistant receives bounded cached inspection metadata, freshness and a
  scoped allowlisted view link, never report notes, proof bodies or local paths.
  Asking a question cannot inspect, prepare, approve or release a checkpoint.
- [x] Local Python/JavaScript regressions and disposable browser QA; preserve
  live state and the no-extra-GitHub-Actions-billing boundary.

## Explicit exclusions

Public checkpoint review/release, Play, new-generation correction and rereview,
live admission/native evidence, real usage collection, onboarding rollout,
runtime restart, skill installation, autonomous merge and paid CI are separate
work. An intact saved report is neither a fresh native observation nor permission
to continue. Existing owner release checks remain unchanged.

## Owner workflow after a separate installation

Select a workspace, then open **Phase checkpoints** from its navigation or
Overview. **Load report history** reads metadata only. Reports appear oldest
first by original save time, with version numbers belonging to their run (the
version counter restarts for each run). **Inspect report** validates its hashes,
receipts, report artifact and retained source proof bytes in one read transaction.
It then compares the report with the exact local parked context if available.

The outcome table keeps unfinished tasks, accepted worker results, changes
required, unreviewed workers, other retained workers and pending controls separate.
Expand the disclosures for scope/checkpoint/note, configured limits, individual
result axes/criteria and the exact JSON. **Read retained report artifact** opens
the corresponding immutable version in the existing artifact reader. Text is
rendered inertly, not interpreted as Markdown, commands or links.

An empty history does not mean success or native inactivity. Ask the designated
brain to prepare a report only after its exact parked-run prerequisites exist.
Corrupt or missing evidence shows unavailable, without displaying old results as
current proof. Earlier versions remain inspectable but cannot replace the latest
release candidate. A changed workspace needs a new report; an unavailable current
parked context is not guessed to be idle. None of these states grants a release.

## Read and cache contract

- Authenticated `GET /api/workspaces/{id}/phase-checkpoints` returns bounded
  metadata, not proof verification. At most 128 report records are considered;
  larger history refuses as a whole, with the count and no partial list. Invalid
  metadata is counted, never assigned fabricated creation times or artifact links.
- The same route with exactly one `reportHash` and one `artifactId` performs an
  explicit historical inspection. There is no POST route, prepare button, owner
  review/release route, approval action or native notification.
- Reads use the selected ledger only and do not mutate its logical contents,
  initialize shared accounting, observe filesystem/Git/native state or call an LLM.
  Per-workspace locks reject overlapping expensive inspections.
- General state polling contains only the server's latest cached inspection
  summary. The assistant sees counts/status/times, not report notes, source proof
  bodies, local paths, native IDs or report hashes. Its `phaseCheckpoints` link is
  allowlisted and scoped by the browser; no new assistant action is available.
- Cached inspections are always historical, flagged after a workspace revision
  change, a clock reversal or 60 seconds. This TTL does not claim current native
  truth. Inspection time never replaces checkpoint/report/result observation time.
- Browser caches are per workspace and per tab; request-generation guards drop
  late responses after switching away, including switching back to the same ID.
  Reloading the page clears its cached display; it never triggers an inspection.

## Verification

Disposable browser checks covered two saved versions, latest report details,
task disclosures, the exact version's artifact reader and switching to an empty
second workspace without inheriting reports. The narrow three-pane layout keeps
version actions visible without horizontal scrolling; no browser console errors
were observed. Inference and native notification were disabled in the fixture.
The fixture is `PYTHONPATH=.:tests python3 tests/manual_checkpoint_fixture.py`.
No live dashboard, token, private portfolio or schedule was used.

Final local verification: **1,300 Python tests passed** in 184.859 seconds;
all **nine JavaScript UI suites**, all web-script syntax checks, Python module
compilation and `git diff --check` passed. The new regressions cover immutable
ordering (including equal-time saves), authenticated workspace isolation, read
purity, corrupt/missing artifacts and receipts, superseded/changed context,
bounded history, historical redacted assistant context and late browser responses.
Read-only GitHub checks found **zero Actions workflows and zero runs**. No hosted
CI, live native worker, inference service or runtime rollout was used.
