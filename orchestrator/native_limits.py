"""Native account-limit projections. No token billing, model calls or reset credits."""
import json
import math

from .admission import exact, identifier, sha, timestamp
from .core import Refusal, canonical, digest, require

KIND = "native_account_observation"


def bounded(value, maximum=128000):
    try: raw = canonical(value).encode()
    except (TypeError, ValueError, RecursionError) as error:
        raise Refusal("Native response must be bounded finite JSON") from error
    require(len(raw) <= maximum, "Native response exceeds its bound")
    return digest(value)


def normalize(result, observed_at):
    timestamp(observed_at); source = bounded(result)
    require(isinstance(result, dict), "Native usage response must be an object")
    issues = []; windows = {"short": None, "long": None}
    if result.get("errors") or result.get("error") or result.get("isError"):
        issues.append("native_tool_error")
    account = result.get("accountId")
    account_key = digest({"accountId": account}) if isinstance(account, str) and 0 < len(account) <= 256 else None
    if account_key is None: issues.append("account_identity_unavailable")
    if result.get("ordinaryUsageAllowed") is not True: issues.append("ordinary_usage_not_confirmed")
    # A present nonempty bucket map is authoritative; never select a random
    # model bucket or fall back from its missing Codex bucket to older fields.
    buckets = result.get("rateLimitsByLimitId")
    if buckets is None or buckets == {}: bucket = result.get("rateLimits")
    else: bucket = buckets.get("codex") if isinstance(buckets, dict) else None
    if not isinstance(bucket, dict) or bucket.get("limitId") not in (None, "codex"):
        bucket = {}; issues.append("codex_bucket_unavailable")
    if bucket.get("spendControlReached") is not False: issues.append("spend_control_not_clear")
    if bucket.get("rateLimitReachedType") is not None: issues.append("rate_limit_reached")
    seen = set()
    for slot in ("primary", "secondary"):
        window = bucket.get(slot)
        if window is None: continue
        if not isinstance(window, dict): issues.append("invalid_window"); continue
        duration = window.get("windowDurationMins")
        name = {300: "short", 10080: "long"}.get(duration) if type(duration) is int else None
        if name is None: issues.append("unsupported_window_duration"); continue
        if name in seen: windows[name] = None; issues.append("duplicate_window_duration"); continue
        seen.add(name)
        used, reset = window.get("usedPercent"), window.get("resetsAt")
        if (type(used) not in (int, float) or not math.isfinite(used) or used < 0 or
                type(reset) not in (int, float) or not math.isfinite(reset) or reset <= observed_at):
            issues.append("invalid_or_reset_"+name+"_window"); continue
        windows[name] = {"usedPercent": min(100, used), "resetsAt": reset}
    for name, value in windows.items():
        if value is None: issues.append(name+"_window_unavailable")
    # Credits, plan labels, upsells, identities and unrelated bucket payloads
    # are deliberately not retained. Account identity is a private digest only.
    return {"kind": KIND, "schemaVersion": 1, "observedAt": observed_at, "sourceHash": source,
            "accountKey": account_key, "windows": windows, "issues": sorted(set(issues)),
            "complete": not issues, "tokenCountersAvailable": False}


def exists(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE name='native_account_records'").fetchone() is not None


def record_in(db, key):
    sha(key)
    require(exists(db), "Native account journal missing; retain admission fence")
    row = db.execute("SELECT data FROM native_account_records WHERE hash=? AND length(CAST(data AS BLOB))<=16000", (key,)).fetchone()
    require(row is not None, "Native account record missing or oversized")
    doc = json.loads(row[0])
    require(digest(doc) == key and doc["kind"] == KIND, "Native account evidence integrity changed")
    return doc


def current_in(store, db):
    meta = store.get(db, "meta", 1); pointer = meta.get("nativeAccountHash")
    count = db.execute("SELECT count(*) FROM native_account_records").fetchone()[0] if exists(db) else 0
    if pointer is None:
        require(not count and not meta.get("nativeAccountIdentity"), "Native account pointer missing; do not fall back")
        return None
    doc = record_in(db, pointer)
    require(doc["version"] == count and doc["accountIdentity"] == meta.get("nativeAccountIdentity"),
            "Native account history or identity diverged")
    if doc["previousHash"] is not None:
        prior = record_in(db, doc["previousHash"])
        require(prior["version"]+1 == doc["version"], "Native account history is incomplete")
    return doc


def legacy_projection(doc):
    p = doc["projection"]
    return {"observedAt": p["observedAt"], "evidenceHash": digest(doc), "windows": p["windows"]}


def enforce(store, db):
    """Once enabled explicitly by observation, older manual limits cannot bypass it."""
    doc = current_in(store, db)
    if doc is None: return
    meta = store.get(db, "meta", 1); p = doc["projection"]
    store.fresh(p["observedAt"], meta["policy"])
    require(p["complete"] and not doc["bindingIssues"], "Native account limits incomplete or changed; new work remains fenced")
    require(meta["account"] == legacy_projection(doc), "Account limits diverged from native observation; no legacy fallback")


def retain(store, db, workspace_id, ledger_id, request):
    exact(request, {"id", "expectedHash", "observedAt", "result"})
    identifier(request["id"])
    if request["expectedHash"] is not None: sha(request["expectedHash"])
    projection = normalize(request["result"], request["observedAt"])
    current = current_in(store, db); meta = store.get(db, "meta", 1)
    key = digest({"workspaceId": workspace_id, "ledgerIdentity": ledger_id, "id": request["id"]})
    fingerprint = digest({"expectedHash": request["expectedHash"], "projection": projection})
    old = db.execute("SELECT hash FROM native_account_records WHERE request=?", (key,)).fetchone() if exists(db) else None
    if old:
        prior = record_in(db, old[0])
        require(prior["fingerprint"] == fingerprint, "Account request ID reused with different content")
        return {"recordHash": old[0], "currentHash": digest(current), "historical": old[0] != digest(current)}
    require(request["expectedHash"] == meta.get("nativeAccountHash"), "Native account observation changed; inspect before recording")
    store.fresh(projection["observedAt"], meta["policy"])
    previous_time = (current["projection"]["observedAt"] if current else
                     (meta["account"] or {}).get("observedAt", 0))
    require(projection["observedAt"] > previous_time, "Native account observation moved backwards")
    pinned = meta.get("nativeAccountIdentity") or projection["accountKey"]
    binding_issues = ["account_identity_changed"] if pinned and projection["accountKey"] not in (None, pinned) else []
    doc = {"kind": KIND, "schemaVersion": 1, "workspaceId": workspace_id, "ledgerIdentity": ledger_id,
           "projection": projection, "accountIdentity": pinned, "bindingIssues": binding_issues,
           "fingerprint": fingerprint, "version": current["version"]+1 if current else 1,
           "previousHash": meta.get("nativeAccountHash"), "at": store.clock()}
    require(doc["version"] <= 10000, "Native account history requires explicit archival migration")
    db.execute("CREATE TABLE IF NOT EXISTS native_account_records(hash TEXT PRIMARY KEY, request TEXT UNIQUE NOT NULL, data TEXT NOT NULL)")
    digest_doc = digest(doc)
    db.execute("INSERT INTO native_account_records VALUES(?,?,?)", (digest_doc, key, canonical(doc)))
    meta.update(nativeAccountHash=digest_doc, nativeAccountIdentity=pinned)
    # Never leave an older healthy projection visible to a cached reader that
    # predates the native journal. Historical evidence remains in the journal.
    meta["account"] = legacy_projection(doc) if projection["complete"] and not binding_issues else None
    store.put(db, "meta", 1, meta)
    store.event(db, "native_account_observed", recordHash=digest_doc)
    return {"recordHash": digest_doc, "currentHash": digest_doc, "historical": False}


def status(store, db):
    doc = current_in(store, db)
    meta = store.get(db, "meta", 1)
    if doc is None: return {"currentHash": None, "status": "not_observed", "windows": None, "issues": []}
    p = doc["projection"]; issues = list(p["issues"])+doc["bindingIssues"]
    if p["complete"] and not doc["bindingIssues"] and meta["account"] != legacy_projection(doc):
        issues.append("account_projection_diverged")
    age = store.clock()-p["observedAt"]
    if not 0 <= age <= meta["policy"]["maxObservationAgeSeconds"]: issues.append("observation_stale_or_future")
    windows = {}
    for name, window in p["windows"].items():
        windows[name] = {**window, "remainingPercent": 100-window["usedPercent"]} if window else None
        if window:
            if window["resetsAt"] <= store.clock(): issues.append(name+"_window_reset")
            if 100-window["usedPercent"] < meta["policy"]["minAccountRemainingPercent"]: issues.append(name+"_headroom_low")
    return {"currentHash": digest(doc), "observedAt": p["observedAt"], "status": "blocked" if issues else "headroom_observed",
            "windows": windows, "issues": sorted(set(issues)), "phaseTokenUsageUpdated": False,
            "executionAuthorized": False, "nativeCallMade": False}
