# WSP-09A — canonical portfolio measurements

Plan saved before implementation from PR #46 merge
`89879836bf16fbe5e80f29cd600f142aa0d56d62`.

The native/host evidence dependency in milestone 3 remains open. This independent
part of milestone 9 improves recorded code statistics, not resource admission,
runner fairness, token accounting or autonomous Play.

## Delivery checklist

- [x] Capture bounded local common-directory and conventional origin identity at
  explicit metric collection, before and after the immutable commit scan. Retain
  only hashed identities, never raw remote URLs or credentials.
- [x] Use one pure aggregation path for selected-workspace totals, all-workspace
  totals and exports. Count an identity/commit/measurement-policy snapshot once;
  keep different commits distinct. Do not merge forks by equal commit alone.
- [x] Preserve distributed rows and aliases. Exclude conflicting measurements,
  changed configuration and unqualified historical identities from deduplicated
  totals, with explicit coverage and a request for a fresh observation.
- [x] Keep summary reads free of Git/filesystem identity probes, remote requests,
  native calls and ledger writes. Repository identity is descriptive, not an
  authorization or lock; literal origin equivalence is not host attestation.
- [x] Explain counts and exclusions in the existing metrics views and export.
  Validate worktrees, clones, forks, differing commits, corrupted/legacy records,
  workspace filtering, deterministic ordering and larger synthetic portfolios.

## Counting contract

New metric records retain their existing schema version and add a versioned
identity and measurement-policy marker. Old records remain readable; they cannot
establish clone/worktree equivalence retroactively. A normal explicit observation
refresh produces new records. No migration or scan runs during upgrade or polling.

Conventional literal origin keys use the existing credential-rejecting normalizer;
no redirects, SSH aliases, insteadOf rules or local-file remotes are resolved.
The local common-directory device/inode key identifies worktrees even without a
supported origin. Conflicting origins for a shared local key are excluded pending
refresh. Configured checkout-path and ref bindings prevent an old observation from
being relabelled after repository configuration changes.

Each distinct commit stays visible and is counted separately, even when its text
counts happen to match. Therefore the aggregate measures repository snapshots,
not the size of one hypothetical merged codebase. Alias rows and workspace rows
overlap and must not be summed. Removed repositories and superseded observations
do not contribute. A newer unavailable observation cannot fall back to old success.
Zero measured files is a valid empty snapshot; no usable snapshots means unavailable.

The owner is the technical audience: comparing product scopes and deciding where
to investigate, often after seeing inconsistent counts. Copy follows the existing
assured, precise, composed design context: state what was counted, why some rows
are excluded, and the next action. No layout/theme redesign is needed.

## Boundaries

No live scan, installed skill, dashboard restart, private ledger, model call,
native endpoint, schedule, allocation, maintenance release, workflow or paid API
is changed by this source delivery. Tests use disposable repositories and ledgers.
Milestone 9's runner fairness and full browser/scale qualification remain separate;
this increment does not decrement the conditional remaining-iteration estimate.

## Implementation and verification

`portfolio_metrics.py` supplies pure selection and grouping. `repository.measure`
captures identity during explicit observation, clears inherited Git targeting and
global/system configuration, and disables replacement objects. Identity changes
during collection leave the text observation readable but unqualified for totals.
No raw remote URL is stored. The existing observation import/scan scope is unchanged.

Workspace and all-workspace totals, Markdown export and numeric inference facts
use the same counting path. The inference projection receives counts/coverage only,
not local identity hashes, repository names, paths or credentials. The historical
`measuredRepositories` aggregate field now denotes counted unique code snapshots;
the UI names it accordingly. Distributed repository measurements stay available.
The code projection refuses more than 10,000 configured rows rather than silently
truncating totals. This is a projection bound, not a whole-server memory guarantee.

All-workspace snapshot tables render 40 rows per page independently of artifact
pagination. Alias lists are expanded on request. Pages and open disclosures survive
polling; changing workspaces clears that transient inspection state. The selected
workspace's local-refresh control uses the existing scoped endpoint, never a
cross-workspace scan. Ordinary summary polling does not collect or mutate evidence.

Verification on 2026-09-21:

- **1,255 Python tests passed** in 173.611 seconds, including 25 new portfolio
  tests; the focused repository/workspace/observation/inference/assistant suite
  passed 88 tests. Eight JavaScript UI test files and both changed-script syntax
  checks passed. Fixtures cover real disposable clones/worktrees/forks, invalid
  metadata, configuration drift, no healthy fallback, deterministic grouping,
  readonly summaries and unchanged ledger fingerprints.
- A separate 3,200-row pure aggregation (32 synthetic workspace scopes × 100
  repositories) produced 100 snapshots and 3,100 aliases in **0.0308 seconds** on
  this machine. This is a local function measurement, not endpoint latency,
  scanner throughput, full browser performance or a service-level guarantee.
- A disposable loopback dashboard with two synthetic workspaces and 170 repository
  entries visibly showed 85 snapshots / 255 lines, 84 duplicate aliases and one
  excluded legacy record. Workspace rows separately showed 255 and 252 lines.
  Browser checks verified page 2, refresh-preserved disclosure, exclusion deep link
  to the correct workspace and visible local-refresh control. The temporary tab
  and server were closed afterward. No production dashboard was restarted.
- Read-only GitHub inspection found zero workflows and zero Actions runs. These
  local checks are not CI, merge evidence, deployment or autonomous acceptance.
