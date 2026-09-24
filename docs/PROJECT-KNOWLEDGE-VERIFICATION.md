# Durable knowledge milestone — evidence ledger

This separates source implementation from installation, merge and live
qualification. None of these entries grants standard Play, a brain replacement
or strict Harness execution authority.

| Item | Implemented source | Local verification | Not yet qualified |
| --- | --- | --- | --- |
| KNW-01 | `brain_memory.py`, standard admission/projection, immutable usage and terminal closeout snapshots | Duplicate, prefix, reset, malformed, delayed closeout, new-brain baseline, concurrency/high-water and budget-gate tests | Provider billing completeness or a hard provider cap |
| KNW-02 | Private allowlisted Git index, optional Graphify 0.9.66 executable/version/hash adapter, content manifest and retained record links | Mocked safety tests plus actual 0.9.66 code-only/no-cluster extraction in a disposable Git project; cross-file relationship resolved; real PEM marker refused while source-code literal is accepted | Owner-reviewed installation and live-project configuration; complete dependency attestation is not claimed |
| KNW-03 | Knowledge status/refresh/search/source/related/records API and CLI, dashboard view, direct HEAD fallback, bounded worker references and advisory metadata-only context | HTTP project/auth/CSRF test, Knowledge UI test, rendered isolated fixture search/source/real Graphify relationship review and fixed 20-question retrieval evaluation | Fresh-index quality on a selected live project |
| KNW-04 | Immutable package, two signed owner previews, one-shot native candidate, final-reply-bound package receipt, exact registry rebinding and fail-closed interrupted-commit repair | Disposable local Git/project fixture, wrong project, missing/stale/non-final/wrong-summary native reply, stale review, unsettled work, replay and recovery tests | Real disposable native Codex task receipt, independent native project-membership attestation and owner-reviewed browser handoff |
| KNW-05 | Fixed evaluation suite and this separate evidence ledger | 19/20 expected owner modules in top ten, two missing-evidence questions with no citation; local suites reported separately below | Merge, optional provider installation and explicit selected standard-project activation |

The 20 questions and expected sources are fixed in
`tests/test_knowledge_eval.py`. They are implementation-location questions,
not an acceptance test for semantic correctness of arbitrary answers. The
search result is a versioned hint; every returned citation is opened against
its recorded Git blob in the test. The one missed expected module remains a
quality gap, not a reason to invent a citation. No question or excerpt goes to
the inference tenancy: the assistant sees only index metadata and a Knowledge
navigation destination.

## Local regression record

- Python: previous PR #78 qualification ran the disposable Graphify test with
  its explicit executable. This handoff-hardening run completed 1,720 tests:
  1,719 passed and the optional Graphify executable test was skipped because
  `GRAPHIFY_TEST_EXECUTABLE` was not configured. The handoff tests passed again
  after the final receipt-evidence edit.
- JavaScript: 23 local tests passed, including Knowledge UI.
- Rendered browser: isolated local fixture displayed index status, accepted a
  scoped search, opened the versioned Git source, and displayed real Graphify
  `EXTRACTED` cross-file relationships. One-time fixture browser tokens were
  removed after QA. No live service was restarted.
- Graphify qualification: disposable Python 3.12 virtual environment with
  `graphifyy==0.9.66`; local fixture extraction produced a graph and related
  `src/service.py` to `src/helper.py` without a configured model key. The
  official 0.9.66 wheel SHA-256 is
  `104f1e148ecde571c3a8253a7121bfff7966f6cf907720d1e274c31bbc4b8931`.
  This tested environment is not a platform installation or a proof of
  network isolation. The disposable environment was moved to local Trash
  after testing; it was never installed into the platform.
- Syntax and whitespace: Python compile, JavaScript checks and `git diff --check`
  passed.
- GitHub Actions: no workflow directory in this repository; none was added or
  triggered. GitHub checks are not represented as passing by their absence.

## Rollout states

| Boundary | State |
| --- | --- |
| Source baseline | PR #77 merged as `7a90302e334945f1be32a6bd2038e34f63269e6e`; PR #78 merged as `f122790e4edb7c2dc688303bc0682d7cf26615ec` |
| Pull request / merge for final-reply handoff hardening | This source change is not yet merged or installed |
| Optional Graphify installation | Disposable venv tested; no platform installation |
| Installed dashboard/backend revision | Not changed by this source work |
| Selected standard-project activation | Not requested or performed |
| Strict Harness qualification | Not claimed; existing strict gates unchanged |

Source merge alone cannot satisfy the remaining live and native-tool evidence.
Owner must explicitly review an installation/activation proposal later.
