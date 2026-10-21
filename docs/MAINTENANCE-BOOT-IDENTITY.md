# Stable maintenance review boot identity

## Root cause

During authorized PR-191 installation, the unchanged prepared maintenance review
failed `current()` with only `context.bootedAt` different: the saved calendar boot
timestamp was `1792596694.64218`, versus `1792596694.703831` on revalidation.
All five databases and 1,419 separately protected private inputs still matched.
The 61.651-millisecond shift was not treated as a valid review or silently patched.
The old review, preview and backup remain untouched and unconfirmed.

Apple's kernel explicitly adjusts the boot-time calendar variables when calendar
time changes. `kern.boottime` reads those variables; its exact floating-point
value is not a stable boot identity. This is a local review-stability defect, not
evidence about native host availability or the reason a native host exited.

Primary sources:

- [Apple XNU calendar-clock implementation](https://github.com/apple-oss-distributions/xnu/blob/main/osfmk/kern/clock.c)
- [Apple XNU read-only boot-session UUID and boot-time sysctls](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/kern/kern_sysctl.c)

## Correction, not an expiry extension

Version 2 reads only fixed `/usr/sbin/sysctl -n kern.bootsessionuuid` and the
existing fixed boot-time metadata read. The UUID must be complete, nonzero and
unchanged at both ends of the local inspection. It is pinned in the new exact
review. A changed UUID refuses even if the device, inode and reported boot time
appear identical. Unsupported identity never falls back to timestamps.

The original reviewed boot timestamp remains immutable. Every historical
observation, receipt and applicable change time must still predate **both** that
original cutoff and the currently observed boot timestamp. A forward calendar
adjustment cannot admit newer evidence; a backward adjustment can tighten the
boundary and refuse. No tolerance, rounding, timestamp renewal, evidence import
or native freshness relaxation is added.

Version-1 reviews are not converted, rehashed, retried or approved by source
installation. A new version-2 review is required. Both versions retain the same
canonical original-startup/inode owner and target fence; an existing partial or
completed claim blocks another attempt regardless of version/source/device.

## Unchanged boundaries

Only the explicit read-only maintenance path can recognize a confirmed
certificate. No SQL/registry/binding update, host connection/launch, load, turn,
permission response, cancellation, readiness/Play/recovery replay, usage reset,
ownership release, current/historical terminal-safety assertion or pilot
acceptance follows. The old source release remains installed inactive; this
correction is separate source delivery until manual merge and authorized rollout.

See [the exact local qualification record](MAINTENANCE-BOOT-IDENTITY-QUALIFICATION.md).
