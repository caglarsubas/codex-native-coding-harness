# Owner-reviewed native source patch

`patches/public-host-identity.patch` is the combined Code Mode enforcement,
loaded-thread policy reporting and exact empty-store project metadata restore
patch against public Codex commit
`740e5af33c71225640e0c1c1555c514c2c93ab74`
(`rust-v0.162.0-alpha.17.2`). It is source, not a signed runtime or installation.

Apply it only to that exact clean, independently reviewed source checkout:

```text
git apply --check /ABSOLUTE/PATH/public-host-identity.patch
git apply /ABSOLUTE/PATH/public-host-identity.patch
```

Generated compressed protocol exports are deliberately not embedded as opaque
binary diffs. Regenerate them using the native protocol's existing ignored test
entrypoint from `codex-rs`, with `CODEX_APP_SERVER_SCHEMA_ROOT` set to that
checkout's absolute `app-server-protocol/schema` directory:

```text
CODEX_APP_SERVER_SCHEMA_EXPERIMENTAL=0 cargo test --offline -p codex-app-server-protocol --lib schema_fixtures_tests::write_schema_fixtures_from_env -- --exact --ignored
CODEX_APP_SERVER_SCHEMA_EXPERIMENTAL=1 cargo test --offline -p codex-app-server-protocol --lib schema_fixtures_tests::write_schema_fixtures_from_env -- --exact --ignored
cargo test --offline -p codex-state --lib
cargo test --offline -p codex-app-server-protocol --lib
cargo build --offline --release -p codex-cli --bin codex
```

These use already installed, separately authorized Rust/dependencies. No download,
`uv` SDK setup, telemetry/provider, paid CI, signing impersonation or desktop
peer-check bypass is part of this source delivery. The generated stable API has
no new ordinary operation; the exact restore remains experimental/opt-in.

The private qualified source commit is
`23c298819ad88b8dcc3ef12cf955b852ff5dc33b`, tree
`b42c8c9891cdb71c70b72a055ed5cfd97f59f6ba`. Public source patch application and
regeneration must be independently checked before assigning any build pins;
do not infer that another binary came from this tree. A separately staged
private source bundle retains the complete generated files for exact review.

The compiled-runtime identity fixture is described in
`docs/PUBLIC-IDENTITY-TRANSFER.md`. Build/source tests and disposable protocol
fixtures do not establish installed launch provenance, effective live policy,
authentication, old terminal cleanup, same-run continuation or pilot acceptance.
