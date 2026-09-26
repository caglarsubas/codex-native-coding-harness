# Workspace brain conversation

## Project outcomes in the conversation

The newest conversation page includes a read-only **Project activity** section
above message replies. It shows the latest five retained cooperative phases
(bounded to 100 recorded versions), checkpoint summaries, task outcomes, source,
test and preservation evidence, and exact GitHub PR links found in retained results.
This makes run completion visible even when Play was a typed control rather than
a chat message; it does not rewrite an earlier reply or require another model turn.

PR state comes only from saved, same-project Git observations with their original
timestamps. Without an observation it is explicitly unknown. Use **Git & delivery
→ Refresh GitHub status**, then return to the conversation to see the updated
observation. A failed refresh leaves older observations labelled as such. Open,
closed and merged have distinct next actions; phase completion never implies PR
merge or deployment. Result reads validate their retained digest and task/run IDs.

This is not a complete Codex transcript: native-only messages, security prompts,
and unrecorded legacy/strict outcomes are not mirrored. No native calls, GitHub
requests, approvals, merge actions, or model calls are performed by reading this
feed. Inference context does not receive these full result bodies.

Owner request, 2026-09-21: select the real multi-repository project and manage
routine Codex interaction in the dashboard, not in the tooling-development chat.

## Delivery plan

- Register the existing Harness ledger in place, with a verified backup, without
  copying its brain, approving work or opting it into the standard protocol.
- Show the selected project's introduction, repository membership and existing
  brain identity. Keep pilot workspaces explicitly labelled as disposable.
- Add a durable workspace-scoped conversation separate from inference chat.
  Send only a fixed notification to the configured existing Codex brain.
- Preserve saved, delivered, received and replied as distinct states. Retain
  original messages/replies, exact artifact and decision links, and failed or
  uncertain delivery without automatic retries.
- Keep approvals and safe-stop/resume in their existing typed controls. A chat
  message neither overrides a stopped brain nor grants packet/target authority.
- Verify cross-workspace routing, stale forms, replay, Pause, restart, safe text
  rendering and real dashboard presentation. Run tests locally; no Actions.

## Contract

A message is an explicitly confirmed `reconcile` request with the closed payload
`{message, brainId, confirmed}`. The configured brain ID must still match at save
and receipt. The owner cannot select an arbitrary recipient, shell command,
model, effort or transport. Text is stored privately in the ledger and is never
placed in the native CLI arguments or sent automatically to inference.

The compatible reconcile envelope permits an older helper to acknowledge a
request without mistaking it for a worker action. That acknowledgment is **not**
a conversation reply: only the designated brain's dedicated reply operation
closes the conversation. The updated notification directs the brain to the exact
source checkout and workspace protocol. Older installed skills are not silently
replaced. Pending unanswered messages remain visible even if an older helper
marked the control complete.

One unanswered conversation request per workspace prevents accidental duplicate
work. The owner can still use Pause, Resume, decisions and other controls. Paused
brains keep messages saved without waking; Resume drains the inbox. Messages
may request explanation/planning or work within existing reviewed authority;
new packet, phase, access, installation, budget and merge permissions still need
their existing exact approval flow. Native security/OS prompts cannot be
automatically approved by this dashboard.

The conversation displays only messages sent through this platform and replies
retained by its brain, not a fabricated mirror of the whole Codex transcript.
Existing checkpoints, activity, decisions, artifacts and workers remain visible.
History is paginated, oldest first within each page, with newest page by default.
Reading/polling never wakes a model or refreshes evidence timestamps.

## Local rollout

Serve the registry containing the actual project ledger, not a disposable-pilot
registry. Existing ledger identity checks (including single-link databases) are
not bypassed by this feature. If those checks fail, retain the current runtime
and request explicit recovery approval before replacing or rebinding live state.

The startup-only `serve --inference-env /absolute/private/.env` option can reuse
the owner's existing inference tenancy when serving from an isolated source
checkout. It is never a browser-supplied path; the file and its credentials stay
outside Git. Conversation uses the configured native Codex notification transport,
not the inference endpoint. The legacy desktop queue can acknowledge without
starting an unloaded brain; see [owned wake](OWNED-BRAIN-WAKE.md) for the
separately reviewed standard-project alternative.
