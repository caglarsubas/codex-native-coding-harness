# Codex Orchestrator — personal tooling

This is private development tooling, not a Harness product repository. Do not
edit Harness product checkouts from this workspace. Product workers must follow
their own approved packet, allowedPaths, AGENTS.md and trusted execution rules.

Use Python standard-library tooling. No runtime downloads or external telemetry.
The user-authorized optional llm-inference-engine integration is the only model
service exception: load its credential server-side from a Git-ignored .env, send
only the documented bounded status projection and, for assistant chat, explicitly
submitted messages plus bounded process/capability/decision/artifact metadata on explicit request,
use an allowlisted on-prem model, and never dispatch or mutate based on model output alone.
Chat may propose only server-catalogued existing typed controls. A separate explicit owner
confirmation of the exact, signed, expiring, revision-bound preview is required before the
normal ledger submission and notification path. No model-authored commands, direct native
execution, implicit packet approvals or inferred confirmations. Keep durable command receipts
separate from transient chat, and preserve every existing control gate.
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

Workspace mission/phase authority records are configuration-only in WSP-03A.
Owner review is not packet approval, delegation, enforced budget or activation.
The brain can propose drafts under its controller but cannot review/revoke them.
Do not read `reviewed` as executable authority or auto-activate on upgrade. See
docs/MISSIONS.md; resource/budget admission and run/checkpoint gates must ship
before a separate exact owner-bound activation can enable autonomous Play.

WSP-04A's admission kernel is capacity accounting, not execution authority. It
has no allocation/dispatch write route or native-dispatch integration. Do not initialize
live allocations, auto-adopt owners or change legacy dispatch during an upgrade.
The explicit platform-resources command is read-only, bounded metadata inspection;
its snapshot is not a lock. WSP-04B must implement legacy-owner adoption, authority
fences and cross-database recovery before using the kernel for native operations.

WSP-04B1 enrollment is an explicit maintenance fence, not activation. Do not run
platform-enroll or its recovery on live state merely because tooling is upgraded.
It has no unfence path in this version. Retain both the private file and SQLite
fence; never delete them to bypass a refusal. Updated legacy --state commands
must honor either signal. Only safe-stop supervision and reconciliation of
existing native work may continue; no new tasks, acceptance, retries or merges.
See docs/ENROLLMENT.md for exact scope, recovery and remaining activation gates.

WSP-04B2 provides explicit owner-confirmed quarantined ownership import only.
See docs/OWNERSHIP-ADOPTION.md. No automatic live adoption, guessed resource
identity, zero-usage assumption or implicit budget grant. Preserve every owner
version and both platform sidecars; do not delete a fence or pin to recover.
Imported ownership is not verified native inventory or executable run authority.
An empty recorded inventory is not proof of free global capacity. Kernel policy
initialization is allowed only by this exact maintenance review or isolated tests;
new allocations remain unavailable through public routes.
