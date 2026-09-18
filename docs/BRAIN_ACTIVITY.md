# Brain activity

Overview starts with the designated brain, before operational readiness and the
executive brief. Knowledge shows the same panel plus recent activity metadata.
Workers & evidence is for implementation workers, not the brain.

The panel separates three independent signals:

- **Activity observed:** a timestamp from task events or a recorded native status.
- **Checkpoint saved:** the last completed ledger reconciliation, not a heartbeat.
- **New worker dispatch:** paused/enabled; pausing never stops an existing task.

Open brain in Codex uses the desktop task link. Browser/OS handling can vary;
Copy brain task ID is the fallback. Read latest brain artifact opens the retained
version in the library, filtered to this brain and across all repositories.
Artifacts are ordered by their existing creation/reference ordering, not guessed
from file modification times. Full messages remain in Codex.

## Data source and limits

The existing private `observations.json` must explicitly configure `codexHome`.
Authenticated dashboard polling reads only matching brain rollout filenames in
`sessions` and `archived_sessions`. The session header must confirm the exact
brain ID and a working directory beneath a configured repository path before
the tail is read. No other task bodies, private app databases or native APIs are
used. This best-effort adapter is not a supported streaming API contract; unknown
formats remain unknown. Remote-only tasks need native observations instead.

Each file read is bounded to a 64 KiB header and a 256 KiB tail (plus at most one
256 KiB partial-record discard). Discovery stops at 20,000 entries / 64 matching
segments. Symlinks and special files are refused. The reader keeps up to 12
deduplicated, timestamped event kinds in memory, not on disk. No conversation
text, reasoning, tool names, arguments, output, credentials or log paths enter
the activity response. A generic step such as "Tool activity recorded" is not a
semantic summary of the task's work.

Visible-page polling happens every five seconds, with a three-second read cache.
Polling does not change evidence timestamps. An activity/native status older than
two minutes becomes **Activity unknown**, retaining the last recorded step and
time. Silence is not proof of a stopped task: a long tool call or model response
may produce no events. A finished turn is not packet acceptance. Missing,
unreadable, excessive or future-dated evidence cannot report a healthy task.

A newer, fresh `native-observe` brain status wins over log evidence. Its optional
`title` (at most 200 characters) must come verbatim from native task tools. Titles
can be retained after status expires. This panel's two-minute freshness is
independent of readiness's 15-minute inventory and 30-minute checkpoint gates.

## Safety and rollout

This reader performs no native task action, model request, repository command,
queue write, approval, heartbeat update or dispatch. No background monitor or
dispatcher is installed. When the webpage is closed, it performs no reads.
Runtime provenance remains independent: a dashboard server restart is required
to load the new Python module; simply refreshing assets does not prove that.

Verification: `python3 -m unittest discover -s tests -v`,
`node --check web/app.js`, `node --check web/activity.js`, and rendered-browser
checks of Overview, Knowledge, worker empty state and the latest-artifact link.
