# Application-owned public host runtime

`public_app_server_host_v1` is a separate, opt-in macOS ARM64 launch profile for
the source-built public task backend. It does not grant desktop tool access,
substitute an ad-hoc signature for a vendor identity, forward a protected pipe,
disable signing/peer checks, or change `standard_owned_host_v1`. Review hashes
from those profiles are not interchangeable.

## Closed package and provenance

The first package contains exactly three files:

```text
public-runtime.json
bin/codex
source.bundle
```

The native source's `arg0` entrypoint dispatches its patch, filesystem and exec
helpers inside the same macOS executable. The profile supports this monolithic
layout only, with no external Code Mode/Node helper. It does not qualify other
platforms, fat binaries, isolated worktrees, arbitrary command dependencies,
Python/Node/ripgrep packages or a complete desktop replacement.

`public-runtime.json` is a closed schema-1 record with profile, explicit
`operator_reviewed_build_v1` trust, `desktopBridge: absent`, native source commit
and tree, executable/source-bundle SHA-256, version, target, exact entrypoint,
`helperMode: monolithic_arg0` and `dependencies: macos_system_libraries_only`.
Inspection pins every file's bytes, modes, device/inode and change times, plus
directory identities. Canonical private roots, bounded files and no symlinks or
hard-link aliases are required. Unexpected entries and any drift refuse.

Bounded ARM64 Mach-O parsing permits only the supported load-command set and
absolute macOS system library/framework paths. External/relative/loader
dependencies, rpaths, dyld environment commands and unknown commands refuse.
The package inspector executes neither its CLI nor a helper and starts no host.
These pins are integrity/provenance inputs to independent owner build review,
not reproducible-build attestation, OS enforcement or vendor authorization.

`scripts/stage_public_runtime.py` copies only explicit already-existing reviewed
binary/bundle inputs into a new exclusive private destination. It verifies both
hashes, the exact clean local source HEAD/tree and the bundle's sole source branch.
It downloads nothing, runs only fixed read-only Git metadata commands, creates
no host, and never overwrites/retries a partial staging directory. Staging a
package does not install it on an existing process or qualify a launch.

## Non-executing setup and launch review

Use `python3 -m orchestrator.public_host_lifecycle package-preview PACKAGE` for
file inspection. `setup-preview PACKAGE CHECKOUT ISOLATED_HOME SOCKET_DIRECTORY`
pins existing, disjoint canonical directories and their current identities.
It creates/configures nothing. The checkout must be an existing non-worktree
Git root; additional checkout/system/managed configuration requires a separately
qualified profile instead of being ignored or weakened.

The new owner-private home contains only the byte-exact `CONFIG` from this
module, and the owner-private socket directory is empty. Credential mode is
explicitly `unconfigured`: no auth, session, plugin, `.env`, transcript or old
state is copied or inherited. HOME stays the real OS user's home; CODEX_HOME
alone points to isolated native state. The new home is outside the fixed system
temporary root so release-build arg0 helpers are not disabled by a temp-home
collision. No future socket epoch or server identity is invented in a preview.

The fixed config requests workspace-write/on-request/user, network off, Code
Mode off, no apps/plugins/hooks, no analytics, and file-only credentials.
Login shells are disabled and shell tools inherit no environment; only fixed
PATH/LANG entries are supplied. The host's launch environment contains only
fixed PATH/TMPDIR, OS user identity and the exact isolated CODEX_HOME. No desktop
pipe, provider/API secret, proxy, preload, DYLD or arbitrary inherited setting
is forwarded. These are launch/configuration facts, not current per-thread
policy, terminal safety or a grant to read private files from a worker.

Save the exact setup `spec` as a private manifest. `preview MANIFEST` produces
one mode-bound hash without a clock countdown. Elapsed reading time does not
expire it, but every package/config/directory/scope check repeats before intent
and after the permanent exec claim. Source delivery and generic assent do not
confirm the new scope. A separately reviewed exact owner hash remains mandatory.

An explicitly confirmed launch uses only:

```text
exec python3 -m orchestrator.public_host_lifecycle exec PRIVATE_MANIFEST NEW_PRIVATE_ATTEMPT --confirm-hash EXACT_PUBLIC_REVIEW_HASH
```

The exclusive intent and fsynced claim precede a same-PID `execve` of the pinned
binary with fixed `app-server --listen unix://.../host.sock` arguments and the
closed environment. There is no shell-authored launcher, detached supervisor,
background dispatcher, timeout/restart or fallback. The foreground context must
outlive the host; this is not a boot service or a guarantee across desktop exit.
Exec failure, drift, interrupted persistence or lost outcome consumes the attempt.
`status ATTEMPT` is historical metadata only, never proof of liveness or cleanup.

## Qualification and migration remain separate

An exec-boundary record means neither host-ready nor native-tools-qualified.
Independently observe the actual process/ancestry, package, socket epoch,
initialization identity, empty complete MCP inventory, and actual repeated
per-thread effective policy before proposing any new binding. The unchanged
vendor/shared host is never overwritten, retired or used as a fallback.

The staged binary's actual ad-hoc signature may verify as intact; that still
does not authorize the protected desktop bridge. Native protocol fixtures must
use an isolated disposable home and loopback fake provider. The optional
`qualify_public_native_tasks.py --public-host-config --exercise-tools` exercises
the fixed config/environment with a clearly fixture-only provider overlay,
actual native patch, fixed command and complete current fixture terminals.
It grants no real login, host launch, binding, historical cleanup or pilot result.

This initial launch profile deliberately contains no existing brain/project
store or credentials. Moving exact project/brain identities and native history
needs a separately reviewed supported transfer/evidence contract; do not copy
an entire shared home, edit native stores, invent IDs or treat a new project with
the same checkout as the original. The existing public migration assessment
still returns `migrationQualified: false`. No original Play profile is backfilled
or old observer reconnected, and no same-run Resume permit is shipped here.

The separate exact one-brain metadata/history transfer source is now described
in [PUBLIC-IDENTITY-TRANSFER.md](PUBLIC-IDENTITY-TRANSFER.md). It needs another
reviewed native build and already qualified endpoints; it does not make this
empty-home launch review a transfer, binding or continuation permit.

Source, merge, installation, launch review, actual host/binding qualification
and same-run transition are separate. The fresh paused run's original Play,
consumption/high-water/gaps, expiry and unknown current/historical terminals
remain unchanged. No Play/recovery replay, usage reset, load, permission response,
Resume or pilot acceptance follows this source delivery.

## Source qualification record — October 14, 2026

The final runtime source passed 2,513 local Python tests with one optional skip,
all 36 JavaScript suites, 31 web syntax checks, 120 runtime/script AST checks
and diff checks. Twenty-nine focused package/staging/lifecycle tests cover
closed inventories, identity/hash/config drift, credential/environment isolation,
different trust profiles, permanent claims, interrupted persistence/exec and
historical unknown status. No GitHub Actions workflow is configured or run.

The exact already-built native binary and source bundle were privately staged
without launching or installing a host. Its copied ad-hoc signature verified
as intact, not vendor-authorized. That package's binary passed actual policy and
public task fixtures, including the restricted public config/environment with
three loopback responses, exact native patch, fixed successful command and
known-empty current fixture terminals. No cloud model or desktop pipe was used.
These are package/protocol fixtures, not launch, binding, state-transfer,
historical cleanup, migration or pilot acceptance.

One private non-executing launch scope/preview was prepared; no intent or exec
claim was consumed, no socket/server identity was invented, and no confirmation
was requested. The existing fresh dashboard stayed on the installed PR149/150
source. Its original Play/run/usage/gaps/expiry remained byte-equivalent in the
private databases, paused with zero workers and unknown terminal safety. This
new source has not been installed on that dashboard or native host.
