# Local preservation verification

Scope: WSP-04C3g, starting from PR #36 independently verified merged at
`3fb9bf9b77256a1e7cbcd1f8148d3ca8bffaaefd`. Fetched `origin/main` matched that
commit. All implementation and source-bearing probes used an isolated tooling
worktree and disposable test repositories, not Harness product checkouts.

## Evidence boundaries

| Boundary | Result |
| --- | --- |
| Local Git | Exact base/result reachable objects retained in an 8 MiB maximum bundle; restored into an empty object store and strict integrity checked |
| Ledger | Exact handoff and result evidence versions bound to manifest; bundle, manifest, journal and receipt retained atomically |
| Review | Optional measured local preservation proof; separate existing acceptance/rejection remains mandatory |
| Remote/CI | Collector invokes no remote operation or workflow; metadata-only development checks found zero configured GitHub workflows and zero Actions runs |
| Billing | No Actions workflows added/enabled/dispatched/rerun, runners provisioned, paid API/storage or new dependency introduced |
| Native/runtime | No native task/message/archive, live ledger collection, resource/budget setup, installed skill, schedule or dashboard change |
| Acceptance | No real pilot, Harness acceptance, autonomous Play, deployment, runtime or tenant acceptance claim |

The orchestrator skill's separation of preservation, acceptance and explicit
archival authority shaped this increment. Collection returns no archive or
execution permission. Harness and delegated task scope refuse before source I/O.

## Local checks

```sh
python3 -m unittest discover -s tests -v
node --check web/app.js
node --test tests/test_*_ui.js
git diff --check
```

Python 3.12: **1,043 tests passed**, including **28 new preservation/cost-policy
tests**. All **7 JavaScript UI test files passed**. Syntax and whitespace checks
passed. UI code is unchanged; this is regression evidence, not new browser QA.
No GitHub-hosted CI check is claimed. Local tests are not relabelled as CI.

## Fixture coverage

- Real bundle creation/unbundle/full integrity validation. A second independent
  clone restores committed content after the original fixture repository is moved
  away; uncommitted working content is excluded and the source repo is unchanged.
- Packed objects/refs and linked worktrees. Repository configuration, replacement
  refs and inherited Git environment are ignored. Missing blobs, corrupt packs,
  oversized output, shallow/alternate/symlink storage and branch drift refuse.
- Subprocess CLI collection/read/review and historical state; no source, native,
  account/ownership or pilot effects. Synthetic GitHub responses use the inherited
  fixed fake `gh` fixture, not an external network request.
- Current revision, exact controller/workspace/worker, settlement and approval
  gates; real Harness and delegated fixture approvals refuse before Git access.
- Pause before and during collection, maintenance fence, expiry, unchanged
  historical replay after the checkout disappears, and no read-refreshed times.
- Atomic event failure leaves neither bundle nor manifest/receipt. Concurrent
  identical requests retain one pair. Changed request content and malformed
  receipts refuse instead of recollecting or repairing.
- Missing/corrupt bundles, handoffs, evidence, receipts and altered provenance;
  historical review detects missing preservation custody. A manifest cannot
  cover changed/missing result proof versions or itself/the later reviewer report.
- Original collection freshness remains required even with a new proof timestamp.
  Accepted attempts cannot collect a new bundle or implicitly archive.
- A repository-local regression test rejects `.github/workflows/*.yml` and
  `*.yaml`, retaining the owner's no-extra-Actions-billing constraint.

## Remaining gates

This covers bounded local Git objects and already retained result/handoff evidence,
not all native attachments/transcripts, external LFS/submodule payloads or off-device
backup. Native descendant/counter/host qualification, trusted Harness acceptance,
new-generation continuation/rereview, safe archival, exact owner rollout and real
supervised pilots remain open. Older helpers must be quiesced before a separately
authorized rollout; no mixed-version/downgrade or live activation is implied.
