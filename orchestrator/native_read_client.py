"""Bounded read-only public Codex proxy client. Never starts an app-server."""
import hashlib
import json
import os
from pathlib import Path
import selectors
import stat
import subprocess
import time

from .admission import exact, identifier, sha
from .core import Refusal, canonical, digest, require

MAX_RESPONSE = 1_000_000
MAX_TOTAL = 8_000_000
SOURCES = ["cli", "vscode", "exec", "appServer", "subAgent", "subAgentReview",
           "subAgentCompact", "subAgentThreadSpawn", "subAgentOther", "unknown"]


def secure_path(value, *, socket_file=False):
    require(isinstance(value, str) and 0 < len(value) <= 4096 and "\x00" not in value, "Invalid endpoint path")
    path = Path(value)
    require(path.is_absolute() and str(path.resolve(strict=True)) == value, "Endpoint paths must be canonical without symlinks")
    for parent in path.parents:
        info = parent.stat()
        require(info.st_uid in (0, os.getuid()) and
                (not info.st_mode & 0o022 or info.st_uid == 0 and info.st_mode & stat.S_ISVTX),
                "Endpoint ancestor permissions are unsafe")
    info = path.lstat()
    require(info.st_uid in ((os.getuid(),) if socket_file else (0, os.getuid())) and not info.st_mode & 0o022,
            "Endpoint ownership or permissions are unsafe")
    if socket_file:
        require(stat.S_ISSOCK(info.st_mode) and not path.parent.stat().st_mode & 0o077,
                "Private existing local socket required")
    else:
        require(stat.S_ISREG(info.st_mode) and info.st_mode & 0o111 and info.st_size <= 512_000_000,
                "Bounded installed executable required")
    return path, info


def socket_identity(info):
    return {"device": info.st_dev, "inode": info.st_ino, "owner": info.st_uid,
            "mode": stat.S_IMODE(info.st_mode), "changedNs": info.st_ctime_ns}


def file_identity(info):
    # Reading may update atime. Pin identity, permissions and content-change times.
    return (info.st_dev, info.st_ino, info.st_uid, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def inspect_endpoint(executable, socket_path, server_identity_hash):
    """Internal owner setup inspection only; never connects or executes."""
    sha(server_identity_hash)
    binary, before = secure_path(executable)
    _, sock = secure_path(socket_path, socket_file=True)
    with binary.open("rb") as stream:
        require(file_identity(os.fstat(stream.fileno())) == file_identity(before), "Executable changed during inspection")
        value = hashlib.file_digest(stream, "sha256").hexdigest()
        require(file_identity(os.fstat(stream.fileno())) == file_identity(before) == file_identity(binary.stat()), "Executable changed during inspection")
    return {"executable": executable, "sha256": value, "socket": socket_path,
            "socketIdentity": socket_identity(sock), "serverIdentityHash": server_identity_hash}


def validate_endpoint(value):
    exact(value, {"executable", "sha256", "socket", "socketIdentity", "serverIdentityHash"})
    sha(value["sha256"]); sha(value["serverIdentityHash"])
    require(inspect_endpoint(value["executable"], value["socket"], value["serverIdentityHash"]) == value,
            "Reviewed endpoint changed; owner review required")


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate native response key")
            result[key] = value
        return result
    def constant(_): raise Refusal("Non-finite native response")
    try: return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError): raise Refusal("Invalid native response") from None


class ReadProxy:
    """One explicit connection, fixed argv, allowlisted metadata RPCs only."""
    def __init__(self, endpoint, *, timeout=15):
        self.endpoint = endpoint
        self.timeout = min(15, max(0.05, timeout))
        self.sequence = self.total = 0
        self.buffer = b""
        self.process = None
        self.query_attempted = False

    def __enter__(self):
        validate_endpoint(self.endpoint)
        self.deadline = time.monotonic() + self.timeout
        env = {k: os.environ[k] for k in ("HOME", "USER", "LOGNAME", "TMPDIR") if k in os.environ}
        env["PATH"] = "/usr/bin:/bin"
        try:
            self.process = subprocess.Popen([self.endpoint["executable"], "app-server", "proxy", "--sock", self.endpoint["socket"]],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env,
                close_fds=True, start_new_session=True)
            os.set_blocking(self.process.stdin.fileno(), False)
            os.set_blocking(self.process.stdout.fileno(), False)
            response = self._rpc("initialize", {"clientInfo": {"name": "codex_orchestrator_observer", "version": "1"},
                "capabilities": {"experimentalApi": True}})
            require(isinstance(response, dict), "Missing native server identity")
            identity = {k: response.get(k) for k in ("userAgent", "platformFamily", "platformOs", "codexHome")}
            require(all(isinstance(v, str) and 0 < len(v) <= 4096 for v in identity.values()) and
                    identity["platformFamily"] == "unix" and digest(identity) == self.endpoint["serverIdentityHash"],
                    "Native server identity changed")
            self._write({"method": "initialized", "params": {}})
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        if self.process:
            for stream in (self.process.stdin, self.process.stdout):
                if stream: stream.close()
            if self.process.poll() is None:
                self.process.terminate()
                try: self.process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    self.process.kill(); self.process.wait(timeout=0.5)
            self.process = None

    def _ready(self, stream, event):
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, "Native read deadline exceeded")
        with selectors.DefaultSelector() as selector:
            selector.register(stream, event)
            require(selector.select(remaining), "Native read deadline exceeded")

    def _write(self, value):
        raw = (canonical(value)+"\n").encode()
        require(len(raw) <= 4096, "Native request exceeds its bound")
        while raw:
            self._ready(self.process.stdin, selectors.EVENT_WRITE)
            try: size = os.write(self.process.stdin.fileno(), raw)
            except BlockingIOError: continue
            require(size > 0, "Native proxy input closed")
            raw = raw[size:]

    def _line(self):
        while b"\n" not in self.buffer:
            self._ready(self.process.stdout, selectors.EVENT_READ)
            try: chunk = os.read(self.process.stdout.fileno(), 65536)
            except BlockingIOError: continue
            require(chunk, "Native proxy output closed")
            self.total += len(chunk); self.buffer += chunk
            require(self.total <= MAX_TOTAL and len(self.buffer) <= MAX_RESPONSE, "Native response exceeds its bound")
        line, self.buffer = self.buffer.split(b"\n", 1)
        return decode(line)

    def _rpc(self, method, params):
        self.sequence += 1
        require(self.sequence <= 128, "Native query count exceeds its bound")
        self.query_attempted = True
        self._write({"id": self.sequence, "method": method, "params": params})
        for _ in range(65):
            row = self._line()
            require(isinstance(row, dict), "Invalid native response envelope")
            if "id" not in row:
                require(isinstance(row.get("method"), str), "Malformed native notification")
                continue  # Drop notifications, including all conversation content.
            require("method" not in row and type(row["id"]) is int and row["id"] == self.sequence,
                    "Unexpected native response or server request")
            require("error" not in row and "result" in row, "Native read unavailable")
            return row["result"]
        raise Refusal("Native notification count exceeds its bound")

    def call(self, method, params):
        """Callers cannot use this client for an arbitrary RPC or broaden listing."""
        if method == "thread/read":
            exact(params, {"threadId", "includeTurns"}); identifier(params["threadId"])
            require(params["includeTurns"] is False, "Metadata-only native reads required")
        elif method == "thread/list":
            exact(params, {"ancestorThreadId", "archived", "cursor", "limit", "sourceKinds", "modelProviders", "useStateDbOnly"})
            identifier(params["ancestorThreadId"])
            require(type(params["archived"]) is bool and params["sourceKinds"] == SOURCES and
                    params["modelProviders"] == [] and params["useStateDbOnly"] is True, "Exact scoped read-only list required")
        elif method == "thread/backgroundTerminals/list":
            exact(params, {"threadId", "cursor", "limit"}); identifier(params["threadId"])
        else: raise Refusal("Native mutation or unsupported RPC refused")
        if "cursor" in params:
            require(params["cursor"] is None or isinstance(params["cursor"], str) and 0 < len(params["cursor"]) <= 256,
                    "Invalid native cursor")
            require(type(params["limit"]) is int and params["limit"] == 64, "Fixed native page bound required")
        return self._rpc(method, params)
