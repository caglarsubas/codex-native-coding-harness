# Complete runtime-package preflight

## Defect and correction

A reviewed launcher and an alive app-server socket do not prove that its local
tool runtime can execute. The previous launch manifest pinned only the launcher.
It could admit a copied CLI before its helper and resource package was present.
Later adding files cannot establish how that already initialized process resolved
its runtime. A package change time after process launch is a warning, not proof
of a particular vendor cache algorithm or proof that copying caused that timestamp.

New operator launch attempts require schema 2 and an exact complete-package pin.
Schema-1 manifests remain readable historical records, but no longer authorize
a new exec or supervised process boundary. Old owner hashes never approve the
new manifest. No live process, binding, ledger or old journal is rewritten.

## Explicit non-executing inspection

```text
python3 -m orchestrator.host_lifecycle package-preview EXACT_LOCAL_PACKAGE_ROOT
```

The command accepts one canonical existing local package. It reads only
`codex-package.json`, `bin`, `CodexCLI.app`, `codex-resources` and `codex-path`.
Surrounding host journals, credentials, Codex state and transcripts are not
inspected. Symlinks, special files, unsafe owners/writable ancestors, unsupported
layout, hard-link aliases, missing/non-executable CLI/helper/search and empty resources refuse.
The file/directory inventory, depth and total bytes are bounded. No runtime is
downloaded, installed, copied, discovered, executed or modified by this command.

The result's `runtimePackage` has exactly:

- Canonical `root`, `version` and `target` from the closed layout-1 manifest.
- `manifestHash`, `cliHash`, `helperHash` and complete `inventoryHash`.
- `fileCount` and `totalBytes`.

The inventory digest binds each file's relative path, bytes, SHA-256, permission
mode, device/inode, modification and change times. Reading may update access
time, which is excluded. The digest also binds package-root identity and the
closed trees' directory metadata, including empty directories. Missing/added files, mode changes or same-bytes file
replacement invalidate the review. The inspector checks earlier files again
after hashing later ones and repeats the directory inventory to detect drift.
This is a bounded cooperative check, not a filesystem lock against a malicious
owner rewriting files after its final read.

Insert the exact pin as `runtimePackage` in a private schema-2 launch manifest,
keeping the existing launcher/profile/checkout fields. Review in its exact launch
mode. Validation runs before intent creation and again after the permanent
monitor/exec claim, before crossing the process boundary. Drift after claim
retains the consumed attempt; there is no fallback, mutation-in-place repair,
automatic second launch, changed environment or alternate helper.

The reviewed launcher must independently use that exact package's entrypoint,
verify vendor signature/provenance and final app-owned ancestry, and enforce the
restricted native policy. An integrity pin cannot inspect script semantics or
certify a developer signing identity. Use an owner-private staging ancestor for
a copied complete vendor package; a shared writable install ancestor cannot be
used as a trusted immutable launch pin. Never modify the signed vendor bytes or
disable its tool-host feature to bypass a runtime failure.

## Qualification and rollout stay separate

`startsHost: false` and `nativeToolsQualified: false` are explicit in the preview.
Neither an inventory pass, helper `--help`, Doctor, process existence, listener
handshake nor tool catalog proves execution/approval handling. Host startup and
complete current package presence are separate from that running host's tool
qualification. The app-server listener and its Code Mode host connection are
separate in the [official app-server documentation](https://learn.chatgpt.com/docs/app-server).

Prepare the complete runtime before a separately reviewed launch. Back up private
state and quiesce older writers before installing source. Independently review
host retirement, replacement launch, destination qualification and exact binding
continuity; source delivery performs none of them. A repaired runtime grants no
new receipt window, phase time, allowance, Play, Resume, native response or replay.

When the existing receipt recovery already started and ended without its ledger
receipt, inspect the saved attempt. The dashboard labels it **Recovery ended
without a Pause receipt** (or missing checkpoint after receipt), not continuing
progress. Help is blocked with the exact retained request ID and no suggested
confirmation. Native outcome, historical terminal/effect gaps, usage and expiry
stay unchanged. See the [separate continuation proposal](ENDED-RECOVERY-CONTINUATION-PROPOSAL.md).

## Local source verification (2026-10-11)

The frozen source passed `python3 -m unittest discover -s tests -v`: 2,260 tests,
one skipped. All 35 local JavaScript suites and 31 web syntax checks passed,
including `node --check web/app.js`. Package/launch regressions cover missing
components, unsupported layout, writable/symlink/hard-linked paths, bounded
inspection, metadata/content drift and permanent post-claim refusal. Recovery
tests retain the exact original records and prove that blocked projection neither
collects native metadata nor resends the recovery.

A disposable `recovery-ended` project was rendered at desktop and 320px widths.
The graph remained in the workspace; **Inspect blocked recovery** opened its
existing control history without a confirmation or send. The narrow view had no
horizontal overflow. The test server/tab were cleaned up and viewport reset.
These synthetic checks do not establish live installation, runtime execution,
historical effect reconciliation or pilot acceptance. No GitHub Actions were
configured or enabled.
