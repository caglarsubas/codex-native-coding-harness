# Backend-specific public-host readiness

## Why the desktop check failed

The opted-in `public_app_server_tasks_v1` backend deliberately has no protected
desktop tools bridge or external MCP inventory. Asking its brain to discover
desktop creation/message schemas is therefore the wrong readiness procedure.
A native `catalog_error` is a real receipt of that check, not missing delivery,
and must remain unchanged. A model list alone is still not task-capability proof.

Future first-phase public notifications use version 2 of the checkout-local
pre-Play handoff. Version 1 desktop-tool observations and their receipts retain
their existing meaning. Neither source delivery nor installation converts,
replays, backfills or renews either old attempt.

## Original-bound evidence

Only the original sending public capability command may claim a capture, before
its native turn starts. Require the exact registered empty paused standard
project, reviewed mission, unchanged binding/source/ledger identity, no controller,
runner, tasks, decisions, competing controls or Brain Stop. The existing reviewed
connection must already report the exact brain loaded-idle. This path never calls
`thread/resume`; `notLoaded`, active, unsupported or changing state refuses.

The private permanent capture claim precedes collection. The evidence combines:

1. The reviewed executable's SHA-256 and file epoch, checked before and after
   its fixed `app-server generate-json-schema --experimental --out` export.
   Export runs in a disposable empty home with a closed environment, no inherited
   credentials, plugins, proxy or desktop pipe. It starts no app-server or turn.
   Bound and decode the four versioned v2 request/model schemas. Verify the exact
   arguments produced by the public task adapter, including project identity,
   model/effort, restricted sandbox/approval/reviewer and Code Mode configuration.
2. Two complete, agreeing, bounded `model/list` page sets from the original
   connection. Retain page hashes and only the observed intersection with the
   existing standard effort vocabulary. Missing, cyclic, duplicate, changing,
   over-bound or unsupported-only observations refuse; there is no guessed default.
3. Repeated exact native project/checkout/loaded-brain identity, independently
   reported enforced policy, complete empty public MCP inventory and non-refreshing
   authentication metadata. Account bodies and credentials are never retained.

Pin the original command, brain, handoff, source, binding/executable hashes, both
project IDs, backend build contract and observation time. Persist the immutable
capture and its protected notification hash before turn/start; repeat intent,
loaded-idle and effective-policy checks at that boundary. A capture interrupted
before publication stays consumed. No old or partially claimed attempt can capture
again, reconnect, load a brain or become an automatic delivery retry.

The schemas establish this binary's accepted public request shape, not successful
execution. `model/list` can use a bundled/cached catalog; neither it nor a schema
export proves account entitlement, current model access, arbitrary worker tools,
terminal cleanup or pilot acceptance. Actual requested/applied model and policy
checks remain at worker creation/first turn. No new model service or paid CI is used.

## Designated brain receipt

Read this document and use the exact original source/handoff pointer:

1. `--preplay-handoff HANDOFF standard-preplay-state` reads only checkout-local
   files. Its `publicReadiness` section returns observed choices, schema hashes,
   original time, boundaries and one `evidenceHash`. It makes no native read.
2. Write one private closed JSON object with `operation: public_catalog_ack`,
   the exact `requestId`, and that `evidenceHash`. If unavailable, retain a closed
   `catalog_error` instead. Do not discover desktop tools, provide new model
   values, select a model or access the shared registry/controller/socket.
3. Submit through `standard-preplay-receipt` and follow only
   `standard-preplay-status`. The original open observer verifies the exact
   command/turn/evidence/backend and atomically records the existing catalog
   receipt. A mismatched hash, added fields, foreign binding, ended observer,
   source drift or Stop refuses. A lost reply never reapplies the receipt.
4. End. This is not Play, worker dispatch, a native permission response, recovery,
   a brain reload, usage measurement or a terminal-safety assertion.

Cached readiness checks validate the retained provenance without collecting or
refreshing it. The exact public catalog remains bound at subsequent public
Play/Resume and public-task effect checks; another backend or model list cannot
substitute. Desktop and strict Harness gates are not relaxed.

## Owner experience and rollout

For a retained version-1 public schema failure, updated source may expose
**Request a new public-host readiness check** under its diagnostic. This is an
explicit distinct request with its own ID/context; the old failed status and
retryability stay unchanged. The source-availability indicator is not native
readiness, an installation assertion from model text, or a send permit. Rendering
and polling never click it. Version-2 pre-turn failures have no automatic retry.

Merge, source installation, host availability, explicit new request, catalog
receipt, owner Play, worker outcome and pilot acceptance are separate. Quiesce
writers and verify private backups before separately authorized installation.
Preserve both original requests, all old runs/usage/gaps/expiry, disposition,
claims and bindings. This source neither installs nor sends anything to v3.
Current and historical terminal safety remain unknown.

## Qualification

Unit fixtures cover actual argument-schema validation, model-list-only rejection,
schema/identity/policy/environment drift, partial captures, lost replies, Stop
races, foreign bindings, already-loaded-only delivery and no automatic resend.

`python3 scripts/qualify_public_readiness.py --executable BINARY --sha256 HASH`
explicitly exercises the pinned compiled binary in a separate disposable stdio
process/home. It creates one fixture project/brain, exports real schemas and
repeats actual public model/policy/identity reads with zero loads, turns, provider
requests, credentials or live-host connections. Its source pins are labelled
synthetic and its stdio endpoint does not qualify a live socket/binding or pilot.

Protocol basis: [official app-server schemas and models](https://learn.chatgpt.com/docs/app-server)
and [catalog versus model access](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server).
The pinned binary's generated schemas, not changing documentation examples, are
the implementation evidence.
