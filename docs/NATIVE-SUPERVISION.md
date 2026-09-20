# WSP-04D2 — native task and account-limit supervision

Update: [WSP-04F](NATIVE-EVIDENCE-COLLECTION.md) separately collects bounded
diagnostic metadata through an owner-pinned existing public native endpoint.
It does not replace these tool observations or establish complete host/counter
coverage. No source upgrade authorizes a live endpoint connection.

Plan saved before implementation on merged PR #31 (`200cdca`). The designated
brain remains the native caller. This increment connects supported read-only tool
results to existing lifecycle/admission checks; it does not start an app-server,
model process, worker, scheduler or live mission.

## Implementation plan

- [x] Add designated-brain CLI task observation plan/record/state commands for
  exact, already confirmed admitted tasks, plus account-limit record/state.
- [x] Normalize current `wait_threads` results without retaining assistant text,
  tool arguments, titles, paths or error messages. Separate current native activity
  from the last turn; `notLoaded`, unsupported, missing and error results stay
  unknown. Never infer complete descendant coverage or successful acceptance.
- [x] Bind observations to exact native identities and native journal versions;
  reuse shared-first lifecycle recording/replay/recovery after Pause. No messaging,
  continuation, runner launch, release, archival or implicit new task.
- [x] Normalize `get_usage_limits` using the explicit Codex bucket and window
  duration, never primary/secondary position. Missing values stay unknown. Pin
  the account identity privately; preserve every version and supersession.
- [x] Integrate fresh account evidence into admission conservatively: a newer
  missing/exhausted/changed-account observation blocks new effects even if older
  limits looked healthy. Reads, retries and legacy updates cannot refresh or
  bypass it. Keep percentages separate from cumulative phase/task token counts.
- [x] Test real subprocess CLI flows and tool-shaped fixtures, identity conflicts,
  replay, stale/error responses, Pause races and interrupted local attachment.
  Run the full Python/JavaScript regression suite; preserve a verification report.

## Observed interface boundary

The current native app tools expose `wait_threads` and `get_usage_limits`. A
read-only host check returned wait poll schema 1 with current `notLoaded` status
and an older completed turn; the usage result returned a weekly window in
`primary` and a null `secondary`. Neither observation was written to live state.
Private native IDs, account identity and conversation content are not published.

The official [App Server reference](https://learn.chatgpt.com/docs/app-server)
distinguishes current thread status from turn events and exposes thread token
usage updates. That public protocol is not the desktop task tool's wire schema,
and does not justify connecting a new server to the existing brain. This adapter
uses only the app's available tool responses. Those responses do not establish
complete descendant inventory or cumulative phase-scoped token accounting.

Native results are trusted brain-supplied observations, not cryptographic
attestation. No tool call, shared observation, baseline, allocation, live ledger,
installation or heartbeat change is authorized merely by merging this source.

## Brain operator interface

These commands require an existing private platform admission store, an explicitly
selected registered workspace and that workspace's designated brain controller
token in `ORCHESTRATOR_CONTROLLER_TOKEN`. They never acquire a controller or
initialize an allocation. Examples use placeholders, not live paths or IDs:

```sh
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace WORKSPACE native-task-plan WORKER_ID
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace WORKSPACE native-task-record WORKER_ID PRIVATE_REQUEST_JSON
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace WORKSPACE native-task-state WORKER_ID
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace WORKSPACE native-account-state
python3 -m orchestrator.cli --platform PRIVATE_PLATFORM --workspace WORKSPACE native-account-record PRIVATE_REQUEST_JSON
```

Task flow:

1. `native-task-plan` reads the owned task's current journal and emits exact
   single-target `wait_threads` arguments with `timeoutMs: 0`. Only confirmed
   local task IDs qualify; pending client IDs are never task targets. A previously
   retained cursor is scoped to this exact task.
2. The designated brain calls that native read-only tool. Python does not call
   it, start a polling loop or send a message. No task is woken by these helpers.
3. Supply `native-task-record` a JSON object with exactly `id`, `expectedHash`
   (from the plan), `observedAt` (actual observation time, Unix seconds), and
   `result` (the decoded native tool result object). The latter is the JSON body
   containing `polls`, **not** the MCP `content` envelope. Do not translate old
   assistant prose into status. Input is a bounded, regular nonsymlink file;
   keep raw tool responses private and out of Git.
4. Inspect `native-task-state`. It distinguishes retained observation time from
   current freshness, shared journal hash from locally attached hash, and
   ownership from activity. Expiry displays unknown without refreshing evidence.

One exact poll is accepted, not a batch that might silently mix tasks. Current
`active` becomes running; `idle` becomes idle only without conflicting turn or
active-flag evidence. `notLoaded`, system errors, absent polls, unsupported schema
or statuses, and contradictory results become unknown. Foreign IDs and malformed
identity fields refuse. An old completed turn does not turn `notLoaded` into idle.
Only bounded identity, status, cursor/revision and provenance hashes are retained;
conversation/tool content and error text are discarded.

Recording reuses the existing lifecycle's optimistic version, unique identity,
shared-first journal and local attachment checks. Exact replay is historical and
does not refresh time or overwrite a newer result. If the shared record committed
but local attachment failed, replay the exact request or use the existing
receipt-only recovery path; do not repeat creation. Observations remain allowed
after Pause, but do not resume it. Existing in-flight continuation/runner barriers
still apply: resolve them through their own coordination protocol rather than
using task observations to bypass them. This interface is for still-owned tasks;
it is not a terminal archive browser or a complete runner/descendant observer.

## Account headroom, not task token accounting

The brain reads `native-account-state`, calls `get_usage_limits`, and supplies
`native-account-record` the same four request fields. `expectedHash` is the current
account journal hash, or `null` before its first observation. All registered
workspace brains observe the same platform-wide account headroom; request IDs are
scoped by workspace and ledger identity. They do not receive each other's task
authority. Concurrent observations use the shared transaction and expected hash.

The projection prefers a nonempty `rateLimitsByLimitId` map's exact `codex`
bucket. Only an absent/null/empty map permits the legacy `rateLimits` fallback;
a missing Codex entry never falls back to another model bucket. Required windows
are identified by duration: 300 minutes and 10,080 minutes, regardless of their
primary/secondary position. Missing/null/invalid windows are unknown, not zero
usage. The first available account identity is pinned as a private digest; a
different identity fences admission and requires separate migration decisions.
Raw account IDs, credit counts, reset-credit details, plan labels and upsells are
not journaled. No credits can be purchased or redeemed through this interface.

The first explicit native observation activates this evidence path; reads alone
do not. Every record is immutable, linked to its predecessor and separately
timestamped. New missing/blocked/changed-account evidence supersedes old healthy
evidence and clears the usable account projection. Admission checks the current
native record, its exact projection, freshness, reset times and the existing
minimum headroom policy. Legacy manual account updates refuse after native
observations exist. Replaying an older healthy record cannot restore it as current.

This is an additive source interface, **not a rolling-upgrade protocol**. Do not
run older admission writers alongside it or downgrade an observed store. A future
explicit installation/activation must quiesce old writers, preserve the private
store and deploy compatible helpers together. Clearing an invalid projection also
protects an older budget reader from stale healthy limits; it is not a claim that
old write implementations enforce the new native journal contract.

The currently observed weekly-only response remains blocked under the existing
two-window admission policy. This change deliberately does not infer that a
missing short window is unlimited or silently relax that policy. A supported
account/window policy decision is still needed before such an account can qualify
for live admission. Additional model-specific buckets are not adaptive model
routing evidence.

Percentages are account-wide consumption ratios, not token counts or costs.
Neither supported response proves complete brain/worker/reviewer cumulative
usage, descendant coverage, settlement, acceptance or permission to execute.
Existing phase counters, reservations and checkpoint reserves remain unchanged
and independently mandatory. Status `headroom_observed` is not a Play permit.

## Delivery and next gates

See [verification evidence](NATIVE-SUPERVISION-VERIFICATION.md). No public HTTP or
assistant mutation route, dashboard control, live baseline/allocation, native
send, skill installation, schedule, model setting or maintenance release is added.

The next pilot integration needs complete native/descendant and phase-token
evidence, supervised runner/result evidence, an explicit owner setup/activation
path and brain operator installation, then a tiny real standard-policy pilot.
Continuous phase execution, preservation-backed archival, adaptive routing and
the trusted Harness acceptance adapter remain distinct later gates.
