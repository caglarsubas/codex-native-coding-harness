"""Fixed-destination local gateway. No ledger, Codex, model or dispatch access."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import sys


def port(value):
    result = int(value)
    if not 1 <= result <= 65535:
        raise ValueError("Invalid port")
    return result


class Gateway(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, backend_host, backend_port, public_port):
        self.backend_host = backend_host
        self.backend_port = port(backend_port)
        self.public_host = f"127.0.0.1:{port(public_port)}"
        self.origin = "http://" + self.public_host
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalGateway"

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *args):
        pass  # Never log private URLs, headers, credentials or message bodies.

    def reject(self, status, message):
        data = json.dumps({"error": message}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True

    def do_GET(self):
        self.proxy()

    def do_POST(self):
        self.proxy()

    def proxy(self):
        for name in ("Host", "Origin", "Content-Length", "Content-Type", "Cookie", "X-CSRF-Token"):
            if len(self.headers.get_all(name, [])) > 1:
                return self.reject(400, "Duplicate request header")
        if self.headers.get("Host") != self.server.public_host:
            return self.reject(403, "Host refused")
        origin = self.headers.get("Origin")
        if (origin is not None and origin != self.server.origin) or (self.command == "POST" and origin is None):
            return self.reject(403, "Origin refused")
        if not self.path.startswith("/") or self.path.startswith("//") or "#" in self.path:
            return self.reject(400, "Relative request path required")
        if "Transfer-Encoding" in self.headers or "Expect" in self.headers or "Upgrade" in self.headers:
            return self.reject(400, "Unsupported request framing")
        raw_length = self.headers.get("Content-Length", "0")
        if not raw_length.isascii() or not raw_length.isdecimal() or len(raw_length) > 5:
            return self.reject(400, "Invalid request length")
        length = int(raw_length)
        if length > 32768:
            return self.reject(413, "Request too large")
        if self.command == "GET" and length:
            return self.reject(400, "GET body refused")
        headers = {"Host": self.server.public_host, "Connection": "close"}
        for name in ("Origin", "Content-Type", "Cookie", "X-CSRF-Token"):
            if name in self.headers:
                headers[name] = self.headers[name]
        # Never forward caller-selected routing, forwarding or hop-by-hop headers.
        upstream = http.client.HTTPConnection(self.server.backend_host, self.server.backend_port,
                                              timeout=3 if self.path == "/healthz" else 180)
        response_started = False
        try:
            body = self.rfile.read(length) if length else None
            if body is not None and len(body) != length:
                return self.reject(400, "Incomplete request")
            upstream.request(self.command, self.path, body=body, headers=headers)
            response = upstream.getresponse()
            if self.path == "/healthz" and self.command == "GET":
                health = response.read(1025)
                if response.status != 200 or len(health) > 1024 or json.loads(health) != {"status": "ok", "service": "codex-orchestrator"}:
                    return self.reject(503, "Native backend unavailable")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(health)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                response_started = True
                self.wfile.write(health)
                return
            self.send_response(response.status)
            # Closed response headers preserve cookies/security, not upstream routing.
            allowed = {"content-type", "content-length", "cache-control", "set-cookie",
                       "content-security-policy", "x-content-type-options", "referrer-policy",
                       "x-frame-options", "content-disposition", "retry-after"}
            for name, value in response.getheaders():
                if name.lower() in allowed:
                    self.send_header(name, value)
            self.send_header("Connection", "close")
            self.end_headers()
            response_started = True
            while chunk := response.read(65536):
                self.wfile.write(chunk)
        except (OSError, http.client.HTTPException, ValueError):
            if not response_started:
                self.reject(503 if self.path == "/healthz" else 502,
                            "Native backend unavailable; check its process. A submitted action may have been recorded; inspect its receipt before retrying.")
        finally:
            upstream.close()
            self.close_connection = True


def main():
    public = port(os.environ.get("GATEWAY_PUBLIC_PORT", "8768"))
    if sys.argv[1:] == ["--healthcheck"]:
        connection = http.client.HTTPConnection("127.0.0.1", 8080, timeout=4)
        try:
            connection.request("GET", "/healthz", headers={"Host": f"127.0.0.1:{public}"})
            response = connection.getresponse()
            return 0 if response.status == 200 else 1
        except (OSError, http.client.HTTPException):
            return 1
        finally:
            connection.close()
    backend = port(os.environ.get("GATEWAY_BACKEND_PORT", "8767"))
    server = Gateway(("0.0.0.0", 8080), "host.docker.internal", backend, public)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
