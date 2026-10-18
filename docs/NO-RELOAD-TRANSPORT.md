# No-reload owning subscription transport

This repair adds an explicit experimental `thread/subscribe` operation to the
operator-reviewed public native build and a narrow Python transport adapter. It
is a transport component, **not an executable canceled-Play continuation control**.
It changes no live binding, launches no live host and grants no new turn authority.

## Why an explicit native operation is necessary

The pinned original build attaches its owning connection through `thread/resume`.
Metadata-only `thread/read` does not subscribe; `turn/start` on a new connection
does not establish its permission/lifecycle observer. A client-side loaded read
followed by resume has an unload race and is not a no-reload guarantee. The
[official app-server documentation](https://learn.chatgpt.com/docs/app-server)
separates stored reads, resumes and turn execution. This additional experimental
operation is a locally reviewed source-build extension, not a claimed stock API.

The supplemental [native patch](../native-runtime/patches/no-reload-subscription.patch)
applies on native `8b996031008c1e60a1d4539b96c9cd900a4a6a87`. Apply only at that
verified base with `git apply --binary --unidiff-zero`; the patch carries the
binary schema delta and zero-context text hunks. The request is exactly
`{"threadId":"CONFIRMED_NATIVE_UUID"}`; unknown load/configuration/policy fields
are rejected. The server holds its existing pending-unload mutex across the
in-memory lookup and subscription insertion, so it either subscribes the same
already-loaded idle runtime or refuses. Active/approval-wait, unloading, missing,
unloaded and closed-connection states refuse. It never reconstructs history,
changes settings, starts input, emits a synthetic thread start or answers a
permission. Existing listener machinery delivers future turn/item events and
native permission requests on this connection. Losing that connection is not
permission to reconnect to an old turn.

The closed acknowledgement is exactly `version: 1`, `threadId`, `subscribed: true`
and `reloaded: false`. Acknowledgement establishes only subscription, not current
or historical terminal safety, usage coverage, phase authority or acceptance.

## Narrow client and one-shot caller boundary

`orchestrator.no_reload_transport.Subscription` accepts one already-open reviewed
connection, one exact brain/binding and a separate closed build contract:
`protocol`, `method`, `sourceCommit`, `sourceTree`, `executableSha256`. Both native
policy source pins and the endpoint executable must match. Old bindings cannot
inherit this capability from an installed dashboard or a successful resume.

The adapter repeats exact project/brain/cwd/loaded-idle, actual enforced policy
and complete current tracked-terminal reads before and after subscribing. Unknown
coverage, running terminals, drift and lost/refused/malformed responses leave it
unready. It attempts only one fixed subscription on the same process/connection;
errors and concurrent duplicate calls cannot cause resume/reconnect/retry.
It performs no account refresh, permission response, native turn, cancellation,
ledger write, source installation or binding modification.

The claim callback is an internal interface for a **separately implemented exact
owner-control adapter** to commit its permanent prospective claim before the RPC.
The transport checks the closed returned context but does not authenticate owner
approval or provide a durable control journal. Merely calling it is not authority.
There is deliberately no CLI/browser route and no production continuation caller
in this delivery. A future control must validate a complete canceled-Play
disposition, unchanged requests/run/mission/limits/expiry/usage, measured usage,
current policy/tracker evidence, stopped older writers and verified private backups;
commit its exact new owner intent; and retain the same original new connection
for the new instruction and observer. It must not attach to or replay the old Play,
backfill a mailbox/receipt, fabricate cleanup, reset usage or extend the clock.

## Disposable qualification

Use only already installed Rust/dependencies, with offline Cargo. Native regression
tests cover loaded subscription, stored-unloaded refusal and rejection of extra
load/policy fields. The compiled Unix fixture creates a disposable home/project
and a new brain, then subscribes a different initialized connection without resume.
It compares durable history and observes no provider request before subscription.
After the creating connection unsubscribes, that same new connection observes one
fake-provider receipt turn and one native permission wait. The fixture alone
cancels its exact `/usr/bin/true` request; production code never responds. An
additional connection cannot subscribe to that active permission wait. The test
then observes an actual unload and proves subscribe refuses without reloading.

```text
python3 scripts/qualify_no_reload_transport.py --executable EXACT_LOCAL_BINARY --sha256 EXACT_SHA256 --source-commit EXACT_COMMIT --source-tree EXACT_TREE
```

All model traffic goes to a labelled loopback provider with no real credential,
shared home, live ledger or live host. These fixture turns are not an old control
replay, entitlement evidence, a real worker completion or pilot acceptance.

### Qualified native artifact

Native source commit `381a6ed1f442f3341c3c46522e5392d5949c0978`, tree
`59cafd680e5ab468951ab1714748b6971cd38d1a`, was built offline with the existing
Rust 1.95.0 toolchain. The macOS ARM64 monolithic candidate's SHA-256 is
`ff7586a251223f2aa21b2647e60e230bc07062aff5a3ab95183f1a344a5a007f`.
The complete private source bundle's SHA-256 is
`bbabb61c9cb268ee60d7ed321c870e1cdab2f08d5fb332ca3b76487dab2b8e39`.
Its intact ad-hoc signature and closed system-library package passed inspection;
this is operator-reviewed build provenance, not vendor desktop authorization or
reproducible-build attestation. Nothing was installed on the live native host.

All **379 app-server unit tests**, **320 protocol/schema tests** (one explicit
generation helper ignored), **3 subscribe regressions** and **5 existing
unsubscribe regressions** passed. Stable schemas remained unchanged; experimental
exports were regenerated and checked. The compiled two-connection fixture passed
native lifecycle/permission delivery, unchanged subscription-time history, active
wait refusal, exact observed unload and deterministic preflight-to-unload refusal
with a consumed claim and an actual rejected subscription RPC. It used two fake
loopback responses and no reload or live connection. The prior binary failed at
the new operation and was not treated as capable.

The same candidate also passed the existing public-task tool fixture: actual
apply_patch, fixed pwd, restricted native policy, two retained item lifecycles and
known-empty current fixture terminals, using three loopback responses. This is
not historical process cleanup, measured live phase usage, migration or pilot
acceptance. Full Python/JavaScript results are recorded separately in the evidence
ledger; these native checks do not stand in for them.

## V3 boundary and rollout

Keep native source/build qualification, manual source merge, installation, exact
host/build/binding review, canceled-Play disposition and a distinct continuation
control separate. Do not change the existing v3 binding to make this new build fit.
The original pinned host process is absent. A new build cannot resurrect an
in-memory brain from that exited process; a stored thread is not loaded. If no
already-loaded brain exists on the unchanged binding, this transport must refuse.
No no-reload implementation can manufacture that prerequisite.

V3's old requests, usage/gaps, claims, original missing receipt, limits, expiry,
binding and historical effects remain preserved. Its current and historical
terminal status remain unknown. No source/fixture result applies the disposition,
launches/rebinds a host, reloads a brain, replays Play/recovery, resets usage or
continues/accepts the live pilot. Further live progress requires a permitted runtime
and separately reviewed continuation scope, not another original Play confirmation.
