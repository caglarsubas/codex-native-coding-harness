# Public-host authentication readiness

Transport, project/history transfer, loaded policy and model authentication are
different facts. The separately reviewed public-host launch deliberately creates
an isolated home without credentials. A successful socket handshake or metadata
transfer therefore does not establish that its brain can make a model request.

## Source-only guard

For future bindings explicitly selecting `public_app_server_tasks_v1`, the existing
one-shot wake bridge reads `account/read` with exactly `refreshToken: false` twice
before its authorized brain load and again before starting its turn. The existing
owned worker observer repeats the same check before the creation claim and before
the first-turn claim. No second dispatcher, extra effect permit or fallback exists.

The fixed response must explicitly report an actual boolean `requiresOpenaiAuth`
and either null or a supported native account type. Malformed, unsupported,
oversized, unavailable or changing samples refuse before the next native boundary.
If the provider requires authentication and the account is null, new work is
refused. Account identity/routing drift between samples also refuses. No account
details, emails, credential bodies or native error text are retained or displayed.

This is a missing-sign-in guard, not validation of token freshness, subscription
limits, model entitlement or billing. An account record may still have invalid or
expired credentials. Actual model access remains a separate native result, never
an assertion from a model catalog or this check. A provider not requiring OpenAI
authentication can pass only on its existing separately reviewed host configuration;
this adapter never selects or configures a provider. The loopback disposable fixture
uses that branch without real credentials or cloud requests.

The public account method and non-refreshing parameter are documented in the
[Codex App Server authentication reference](https://learn.chatgpt.com/docs/app-server#authentication).
This private local tooling does not introduce commercial or hosted authentication,
an OAuth application, a new model service, shared-home credential copying, a login
flow, logout, token refresh or authentication storage edits. Authentication setup
still needs its separate operator/user action on the reviewed host.

## Diagnosis and failure conservation

The existing explicit **Check native policy evidence** action also reads sign-in
state on a public-task binding, including when the brain is unloaded. Its closed
`authentication` diagnostic remains distinct from `policyVerified`: loaded policy
can match while sign-in is missing, or both can remain unavailable. The visible
detail explains that native sign-in is needed without sending a login. Normal
polls read only that cached diagnostic. Cache age, changed run/revision/binding
or shutdown invalidates its ready flag without renewing the original timestamps.
Original/non-opted-in hosts do not acquire account reads automatically.

Failure before loading retains a consumed notification and records no resume or
turn attempt. Failure after loading retains its original resume profile without
starting a turn or observation marker. A worker preflight failure consumes only
the explicit query, with no native creation claim or schema bump. If sign-in is
lost after creation, retain that exact worker as `pre_turn_blocked`; no first turn,
new worker, implicit retry, result, usage reset or terminal-safety claim follows.
Repairing sign-in never replays an old notification/query. Pause, source identity,
usage, expiry, native policy and cross-workspace ownership checks remain intact.

## Qualification and rollout

Run the full local Python and JavaScript suites. The real pinned-binary fixture
can inspect an isolated unauthenticated default-provider home with:

```text
python3 scripts/qualify_public_native_tasks.py --executable REVIEWED_BINARY --sha256 REVIEWED_HASH --missing-auth
```

That mode creates no project, thread, turn, login or model request. The existing
receipt-only and `--exercise-tools` loopback modes separately exercise the guard
against actual native `requiresOpenaiAuth: false` responses before one disposable
worker and turn. No live host/ledger, credentials, paid service or Actions is used.

Source delivery installs or authenticates nothing, changes no host/dashboard
binding and confirms no control. The original expired pilot keeps its immutable
Play, consumed transfer claims, checkpoint, original usage/gaps/expiry and unknown
current/historical terminal coverage. This guard neither implements the separate
expired-phase transition nor qualifies closeout, migration, Resume or the pilot.

## Source qualification — October 15, 2026

2,598 local Python tests passed with one optional skip, including 15 new sign-in,
privacy, drift, cache, one-shot, Pause and partial-creation cases. All 36 JavaScript
suites, 31 web syntax checks, Python AST and diff checks passed. No workflow is
configured or invoked and no remote CI pass is claimed.

The exact previously reviewed compiled binary passed the unauthenticated fixture
with zero project/thread/turn creation, login or model requests. Both existing
receipt-only and tool-exercising public-config fixtures passed their actual native
account reads and one disposable worker/turn, with only loopback model responses.
No live native action, real credential or cloud request occurred.

Disposable rendered checks at 1440px and 320px passed for both unknown-policy and
matching-policy/missing-sign-in states. The latter is a warning, not a successful
readiness notice. No horizontal overflow, JavaScript errors or phase/control
submission occurred. Saved policy/Play evidence remained independent and unchanged.
