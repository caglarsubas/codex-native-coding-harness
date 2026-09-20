# Runner handoff verification

Scope: WSP-04D4, based on merged PR #33 at exact commit
`2c1acc3478e950fece554f62c211223ae7825990`. PR #33 was independently verified merged
at `2026-09-20T02:52:20Z`; the fetched `origin/main` matched that merge commit.

## Evidence boundaries

| Boundary | Result |
| --- | --- |
| Source | Selected-workspace runner CLI, exact acceptance message handoff and single-use launch/send check |
| Delivery | Caller-supplied acknowledgment/uncertainty retained separately in the existing shared journal |
| Execution | Process identity, exit and cleanup require independent observations; no test process or native message is invoked by this helper |
| Recovery | Local/shared launch boundaries retained; receipt recovery and replay cannot reissue send permission |
| Live state | No live allocation, ledger write, task message, settings/schedule change, skill installation or dashboard restart |
| Acceptance | No real pilot, trusted Harness run, autonomous Play, hosted CI or deployment claim |

The orchestration skill's designated-brain and approval boundaries shaped this
implementation: no helper scheduler or implicit product dispatch. The active
native tool contract accepts existing task/host/message fields and optional
settings; the generated handoff supplies only the former. No actual native call
was made to validate delivery. Complete descendant/counter and host evidence
collection remains unqualified, as documented in the roadmap.

## Local verification

```sh
python3 -m unittest discover -s tests -v
node --check web/app.js
node --test tests/test_*_ui.js
git diff --check
```

Python 3.12: **949 tests passed**, including **35 new runner-handoff tests**.
All **7 JavaScript UI test files passed**. Syntax and whitespace checks passed.
No UI behavior changes in this increment; this is not rendered-browser evidence.
Hosted checks, source merge and live runtime must be verified independently.

## Fixture coverage

- Real subprocess CLI round trip through reservation, prepare/check, delivery,
  process exit, cleanup release, status and receipt recovery in private fixtures.
- Exact confirmed local native identity, owner-approved execution, no model or
  effort overrides, no arbitrary prompt input and no instruction-body injection.
- Concurrent preparation/send checks return at most one fresh handoff/permission;
  repeated checks, historic coordinator receipts and recovery cannot send again.
- Fresh idle/cleanup evidence, account headroom, missing phase counter coverage,
  approval revocation, worker checkpoint controls and maintenance fences.
- Artifact bytes/repository and handoff document/pointer tampering, closed input
  shapes, reused request IDs, wrong controller/workspace/host/task, bounded files
  and symlink refusal.
- Pause before check; Pause/preflight/artifact changes between local/shared
  launch commits; crash after shared launch/delivery commit before local receipt.
- Uncertain delivery holds resources; acknowledgment does not promote activity
  or acceptance; historical replay preserves newer process state and timestamps.
- Nonzero process exit stays distinct from cleanup. Runner-only release keeps
  repository ownership, task attempt and conservative token holds.
- Subprocess guard confirms the handoff itself never executes commands. Existing
  runner contention, settlement, phase accounting and pause regressions also pass.

No live secrets, account identifiers, private prompts or inference credentials
are included. All new test IDs, runner/process keys and evidence are synthetic.
