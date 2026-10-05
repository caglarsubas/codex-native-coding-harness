"""Opt-in operator host supervision, not a dispatcher or automatic restart.

Runs one exact, privately reviewed guarded launcher. Foreground supervision keeps
the caller alive; detached supervision proves process lifetime only, not native
app-tools trust. The launcher must validate its execution context and policy.
This module never discovers sockets, rebinds a ledger or invokes native task RPCs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

from .core import Refusal, canonical, digest, require

# Retain ownership of detached children while this operator process is alive;
# never turn a Popen destructor/foreground request lifetime into host teardown.
_supervisors = []


def private_file(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=True) == path, "Use a canonical private path without symlinks")
    for parent in path.parents:
        info = parent.stat()
        require(info.st_uid in (0, os.getuid()) and
                (not info.st_mode & 0o022 or info.st_uid == 0 and info.st_mode & stat.S_ISVTX),
                "Unsafe runtime ancestor")
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077 and
            info.st_size <= 65536, "Small owner-only runtime file required")
    return path


def specification(manifest):
    value = json.loads(private_file(manifest).read_text())
    return validate_spec(value)


def validate_spec(value):
    require(isinstance(value, dict) and set(value) == {"schemaVersion", "profile", "launcher", "launcherSha256", "cwd"} and
            type(value["schemaVersion"]) is int and value["schemaVersion"] == 1 and value["profile"] == "standard_owned_host_v1", "Exact standard owned-host launch manifest required")
    launcher = private_file(value["launcher"])
    require(hashlib.sha256(launcher.read_bytes()).hexdigest() == value["launcherSha256"], "Reviewed launcher changed")
    cwd = Path(value["cwd"])
    require(cwd.is_absolute() and cwd.resolve(strict=True) == cwd and cwd.is_dir(), "Exact existing checkout required")
    return value


def write_record(path, value):
    # Private runtime metadata only, no environment, native output or transcript.
    temp = path.with_name(path.name + ".next")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        output.write(canonical(value))
    os.replace(temp, path)


def review_hash(spec, mode):
    require(mode in ("foreground", "detached"), "Unsupported supervision mode")
    # Preserve historical detached reviews. They cannot authorize foreground
    # execution: the new mode requires its own exact, mode-bound owner review.
    return digest(spec) if mode == "detached" else digest({"manifestHash": digest(spec), "mode": mode})


def prepare_attempt(manifest, attempt, confirm_hash, mode):
    spec = specification(manifest)
    require(confirm_hash == review_hash(spec, mode), "Review the exact launch mode and manifest hash first")
    # This is only a presence fence. A pipe is NOT native connectivity proof;
    # the reviewed guarded launcher must validate it in its app-owned context.
    require(bool(os.environ.get("CODEX_APP_TOOLS_PIPE_PATH")), "Launch from the current Codex execution context; do not copy native environment values")
    attempt = Path(attempt)
    require(attempt.is_absolute() and attempt.parent.resolve(strict=True) == attempt.parent and
            attempt.parent.stat().st_uid == os.getuid() and not attempt.parent.stat().st_mode & 0o077,
            "Use a new attempt directory under a canonical owner-only runtime directory")
    try:
        attempt.mkdir(mode=0o700)
    except FileExistsError:
        raise Refusal("Attempt already exists; inspect its lifecycle record, never replay its launch") from None
    write_record(attempt / "launch.json", {"spec": spec, "manifestHash": digest(spec), "mode": mode,
                                          "reviewHash": confirm_hash, "createdAt": time.time()})
    # The exclusive intent precedes process creation. Even a lost Popen result
    # never permits this attempt to start a second host.
    write_record(attempt / "status.json", {"status": "launch_intent", "mode": mode, "observedAt": time.time(),
                                          "hostReady": False, "nativeToolsQualified": False})
    return attempt


def launch(manifest, attempt, confirm_hash):
    attempt = prepare_attempt(manifest, attempt, confirm_hash, "detached")
    try:
        supervisor = subprocess.Popen([sys.executable, "-m", "orchestrator.host_lifecycle", "_monitor", str(attempt)],
                         cwd=str(Path(__file__).resolve().parent.parent), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True, start_new_session=True)
        _supervisors[:] = [p for p in _supervisors if p.poll() is None]
        _supervisors.append(supervisor)
    except OSError:
        write_record(attempt / "status.json", {"status": "launch_failed", "mode": "detached",
                     "observedAt": time.time(), "hostReady": False, "nativeToolsQualified": False})
        raise Refusal("Supervisor could not start; launch intent remains retained") from None
    return {"status": "launch_requested", "attempt": str(attempt), "mode": "detached", "hostReady": False,
            "nativeToolsQualified": False,
            "boundary": "Process supervision only; detached ancestry may be rejected by Codex native app tools."}


def run_foreground(manifest, attempt, confirm_hash):
    attempt = prepare_attempt(manifest, attempt, confirm_hash, "foreground")
    # No detached Python supervisor or daemon fallback. This call stays in the
    # current app-owned process ancestry until the guarded launcher exits.
    return monitor(attempt, foreground=True)


def monitor(attempt, *, foreground=False):
    attempt = Path(attempt)
    record = json.loads(private_file(attempt / "launch.json").read_text())
    mode = record.get("mode", "detached")
    require(mode == ("foreground" if foreground else "detached"), "Supervisor mode differs from the reviewed intent")
    require(record.get("reviewHash", record["manifestHash"]) == review_hash(record["spec"], mode),
            "Reviewed supervision intent changed")
    # A replayed monitor cannot create another native process either.
    try:
        claim = os.open(attempt / "monitor.claim", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise Refusal("Supervisor attempt already claimed") from None
    os.close(claim)
    spec = validate_spec(record["spec"])
    require(digest(spec) == record["manifestHash"], "Launch manifest changed")
    launcher = private_file(spec["launcher"])
    require(hashlib.sha256(launcher.read_bytes()).hexdigest() == spec["launcherSha256"], "Reviewed launcher changed before launch")
    child = None
    try:
        child = subprocess.Popen(["/bin/zsh", str(launcher)], cwd=spec["cwd"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 close_fds=True)
        write_record(attempt / "status.json", {"status": "process_running", "supervisorPid": os.getpid(),
                     "pid": child.pid, "mode": mode, "observedAt": time.time(), "hostReady": False,
                     "nativeToolsQualified": False})
        # No timeout, polling dispatcher, native task call or automatic restart.
        code = child.wait()
        write_record(attempt / "status.json", {"status": "process_exited", "pid": child.pid,
                     "exitCode": code if code >= 0 else None, "signal": -code if code < 0 else None,
                     "mode": mode, "observedAt": time.time(), "hostReady": False,
                     "nativeToolsQualified": False, "restarted": False})
    except (OSError, KeyboardInterrupt) as error:
        # Losing monitoring/record I/O after Popen is not proof of non-creation.
        # Preserve the PID and uncertainty; neither state permits a restart.
        write_record(attempt / "status.json", {"status": "process_outcome_unknown" if child else "launch_failed",
                     "pid": child.pid if child else None, "mode": mode, "observedAt": time.time(),
                     "hostReady": False, "nativeToolsQualified": False, "restarted": False})
        if isinstance(error, KeyboardInterrupt):
            raise
    return json.loads(private_file(attempt / "status.json").read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    preview = sub.add_parser("preview"); preview.add_argument("manifest", type=Path)
    preview.add_argument("--mode", choices=("foreground", "detached"), default="detached")
    start = sub.add_parser("start"); start.add_argument("manifest", type=Path); start.add_argument("attempt", type=Path)
    start.add_argument("--confirm-hash", required=True)
    run = sub.add_parser("run", help="Keep the supervisor in the current app-owned foreground context")
    run.add_argument("manifest", type=Path); run.add_argument("attempt", type=Path)
    run.add_argument("--confirm-hash", required=True)
    status = sub.add_parser("status"); status.add_argument("attempt", type=Path)
    internal = sub.add_parser("_monitor", help=argparse.SUPPRESS); internal.add_argument("attempt", type=Path)
    args = parser.parse_args()
    try:
        if args.operation == "preview":
            spec = specification(args.manifest)
            result = {"spec": spec, "manifestHash": digest(spec), "mode": args.mode,
                      "reviewHash": review_hash(spec, args.mode), "startsHost": False,
                      "nativeToolsQualified": False,
                      "boundary": ("Keep the current app-owned terminal open; native tools need separate observation."
                                   if args.mode == "foreground" else
                                   "Process supervision only; detached ancestry may be rejected by Codex native app tools.")}
        elif args.operation == "start":
            result = launch(args.manifest, args.attempt, args.confirm_hash)
        elif args.operation == "run":
            result = run_foreground(args.manifest, args.attempt, args.confirm_hash)
        elif args.operation == "status":
            result = json.loads(private_file(args.attempt / "status.json").read_text())
            # An old running record is historical, never a current liveness claim.
            result["historical"] = True
        else:
            monitor(args.attempt); return
        print(canonical(result))
    except (Refusal, OSError, ValueError) as error:
        parser.exit(1, "Host lifecycle refused: " + (str(error) if isinstance(error, Refusal) else "private runtime unavailable") + "\n")
    except KeyboardInterrupt:
        parser.exit(130, "Host monitoring interrupted; inspect the retained attempt, never replay its launch.\n")


if __name__ == "__main__":
    main()
