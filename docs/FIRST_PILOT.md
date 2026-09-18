# First native-worker pilot proposal

**State: proposed scope only. Not approved, prepared, scheduled or dispatched.**

Recommended target: this orchestration repository, under the standard profile
and manual-merge policy. This avoids using an unqualified controller to execute
a Harness product packet with stricter isolation and acceptance requirements.
Selecting the target does not waive any of those requirements for future work.

## Useful pilot task: runtime provenance

Add a read-only runtime provenance indicator that distinguishes the server's
loaded revision from the current checkout and the observed remote default branch.
This addresses a real operational gap: merging a PR or checking out new code does
not prove that the running dashboard has loaded that revision.

Proposed scope to review before an immutable seed is prepared:

- `orchestrator/provenance.py` and `tests/test_provenance.py`
- `orchestrator/server.py`
- `web/provenance.js`, `web/index.html`, `web/app.js`
- `docs/RUNTIME.md`

Acceptance should prove startup revision capture, honest dirty/unknown states,
changed-checkout restart advice, no background fetch, no credential exposure and
no changes to controller authority. The new native task would implement one
`codex/` branch and open one PR; manual merge remains with the owner.

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
