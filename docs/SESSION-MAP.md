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
- Selecting a node opens details below. Selecting a line or its text label opens
  the responsibility view for that task. Selection never sends a control.
- Overview describes responsibility and timestamped activity. Conversation shows
  saved project-brain messages inline, or links to the confirmed worker in Codex.
  Evidence exposes the existing retained scope, results and linked artifacts.
  Metadata labels requested model settings and partial token observations.
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

Animation requires a fresh native activity observation, with an age below two
minutes. A saved `running` lifecycle, an old observation, future timestamp, pending
identity or disconnected dashboard cannot animate as working. Timestamps are
never refreshed by the graph. A disconnected view retains the last snapshot with
an explicit notice.

## Interaction and accessibility

Nodes, edges and filters are keyboard accessible. Tabs support Left/Right and
Home/End. List view provides the same task selection; narrow project panes use a
vertical arrangement without horizontal page overflow. Status text accompanies
color, and reduced-motion preferences disable pulse/flow animation. Polling
retains selection, restores graph control focus and preserves conversation drafts.
Graph preferences are project-scoped, transient and cleared on sign-out.

## Local preview and verification

`python3 tests/manual_session_map_fixture.py` serves an explicitly synthetic,
isolated two-project preview on loopback port 8794. It creates temporary ledgers,
has no inference credentials or native notifier, and never touches live state.
The preview includes active, blocked, completed, pending and archived examples,
plus an empty project. Its task IDs are intentionally synthetic.

The unit suite covers freshness expiry, future timestamps, pending identities,
completion versus archival, task deduplication, filtering and inert native links.
Browser verification covers node/edge selection, arrow-key tabs, search/history,
inline conversation, retained unsent drafts, project switching, empty state,
light/dark appearance and the 390px mobile layout. Source delivery does not restart
or install the live dashboard or change any brain, schedule or authority.
