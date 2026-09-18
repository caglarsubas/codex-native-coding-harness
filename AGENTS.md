# Codex Orchestrator — personal tooling

This is private development tooling, not a Harness product repository. Do not
edit Harness product checkouts from this workspace. Product workers must follow
their own approved packet, allowedPaths, AGENTS.md and trusted execution rules.

Use Python standard-library tooling. No runtime downloads or external telemetry.
The user-authorized optional llm-inference-engine integration is the only model
service exception: load its credential server-side from a Git-ignored .env, send
only the documented bounded status projection and, for assistant chat, explicitly
submitted messages plus bounded decision/artifact metadata on explicit request, use an
allowlisted on-prem model, and never dispatch or mutate based on model output.
Never commit endpoint credentials or the supplied credential document. No hosted
provider fallback or new paid-service integration. The installed PyYAML is used
only by the read-only packet importer; it never executes a packet. Tests use
temporary fixture repos.

Run `python3 -m unittest discover -s tests -v` and `node --check web/app.js`.
Keep `.state/` private. Never commit auth tokens, conversation transcripts or
the live SQLite database. No background dispatcher or private Codex API. The
owner-authorized notification bridge may invoke only the installed `codex queue`
CLI with a fixed message to the configured existing brain after a validated,
committed dashboard decision response or typed resume/reconcile/checkpoint/archive/
brain_stop/brain_resume or locally applied approve/hold/prioritize/listening/pause
control awaiting its brain receipt. A brain stop is a cooperative checkpoint, never
a process kill. Saved ordinary inputs do not wake a stopping/parked brain; only
explicit brain resume does. No response text, arbitrary argv, target,
model or effort comes from the browser. Claim before sending; never blindly retry
uncertain delivery. All worker operations and authority remain with the brain.

Dispatch defaults to paused. Queue authorization must identify exact packet and
seed hashes. A request to build this controller is not product packet approval.
