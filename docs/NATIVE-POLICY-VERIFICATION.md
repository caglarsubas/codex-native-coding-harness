# Owned standard Code Mode policy verification

## What failed

The reviewed binding requires workspace-write, on-request and Code Mode off.
The bridge already sends the nested `features.code_mode.enabled=false` override.
Its metadata-only resume response reports sandbox, approval policy and reviewer,
but the installed v1 protocol has no effective tool-mode or tool-surface field.
The feature override's acknowledgement is not proof that Code Mode is disabled.
Public runtime source also allows model tool-mode metadata to take precedence
over feature flags. An exposed `functions.exec` contradicts an off assumption;
a separate disk-config probe cannot establish the active thread's policy.

Previously `standard-host-inspect` reported this only as a gap while its issues
could be empty. Cooperative brain guidance could stop, but standard claim/issue
and Resume had no corresponding retained-policy gate.

## Source behavior

- Host inspection retains the original null Code Mode report and gap, and adds
  `native_code_mode_unverified`. No request value becomes an observed value.
- `standard_native_policy` reads only saved command metadata for the exact run.
  It projects configured, acknowledged and native-reported dimensions separately,
  with the original observation time. Missing, changed, foreign or malformed
  profiles remain unverified. An older matching profile cannot replace a newer
  unavailable handoff. Unsolicited `codeMode`, tool names or `policyVerified`
  fields do not introduce an unsupported native attestation format.
- Existing standard admission checks fence claim, issue, merge and Resume once
  this owned-run handoff exists. Non-owned transports keep their existing separate
  contract; strict Harness is unchanged. Safety receipts, read-only observations,
  usage refresh and checkpoint retention remain available.
- The paused workspace leads with **Codex policy verification is blocked** and
  **Inspect policy evidence**, not a new recovery wake or prompt-writing task.

This change closes the application's fail-open verification gap. It does **not**
make the current native runtime report or enforce Code Mode off. The installed
v1 owned policy path is therefore not qualified for new effects or Resume. A
future effective-policy evidence adapter needs actual supported runtime evidence
and separate qualification; this patch creates no caller-authored proof escape.
Do not disable the shared Code Mode host, switch models, modify vendor binaries
or weaken the owner-reviewed policy to bypass this refusal.

## Rollout and fresh pilot

Source, manual merge, installation and live qualification remain separate. Keep
the accepted Play and all prior controls byte-identical; no profile/report is
backfilled. Quiesce older writers and back up private state before installation.
Preserve cumulative usage, gaps, original expiry, checkpoint and native ownership.
An ended turn or unloaded thread is not known-empty tracked-terminal evidence.
No Play/recovery replay, native load, host launch/rebind, implicit Resume or pilot
acceptance follows source delivery. Current paused state remains paused.

## Inspector resize regression

A media-query listener updates dialog/complementary semantics independently of
render and polling. It preserves a visible composer, draft, caret and focus;
an open narrow sheet makes background controls inert, traps keyboard focus and
restores original inert states on close, desktop reflow or workspace teardown.
Outside focus moves inside an opening modal; a hidden sheet-only control cannot
retain desktop focus. No command or request follows resizing.

Local tests use synthetic protocol metadata and disposable projects. Verify both
resize directions with a focused draft, closed/open sheets, keyboard Escape/Tab,
320px reflow, reduced motion and project-switch listener cleanup. Passing these
checks is source/UI evidence, not native runtime qualification or pilot success.

Primary references: [configuration](https://learn.chatgpt.com/docs/config-file/config-reference),
[app-server protocol](https://learn.chatgpt.com/docs/app-server), and
[runtime tool-mode resolution](https://github.com/openai/codex/blob/a68a7a6ab05242735b816c71dfa4c3f794c6efd7/codex-rs/core/src/tools/mod.rs).

## Local source verification (2026-10-13)

- 2,426 Python tests passed; one optional dependency test skipped.
- All 36 JavaScript suites, 31 web-script syntax checks and 109 Python module
  AST checks passed. Whitespace/diff checks passed.
- Disposable rendered checks passed at 320, 375, 799, 800 and 1440px, including
  focused drafts/carets across both resize directions, Tab/Shift+Tab, Escape,
  closed-sheet resize, hidden Close focus correction, polling, reduced motion
  and project switching. No horizontal overflow, JavaScript errors, control
  submissions or native actions were observed.
- Policy fixtures verify an unknown effective setting cannot permit claim,
  issue or Resume, while receipt/checkpoint paths remain available and retained
  usage/expiry stay unchanged. Unsolicited fields cannot qualify the runtime.

These are local source/fixture results, not CI, installation, live native policy
qualification or pilot acceptance. No GitHub Actions workflow is configured or
added. The native runtime's missing effective-policy evidence remains a blocker.
