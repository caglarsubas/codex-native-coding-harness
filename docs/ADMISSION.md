# Shared admission foundation — WSP-04A

Implemented: a private, transactional **capacity-accounting kernel** and an
explicit read-only cross-workspace resource audit. **Not implemented: connection
of this kernel to native dispatch, run activation or autonomous Play.** This is
the dependency below those controls, not a second scheduler.

Follow-up WSP-04B1 adds [explicit maintenance enrollment and legacy dispatch
fences](ENROLLMENT.md). It journals existing owners and prevents upgraded legacy
callers from reopening dispatch, including after partial setup. It does not yet
adopt these owners as kernel claims or provide an activation/unfence path.
WSP-04B2 now adds [owner-reviewed quarantined ownership import](OWNERSHIP-ADOPTION.md),
preserving conflicts and unknown usage inside this store. Imported claims are not
verified native activity or phase allocations; no release/activation path exists.

Existing exact packet approval, legacy worker limits and brain controls remain
intact; only explicit maintenance enrollment adds the dispatch fence above. Live
state and the installed skill are unchanged. A reviewed mission remains inactive. No
server route or CLI command opens allocations, changes budgets, records usage,
reserves capacity or invokes native operations through this kernel. Its Python
interface is for the future trusted run controller and isolated tests only. The
explicit maintenance adoption CLI may initialize its exact reviewed policy and
quarantined inventory; it does not open allocations or reserve new work.

## Read-only resource audit available now

From this checkout:

```sh
python3 -m orchestrator.cli --platform /absolute/private/.platform platform-resources
```

This explicit operation covers all registered workspaces; do not pass
`--workspace`. It reports each ledger revision, repository identity coverage,
aliases, active owners, cross-workspace conflicts and legacy runner identity gaps.
It never writes approvals/worker state or creates an admission database.

Two identity keys are observed where possible:

- The canonical Git common-directory device/inode identifies a checkout and its
  worktrees, including symlink aliases.
- A digest of the conventional origin host/port/repository identifies separate
  clones using equivalent HTTPS/SSH URLs. GitHub path case and `.git` suffixes are
  normalized. Other servers retain path case; non-default ports retain protocol.

Only fixed local Git metadata commands run, without network access, fetch,
checkout, hooks, packet commands or source-file reads. System/global Git config
is disabled, and the origin reader does not follow local config includes. Remote credentials, local-file
remotes, multiple origins, unsupported syntax, missing checkouts and obvious SSH
aliases produce **unknown**, never an invented global identity. Output excludes
checkout paths, origin URLs and stderr. Partial local keys still expose worktree
conflicts without claiming cross-clone completeness.

This is literal identity observation, **not** proof of host equivalence or the
effective remote after SSH aliases, redirects or Git URL rewrites. Such cases
need explicit verified mappings before future dispatch. Runner labels likewise
need a pinned operator identity; legacy `runner` records cannot establish it.
The audit is bounded to 32 workspaces, inspects at most 100 repositories and stops
starting inspections after 25 seconds (each Git command has a 3-second timeout).
It marks the remainder uninspected. Results are per-ledger snapshots, not an
atomic platform snapshot or reservation. Unmanaged native tasks and actual
external runner occupancy are outside coverage.

## Capacity kernel contract

`orchestrator.admission.AdmissionStore` owns `admission.sqlite3` in a private
platform directory. It uses SQLite `BEGIN IMMEDIATE`, WAL and full synchronous
writes. Database ownership, permissions, inode and link identity are checked;
construction without explicit policy refuses an absent store. Policy, allocation
bindings and request fingerprints are immutable. Initialization does not occur
as a side effect of dashboard reads or the resource audit.

The internal API provides:

| Operation | Capacity effect; never execution permission |
|---|---|
| `open_allocation` | Pin workspace, opaque exact run-binding hash, repository/runner keys and phase limits; one open allocation per workspace |
| `observe_account` | Record both account windows with observed/reset times and an evidence hash |
| `observe_usage` | Record cumulative allocation counters, coverage and explicitly incorporated settlements |
| `reserve` | Atomically claim all requested repositories, a global/workspace task slot and estimated tokens |
| `begin` | Recheck fresh headroom and durably mark a one-shot creation attempt |
| `bind` | Bind an observed `(hostId, threadId)` uniquely across the store; never a pending client ID |
| `block` | Retain uncertain/blocked task ownership, slot and estimate |
| `runner` | Exclusively acquire a pinned shared runner or release after fresh exit evidence |
| `settle` | Reconcile terminal task or confirmed non-creation, record actual usage, release repository ownership |
| `close_allocation` | Close only after every claim is settled; retain the complete history |

After explicit WSP-04B2 adoption, the `legacy` snapshot retains grouped historical
owners, resource/native conflicts and unknown usage separately from phase claims.
Every logical workspace/worker owner conservatively retains a slot, including
runner-only records. Either platform sidecar or the metadata binding blocks new
allocation, reservation, creation boundaries and runner acquisition. Even zero
recorded legacy owners remains quarantined pending external inventory/baseline
reconciliation. These slots are not added to an arbitrary phase token budget.

All repositories in one reservation commit or none do. `reserved`, `starting`,
`running`, `uncertain` and `blocked` claims consume capacity. Worker, reviewer and
nested-task reservations count equally. The existing brain is not a newly opened
worker slot, but its tokens must be included in allocation usage. Total phase
attempt counts include even reservations later cancelled without native creation;
they do not silently replenish. Resource ownership never expires with age.

Retrying an identical reserve ID returns the **current** claim and does not acquire
again. Reusing the ID with different content refuses. `begin` is deliberately
not replayable: a second call refuses even if creation never returned. A crash
after the durable creation boundary requires native reconciliation, not retry.
Binding a task requires a confirmed native ID, unique even against settled claims.
Pending and uncertain creation retain the original claim.

Settlement requires fresh evidence later than the attempt. A bound task must be
terminal; a claimed `not_created` outcome requires no bound native ID and zero
actual tokens. A runner must be separately released before settlement. Actual
token overruns are retained as truth and may make remaining headroom negative;
they are not rejected to make the budget look healthy. Replayed settlement must
match the exact original proof. Evidence hashes and observations are assertions
from the trusted caller, not independently verified facts or an OS security fence.

## Token math and freshness

Policy explicitly supplies a global parallel-task cap, an observation age of
1–300 seconds and minimum remaining account percentage. Both short and long
account windows must be known, fresh, non-future and not past their recorded reset.
Account percentages are **not converted to tokens or dollars**. There is no
default unlimited mode when usage is missing, stale or incomplete.

Allocation usage must cover the brain, workers (including children) and reviews.
Counters are cumulative from the allocation's explicit baseline. Each claim
estimates work, review and handoff tokens separately; checkpoint tokens are held
at the allocation level. The calculation is:

```text
raw tokens = inputTokens + outputTokens
new-work headroom = phase token budget
                  - observed cumulative raw tokens
                  - full estimates for all held claims
                  - settled actual tokens not yet incorporated in the observation
                  - protected checkpoint reserve
```

Cached input is a subset of input; reasoning is a subset of output. Neither is
added a second time, nor are cached tokens discounted as if this were a bill.
Active estimates can overlap observed partial usage: the kernel intentionally
over-counts conservatively until settlement and explicit coverage reconciliation.
An observation can incorporate only settled claims from this allocation, with
enough reported tokens and an observation time after settlement. Incorporated
claims and cumulative counters cannot move backwards.

These are admission estimates, not a provider-side hard token cap. An in-flight
model call may exceed its estimate; future control integration must check before
every continuation/new effect and stop safely on overrun. No model pricing,
fast-mode cost assumption, model/effort selection, speed override or inference
tenancy usage is inferred here. The dashboard assistant's separate inference
service remains separate from Codex account usage.

## Integration gates still open — WSP-04B and WSP-03B/C

WSP-04B3 adds [versioned admission-evidence reviews](ADMISSION-RECONCILIATION.md)
and continuity-checked cumulative usage baselines. These validate caller-supplied
observations, not their native provenance. A consistent historical receipt is
neither free capacity nor execution authority; all imported ownership and fences
remain intact. Actual observation collection and the controller gates below are
still required.

Do not wire a successful capacity reservation directly to native task creation.
The remaining controller work must:

1. Require a new exact owner-bound run activation and valid phase authority,
   packet/seed approval, policies, checkpoint destination, task settings and
   approved numeric limits. The opaque binding hash is not an authority verifier.
2. Reconcile WSP-04B2 imported workspace/legacy workers and runners, including
   uncertain native creation and conflicting histories, against actual native
   inventory before enabling cross-workspace dispatch. Preserve WSP-04B1 legacy
   `--state` fences. Do not assume an empty recorded inventory establishes free
   global capacity or silently settle missing owners.
3. Verify canonical repository and operator runner mappings, actual native
   inventory, account identity, allocation baseline and complete token coverage.
   Closing/reopening an allocation must not become an unapproved budget reset.
4. Implement crash-safe ordering between global claims and workspace receipts.
   These are separate SQLite databases; this increment does not claim atomicity
   across them. Incomplete adoption/receipts must retain ownership and fail closed.
5. Fence owner Pause, mission revocation, mandatory checkpoints and material
   budget/plan changes at each admission/continuation boundary. Existing claims
   remain owned through cooperative quiescence. Add fairness and starvation handling.
6. Add native requested/applied/observed model/effort/speed records and real
   supervised two-workspace acceptance before activating live autonomous Play.

No mission is activated, no current worker is retroactively admitted, no budget
is granted, and no heartbeat or live process is restarted by this increment.

## Verification

Isolated tests cover two-process resource and global-slot contention, transaction
rollback, restart/idempotency, one-shot uncertain creation, unique native binding,
runner exclusion/exit evidence, immutable policy, stale/unknown/reset usage,
protected reserves, accounting subsets, overrun, settlement coverage and private
database identity. Git fixtures cover worktrees, symlinks, equivalent clone
origins, malformed/credential-bearing origins and read-only multi-workspace audits.
All native identities, account observations, repositories and usage in these tests
are synthetic. They do not establish a real worker pilot or live admission.

Local verification on 2026-09-19: **284 Python tests passed**, including 36 new
admission/resource tests. All four JavaScript regression suites, JavaScript syntax
checks, skill validation and whitespace validation passed. This increment adds
no new rendered UI component; the mission activation explanation stays inactive.
These are local checks, not hosted CI, deployment or live acceptance evidence.
