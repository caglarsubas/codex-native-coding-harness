# Worker-phase readiness source qualification

Complete orchestrator implementation hash:
`9b50866bc27ba97c17f3ac1fd73d9002ad5623bea84a1b9fc00534a244ada197`.

This qualifies the metadata-only source, not worker Play or pilot acceptance.
No dashboard installation, live load, subscription, turn, permission response,
binding change, readiness/Play/recovery replay, usage reset or ownership release
was performed. The existing dashboard/runtime remains unchanged.

## Verification

- Complete Python discovery: 3,444 cases, zero failures/errors and one existing
  optional Graphify skip. Eight fresh spawn-safe processes exactly matched the
  full discovery test-ID multiplicity, including its 30 duplicate legacy IDs.
  Every partition retained the same implementation hash before and after.
- All 29 new worker-readiness tests passed. These include real temporary
  admitted SQLite/Git lineage, preservation of both admission claims and the
  original readiness/startup records, loaded/unloaded observations, missing
  usage and larger overruns, current policy/identity/account/model drift,
  closed RPC vocabulary, partial artifacts, no renewed timestamps and no Play.
- All 42 JavaScript suites and all 31 web JavaScript syntax checks passed,
  including `node --check web/app.js`. AST parsing passed for 370 Python files
  across orchestrator, scripts and tests, and for all 372 tracked Python files.
  No frontend code changed; no new
  rendered desktop/mobile claim is made.
- The pinned compiled-native disposable fixture passed. It used a new private
  home/socket and loopback-only provider. Its original deadline failure and
  brain mailbox publication were explicitly synthetic. The native preparation
  load/turn, effective policy, schemas and subsequent metadata reads were real.
  The new worker observation added zero loads, subscriptions, turns or provider
  requests and observed an actually idle loaded runtime with eight advertised
  model choices. This is not live entitlement, tool compliance or acceptance.
- A separate explicit read-only live candidate observation validated the exact
  qualified PR-189 startup source and existing binding, four task/model API
  schemas and seven advertised model choices. It found the brain `notLoaded`,
  with null current policy/trackers, and correctly returned `brain_not_loaded`.
  Source and cached observations never convert that absence to idle or safe.
  The original 15,823-token startup charge and conservative 5,720,550 future
  ceiling were retained, not reset or treated as new executable authority.

The executable was already available and operator-pinned at SHA-256
`f7129d8763a45268aaa136b3a50de20acfcb6e07458a672d6c253d6d727f2ec9`.
Nothing was downloaded. The fixture connected to no live host and made no
external provider request. No GitHub Actions or paid CI was added or run.

## Retained non-qualifying runs

Exploratory test runs and native-fixture assumptions were corrected before final
qualification and retained privately, not counted as green. An initial private
verification runner inherited umask `077`, making deliberately public `0755`
fixture directories private and invalidating two older permission tests. A
replacement wrapper lacked a multiprocessing main guard; those results were
also invalid and retained. The final independent runner uses ordinary fixture
umask `022` and a proper spawn guard. No production permission guard or test
assertion was weakened. The native fixture now checks its actual loaded or
unloaded metadata rather than assuming immediate unload after connection close.

The requested single-process `python3 -m unittest discover -s tests -v` was
started and its output retained. It was interrupted only after the complete
exact-discovery isolated run passed; that redundant invocation is not counted
as a passing run. The final eight-part inventory, logs, per-part results and
full multiplicity proof are retained separately from all earlier runs.

## Rollout and remaining pilot boundary

Read [the operator contract](WORKER-PHASE-READINESS.md). Source delivery does not
install, confirm a review or unlock the permanent startup fence. The live host
was reachable, but its brain was unloaded at the explicit observation. Continuing
worker execution cannot satisfy the present no-reload constraint from that state.
Neither another long user message nor repeating a consumed control supplies
current runtime policy. Do not request a futile executable confirmation.

Manual merge, backed-up installation, a supported worker-phase review/new Play,
fresh effect-boundary evidence, actual worker results and pilot acceptance remain
separate. Preserve every historical run, request, claim, usage/gap, binding and
hold, and leave current/historical terminal safety unknown.
