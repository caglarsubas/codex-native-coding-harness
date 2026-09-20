# Optional portfolio intelligence

The integration with the Planeon `llm-inference-engine` tenancy provides an on-demand executive brief
on **Overview**: what is recorded, what needs attention, and read-only next steps.
The model is an adviser, never the brain, a scheduler, or an approval authority.
Dispatch, heartbeat, pilot and repository merge policies are unchanged.

The right-side [AI assistant](ASSISTANT.md) reuses the same server-side tenancy.
Unlike the aggregate-only brief, explicit chat sends submitted messages and the
bounded decision/artifact metadata documented below. Neither feature has tools
or controller authority.

## Configure locally

1. Copy `.env.example` to `.env` in the controller checkout, then set mode `600`.
2. Set `CODEX_LLM_BASE_URL` to the supplied HTTPS base ending in `/v1`, set
   `CODEX_LLM_API_KEY` privately, and select `CODEX_LLM_MODEL`.
3. Keep the default `ministral-3:8b` for low-overhead briefs. The explicit local
   allowlist also includes `qwen3.8:27b`, `gemma4:26b`, and `llama3.2:3b`.
   Optional `CODEX_LLM_ASSISTANT_MODEL` selects a different model from this same
   allowlist for chat only. Omit it to reuse the brief model. The endpoint and
   bearer tenancy remain shared; neither model is selectable from the browser.
4. Run `python3 -m orchestrator.cli inference-check` to verify both configured models
   are advertised, then choose **Generate brief**
   on Overview, or run `python3 -m orchestrator.cli executive-summary`.

The CLI and dashboard load the same file on demand; configuration changes do not
require exporting environment variables. This is a simple key/value file, not a
shell script: no interpolation, `source`, or command execution. Files with group
or world access, symlinks, duplicate settings or non-HTTPS URLs are refused.
Do not put real endpoints or credentials in tracked examples, docs or screenshots.
`.env` and `.env.*` are ignored; only the credential-free `.env.example` is tracked.
Keep the supplied credential document outside the repository or in its ignored
`.planeon/` directory; never force-add it. Ignore rules prevent accidental staging,
not deliberate publication. The document is not runtime configuration: `.env`
remains the only credential source. Never print its value in diagnostics.

All portfolios in one checkout share this server-side configuration. Separate
checkouts/configurations are required for separate service identities; selecting a
portfolio does not change tenant identity. Bearer authentication alone determines
the service tenant/org. The client does not send tenant headers or overrides.

## Executive-brief data boundary

The executive-brief request contains a fixed instruction plus eight allowlisted facts:

| Evidence | Contents |
|---|---|
| F1 | Paused/pilot/heartbeat states, queue/worker counts, reconciliation time |
| F2 | Configured, mapped/unmapped and measured/unmeasured repository counts |
| F3 | Aggregate tracked-file, physical-line and character counts |
| F4 | Aggregate retained task/message/token counts, cache rate and coverage gaps |
| F5 | Local Git repository, worktree, dirty-worktree and branch counts |
| F6 | Bounded observed PR states, repository count and observation age |
| F7 | Roadmap checkbox counts and artifact version count excluding briefs |
| F8 | Local observation time/status and brain freshness |

No repository names, paths, native task IDs, source files, prompts/transcripts,
checkpoint prose, artifact contents, or credentials enter the model prompt.
**Inspect evidence & data sent** shows the current projection before a request and
the immutable projection used for the displayed answer. Aggregates are still
private operational data: enabling this feature authorizes sending them to your
configured service. The bearer key is necessarily sent as an HTTPS auth header,
only server-side; it never enters browser state or the model prompt.

The client disables ambient HTTP proxies and refuses redirects. It only calls
`GET /v1/models` and `POST /v1/chat/completions`, permits documented on-prem model
IDs, and rejects answers whose reported model/routing differ. It never requests
OpenRouter models, retries automatically, or falls back to an external provider.
The service's `local-inference` field is a routing assertion, not an independent
attestation of the server's execution. The supplied key itself may have wider
permissions; this client allowlist is not a server-side key policy. Ask the service
owner for a restricted key if stronger account-level enforcement is needed.

## Lifecycle, quality and limits

- Generation is explicit. Page loads, polling, local observation refreshes and
  scheduled brain reconciliation never make model requests.
- One request per portfolio can run at a time across CLI and dashboard. This is
  not a global tenant quota; other portfolios/clients can still contend.
- A matching snapshot/model/prompt version is reused for 15 minutes. A new source
  snapshot invalidates it; **Regenerate brief** explicitly bypasses this cache.
- Both briefs and chat use server-side SSE and JSON-object output. Partial text
  is buffered privately until completion and schema/routing validation; a failed
  stream retains the previous brief. There is no blocking-generation fallback.
  Requests use 2,048 output tokens for small models (4,096 for the larger models);
  the shared client refuses budgets below 1,024, above the model cap, noninteger
  budgets and model overrides. A 90-second socket timeout, 240-second processing
  window checked at each read and bounded stream size apply. This is not a hard
  whole-request deadline while a socket read is pending. There is no background retry.
- HTTP 429 gives a manual retry hint. Authentication errors, timeouts, null or
  truncated answers, unexpected models/routing, tool calls, invalid JSON/schema,
  or unknown evidence IDs keep the previous brief and show an explicit failure.
- Next-step control-action patterns are conservatively rejected as an additional
  safeguard. This is not semantic verification. Narrative claims and numeric
  interpretations still require human review; the output never operates controls.
- Every successful brief becomes an immutable JSON artifact version, ordered by
  generation time. Earlier versions remain readable in Artifact library. Export
  includes the last brief with its original evidence, not a fresh verification.
- Streams explicitly request final usage with `stream_options.include_usage`.
  Prompt/completion token counts are service-reported, separate from Codex usage.
  If the service omits them, they remain unknown, not zero.
  Retained-brief totals exclude failed/discarded calls and older versions without
  usage metadata. They are not complete account usage or a currency estimate.
- The supplied service is a shared single-node proof of concept, not a production
  SLA. Its benchmark is grounded QA, not demonstrated coding-agent competence.
- The documented tenant queue holds four requests; overflow returns 429 with a
  retry hint. The local portfolio lock is not a cross-client tenant queue limit.
  Do not retry automatically or request quota increases without owner approval.
- Embeddings and local vision are unsupported by the supplied contract. No vector
  search, screenshot understanding, or autonomous coding dependency is added.

Use `python3 -m orchestrator.cli inference-status` for configuration/freshness and
`python3 -m orchestrator.cli executive-summary --force` for an explicit new answer.
Removing `.env` disables new requests without affecting orchestration or retained
briefs. Stopping a server can abandon an in-flight response; restart never retries
it automatically. Native task lifecycle remains exclusively in Codex.

### Planeon contract update

[Issue #38](https://github.com/caglarsubas/codex-native-coding-harness/issues/38)
reissued the existing tenant notes under the Planeon name; no new key/endpoint was
required. This client does not consume OpenTelemetry attributes or pin the model
plane usage-ledger schema, so the `planeon.*` / `planeon-model-usage-v2.schema.json`
rename needs no telemetry migration here. It does not add external telemetry.
See [contract alignment and verification](PLANEON-INFERENCE.md). Live configuration
checks, merged source, installed source and dashboard runtime remain separate.

## Assistant chat data boundary

`POST /api/assistant` requires the same loopback Host/Origin, authenticated session
and CSRF checks as dashboard controls, but never invokes those controls itself. It accepts
only a whitelisted current view and alternating user/assistant message data (at
most four prior exchanges plus the new question; 4,000 characters per message,
16,000 combined). The fixed instruction, model, endpoint and credential remain
server-owned. There is no tenant override, provider fallback or automatic retry.

Each request rebuilds F1–F8 and adds:

- F9: recorded brain desired state/phase, workflow, pending request kinds and
  notification statuses, and follow-up status counts. No checkpoint narrative.
- F10: up to six current decision titles, questions, scopes, next steps and option
  labels, open decisions first, then answered/received items awaiting a result.
  Closed/blocked historical prompts are withheld to avoid reopening settled
  questions; only historical status counts are included in F9.
  Answer-present and needs-input flags are included, not
  owner responses, selected options or resolution text. Option labels are omitted
  for answered/received decisions.
- F11: names, versions and creation/reference timestamps for eight recent artifacts.
  No file contents, paths or native conversation retrieval.
- F12: activity source/status/freshness, ownership flags, safe-checkpoint time,
  readiness freshness, runtime revisions and current observation/inference jobs.
- F13–F18: bounded per-repository metrics/Git/readiness, packet gates, worker
  evidence axes, pending/recent control outcomes, retained follow-up summaries
  and external dependencies, and roadmap checklist metadata. Owner-answer bodies
  remain withheld; a follow-up outcome is not an unanswered historical question.
- F19–F21: bounded repository/model/effort usage groups, branch/tracking/push
  observations and PR states. No paths, task identifiers or URLs from these records.

The dashboard and assistant use one snapshot builder. It reads bounded local
activity metadata and recorded evidence, not live private Codex APIs or arbitrary
files. A missing explicit brain-control record is labelled as such; the legacy
running/ready policy default is not presented as observed activity. Larger row
sets carry included/total/omitted counts and are reduced to fit 48,000 UTF-8 bytes.
Actions are restricted to fixed controls and bounded server-resolved targets.
Capabilities and restrictions for all eleven views are included on every request.

The service receives link aliases and labels, not executable routes. Validated
aliases map back to server-owned dashboard hashes. Model text is rendered with
`textContent`; arbitrary model URLs/HTML cannot become actions or links. Evidence
IDs are validated, not the truth of narrative claims. Owners must verify advice.
The client requests JSON-object output and still validates every returned field.
The schema adds `action: null` or one catalogued action key. A free-text decision
answer additionally contains `text`, validated as an exact excerpt of the latest
owner message. No arbitrary command, target, URL, option, payload or function/tool
call is accepted from the model. An action proposal is not a tool invocation.

`POST /api/assistant/confirm` is separate and requires authentication, Origin,
CSRF, an HMAC-signed session-bound preview and `confirmed: true`. It submits the
original revision-bound command through `Ledger.submit`, with actor
`assistant_owner_confirmed`, then uses the same one-shot notification bridge as
dashboard controls. The same payload, expiry, revision, decision-version,
checkpoint, packet and worker gates apply. Preview signing keys are in memory;
restart invalidates outstanding previews. Confirmed command/event/receipt data is
durable, but unconfirmed suggestions and chat transcripts are not stored. A
repeated exact confirmation returns its recorded receipt and never retries the
native notification. The model cannot grant approval or confirmation.
An initial chat trial produced invalid JSON and was rejected. A subsequent live
trial returned a valid schema but still inferred unsupported owner choices and
native activity. Prompt clarification and explicit data-availability fields reduce
ambiguity but do not establish factual accuracy. Replies therefore carry a visible
AI-draft warning and deterministic open-decision/pending-control/dispatch counts
from the actual snapshot. Factual-accuracy qualification remains open.
In a subsequent same-snapshot trial, `qwen3.8:27b` preserved the recorded/unknown
distinction and did not reopen settled questions. That single response took about
84 seconds; it is a smoke test, not a comparative benchmark or model qualification.
The optional assistant-only model setting allows this latency/quality trade-off
without changing executive briefs or the service identity. There is no automatic
model fallback on timeout or validation failure.

`GET /api/assistant/context?view=overview` previews the bounded context with no
inference request. Sending captures a fresh snapshot, which can differ from the
preview. Each answer exposes the exact context that was sent. Automatic dashboard
polling, pane expansion, suggested-question selection, and navigation never call
the model. Chat and briefs share one portfolio file lock, including CLI requests.

Chat lives only in browser-tab memory, not SQLite, artifacts or localStorage.
Confirmed controls (including an explicitly confirmed decision-answer excerpt)
are durable ledger records; clearing chat does not remove or cancel them.
Reload and Clear chat discard it locally; upstream retention is the service's
policy. Only pane preferences persist in localStorage. Token totals cover accepted
replies in this tab, exclude failed/discarded calls, reset with chat, and are not
Codex usage or billing. New conversation storage/retrieval needs separate scope.
Chat uses server-side SSE to avoid the service's documented roughly 120-second
public-tunnel cutoff for blocking generations. Partials are buffered, not shown or
executed. A valid completion marker, single finished answer, exact local model and
routing are required before normal JSON/intent validation. Streams are capped at
4 MiB/16,384 events and checked against a 240-second processing window on each
read; the socket timeout is 90 seconds, not a hard whole-request deadline.
No automatic retry or hosted/model fallback occurs. Repository metrics,
usage/Git/readiness and control-history details expand in their corresponding workspace views; other views use compact
rows while preserving aggregate coverage and omitted counts for every domain.
Generation uses 2,048 tokens for smaller models and 4,096 for larger models;
incomplete output is rejected rather than published or converted into a control.

## Useful next applications — proposals, not enabled automation

### Initial live quality finding

Live integration checks accepted structured briefs from `ministral-3:8b` with
reported local routing. However, it sometimes conflated repository/branch scope
or inferred inaccurate relative ages. The UI therefore labels every narrative an
unverified AI draft, retains the exact evidence, and grants no action authority.
Larger-model trials returned `finish_reason=length` within tested budgets and were
rejected rather than published. Listing a model is not qualification for this task.
A matched, repeatable factual-accuracy evaluation remains open; do not use these
briefs as a replacement for the deterministic metrics or an accepted status report.

### Candidate follow-ups

1. **Change brief:** compare two recorded snapshots and explain new PRs, changed
   readiness and roadmap movement. Use deterministic deltas and source links.
2. **Review preparation:** draft an evidence-gap checklist for one approved packet;
   source/CI/merge/deployment/runtime/acceptance remain separate facts.
3. **Inheritance draft:** suggest a compact worker knowledge packet from explicitly
   selected material. Human/brain review and hash-bound approval remain mandatory.
4. **Artifact digest:** summarize selected versions and explain their differences.
   Unlike this first feature, this transmits contents and needs a separate data
   scope/privacy decision before implementation.

Start with status/delta synthesis. Keep coding decisions in native Codex until
matched evaluations demonstrate that the service improves quality, latency or
resource use. Do not claim measured cost savings from this integration alone.
