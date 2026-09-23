# Roadmap sources, current claims and private proposals

The Roadmap page is a read-only source catalog, not an execution queue or a
project-completion score. Narrative plans without checkboxes show **Checklist
completion not available**, not `0 / 0`.

For an observed published source in a registered workspace, **Prepare draft**
offers at most 20 current, open checklist actions and current section headings
from the retained display. Historical, completed, unclassified, unavailable and
private-proposal entries do not offer this handoff. Select one action to open one
unsaved, editable Mission draft for that workspace. An existing unsaved Mission
draft is opened rather than overwritten. A changed source version, workspace or
source repository refuses the old button; refresh Roadmap before trying again.

The draft starts with the selected action as its goal and records the repository,
path, commit, retained document ID/version, source kind/line and observation time
in its phase objective. That provenance line is kept while editing the initial
draft and included in the saved Mission document. The remaining required Mission
fields, repository scope and numeric limits are blank; approval mode starts at
`prepare_only`. Saving requires the normal Mission form and creates a draft
version only. Separate owner review is still required. No packet approval,
Play, admission, budget, model, schedule, controller, notification or native task
is changed by preparing the draft. Subsequent revisions are normal owner edits;
the owner should retain or update the source reference when changing the scope.

For a selected configured standard project, the page also shows the recorded
Review & Play prerequisites and routes to the existing mission review flow. It
does not open a Play preview itself: the owner reviews that exact preview and
confirms it separately. Harness and nonconfigured projects remain outside the
standard protocol; roadmap reading never changes their policy.

## Published sources

Add registered repository IDs and repository-relative Markdown paths to
`roadmaps` in the selected ledger's private `observations.json`. The dashboard
reads the configured Git ref, retains immutable byte versions and reports the
resolved commit and observation time. It never fetches or follows document links.
A local tracking ref can be stale. Use `config/roadmaps.harness.example.json` for
the seven-document Harness catalog; replace its example repository ID.

Optional `currentSectionPrefixes` explicitly selects heading prefixes. A section
runs until the next heading of equal or lower depth. Optional `historyBoundary`
is an exact heading: everything from its first occurrence onward is historical,
even if an older heading starts with “Current”. Missing configured headings are
visible mapping gaps; they suppress checklist summaries until corrected. Without
a mapping, tables are readable document content with unclassified currency.

Statuses stay literal. `DONE_SOURCE_GATES` is not rewritten as implementation
complete. Blocked, waiting, design and acceptance claims are not collapsed into
one percentage. Checkboxes measure their source checklist only; historical
checkboxes are excluded. Overlapping documents never become a project total.

## Private proposals

Optional `roadmapDrafts` entries use the same descriptive fields, but `path` must
be an exact absolute `.md` path beneath that repository's existing artifact root.
No recursive discovery, arbitrary file opening or cross-repository root reuse.
Symlinks are refused. Draft bytes are versioned separately and displayed under
**Private proposals — not published**. Reading them does not publish, adopt,
approve or execute them. Empty coverage means no drafts were configured, not that
Codex has none. Proposals do not contribute to published-plan or inference
checklist totals. Inference receives counts only, never document excerpts.

## Refresh and limits

Use **Refresh local observations** after configuration or source changes. Normal
page reads use retained observations. Legacy snapshots remain readable with
unclassified tables until refreshed. Source and version buttons open immutable
artifacts through project-scoped navigation.

At most 32 published sources and 32 proposals are configured; each has the existing
8 MiB artifact limit. Display retains up to 8 excerpts of 6,000 characters and
32 tables of 100 rows, with at most 20 columns. Unsupported/omitted rows and tables
are disclosed. Markdown and HTML remain inert text. Read the full source when
the bounded display is insufficient.

No plan file, packet, authority, budget, native task, GitHub workflow or acceptance
state is changed by observing the roadmap.
