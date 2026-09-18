# Operational assistant verification — 2026-09-18

## Implemented boundary

`chat → current bounded evidence + capability catalog → inert action preview →
explicit owner confirmation → existing typed ledger control → one-shot notification
→ brain receipt → recorded outcome`.

The model is neither the orchestrator brain nor a native executor. Its proposed
key resolves to a fixed server-owned command and target. HMAC signing, the current
dashboard session, a five-minute expiry and the exact ledger revision bind the
preview. Existing decision, worker, dispatch and safe-checkpoint validation remains
authoritative. Replayed confirmations keep one command ID; an uncertain native
notification is never blindly resent.

## Verified locally

- Python regression suite, JS presentation/geometry checks and syntax checks.
- Host/Origin/session/CSRF protections on context, chat and confirmation.
- No ledger mutation from context, inference, a model suggestion or a dismissed preview.
- Signature/payload/target tampering, wrong session, server restart, expiry and
  changed revision refuse confirmation. Concurrent retries produce one command.
- Existing one-shot native notification works for the server-authored
  `assistant_owner_confirmed` actor (mocked CLI; no real task wake for this test).
- Free-text answers are exact latest-message excerpts with exact decision-version
  binding, no inferred option and no execution/packet approval.
- Browser fixture: stop request is not represented as parked/completed; disabled
  notification is visible; answers stay saved while the brain is stopping.
- Browser fixture: action cards show actual receipts, lock duplicate submission,
  follow the precise decision link, reject changed-state previews, and dismiss
  without creating a control. Desktop and 390-pixel layouts were inspected.
- No console errors in the isolated fixture. Real browser chat/drafts are not
  replaced by fixture data. `.env` stays ignored and mode 600; no credential value
  or private live ledger/transcript is committed.

## Inference transport evidence

The configured service lists the expected on-prem models. A minimal request to
the configured `qwen3.8:27b` returned local routing in 4.9 seconds; a minimal SSE
request completed in 3.3 seconds. Richer blocking requests timed out, and a
1,024-token attempt was correctly rejected as incomplete. None created a control.

The supplied service contract identifies a roughly 120-second public-tunnel cutoff
for blocking requests and recommends SSE for longer generations. Chat now consumes
bounded server-side SSE, keeping partial text/actions private until completion and
schema/routing validation. The overview context was reduced from roughly 36 KB
to 20 KB, with more detail in the matching workspace views and explicit coverage.

Live richer-context SSE validation is tracked in the roadmap. Model factual accuracy,
inference availability/latency, real safe-checkpoint completion and worker acceptance
remain separate from unit tests, fixture results, publication and merge status.

## Source integration

PR #11 was merged into the brain-control branch after PR #9 had already merged
to main. This increment includes that merged assistant/pane baseline when targeting
main; a PR merge into an already-merged side branch is not evidence it reached main.
