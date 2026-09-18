# First native-worker pilot proposal

**State: awaiting target/scope and CI decisions. Not approved, prepared, scheduled
or dispatched.**

Recommended target: this orchestration repository, under the standard profile
and manual-merge policy. This avoids using an unqualified controller to execute
a Harness product packet with stricter isolation and acceptance requirements.
Selecting the target does not waive any of those requirements for future work.

## Scope selection

The earlier runtime-provenance candidate is now implemented through the
maintainer development task; see [RUNTIME.md](RUNTIME.md). It was not dispatched
through the controller and is not native-worker pilot evidence. Do not dispatch
that completed implementation again simply to make the pilot indicator green.

Select a still-open, useful bounded task after native registration and the CI
route are resolved. Review its objective, exact allowed paths, pinned base,
acceptance and stop conditions before preparing an immutable seed. The new native
task must implement one `codex/` branch and one PR; manual merge stays with the
owner. An already completed maintainer change cannot retroactively become a pilot.

## Must resolve before approval

- Register this existing checkout as a saved Codex Git project and verify its ID.
- Review native setup scripts and ignored-file copying. In particular, the ignored
  inference `.env` must not be inherited by the implementation worktree.
- Choose an already available, approved CI evidence route. This repository has no
  hosted workflow; local test success alone cannot certify the required CI axis.
- Pin the then-current packet/catalog/base commits and exact source contracts.
  No mutable `main` reference is sufficient for inheritance or approval.
- Confirm that the designated brain and this pilot target are the intended
  portfolio pairing. Do not change brain ownership implicitly.
- Review and approve the final exact packet and seed hashes, then separately
  request a supervised resume. No heartbeat activation is implied by this proposal.

The real pilot is complete only after native identity, actual changes, independent
checks and retained evidence have been verified. Fixture rehearsal success does
not count. If the owner chooses an existing Harness packet instead, replace this
proposal with that packet's exact approved scope and preserve its trusted runner
and clean-room boundaries; do not adapt this standard-profile execution route.
