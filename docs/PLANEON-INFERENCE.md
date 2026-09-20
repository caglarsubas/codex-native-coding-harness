# Issue #38 — Planeon inference contract alignment

Plan saved before implementation against PR #39 merged at
`e804469ed1b01967c60eb96943b665dfc435d2e4`. Issue #38 reissues the existing tenant
integration notes with the Planeon name; it does not grant new service permissions.

## Plan

- [x] Verify the supplied credential matches the existing owner-only, ignored
  `.env` without displaying or copying its value into source or reports.
- [x] Stream executive briefs as well as assistant chat, retaining complete-answer,
  exact model and `local-inference` validation before publishing any output.
- [x] Enforce the local model and bounded output-token contract in the shared
  client; verify both configured models on the explicit availability check.
- [x] Ignore `.planeon/` in all clones and retain redacted, no-retry error behavior.
- [x] Run local regressions and one bounded synthetic live inference check using
  the existing tenancy, without sending real workspace information. A second
  explicit synthetic probe qualifies final stream-usage reporting.
- [x] Record verification, update integration guidance and prepare a manual-merge
  fix PR before returning to the autonomous-workspace roadmap.

No key rotation, quota request, hosted model/fallback, telemetry integration,
Actions workflow, runner provisioning, live ledger change, dashboard restart or
autonomous Play activation is included. Credentials remain server-side. Automatic
fallback is prohibited in the client regardless of the service configuration.

## Contract findings and implementation

The private supplied document and installed `.env` were compared in memory. The
credential and endpoint already matched, and `.env` retained owner-only mode 600;
neither file was rewritten or printed. The configured brief model remains
`ministral-3:8b`; the existing assistant-only selection remains `qwen3.8:27b`.
No key rotation or quota change was necessary.

The assistant already streamed responses. Executive briefs previously used a
blocking request, which was incompatible with long generations through the
documented public-tunnel cutoff. Both now use the existing buffered SSE parser,
request JSON-object output and publish only after completion plus exact local
model/routing and schema validation. Midstream HTTP protocol failures are
sanitized; no error includes upstream bodies or credentials, and no automatic
retry, blocking fallback or hosted-model route is added.

The shared client rejects unsupported models even with direct settings objects,
model overrides, non-streaming generations and noninteger token budgets outside
1,024–2,048 for small models or 1,024–4,096 for the larger allowed models. Both
product entry points retain their existing 2,048/4,096 budgets. Availability
checks now verify the assistant model too, not just the executive-brief model.

Both generation paths explicitly request final stream usage. Missing token counts
stay unknown and exclude that call from complete retained-usage totals. This is
service-reported inference usage, not Codex consumption or a monetary bill.

The repository does not consume the renamed OpenTelemetry attributes or pin the
upstream usage-ledger schema. There is no telemetry code or digest to migrate.
The `.planeon/` ignore rule now travels with every clone instead of relying only
on one checkout's private `.git/info/exclude`. The credential document is never
runtime-loaded, and ignore rules are not a substitute for avoiding force-add.

## Synthetic live checks — 2026-09-20

One authenticated model-list read advertised both configured models and all four
allowlisted local models. The new client then sent two explicitly requested
synthetic executive-brief probes using an empty disposable ledger; no actual
workspace data, source, artifact contents, conversations or identifiers were sent.
Only the normal HTTPS bearer header carried the secret. No real ledger was written.

| Check | Result |
| --- | --- |
| First streamed brief | Valid schema, `finish_reason: stop`, exact `ministral-3:8b`, reported `local-inference`; 12.23 seconds |
| First usage observation | Counts absent when usage was not requested; retained as unknown, not zero |
| Explicit final-usage probe | Valid schema/completion/local routing; 6.93 seconds |
| Service-reported usage for second probe | 959 prompt + 303 completion = 1,262 total tokens |

These are compatibility smoke tests, not a latency comparison, billing audit,
narrative-accuracy qualification, assistant-model generation benchmark or proof of
the server's actual residency. Routing remains the service's assertion. The first
call's unknown usage is not included in the second call's total.

## Local verification and delivery

The focused inference/stream suite has 28 passing tests; the assistant suites have
21 passing tests. New regression cases cover shared request policy, direct-settings
model refusal, assistant availability, SSE-to-retained-brief composition, unchanged
prior state on truncated/unrouted streams, sanitized midstream HTTP errors and the
portable ignore rule. Existing complete/partial/null/tool-call/routing/secret,
429/manual-retry, cache, artifact, action-confirmation and UI guards remain in force.

All 7 JavaScript UI regression files, JavaScript syntax and Git whitespace checks
passed. The initial Python 3.12 full run passed 1,079 tests before the final
`include_usage` flags were added. The final-tree full run executed 1,079 tests with
one error in the existing GitHub-observation concurrency test; all inference and
assistant tests passed, including their separate final focused reruns. This is
not reported as a clean final full-suite pass.

The failing `GitHubRetentionTest.test_concurrent_identical_observations_retain_one_receipt`
passed alone, but its race was independently reproduced on the clean merged
`e804469` baseline using only synthetic fixtures: delay one identical request after
its first receipt lookup, let the other request retain its result, then release
the delayed request. The second authority transaction checks the stale workspace
revision without first rechecking that receipt, raising `Workspace changed before
GitHub observation`. The inference patch changes neither that observer nor its
test. Track/fix this bounded replay race separately; do not weaken the revision
guard or manufacture green evidence for this integration PR.

The actual credential was compared against all 195 tracked/new-document files and
the staged diff without exposing it: absent. No private `.env` or credential
document is staged. Read-only GitHub checks found zero configured Actions workflows
and zero Actions runs. No workflow, runner or paid service was introduced; local
validation preserves the owner's no-extra-Actions-billing boundary.

The fix PR closes issue #38 on manual merge. Installed code/dashboard runtime are
not automatically replaced, and no restart or autonomous Play is claimed. Return
to the workspace/autopilot roadmap after this prerequisite is merged; do not mix
native lifecycle changes or live activation into the credential-integration fix.
