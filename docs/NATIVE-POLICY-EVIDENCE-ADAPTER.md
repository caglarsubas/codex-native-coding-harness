# Native loaded-policy evidence adapter

This adapter consumes the separately repaired, versioned experimental native
`thread/effectivePolicy/read` contract. It does not repair an old host by sending
another Play/recovery, rewrite old policy receipts, load a thread, or assert
terminal safety. The dashboard's check is diagnostic, not a continuation grant.

## Exact reviewed host opt-in

The existing private binding keeps its closed top-level `endpoint` and `brains`
shape. A **newly reviewed** brain entry may additionally contain:

```json
"policyEvidence": {
  "protocol": "loaded_thread_policy_v1",
  "sourceCommit": "<exact 40-character native source commit>",
  "sourceTree": "<exact 40-character native source tree>"
}
```

These source pins identify the operator-reviewed build; they are not native OS
attestation or evidence that the socket's process was upgraded. The endpoint's
exact executable hash, socket epoch and initialization identity, separately
reviewed launch provenance, both project IDs, brain and checkout must all be
qualified together. A matching version string is insufficient. Do not connect
a repaired proxy executable to an old host and call that an upgraded runtime.
Do not silently add this field to a historical accepted binding. Old bindings
remain readable and do not probe the new method automatically.

The native response must be version 1, match the exact thread and cwd, and name
`loadedThreadDefaults`. Null means unloaded/missing, not safe or empty. The
adapter requires a complete closed sandbox record, workspace-write with no
additional writable checkout or network access, on-request/user approval defaults,
an actual boolean `codeModeOffEnforced: true`, and `effectiveToolMode: direct`.
Unknown versions, extra fields, config echoes, wrong scope/identity, wider roots,
contradictory settings or differing repeated samples fail closed. Model names,
raw paths and native error bodies are not sent to the browser or inference.

## Explicit dashboard inspection

**Check native policy evidence** submits an authenticated, workspace-CSRF-bound
POST to `/api/workspaces/ID/native-policy/check` with exactly `{}`. The browser
cannot choose a method, target, source pin, setting, load or proof value. Standard
workspace/catalog/enrollment gates precede native reads. On its configured host,
the adapter repeats exact project/thread metadata around two fixed policy reads,
then rechecks endpoint, catalog and ledger context. A Pause, identity change or
contrary sample prevents a verified result. Strict Harness remains unsupported.

Only closed diagnostics are cached in the running dashboard. Polls never collect,
renew observations, write ledger evidence, connect a replacement or confirm a
control. Restart discards the cache; elapsed five-minute freshness, a changed run
or revision, a changed binding, or dashboard shutdown invalidates a positive
diagnostic. A later failure replaces a previous success instead of falling back.

`matching` means **loaded-thread defaults match**. It is not active-step grants,
native-tool connectivity, current/historical terminal coverage, effect settlement,
usage, a safe checkpoint, Resume permission or pilot qualification. In particular,
this diagnostic cannot clear the old v1 accepted-Play policy guard. That original
null report and all consumed claims stay byte-identical.

## Future one-shot delivery and brain handoff

For a future owner-confirmed control on the new reviewed binding, the existing
bridge still claims before native effects. After its ordinary authorized resume,
but before `turn/start`, it reads the policy twice on that same connection.
Unknown/off-not-enforced/mismatched policy refuses **before** turn start. Its
notification remains consumed; there is no fallback, resend or automatic load.

The original v1 `nativeResumeProfile` remains an acknowledgement with null Code
Mode. A separate closed `nativeEffectivePolicy` observation binds the exact
command/brain/turn, binding, executable/source hashes and original sample time.
Only this supported future observation can satisfy the retained policy guard.
No unsolicited field in a legacy profile can qualify it. Existing mission,
usage, duration, Pause, terminal and ownership gates remain intact.

An explicit future `standard-host-inspect` uses the existing controller-bound
owned-observer mailbox and fixed read-only policy RPC. It requires agreement
with that command's captured proof; the sandbox still never gets the protected
control socket. A positive result removes only the Code Mode-reporting gap.
`native_effect_inventory_not_complete` remains, as do all false authority/cleanup
boundary fields. Interrupted claims are never recollected or reconnected.

## Rollout and the already paused fresh pilot

Source, merge, installation, host launch, exact binding review and qualification
are separate steps. Quiesce older writers and back up private state before a
separately authorized installation. Preserve the old shared host: other historical
effects own it. Do not overwrite its binary or rebind the fresh pilot implicitly.

The compiled native candidate and its source pins can be prepared now. An exact
usable socket binding **cannot** be finalized before a separately reviewed host
exists: its actual socket identity and initialization response must be observed,
not invented from a future filename. A pre-launch scope packet is not that
endpoint review and grants no launch, load, rebind, notification or Resume.
Its native tools/signing/ancestry remain separately unqualified.

The existing paused run additionally needs an explicitly reviewed continuation
evidence path; a policy diagnostic does not replace its historical profile or
prove old/current tracked-terminal cleanup. No current Play or recovery may be
reissued to capture this future protocol. Usage/gaps, original expiry and all
receipts remain unchanged; unknown terminal status stays unknown.

## Local verification

Synthetic tests cover the closed contract, unsupported/unloaded hosts, request
echoes, wrong scope/identity/version, malicious fields, non-boolean enforcement,
sample and Pause races, endpoint drift, cached freshness, owner authentication,
project isolation, future turn-start refusal, immutable old profiles and the
sandbox-safe brain handoff. JavaScript tests exercise the fixed empty check body
and separation from Resume. No GitHub Actions or paid service is added.

The opt-in compiled-CLI fixture uses an isolated temporary Codex home, ephemeral
thread and loopback fake provider, with no live credentials or socket. Run with
the exact already reviewed executable and SHA-256:

```text
python3 scripts/qualify_native_policy_adapter.py --executable ABSOLUTE_CANDIDATE --sha256 REVIEWED_HASH
```

It verifies actual native response bytes through the adapter, repeated matching
loaded defaults and non-loading null reads. No turn is started or model response
requested. This is adapter/build qualification, never live pilot acceptance.

The final frozen source ran 2,445 local Python tests with one optional dependency
skip and no failures. All 36 JavaScript suites, 31 web syntax checks and 114
Python module/script AST checks passed. The compiled-CLI fixture and rendered
1440px/320px checks passed. No workflow was configured or run. The fresh paused
pilot's original Play, run, usage/gaps and expiry remained unchanged.
