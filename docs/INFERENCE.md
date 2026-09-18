# Optional portfolio intelligence

The first integration with `llm-inference-engine` is an on-demand executive brief
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
4. Run `python3 -m orchestrator.cli inference-check`, then choose **Generate brief**
   on Overview, or run `python3 -m orchestrator.cli executive-summary`.

The CLI and dashboard load the same file on demand; configuration changes do not
require exporting environment variables. This is a simple key/value file, not a
shell script: no interpolation, `source`, or command execution. Files with group
or world access, symlinks, duplicate settings or non-HTTPS URLs are refused.
Do not put real endpoints or credentials in tracked examples, docs or screenshots.
`.env` and `.env.*` are ignored; only the credential-free `.env.example` is tracked.
The supplied credential document must remain outside the repository.

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
- Requests are non-streaming, with a 90-second socket timeout, a 2,048 output-token
  cap for small models (4,096 for the two larger reasoning models), and bounded
  response size. This is a socket timeout, not a strict total
  wall-clock deadline for a slowly arriving response. There is no background retry.
- HTTP 429 gives a manual retry hint. Authentication errors, timeouts, null or
  truncated answers, unexpected models/routing, tool calls, invalid JSON/schema,
  or unknown evidence IDs keep the previous brief and show an explicit failure.
- Next-step control-action patterns are conservatively rejected as an additional
  safeguard. This is not semantic verification. Narrative claims and numeric
  interpretations still require human review; the output never operates controls.
- Every successful brief becomes an immutable JSON artifact version, ordered by
  generation time. Earlier versions remain readable in Artifact library. Export
  includes the last brief with its original evidence, not a fresh verification.
- Prompt/completion token counts are service-reported, separate from Codex usage.
  Retained-brief totals exclude failed/discarded calls and older versions without
  usage metadata. They are not complete account usage or a currency estimate.
- The supplied service is a shared single-node proof of concept, not a production
  SLA. Its benchmark is grounded QA, not demonstrated coding-agent competence.
- Embeddings and local vision are unsupported by the supplied contract. No vector
  search, screenshot understanding, or autonomous coding dependency is added.

Use `python3 -m orchestrator.cli inference-status` for configuration/freshness and
`python3 -m orchestrator.cli executive-summary --force` for an explicit new answer.
Removing `.env` disables new requests without affecting orchestration or retained
briefs. Stopping a server can abandon an in-flight response; restart never retries
it automatically. Native task lifecycle remains exclusively in Codex.

## Assistant chat data boundary

`POST /api/assistant` requires the same loopback Host/Origin, authenticated session
and CSRF checks as dashboard controls, but never invokes those controls. It accepts
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

The service receives link aliases and labels, not executable routes. Validated
aliases map back to server-owned dashboard hashes. Model text is rendered with
`textContent`; arbitrary model URLs/HTML cannot become actions or links. Evidence
IDs are validated, not the truth of narrative claims. Owners must verify advice.
The client requests JSON-object output and still validates every returned field.
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
Reload and Clear chat discard it locally; upstream retention is the service's
policy. Only pane preferences persist in localStorage. Token totals cover accepted
replies in this tab, exclude failed/discarded calls, reset with chat, and are not
Codex usage or billing. New conversation storage/retrieval needs separate scope.
The same 90-second socket timeout and routing assertions described above apply;
the timeout is not a strict whole-request wall-clock deadline.

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
