# Local administrator sign-in

The dashboard can use one local account name/password instead of bootstrap links.
This is an installation-wide administrator across registered workspaces, not a
multi-user identity service, email account, cloud account or role system. Signing
in does not approve work or change any workspace's authority.

## Configure once on the Mac

Use a canonical absolute path inside your private platform directory. The parent
directory must belong to you and have mode 700. This interactive command prompts
twice without echoing the password; never put a password in argv, `.env`, Compose,
a checked-in file or a shell-history command:

```sh
python3 -m orchestrator.account \
  --file /absolute/private/platform/browser-auth/account.json \
  --username owner@example.test
```

Start the native dashboard with the additional flag:

```sh
python3 -m orchestrator.cli --platform /absolute/private/platform serve \
  --port 8767 --public-port 8768 \
  --account-file /absolute/private/platform/browser-auth/account.json
```

Retain your existing `--notify-brain` and `--inference-env` arguments if configured.
The Docker gateway remains unchanged in purpose; do not mount the account file or
other private state into it. Direct non-Docker deployments can omit `--public-port`.

Bookmark `http://127.0.0.1:8768/` and sign in with the configured account. No private
URL is required. Password managers can use the username/current-password fields.
**Remember this browser for 30 days** is unchecked by default; temporary sessions
expire after eight hours or a backend restart. Browser access still supports
7/30/90-day remembered sessions, logout and explicit revoke-all.

Account mode disables token-link login and writes a token-free URL to the local
session file. The browser cookie namespace binds the credential identity as well
as the installation and origin, so old link-mode cookies cannot bypass sign-in.
Missing, unsafe or corrupt configured account files fail closed; there is no
automatic fallback to private links. Omitting the account flag deliberately starts
legacy link mode, so preserve it in every startup command.

## Password reset and recovery

There is no email recovery or public registration endpoint. Stop the identified
dashboard safely, then repeat the setup command with `--replace`. It is an explicit
local-owner reset. Restart with the same account-file flag. Replacing the verifier
invalidates existing sessions through a new credential identity; a still-running
backend refuses the changed file until restarted. Existing brains/workers are not
stopped by account sign-out or reset; use the normal safe checkpoint controls.

After five unsuccessful attempts, all account sign-ins are blocked for five minutes.
The counter is retained on disk before verification and survives backend restarts.
Unknown names and wrong passwords receive the same error and incur the same hash
work. Login throttling is not a guarantee against a malicious local OS user or a
denial-of-service attack. A local owner can explicitly reset credentials if needed.

## Storage and boundary

Only a random salt and scrypt verifier are retained (mode 600); no plaintext or
reversible password is saved. Parameters are `N=2^17, r=8, p=1`, with serialized
verification and constant-time verifier comparison. This follows the
[OWASP scrypt guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#scrypt)
without adding a package dependency. Account setup requires at least 10 characters
and allows up to 1024 UTF-8 bytes. Prefer a unique, longer password; this is not a
breached-password check or an MFA implementation.

Strict Host/Origin checks, scoped CSRF, HttpOnly/SameSite cookies and approval gates
remain in place. HTTP is limited to the trusted local Mac and Docker Desktop path;
credentials are not sent to the inference service or Codex. Do not expose this
listener to a LAN or the internet without a separately reviewed HTTPS/identity
deployment. The single account is not a security boundary against the Mac owner.
