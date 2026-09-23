# Session map

The landing page follows one selected project: its designated brain, registered
tasks, recorded relationships, and the next attention item. It uses the existing
authenticated state snapshot; opening or filtering the graph performs no native
collection, dispatch, model call, approval or transcript import.

## Reading the page

- The project summary shows phase/dispatch state, registered task and history
  counts, and decisions requiring input.
- The brain anchors a stable graph. Four task nodes appear per page; search and
  All/Open/Attention/History filters make larger inventories navigable. The brain
  remains visible when a search has no results.
- Zoom in/out, reset to 100%, or Fit the current page. Drag the background to pan;
  Ctrl/Command + wheel zooms around the pointer. A focused graph accepts +/−, 0,
  F and the native arrow-key scrolling. Touch users can scroll the zoomed canvas.
- Filters combine repository, commit/remote comparison, PR state, CI evidence,
  roadmap/scope ID and last recorded activity. Activity includes 24-hour, 7-day,
  30-day, older, unknown and inclusive local-calendar date ranges. Sort by recent
  or oldest activity or title; unknown dates remain last. Reset filters clears
  the search and lifecycle filter too. Matching counts cover all result pages.
- Selecting a node opens details below. Selecting a line or its text label opens
  the responsibility view for that task. Selection never sends a control.
- Overview describes responsibility and timestamped activity. Conversation shows
  saved project-brain messages inline, or links to the confirmed worker in Codex.
  Evidence exposes the existing retained scope, results and linked artifacts.
  Metadata labels requested model settings and partial token observations.
  Delivery & activity shows the exact commit, saved PR state, GitHub observation
  time, CI evidence reference, packet/phase ID and last recorded activity used
  by the filters. Nodes display compact PR and CI labels.
- The brain's Controls tab uses the existing control components and confirmation
  gates. Plan & controls → Controls & setup retains the previous full overview.
- The advisory assistant is collapsed by default for new layouts; saved pane
  preferences are preserved. Focus map makes room without changing project state.

## Meaning of the graph

Nodes come from the current cooperative run and managed-worker records. The same
confirmed native task is displayed once. Pending client IDs are never usable task
links. Closed/failed/non-created attempts remain visible in their recorded states;
completion does not imply archival, resource release, CI or acceptance of another
evidence axis. History here covers records in this snapshot, not every previous
phase or every native Codex session.

Edges mean the designated brain's recorded responsibility for a task. They do not
assert observed native parentage, complete descendants, conversation transfer or
a new delegation grant. The graph does not discover unregistered sessions.

Each node and connection label has an activity ring and text. Active rings rotate;
Idle rings remain still, Completed uses a check, and Stale/Unknown use a dashed
ring. Pending identity, interruption and disconnected states remain explicit.
The connection badge follows its task's activity; it is not evidence of messages
flowing along the edge. The selected-node/connection inspector shows the original
observation time and source explanation.

Animation requires a fresh native or scoped local task-event observation, with an age below two
minutes. A saved `running` lifecycle, an old observation, future timestamp, pending
identity or disconnected dashboard cannot animate as working. Timestamps are
never refreshed by the graph. A disconnected view retains the last snapshot with
an explicit notice. The existing explicitly configured activity reader can supply
transient worker metadata without changing saved native observations or lifecycle
records (see [Brain activity](BRAIN_ACTIVITY.md)). Newer native observations take
precedence; a failed local read cannot silently reuse an older active signal.

## Filter evidence boundaries

Commit data comes from the task or an exactly associated saved branch/worktree
in the same repository. PR observations must match the task's explicit PR URL or
exact result/head SHA within that repository; multiple matches remain unknown.
The graph never assigns a repository's default branch or newest PR to every task.
Remote tip equality and difference describe saved SHA comparisons, not who pushed
or whether every commit was published. A failed GitHub refresh does not silently
reuse an older successful observation. A local-only refresh may retain the prior
remote snapshot with its original timestamp.

CI choices are **Verified evidence**, **Failed evidence**, **Not applicable** and
**Unverified / not recorded**, based only on the task's retained `ci` axis. No
provider check list is present in this snapshot; local test results, completion,
merge or an empty list cannot imply passing CI. No GitHub queries, workflow runs,
proof reads or collection are triggered by filtering.

Roadmap/scope choices use exact packet IDs for managed workers and the recorded
run phase ID for cooperative tasks. They are not inferred from task titles or
roadmap prose. Missing IDs remain explicitly selectable. Last activity is the
latest recorded creation, issuance, native observation, update or completion
timestamp, not the latest dashboard poll, GitHub refresh or snapshot read. Invalid
and future timestamps cannot make a task appear recently active.

## Interaction and accessibility

Nodes, edges and filters are keyboard accessible. Tabs support Left/Right and
Home/End. List view provides the same task selection; narrow project panes fit the
graph within the viewport and offer a readable vertical list. Zoomed content
scrolls within the graph without horizontal page overflow. Status text accompanies
color, and reduced-motion preferences disable ring/pulse/flow animation. Polling
retains selection, restores graph control focus and preserves conversation drafts.
Graph preferences are project-scoped, transient and cleared on sign-out.
Zoom, pan and filters survive polling. If a filter or result page hides the selected
task, an explicit notice explains why its details remain below.

## Local preview and verification

`python3 tests/manual_session_map_fixture.py` serves an explicitly synthetic,
isolated two-project preview on loopback port 8794. It creates temporary ledgers,
has no inference credentials or native notifier, and never touches live state.
The preview includes active, idle, stale, blocked, completed, pending and archived examples,
plus an empty project, PR/CI examples and older activity. Its task IDs are
intentionally synthetic. `--port 8795` allows an isolated worktree preview alongside
an existing preview.

The unit suite covers freshness expiry, future timestamps, pending identities,
completion versus archival, task deduplication, filtering and inert native links.
It also covers combined delivery filters, exact repository/PR association, failed
remote refreshes, unknown CI, inclusive local date boundaries, sorting and zoom
limits.
Browser verification covers node/edge selection, arrow-key tabs, search/history,
inline conversation, retained unsent drafts, project switching, empty state,
light/dark appearance and the 390px mobile layout. Source delivery does not restart
or install the live dashboard or change any brain, schedule or authority.
