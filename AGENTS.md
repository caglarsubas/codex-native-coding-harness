# Codex Orchestrator — personal tooling

This is private development tooling, not a Harness product repository. Do not
edit Harness product checkouts from this workspace. Product workers must follow
their own approved packet, allowedPaths, AGENTS.md and trusted execution rules.

Use Python standard-library tooling. No runtime downloads or external telemetry.
The user-authorized optional llm-inference-engine integration is the only model
service exception: load its credential server-side from a Git-ignored .env, send
only the documented bounded status projection on explicit request, use an
allowlisted on-prem model, and never dispatch or mutate based on model output.
Never commit endpoint credentials or the supplied credential document. No hosted
provider fallback or new paid-service integration. The installed PyYAML is used
only by the read-only packet importer; it never executes a packet. Tests use
temporary fixture repos.

Run `python3 -m unittest discover -s tests -v` and `node --check web/app.js`.
Keep `.state/` private. Never commit auth tokens, conversation transcripts or
the live SQLite database. No background dispatcher or private Codex API: native
task operations are performed by the brain using the installed personal skill.

Dispatch defaults to paused. Queue authorization must identify exact packet and
seed hashes. A request to build this controller is not product packet approval.
