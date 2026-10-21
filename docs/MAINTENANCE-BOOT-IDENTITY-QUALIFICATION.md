# Stable boot identity qualification

Implementation hash:
`ebb448e5f0523f03e361a85477c651fe21836b37bba9257add3cb07bf050e0a7`.

## Exact local source verification

- Complete current Python discovery: 3,477 cases, zero selected failures/errors,
  one existing optional Graphify skip. Selected results retain exact discovery
  multiplicity, including legacy duplicate IDs, and the same implementation hash
  before and after every partition.
- All 33 maintenance cases passed, including seven new boot-identity cases:
  forward/backward calendar drift with the original review hash, unchanged
  cutoff, same-device reboot rejection before/after confirmation, a boot change
  during inspection, tightened historical bounds, legacy-review refusal and
  fixed bounded UUID parsing with no fallback. All original identity, backup,
  one-winner race, partial-claim, private-file and conservation tests remain.
- All 42 JavaScript suites, all 31 web syntax checks (including
  `node --check web/app.js`), all 375 tracked Python AST checks and diff checks
  passed. No frontend code changed; no new rendered-UI acceptance is claimed.

The first complete parallel discovery retained seven errors from legacy local
fake-GitHub subprocess read timeouts, with zero assertion failures. Those fixture
subprocesses make no external GitHub requests. An isolated affected case passed;
the complete four affected partitions were then rerun at lower concurrency.
All 1,739 rerun cases passed at the same implementation hash and unchanged
assertions/deadlines. The final full-discovery result selects these complete
reruns plus the four originally green partitions. The original errors, full
logs, inventories and hashes remain retained; the first run is not called green.
No production timeout, freshness requirement or safety gate was changed.

## Installation and live boundaries

Merged PR-191 was separately installed **inactive** from its exact merged tree:
653 Git-verified source files, five complete database backups and 1,419 private
input backups. Its 26 installed maintenance tests, 42 JavaScript suites, 31 syntax
checks and 375 tracked AST checks passed. The prior source and global launcher
were not changed; no dashboard, host, load or native turn was started.

The unchanged prepared version-1 review failed with only the calendar boot-time
field different. Its request, preview, backup, approval state and canonical claim
absence remain intact. The corrected source passed a prospective **local-only**
lineage read against the preserved target, with the same canonical owner and no
claim. This is neither native runtime qualification nor application of a review.

Every old run/request/claim/usage/gap/clock/binding/hold stays unchanged. Current
and historical terminal safety remain unknown. The pilot is paused and not
accepted. No native client, schema export, host launch/bind, load, turn, permission
response, cancellation, readiness/Play/recovery replay, usage reset, provider,
download, GitHub Actions or paid CI was used by this correction.

The new version-2 review is separate from source delivery, manual merge and
authorized installation. Old reviews are never auto-converted. The same
permanent canonical claim prevents a version/source/device successor after any
partial or completed confirmation. Normal identity/effect routes remain strict;
the read-only certificate alone cannot restore host connectivity or activate a
worker phase. See [the root cause and correction](MAINTENANCE-BOOT-IDENTITY.md).
