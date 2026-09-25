# Docker Compose on a Mac with native Codex

This is a hybrid deployment, not a Linux copy of your workspace. Docker owns the
web gateway; the native Python backend owns the existing private ledger, browser
sessions, inference configuration and installed Codex CLI bridge. No workspace
data or credentials are mounted into the container. No new dispatcher is added.

Browser `127.0.0.1:8768` → Compose gateway → Mac `127.0.0.1:8767`.

## Start

Prerequisites: Docker Desktop running, Docker Compose, Python 3.12+ on the Mac,
and an already registered platform. Use the same registry and private state as
your current native deployment; do not initialize another empty workspace.

1. Before replacing an existing dashboard, ensure it has no in-flight requests
   or background jobs and the brain/workers are safely parked. Back up the private
   SQLite stores using SQLite's backup API and retain private artifacts and auth
   files. Stop only the identified dashboard process, not Codex or its tasks.
2. From this checkout, start the native backend in a dedicated Mac terminal:

   ```sh
   python3 -m orchestrator.cli --platform /absolute/private/platform serve \
     --port 8767 --public-port 8768 \
     --notify-brain /absolute/path/to/installed/codex \
     --inference-env /absolute/private/.env
   ```

   Use the actual existing paths. Omit optional notification/inference flags if
   not configured. `--public-port` is the exact browser port, not permission to
   bind remotely; the backend still listens only on IPv4 loopback.
3. In another terminal, from the same checkout:

   ```sh
   docker compose --env-file /dev/null up -d --build
   docker compose --env-file /dev/null ps
   ```

4. For conventional sign-in, [configure a local account](LOCAL-ACCOUNT.md) and add
   `--account-file /absolute/private/platform/browser-auth/account.json` to every
   native startup command. Open the normal dashboard URL and sign in; no private
   link is required in this mode.

   For deployments without an account, open the private URL in the existing platform's `dashboard-session.json` once
   per browser. Select **Remember this browser** to retain authentication across
   gateway/backend restarts. The private root and public port must stay the same.
   Never share or commit that link. No token is needed in Compose configuration.

Bookmark `http://127.0.0.1:8768/`. Both Chrome and the Codex browser
have separate cookie stores and must each sign in. A temporary login still
expires on backend restart; remembered sessions remain revocable and time-limited.

Docker Desktop shows the `codex-orchestrator` Compose application. The gateway
restarts with Docker unless explicitly stopped. **Docker does not start the Mac
backend or Codex:** keep that terminal/process running, and start it again after
a Mac reboot. This setup does not install a login agent or change your schedules.

## Health, controls and troubleshooting

```sh
docker compose --env-file /dev/null ps
docker compose --env-file /dev/null logs --tail 30 gateway
curl --fail http://127.0.0.1:8768/healthz
docker compose --env-file /dev/null stop
docker compose --env-file /dev/null start
```

`/healthz` exposes only a fixed service name/status. Healthy means the gateway can
reach the native HTTP backend, not that Codex is active, a workspace has Play
authority, a runner is qualified, or Harness automation is ready. Authentication,
workspace controls and all approval/budget/checkpoint restrictions are unchanged.

An unhealthy gateway or HTTP 502/503 generally means the Mac backend is stopped
or the configured ports disagree. An unexpected upstream service fails health.
Assistant requests have a longer bounded gateway wait so the native backend can
finish its inference stream and report its own result. If that answer still fails,
the chat keeps the question for an explicit resend; the answer request itself
does not apply a project control. A failed control confirmation retains its
separate receipt inspection requirement.
Use `127.0.0.1`, not `localhost`: exact Host/Origin validation is intentional.
If Docker reports a port conflict, identify the process first; do not kill an
unrelated service. Docker Desktop's `host.docker.internal` must reach the Mac's
loopback listener; this was verified on the deployment host. Do not solve a
connectivity failure by exposing the backend on `0.0.0.0`.

The proxy never retries requests. A connection failure after a submitted action
can leave its outcome uncertain: inspect the durable receipt before retrying.
It does not forward arbitrary upstream URLs, forwarding headers or upgrades.

Optional alternative ports must match on both sides:

```sh
# Backend: --port 8877 --public-port 8878
ORCHESTRATOR_BACKEND_PORT=8877 ORCHESTRATOR_PUBLIC_PORT=8878 \
  docker compose --env-file /dev/null up -d --build
```

Use the same overrides for later Compose commands. A changed public port is a
different authentication origin and requires pairing again.

## Security and rollback

The gateway image contains only standard-library Python and the fixed proxy.
The build context is allowlisted. It runs non-root, read-only, without Linux
capabilities, host mounts, Docker socket or credentials, and has CPU/memory/PID
limits. Only `127.0.0.1` is published; no LAN, tunnel or hosted ingress is enabled.
Local HTTP assumes a trusted single-user Mac; this is not a remote deployment.
The base image is pinned by digest; updating it is an explicit rebuild/review.
The first build downloads that image; runtime downloads are not required.
There are no new GitHub Actions workflows or paid APIs.

To remove the gateway, use `docker compose --env-file /dev/null down` (no data
volumes exist). Stop the identified backend safely and restart **the same current
source** directly on `--port 8768`, omitting `--public-port` and preserving
`--account-file` when configured. Existing remembered
cookies still bind to the same public origin/private root. Do not downgrade the
application or restore old ledgers over newer receipts as part of network rollback.

Docker networking reference: [connect containers to a host service](https://docs.docker.com/desktop/features/networking/networking-how-tos/).
