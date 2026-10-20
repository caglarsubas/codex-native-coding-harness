# Finish an already-created empty target without repeating creation

This is an operator-only, pre-phase registration control, not a host repair,
native load, admission, policy attestation or Play control. Source delivery and
disposable tests install nothing and leave every live pilot paused/unactivated.

## Cause

The pinned public native runtime can persist an exact-checkout `trusted` entry
during a restricted `thread/start`. Its original whole-file config epoch then
differs, even though the base policy bytes are unchanged and the host is alive.
The old guard correctly refuses. Retrying creation, reverting the file, hiding
the new epoch or claiming the old guard passed would be incorrect.

The [official app-server protocol](https://learn.chatgpt.com/docs/app-server)
separates thread creation, stored reads, loading and turn execution. The concrete
trust-write behavior is independently identified in the pinned native source;
timing/source correlation is not OS writer attestation. A `trusted` entry can
enable project configuration, so this control refuses additional checkout or
system configuration rather than interpreting trust as execution qualification.

## Exact local transition

`python3 -m orchestrator.empty_setup_transition` supports `preview`, `confirm`
and file-only `status`, always with explicit `--platform` and `--workspace`.
There is no HTTP/assistant write route and no generic rebind fallback.

The private specification has the closed fields in `SPEC_FIELDS`. It names:

- The existing unused target, old registered brain, actual returned new brain,
  and both distinct app-catalog and owned-host project IDs.
- The unchanged original endpoint and exact isolated `config.toml`, its original
  restricted pin, and the observed new epoch. Only the byte-exact fixed base plus
  one exact-checkout trust append is accepted. No configuration is written.
- All original approval/request/intent, consumed project/brain claims/results,
  and both creator observations. They must agree with the original approved
  `prospective_disjoint_v1_native_identity_setup_v1` contract. They are retained
  operator lineage, not independent process cleanup or native safety evidence.
- A complete actual `codex_app.list_projects` observation with its original time.
  Neither a directory nor a matching project label substitutes for either ID.

Preview checks the original operator/package, consumed lineage, exact current
configuration, original registration/catalog mapping, all registered database
identities/content, and an unreviewed draft or no mission. Any run, request,
worker, managed/strict state, admission/disposition claim, ownership fence or
reviewed mission refuses. It independently reads only the already-created new
project, brain, effective policy and one complete empty history page twice.
It never reads the predecessor brain, creates, loads, subscribes, signs in,
refreshes authentication, handles a permission, starts a turn or lists arbitrary
threads. Unavailable or nonempty history refuses. `notLoaded` means unknown
policy and terminals; loaded contrary policy also refuses.

Save the entire preview privately. Its `reviewHash` has **no timer expiry**:
unchanged scope retains the approval. Confirmation needs the new exact owner
review, `--confirm`, `--writers-stopped`, and `--catalog-recheck` pointing to a
new actual complete observation within 120 seconds. The normalized catalog must
still match. Refreshing evidence is not another approval or a renewed hash.
The consumed creation approval cannot authorize this registration change.

Confirmation locks the registry and every registered dashboard/ledger, then
verifies private SQLite backups (including committed WAL content) of every
registered database and copies the non-credential setup/config/catalog inputs.
It repeats unchanged context and actual zero-turn readback at the claim boundary.
An exclusive target claim precedes all local mutations. The only new target
changes are its brain/revision/transition pointer, the exact repository catalog
mapping, and a new **unreviewed** successor draft. Original draft/receipt/event
rows remain unchanged. The old registry mapping/catalog and complete request are
retained in append-only transition history and verified private backups; only
their current routing projection changes. Other ledgers and their usage, claims,
gaps, clocks and repository holds remain identical.

Two SQLite commits are **not** presented as crash-atomic. The external claim
fences direct ledger writes, standard admission and registered routing until
both commits and the exclusive completion receipt exist. A failed/partial
transition stays fenced; there is no automatic retry, claim deletion, downgraded
read or native fallback. An identical completed confirmation returns only its
historical receipt, without rereading native state, reapplying the mapping or
repairing later drift. Preparing a second transition never rearms the first.

## What remains separate

The dashboard startup binding is unchanged. A separately exact-reviewed cutover
must still match the new registration and package. The retained creator policy
does not fill the missing independent loaded-policy sample. Existing readiness
must obtain actual current policy through its own supported owner-confirmed
load/startup path; this control grants no load and no reusable subscription.

Changing registration invalidates any historical proof requiring an identical
whole registry. Never rewrite that proof or silently accept its old result.
Any post-preparation worker-admission lineage must be independently requalified
against the preserved before/after transition before use. This control does not
provide that requalification or erase an old hold. A new mission Review and
fresh target Play remain separate exact controls. Unknown historical/current
terminal safety stays unknown; no pilot success/acceptance is inferred.

Verification uses disposable metadata fixtures, including exact read allowlists,
config/namespace/file-epoch drift, original claims, zero-turn persisted history,
unknown policy, mapping isolation, current-source review, stopped-writer locks,
backup preservation, non-expiring review/fresh evidence separation, and failure
between commits/completion. No live native source or provider call is made.
