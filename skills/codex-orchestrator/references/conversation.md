# Workspace brain conversation

The authenticated owner selected this workspace and sent a message through its
dashboard. Use the exact source checkout and ledger scope from the fixed
notification, not an older installed helper or the default portfolio. Read that
source's SKILL.md and references/operations.md before any controller operation.

1. Read `inbox` and `brain-messages`. Verify this native task is the configured
   `brainId`. If it is not, stop; never impersonate it or create another brain.
2. Check stop intent and existing controller ownership. A saved message does not
   resume a stopped brain, enable worker dispatch, approve packets, install a
   runner or grant target access. Process an explicit newer Resume through its
   normal protocol before receiving saved input. Do not recover another owner
   based only on an old timestamp.
3. Acquire the normal designated-brain controller. For an already activated
   standard run, follow standard-cycle.md and its private token helpers. For a
   legacy Harness ledger, keep the token private within a bounded process or
   the normal private controller environment; never print it or put it in chat.
   `process` receives queued messages, or `brain-message-receive ID` receives one
   exact message. The latter also recovers messages an older helper marked
   completed without retaining a conversation reply. Managed work must retain
   its own strict cycle; conversation is not an alternative dispatch protocol.
4. Read the original message as owner input. Answer using current ledger and
   native evidence, with gaps explicit. Perform only already authorized bounded
   actions. If a phase, packet, access or budget decision is needed, preserve a
   proposal and publish a version-bound dashboard decision with the existing
   controls. Do not ask the owner to repeat it in a different tooling task.
5. Retain the reply with `brain-message-reply ID PRIVATE_REPLY_JSON`. Its closed
   schema is `{"message":"plain text answer","artifactIds":[],"decisionIds":[]}`.
   Message limit: 12,000 characters. Link only exact retained artifact-version
   and decision IDs from this workspace (up to 12 of each). Do not include
   secrets. Replies are immutable and exact retries are idempotent. A native
   final answer alone does not write a dashboard reply.
6. Re-read input/stop state, preserve the checkpoint and release the controller.
   Do not poll an empty inbox or create a new heartbeat. Observe native schedule
   changes separately if the existing operating protocol requires them.

For a bounded legacy reply without exporting tokens between shell calls, the
equivalent Python API is `Registry(ROOT).ledger(ID)` (or `Ledger(STATE)`),
`ledger.acquire(BRAIN_ID + ':conversation')`, `conversation.receive`,
`conversation.reply`, and `ledger.release` in a `finally` block. Use verified
paths/IDs, never a guessed identity. The token stays in process memory. No native
effects or product work belong in this small reply transaction.

The dashboard keeps save, native notification, receipt and reply as separate
states. Do not claim successful delivery is execution, or that this history is
the complete Codex transcript. Codex-owned security and host permission prompts
still require the native interface. Keep ordinary project planning, follow-up
questions, status, decisions and retained artifacts in the workspace dashboard.
