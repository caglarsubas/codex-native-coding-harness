# Observation contracts

Observations are private, read-only evidence. Refresh never changes dispatch,
approval, Git history, product files or a native task. The dashboard polls saved
results; a refresh button starts one non-overlapping collection job. An optional
one-minute local monitor runs only while the page is visible; it is off by default
and never polls GitHub automatically. No model
call, API key, paid service or transcript upload is involved.

## Configure and repeat

Use `config/observations.example.json` as the shape for the selected ledger's
`observations.json`, supplying explicit local paths and registered repository IDs.
Keep artifact roots narrow: deliverable directories, not a home or secrets folder.
The file, reports and database stay private and Git-ignored.

```sh
python3 -m orchestrator.cli observe
python3 -m orchestrator.cli observe --remote
python3 -m orchestrator.cli export
python3 -m orchestrator.cli artifact-add /absolute/path/to/report.md --repo example-project --session TASK_ID
```

For another portfolio pass `--state` before the command. Add `--created-at` only
with a trustworthy creation timestamp, never inferred modification time. Explicit
registration can preserve an artifact before any task links it. The dashboard
reads every captured version or downloads its exact bytes. HTML/SVG is inert
source; Office/PDF/image files download for native viewing. Preview is limited to
500,000 characters; snapshots to 8 MiB each.

## Usage

The importer reads `sessions` and `archived_sessions` JSONL files incrementally.
Only tasks whose initial cwd matches a configured repository or its registered
Git worktree are imported. Unrelated conversation bodies are skipped. Retained
data consists of counters, timestamps, task IDs, model/effort, message hashes/counts
and allowlisted artifact references, not prompts or responses. Original logs are
never modified. Versioned derived indexes can be rebuilt after importer updates.

- Archives and continuation segments are deduplicated. Repeated cumulative
  counters contribute no new tokens. Continuations share their original task ID.
- Per-turn context determines model/effort; setting changes do not relabel history.
- A known fork excludes inherited records at or before the child header time and
  ignores copied parent headers. Forks without metadata cannot be reliably detected.
- Missing prefixes, resets and ambiguous deltas contribute only the last reported
  request, not the inherited lifetime counter, and produce diagnostics.
- Cached input is part of input; reasoning is part of output. Neither is added
  twice. Cache rate is weighted cached/input, not an average of task rates.
- Message counts are logged user/assistant records, not semantic turns. Agent
  tasks are identified only when metadata says so.
- Attribution follows task cwd, not each edited file. A brain doing work elsewhere
  is not automatically split by inferred authorship. Daily dates use UTC.

Counts describe retained local observations, not complete account/cloud history,
quota, invoices or causal model efficiency. Protocol fields were checked against
the [OpenAI Codex source](https://github.com/openai/codex/blob/main/codex-rs/protocol/src/protocol.rs).
Malformed or unsupported records are excluded with diagnostics. Billing is not
inferred. For cache fraction c and cached/uncached input price ratio r, input-only
savings are c × (1 − r); output and subscription charges are separate.

## Git and code

Worktree status, branch SHAs and upstream divergence are local observations.
Cached tracking refs are not freshly contacted remotes. `--remote` uses fixed
GitHub REST GETs through existing gh authentication. It never fetches, pushes or
merges. Up to 100 recently updated PRs and 100 remote branches are read; absence
from those pages is not proof of absence. Local refresh preserves prior remote
observations with their own timestamp. Failures remain unavailable.

Remote tip equality is a SHA comparison, not push authorship. PR open/closed/merged,
head SHA and merge SHA are separate. CI, deployment and runtime acceptance still
belong to independently verified worker evidence. Code counts retain v1 methodology:
exact configured Git ref, tracked UTF-8 physical lines and Unicode characters,
never dirty-worktree LOC or test coverage.

## Artifacts and plans

Assistant Markdown links are discovery evidence, not proof of creation, attachment,
publication or historical contents. Only bounded regular files beneath explicit
roots are captured; symlinks, oversized and missing files are not followed. Each
changed capture is a new immutable byte version, including reversion to older bytes.
Additional task references do not manufacture another byte version.

Order uses supplied creation date, otherwise earliest retained reference or first
observation. Capture timestamps are separate. Overwritten bytes cannot be recovered
by this importer. Native attachments without local references and unlinked artifacts
require explicit registration. Snapshot content lives in the private SQLite database
and is never served by filesystem path.

Roadmaps are configured Markdown paths read at exact Git revisions. Only actual
checkboxes outside fenced code blocks are counted. Documents without checkboxes
remain readable, not synthesized checklists. A checkbox is a recorded author claim,
not approval, tests or acceptance. Versions remain in the artifact library. No
observation changes the source plan.

For status-table plans, the first Markdown table with a Status column is displayed
verbatim, without combining historical checkpoint tables or inferring checkmarks.
