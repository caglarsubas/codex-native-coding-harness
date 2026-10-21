# Preparation-only startup qualification

Source implementation: `bf157af1f6609ede76145cae30f2cee9152fb7b0`.
Complete orchestrator implementation hash:
`b5578722258be1466335191cd186407af5ac1c955d64a5b3b2352ea6a4dc7e55`.

This report qualifies source and disposable behavior, not live pilot acceptance.
No installation, live approval, load, turn, binding change, usage reset or replay
was performed. The exact live review is prepared separately and remains unconfirmed.

## Results

- Complete Python discovery: 3,415 cases, one skip. Exact discovery multiplicity
  was checked across eight disjoint isolated-process partitions. Seven initially
  passed. One 427-case partition had two failures and 17 errors beginning in an
  older evidence-chronology fixture; the full identical partition subsequently
  passed in a fresh process on unchanged source. Its original failures and rerun
  are retained, not overwritten. The affected retention module also passed all
  27 cases independently. Do not describe the initial run as green or infer a
  production-policy defect merely from this fixture failure. No runtime evidence
  gate, assertion or test expectation was relaxed. All 26 new startup cases pass.
- All 42 JavaScript test files pass. `node --check web/app.js` and syntax checking
  of every web JavaScript file pass. Python AST parsing passes for 367 files.
- Real pinned native fixture: one cold loopback receipt, then exactly one new
  restricted startup load and one new preparation turn on the same Unix
  connection; actual loaded-policy checks, separate receipt and connection close
  pass. Original database/request/history/configuration bytes are preserved.
  The original deadline failure is injected, and the brain mailbox acknowledgment
  is synthetic. This does not prove account entitlement or model tool compliance.
- Rendered 1,440px and 320px disposable dashboards: no overflow, page errors,
  readiness retry or Play control, control POST or native action.
- Live read-only preservation audit: five databases and 1,195 protected records
  unchanged before/after preview. Existing runs, requests, claims, usage, binding
  and host epochs remain unchanged. Native preview observes an unloaded brain;
  policy and current/historical terminal safety remain unknown. No startup claim
  was created. The source-candidate package is not a running installation.

The fixed native executable is the already available operator-pinned binary
with SHA-256 `f7129d8763a45268aaa136b3a50de20acfcb6e07458a672d6c253d6d727f2ec9`.
The fixture uses a new disposable native home and loopback-only provider; it
connects to no live host and makes no external model request. Nothing is downloaded.

## Reproduction

The required complete local discovery remains:

```text
python3 -m unittest discover -s tests -v
node --check web/app.js
```

Focused source and runtime checks:

```text
python3 -B -m unittest discover -s tests -p test_prestart_startup.py -v
node tests/test_prestart_startup_ui.js
python3 -B scripts/qualify_public_host_restart.py --executable EXACT_PINNED_BINARY --sha256 EXACT_SHA256 --prestart-startup
node tests/render_prestart_startup.js
```

Rendering uses existing local Playwright and Chrome; no browser/runtime download
is permitted. The native fixture labels its injected failure, synthetic app
catalog/build metadata and synthetic mailbox publication in its output. It cannot
be substituted for live evidence. Source delivery stops at a PR for manual merge;
installation, exact owner approval and application remain separate steps. No
GitHub Actions, paid CI, background scheduler or independent dispatcher is added.
