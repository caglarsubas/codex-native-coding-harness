# Forward-only historical admission requalification

This is an explicit file/SQLite-only evidence path, not recovery, admission,
binding, readiness, loading or Play. Source delivery and disposable qualification
install nothing and leave live runs, requests, claims, usage and bindings intact.

## Why the old validator refuses

An independently completed preparation and its numeric accounting pin the entire
original registry and catalog. The owner-reviewed empty-target setup transition
changes one current registration, its catalog mapping and an unreviewed draft,
retaining the original mapping and all old state. Those are real differences;
pretending the old registry hash is current would be incorrect.

The default completion/accounting/admission paths still refuse these differences.
They never implicitly look for a transition, discover evidence, rewrite an old
hash, recollect telemetry or infer authority from an otherwise empty target.

## Separate causal proof

`historical_worker_admission_requalification_v1` requires the canonical completed
`empty_standard_setup_transition_v1` claim, receipt and registry history row for
the exact new target. It validates:

- Exact original request/approval/configuration epochs, consumed creation claims,
  returned dual identities and original input pins. Only the fixed base and
  original exact-checkout trust append are supported; no config is changed.
- The source-created private backup manifest, complete registered database set,
  every pre-transition database fingerprint and every copied setup input.
  Arbitrary snapshots or owner-authored assertions are not inputs.
- An unchanged source registry inode, the exact pre-transition registry matching
  the historical preparation, and the exact actual current registry. Only the
  reviewed selected registration/catalog projection and append-only receipt row
  may differ. Other schema/rows/catalog mappings refuse.
- Unchanged old ledgers, requests, claims, usage/gaps/clocks and hold pins. The
  unused target preserves its original rows and the new unreviewed setup draft.
  Its later normal mission review, admission and run rows may advance without
  invalidating that historical relationship. This is not permission to advance
  them: their existing owner controls and effect gates remain mandatory.
- Complete original completion/accounting evidence and immutable implementation
  proofs. Historical source is hashed, never imported or executed: existing
  PR181/PR182 requirements remain; PR183 accounting and PR184 setup have separate
  exact allowlists and source epochs. Unknown implementations refuse.

There is no historical registry view or caller-supplied current-hash override.
The original and actual current contexts are compared, with only the two causally
proved registry/catalog facts separated. The original evidence bytes, observation
times, unknown outcomes and both numeric floors are unchanged. A new record binds
that relationship and has its own qualification time, never a new usage sample.

No endpoint, account, native thread, process, telemetry or terminal is contacted.
No load, subscription, new turn, native response, Play/recovery retry, usage reset,
binding change, owner release, clock extension, safety or acceptance follows.

## Operator commands

Use the newly installed source and explicit source-workspace routing. Preparing
this non-executing evidence requires no new execution approval:

```text
python3 -B -m orchestrator.historical_admission --platform PLATFORM --workspace SOURCE qualify TARGET EXISTING_USAGE_DIR NEW_PRIVATE_EVIDENCE_DIR --usage-source EXACT_FROZEN_PR183_SOURCE --setup-source EXACT_FROZEN_PR184_SOURCE
python3 -B -m orchestrator.historical_admission --platform PLATFORM --workspace SOURCE status NEW_PRIVATE_EVIDENCE_DIR
```

Current-source disposable fixtures omit both frozen-source flags. The new evidence
directory must be disjoint and absent. It contains an exclusive intent and result.
Partial or changed records are not overwritten or turned into execution authority.
Status revalidates retained records only; it neither recollects nor retimestamps
the original native/numeric observations. Original freshness requirements are
unchanged. Qualification does not make stale usage fresh.

The optional worker-admission input is explicit:

```text
python3 -B -m orchestrator.worker_phase_admission --platform PLATFORM --workspace SOURCE prepare TARGET EXISTING_TARGET_BINDING EXISTING_USAGE_DIR --local-only --requalification NEW_PRIVATE_EVIDENCE_DIR
```

Omit `--local-only` unless using its separately qualified local repository policy.
The admission preview pins this exact requalification, original accounting,
current reviewed target mission and binding. Another target/report/source refuses.
Its separate exact owner review, stopped writers, verified all-database/private
backups, two one-shot claims and target receipt remain mandatory. Historical
pre-change database copies are explicitly typed, bounded private inputs to that
backup; the ordinary 64-KiB sidecar limit is not globally relaxed. Every copied
historical database and its original must still agree with the closed inventory.

Admission alone starts no run. A separate fresh target Play, current supported
readiness, actual loaded-policy/tracker evidence and existing source/usage/Pause
checks remain mandatory. Unknown activity, terminal state or effects stay unknown.
Old claims and Play/recovery cannot migrate to this path.

## Rollout and qualification

Source, manual merge, safe stopped-writer installation and actual live qualification
are separate. No background dispatcher, telemetry service, download, provider,
GitHub Action or paid CI is introduced. Do not hot-patch an owning observer.

Disposable tests cover complete preservation, registry/schema/catalog and input
epoch drift, changed numeric floors, missing/partial receipts and backups, unrelated
owners, no timer renewal, default-path refusal, exact report binding, separately
reviewed admission and fresh Play, and persistence through legitimate target
history. No fixture reaches a live native host or model. The full local Python
and JavaScript suites are required before source delivery.

### Source qualification — 2026-10-20

The complete local Python suite ran 3,354 cases in 1,279.442 seconds with no
failures/errors and one optional Graphify skip (no reviewed disposable Graphify
executable was supplied). All 40 JavaScript tests, 31 web JavaScript syntax
checks, 359 Python AST checks and `git diff --check` passed. The 27 new tests
include actual disposable setup, exact reviewed admission, verified backups and
a separately confirmed fresh target Play; no fixture uses a live native host.

A separate file-only qualification of the retained pilot evidence succeeded
against the canonical completed setup and its private pre-change backups. It
retained 263,627 original preparation tokens and the unchanged 5,736,373-token
conservative phase ceiling. Its new qualification time did not renew the original
usage observation. Independent preservation checks confirmed the old ledgers,
requests, usage, claims, holds, setup receipt and dashboard binding unchanged.
This is not installation, admission, current native readiness or pilot acceptance;
no native connection, load, turn or replay was performed.
