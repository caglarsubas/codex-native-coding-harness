# Prospective native-item lifecycle capture

`owned_native_item_lifecycle_v1` binds a closed lifecycle contract inside a future
original owned notification transaction, before its first `turn/start`. It uses
the already retained hash-only effect stream. No extra socket, RPC, subscription,
native tool, model request, scheduler or keepalive is added. The original v1
effect-capture file and producer source remain unchanged and readable.

## Original-bound contract

Future standard Play/Pause/Resume and the existing narrowly permitted Pause
recoveries with `owned_observer_v1` receive `nativeLifecycleCapture` beside their
original `nativeEffectCapture`. It pins exact command/brain/run/binding/request,
capture-header and producer hashes, plus original binding time. Accepted, issued,
already-started or previously marked requests cannot obtain another lifecycle
contract. The original one-shot gates remain; an interrupted transaction never
re-arms its already created capture file.

Only a future actual native stream supplies observations. There is no arbitrary
evidence upload, supplied cleanup flag, historical producer, observer reconnect
or endpoint migration. No old Play/recovery receives this field during install.

## Explicit file-only inspection

With exact registered platform/workspace routing:

```text
standard-lifecycle-capture COMMAND_ID
```

The reader validates the immutable original contract and capture file/chain. It
never collects, opens a native connection, loads a thread or changes the ledger.
Legacy absence is `not_enabled_at_original_boundary`, not an empty or safe set.
Incomplete/open/interrupted captures remain incomplete. An unsupported or altered
producer, foreign turn, changed request/anchor or contract bound after observed
effects refuses. Original timestamps are preserved; reading never renews them.

For each recorded item, report actual start/completion observations, terminal
result status and original times. Detect unmatched/duplicate/out-of-order starts
and completions, unfinished items, changed command/checkout/known handle or PID
hashes, unknown item/status and events after turn completion. A handle first
becoming available is new information, not a fabricated birth record. Unknown
or pending lifecycle gaps cannot become a successful observation by filtering
items or interpreting the command/Code Mode program.

Message/command/output bodies, raw paths, handles, OS PIDs, approval prompts and
errors are not exposed. Existing capture bounds remain 512 events, 2 MiB, 16 KiB
per row; no truncation or extra send follows an overflow.

## Qualified boundary

`recorded_item_lifecycles_observed` means the recorded items have matching start
and terminal completion evidence and an observed turn completion. It never
claims complete effect inventory. Native process handles are not OS PIDs; an
optional PID is not a process-birth epoch. This supported stream has no complete
OS process/descendant lifecycle or retrospective cleanup guarantee. Therefore
`processLifecycleCoverage` stays `unavailable`, `processBirthEpoch` null, and
terminal safety/descendant cleanup unknown. All safety/continuation/acceptance
flags stay false, even when every recorded command exits successfully.

This implements native **item** lifecycle capture, not the unavailable OS
cleanup attestor. A separately supported from-first-effect process lifecycle
provider is still needed for that stronger claim. Do not describe this source
as completing the historical-cleanup blocker or the pilot.

The official [App Server reference](https://learn.chatgpt.com/docs/app-server)
describes shared item lifecycle events and current loaded-thread terminal lists;
it does not supply the missing historical descendant-cleanup guarantee.

## Qualification and rollout

Unit fixtures cover original pre-turn binding, privacy, matching and missing
events, changed identities, malformed/legacy captures, stream interruption,
scope/handle/PID drift and refusal to infer cleanup from unsolicited fields.
The compiled native fixture additionally exercises one disposable patch and
fixed `pwd` command through a loopback fake provider:

```text
python3 scripts/qualify_public_native_tasks.py --executable REVIEWED_BINARY --sha256 EXACT_HASH --exercise-tools --public-host-config --capture-lifecycles
```

It uses a new temporary native home/project/thread, no shared credentials or live
endpoint. Native response bytes qualify bounded producer/reader behavior only;
synthetic fixture authority/build pins are not attestation or a live migration.
No live binding, original history, brain load, usage or expiry changes. Source,
manual merge, separately quiesced/backed-up installation and live qualification
remain distinct. No Actions workflow, new runtime download or paid service.

On 2026-10-15 the existing isolated compiled-runtime fixture passed with binary
SHA-256 `8859d4ba8cbbe414a200db74f1f9044ac223e2f93b6086c7373077cc57bf24ba`:
one disposable project/thread/turn, two paired native item lifecycles (patch and
fixed command), three loopback fake-model requests, zero cloud requests and zero
live-host connections or writes. Policy, disposable edit and command checks
passed; OS lifecycle cleanup, migration and pilot acceptance remained explicitly
unqualified. The full 2,707-test Python regression (one skipped) and 36 JavaScript
suites also passed. No download, native sign-in or live brain load was involved.
