# Runtime provenance

A merged PR, a checked-out commit and a running dashboard are separate facts.
Overview shows a compact runtime indicator; Readiness has the full comparison.

## Evidence shown

- **Server-start checkout:** an immutable observation captured when the dashboard
  server is constructed. Includes HEAD, clean/dirty state and a runtime-source
  fingerprint. This is not an attestation of loaded Python memory.
- **Checkout now:** captured at startup and refreshed only with Inspect runtime
  locally or Check GitHub revision. Observations expire after 15 minutes.
- **GitHub default branch:** obtained only by Check GitHub revision, using existing
  `gh` authentication and two fixed REST GETs for the configured GitHub origin.
  The default branch is discovered, not assumed to be `main`. No fetch occurs.

The first-party fingerprint covers regular Python, JavaScript, CSS, HTML and TOML
files beneath `orchestrator/`, `web/`, and `pyproject.toml`. Tracked and non-ignored
untracked files are included. Hidden paths, `.env`, ignored files, conversations,
reports and local state are excluded. No file contents or names are returned by
the provenance API. Limits: 256 files, 2 MiB per file, 16 MiB total. Symlink reads,
unstable observations and unavailable Git roots are refused, not marked clean.

## Interpretation

| State | Meaning | Next action |
| --- | --- | --- |
| Matching source snapshot | Same clean HEAD and runtime fingerprint as startup | Still not proof of CI, deployment or tenant acceptance |
| Runtime files changed | Runtime bytes changed, even if HEAD did not | Preserve/review edits, then restart and reload |
| Checkout revision changed | HEAD changed since startup | Restart to align the recorded startup revision |
| Unverified working copy | Dirty source tree at startup or inspection | Do not attribute it to a clean commit alone |
| Runtime provenance unknown | Missing, unstable or stale evidence | Inspect locally; resolve source/permission problems |

Remote comparisons require a fresh successful check, the same configured origin,
a fresh local snapshot and a clean compared tree. Failed checks replace prior
success with unavailable status; changed origins invalidate comparison. A remote
mismatch means different commits, not necessarily that the checkout is behind.
No ahead/behind or ancestry claim is inferred from SHA inequality.

Python modules may import lazily, and static assets are served from disk. Changes
after startup can therefore produce mixed code/assets. The fingerprint detects
source changes on inspection but is not a loaded-memory hash, build attestation,
dependency inventory or environment fingerprint. Externally changed ignored
dependencies and credentials are deliberately outside this measurement.

## Refresh and restart boundaries

Authenticated `POST /api/provenance` accepts only `{"remote": false}` for local
inspection or `{"remote": true}` for an explicit GitHub check. Host, Origin,
session and CSRF checks apply. One inspection runs at a time. No caller-selected
path, URL, branch, shell, restart or controller action is accepted. GET state and
normal dashboard polling return retained observations without scans or network.

There is no automatic pull or restart. To restart manually, verify the exact
dashboard process, preserve local changes, stop only that process, start `serve`
again, and reopen the newly generated private dashboard link. Authentication
rotates; the durable queue, runner reservations, pilot flag and dispatch state do
not change. Restarting the webpage alone does not reload Python server code.
Remote observations are process-local and reset to not requested after restart.

This feature was implemented through the maintainer development task. It does
not count as the real native-worker pilot described in [FIRST_PILOT.md](FIRST_PILOT.md).
