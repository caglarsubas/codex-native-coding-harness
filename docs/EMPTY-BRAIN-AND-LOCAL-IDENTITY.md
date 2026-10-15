# Empty-brain readback and local-only successor identity

This delivery repairs source and qualifies disposable behavior. It does not
install/restart a live host or dashboard, apply a binding, quarantine an attempt,
review a mission, admit a successor or start/accept the pilot.

## Two causes, two bounded fixes

The native server staged project metadata and returned the requested project ID
on an empty chat's creation response. Its live metadata-only view did not overlay
that staged project ID, and no durable thread existed after the creating client's
subscription ended. An acknowledged UUID was therefore not independent readback
or durable membership. Sending a model turn to materialize it would confuse
setup with execution and cannot be used as the repair.

The supplemental [native patch](../native-runtime/patches/empty-brain-durability.patch)
uses the existing native persistence machinery, propagating persistence and flush
errors before acknowledgement for durable project-scoped threads. It emits no
synthetic input/turn, preserves the requested project and does not weaken the
read-only semantics of `thread/read`. Creation remains one-shot after uncertainty.
This is an operator-reviewed source-build change, not a claimed stock-server
capability or bypass of vendor signing/desktop bridge checks. The public
[app-server guide](https://learn.chatgpt.com/docs/app-server) separately defines
creation, stored readback, loading and turn start.

The default successor gate also required a conventional origin for every
repository. Adding a fake remote to a genuinely local pilot is not evidence.
The new explicit [local-only review](SAFE-SUCCESSOR.md#explicit-local-only-identity-review)
instead pins known remote absence, closed config/file identity, canonical Git
root and complete history roots. It refuses alias/copy/clone/fork overlap and
unknown/partial/drifting history while leaving global resource observation and
the ordinary origin-required default unchanged. It mutates no repository.

## Disposable verification

Against the previous pinned native binary, the new zero-turn fixture fails at
independent empty-brain project readback. The repaired compiled binary must pass
both history modes, repeated exact reads on the creating connection and repeated
stored reads on a second native process, without resuming either thread. The
loopback provider counts requests and fails qualification if any model request
arrives. No login, real credential, protected pipe, live host or cloud is used.

Run only with an independently reviewed local binary/hash:

```text
python3 scripts/qualify_empty_brain_readback.py --executable ABSOLUTE_BINARY --sha256 EXACT_HASH
```

Native source regression:

```text
cargo test --offline --profile dev-small -p codex-app-server --test all empty_project_thread_readback_survives_restart_without_turn -- --nocapture
cargo build --offline --release -p codex-cli --bin codex
```

Use only already installed Rust/dependencies. Local Python tests exercise
known-absence opt-in, unchanged default refusal, alias/clone/fork ownership,
config/remote/lineage drift, foreign ownership and original-ledger preservation.
Existing successor tests retain Play separation, one-shot claims, Pause/budget
races, already-loaded-only delivery and unknown-terminal refusals. Full local
Python/JavaScript/syntax checks remain mandatory; no GitHub Actions is added.

### Qualified native source and artifact

The supplemental patch was applied to native source
`23c298819ad88b8dcc3ef12cf955b852ff5dc33b` and committed as
`8b996031008c1e60a1d4539b96c9cd900a4a6a87`, tree
`ab21f5cbba4c91a993a5b36b53e02b232765e74e`. Offline release compilation produced
`codex-cli 0.162.0-alpha.17.2` with SHA-256
`5efb9e2cefbbca03ab5ec3780105c7873c5f265d10c0e32c749afccc9fda5ee7`.
The patch was independently reapplied against that baseline in a disposable
index and reproduced the exact committed tree.

The compiled zero-turn fixture passed with two process epochs, two history modes,
eight metadata samples, zero loads and zero provider requests. The old pinned
binary failed the same fixture at project readback. All seven native project
protocol regressions and nine pending-metadata store tests passed. The general
public-task fixture also passed with loaded-only preflight, actual tool/item
lifecycle capture, three fake-loopback model requests and no cloud/live-host
connections. Those fixture terminal observations apply only to their disposable
processes, not to any historical or live pilot process.

An immutable candidate package passed binary/dependency/source inspection; it
was not launched or installed. A first file-only staging directory used an
invalid version-string format and was retained as refused; the corrected package
uses a separate directory, not an overwritten claim. No native delivery was
attempted by either staging operation.

The final full local Python run passed: 2,741 tests, one optional Graphify
integration skipped because no reviewed disposable entrypoint was supplied.
All 36 JavaScript suites, 31 web syntax checks and staged diff checks passed.
The first full Python run retained one existing fake-GitHub fixture timeout;
its 28-test archive group and then the entire suite passed on recheck without
changing a timeout or evidence gate. No GitHub Actions or paid CI was used.

## Live continuation boundary

The old run, original Play/recovery, consumed usage/high-water/gaps and expiry
remain unchanged. Its current/historical terminal safety stays unknown and its
held repository cannot become the new target. Do not reload the old brain.

A newly compiled candidate is not the installed process. Prepare its exact
source/package/launch and target-binding review only after independent fixture
qualification; preserve old claims and bytes, quiesce older writers and verify
private backups before a separately authorized rollout. Do not silently modify
an old binding's source pins or attach a repaired proxy to an unchanged server.

The acknowledged but unavailable empty target brain is not repaired by this
source delivery. Keep that claim/result and report its readback as unknown. Any
separately reviewed new identity must explicitly preserve that predecessor setup
record; it must not be a retry of the earlier creation or a database edit.

After installed target qualification, exact owner quarantine, mission review,
binding and successor admission still precede a separate fresh target Play.
Neither this source change nor a generic instruction to continue self-confirms
those scoped reviews. No replay, usage reset, invented cleanup or acceptance
follows. Report the exact next technical/review boundary instead of manufacturing
a ready/complete pilot.
