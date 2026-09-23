# Durable knowledge milestone — evidence ledger

This separates source implementation from installation, merge and live
qualification. None of these entries grants standard Play, a brain replacement
or strict Harness execution authority.

| Item | Implemented source | Local verification | Not yet qualified |
| --- | --- | --- | --- |
| KNW-01 | `brain_memory.py`, standard admission/projection, immutable usage and terminal closeout snapshots | Duplicate, prefix, reset, malformed, delayed closeout, new-brain baseline, concurrency/high-water and budget-gate tests | Provider billing completeness or a hard provider cap |
| KNW-02 | Private allowlisted Git index, optional Graphify 0.9.66 executable/version/hash adapter, content manifest and retained record links | Mocked code-only provider, secret/symlink/scope, stale-index and history tests | Installed Graphify binary and actual structural extraction on a selected project |
| KNW-03 | Knowledge status/refresh/search/source/related/records API and CLI, dashboard view, direct HEAD fallback, bounded worker references and advisory metadata-only context | HTTP project/auth/CSRF test, Knowledge UI test, rendered isolated fixture search/source review and fixed 20-question retrieval evaluation | Installed-backend review; fresh-index quality on a live project |
| KNW-04 | Immutable package, two signed owner previews, one-shot native candidate and package receipt, exact registry rebinding and fail-closed interrupted-commit repair | Disposable local Git/project fixture, wrong project, missing native log, stale review, unsettled work, replay and recovery tests | Real disposable native Codex task receipt and owner-reviewed browser handoff |
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

- Python: 1,717 tests passed in the complete local suite.
- JavaScript: 23 local tests passed, including Knowledge UI.
- Rendered browser: isolated local fixture displayed index status, accepted a
  scoped search and opened the versioned Git source. The one-time fixture
  browser token was removed after QA. No live service was restarted.
- Syntax and whitespace: Python compile, JavaScript checks and `git diff --check`
  passed.
- GitHub Actions: no workflow directory in this repository; none was added or
  triggered. GitHub checks are not represented as passing by their absence.

## Rollout states

| Boundary | State |
| --- | --- |
| Source branch | In progress in this checkout |
| Pull request / merge | Not yet established in this document |
| Optional Graphify installation | Not installed; source-only adapter tests |
| Installed dashboard/backend revision | Not changed by this source work |
| Selected standard-project activation | Not requested or performed |
| Strict Harness qualification | Not claimed; existing strict gates unchanged |

Source merge alone cannot satisfy the remaining live and native-tool evidence.
Owner must explicitly review an installation/activation proposal later.
