"""Phase-owned native metadata collection. Diagnostics, never execution evidence."""
import copy
import json
import re
import subprocess
import time

from . import run_authority as runs
from .admission import exact, identifier, sha
from .core import Refusal, canonical, digest, require
from .native_read_client import ReadProxy, SOURCES, validate_endpoint
from .phase_usage import PhaseUsage

KIND = "native_evidence_report"
GAPS = ["complete_task_tree_source_unavailable", "lifetime_token_counter_source_unavailable",
        "os_process_cleanup_source_unavailable", "per_turn_settings_telemetry_unavailable"]
BOUNDARY = {"executionAuthorized": False, "ownershipReleased": False, "nativeMutationMade": False,
            "taskTreeComplete": False, "phaseUsageAvailable": False, "processCleanupVerified": False,
            "executionTelemetryAvailable": False}


def standard_in(ledger, db, allocation):
    for rid in allocation["spec"]["repositories"]:
        require(ledger.get(db, "repos", rid)["policyProfile"] == "standard",
                "Harness requires its trusted observation adapter")


def endpoint_in(ledger, db):
    meta = ledger.get(db, "meta", 1)
    require(meta.get("nativeEvidenceEndpointHash") and meta.get("nativeEvidenceEndpointRevoked") is False,
            "Exact owner-reviewed native observation endpoint required")
    doc = runs.document(db, meta["nativeEvidenceEndpointHash"], "native_evidence_endpoint")
    require(doc["actor"] == "dashboard_owner" and doc["brainId"] == meta["brainId"] and
            doc["workspaceId"] == runs.missions.workspace(ledger), "Native endpoint identity changed")
    require(doc["version"] == db.execute("SELECT count(*) FROM snapshots WHERE kind='native_evidence_endpoint'").fetchone()[0],
            "Native endpoint pointer is not current")
    return doc


def review_endpoint(bridge, request, *, actor):
    """Internal authenticated-owner seam; intentionally no CLI/HTTP owner route."""
    require(actor == "dashboard_owner", "Only the owner may review an observation endpoint")
    request = copy.deepcopy(request)
    ledger = bridge.ledger
    with ledger.tx() as db:
        meta, key, fp, prior = runs.request_in(ledger, db, request, actor, "native_endpoint_review",
            {"allocationId", "endpoint", "confirmed"})
        if prior: return prior
        require(request["confirmed"] is True and meta["paused"], "Explicit endpoint review while paused required")
        identifier(request["allocationId"])
        with bridge.store.tx() as kernel:
            allocation = bridge.store.get(kernel, "allocations", request["allocationId"])
            require(allocation["spec"]["workspaceId"] == bridge.workspace_id and not allocation["closed"], "Exact open phase required")
            standard_in(ledger, db, allocation)
        validate_endpoint(request["endpoint"])
        count = db.execute("SELECT count(*) FROM snapshots WHERE kind='native_evidence_endpoint'").fetchone()[0]
        require(count < 1000 and (not count or meta.get("nativeEvidenceEndpointHash")), "Endpoint history requires explicit recovery")
        if count:
            previous = runs.document(db, meta["nativeEvidenceEndpointHash"], "native_evidence_endpoint")
            require(previous["version"] == count, "Endpoint pointer changed; explicit recovery required")
        doc = {"kind": "native_evidence_endpoint", "workspaceId": bridge.workspace_id, "brainId": meta["brainId"],
               "actor": actor, "allocationId": allocation["id"], "allocationFingerprint": allocation["fingerprint"],
               "endpoint": request["endpoint"], "at": time.time(), "version": count+1,
               "previousHash": meta.get("nativeEvidenceEndpointHash")}
        value = runs.retain(db, doc["kind"], doc)
        meta.update(nativeEvidenceEndpointHash=value, nativeEvidenceEndpointRevoked=False)
        ledger.put(db, "meta", 1, meta)
        return runs.receipt_in(ledger, db, key, fp, "native_endpoint_review", endpointHash=value)


def revoke_endpoint(ledger, request, *, actor):
    require(actor == "dashboard_owner", "Only the owner may revoke an observation endpoint")
    with ledger.tx() as db:
        meta, key, fp, prior = runs.request_in(ledger, db, request, actor, "native_endpoint_revoke", {"endpointHash"})
        if prior: return prior
        require(meta.get("nativeEvidenceEndpointHash") == request["endpointHash"], "Exact endpoint required")
        endpoint_in(ledger, db)
        meta["nativeEvidenceEndpointRevoked"] = True; ledger.put(db, "meta", 1, meta)
        return runs.receipt_in(ledger, db, key, fp, "native_endpoint_revoke", endpointHash=request["endpointHash"])


def setting(value):
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}", value) else None


def thread_metadata(value):
    require(isinstance(value, dict), "Native thread metadata required")
    identifier(value.get("id"))
    parent = value.get("parentThreadId")
    if parent is not None: identifier(parent)
    status = value.get("status")
    kind = status.get("type") if isinstance(status, dict) else None
    if kind not in ("idle", "active", "notLoaded", "systemError"): kind = "unknown"
    activity = "running" if kind == "active" else "idle" if kind == "idle" and not status.get("activeFlags") else "unknown"
    loaded = kind in ("active", "idle")
    return {"threadId": value["id"], "parentThreadId": parent, "activity": activity, "nativeStatus": kind,
            "configuredSettings": {"model": setting(value.get("model")), "effort": setting(value.get("reasoningEffort"))},
            "settingsSource": "loaded_configuration" if loaded else "persisted_or_unknown",
            "ephemeral": value.get("ephemeral") if type(value.get("ephemeral")) is bool else None}


def pages(client, method, params):
    cursor = None; seen = set(); rows = []
    for _ in range(8):
        result = client.call(method, {**params, "cursor": cursor, "limit": 64})
        require(isinstance(result, dict) and isinstance(result.get("data"), list), "Native page unavailable")
        rows.extend(result["data"])
        require(len(rows) <= 64, "Native page inventory exceeds its bound")
        # Missing cursor is not proof that pagination completed.
        require("nextCursor" in result, "Native pagination completeness unavailable")
        cursor = result["nextCursor"]
        if cursor is None: return rows
        require(isinstance(cursor, str) and 0 < len(cursor) <= 256 and cursor not in seen, "Native cursor repeated or invalid")
        seen.add(cursor)
    raise Refusal("Native page count exceeds its bound")


def collect_pass(client, context):
    roots = {context["brainId"]: None}
    for member in context["membership"]:
        if member["native"]:
            require(member["native"]["hostId"] == "local", "Only local native roots supported")
            require(member["native"]["threadId"] not in roots, "Duplicate native root")
            roots[member["native"]["threadId"]] = member["id"]
    require(len(roots) <= 8, "Native root inventory exceeds its bound")
    forbidden = set(context["otherBrains"]) | {r["threadId"] for r in context["foreignRoots"]} | set(context["pendingClientIds"])
    members = {}; sources = []
    for root, claim in sorted(roots.items()):
        require(root not in forbidden, "Foreign native root")
        children = {}
        for archived in (False, True):
            values = pages(client, "thread/list", {"ancestorThreadId": root, "archived": archived,
                "sourceKinds": SOURCES, "modelProviders": [], "useStateDbOnly": True})
            sources.append(digest(values))
            for value in values:
                row = thread_metadata(value); tid = row["threadId"]
                require(tid not in forbidden and tid not in roots and tid not in members and tid not in children,
                        "Foreign or duplicate native descendant")
                children[tid] = row
        for tid in children:
            cursor, seen = tid, set()
            while cursor != root:
                require(cursor in children and cursor not in seen, "Native descendant ancestry is incomplete or cyclic")
                seen.add(cursor); cursor = children[cursor]["parentThreadId"]
        targets = {root: None, **{tid: row["parentThreadId"] for tid, row in children.items()}}
        require(len(members)+len(targets) <= 64, "Native task inventory exceeds its bound")
        for tid, parent in sorted(targets.items()):
            response = client.call("thread/read", {"threadId": tid, "includeTurns": False})
            require(isinstance(response, dict), "Native thread read unavailable")
            row = thread_metadata(response.get("thread"))
            require(row["threadId"] == tid and row["parentThreadId"] == parent, "Native thread identity/ancestry changed")
            sources.append(digest(response))
            terminals = pages(client, "thread/backgroundTerminals/list", {"threadId": tid})
            identities = []
            for item in terminals:
                require(isinstance(item, dict), "Invalid native terminal metadata")
                identifier(item.get("processId")); identifier(item.get("itemId"))
                pid = item.get("osPid")
                require(pid is None or type(pid) is int and 0 < pid <= 2**32-1, "Invalid native process identity")
                identities.append(digest({"processId": item["processId"], "itemId": item["itemId"], "osPid": pid}))
            require(len(set(identities)) == len(identities), "Duplicate native terminal")
            sources.append(digest(terminals))
            members[tid] = {**row, "hostId": "local", "claimId": claim, "rootThreadId": root,
                            "trackedTerminals": sorted(identities), "observedAt": time.time()}
    known = {r["threadId"] for r in context["required"]}
    require(known <= set(members), "Previously known native task omitted")
    return {"samples": [members[k] for k in sorted(members)], "sourceHash": digest(sources)}


def read_metadata(endpoint, context):
    started = time.time()
    proxy = ReadProxy(endpoint)
    try:
        with proxy as client:
            first = collect_pass(client, context); second = collect_pass(client, context)
        validate_endpoint(endpoint)
        stable = lambda result: [{k: v for k, v in row.items() if k != "observedAt"} for row in result["samples"]]
        unchanged = stable(first) == stable(second)
        issues = [] if unchanged else ["native_metadata_changed_during_collection"]
        if any(row["activity"] == "unknown" for row in second["samples"]): issues.append("native_activity_unknown")
        return {**second, "startedAt": started, "finishedAt": time.time(), "issues": issues,
                "repeatReadStable": unchanged, "readOnlyNativeQueriesAttempted": proxy.query_attempted}
    except (Refusal, OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        # No raw server messages, paths, prompts or terminal commands in reports.
        return {"samples": [], "sourceHash": None, "startedAt": started, "finishedAt": time.time(),
                "issues": ["native_collection_unavailable"], "repeatReadStable": False,
                "readOnlyNativeQueriesAttempted": proxy.query_attempted}

class NativeEvidence:
    def __init__(self, bridge):
        self.bridge, self.ledger, self.store = bridge, bridge.ledger, bridge.store
        self.usage = PhaseUsage(bridge)

    def context_in(self, db, meta, kernel, allocation_id):
        allocation, context, _ = self.usage.context(db, meta, kernel, allocation_id)
        standard_in(self.ledger, db, allocation)
        require(not allocation["closed"], "Phase is closed")
        return allocation, context

    def current_in(self, db, allocation_id):
        slot = digest({"kind": KIND, "allocationId": allocation_id})
        row = db.execute("SELECT kind,CASE WHEN length(CAST(data AS BLOB))<=100 THEN data END FROM snapshots WHERE id=?", (slot,)).fetchone()
        count = db.execute("SELECT count(*) FROM snapshots WHERE kind=? AND json_extract(data,'$.allocationId')=?", (KIND, allocation_id)).fetchone()[0]
        if not row:
            require(not count, "Native evidence pointer missing")
            return None
        require(row[0] == KIND+"_latest" and row[1] is not None, "Native evidence pointer invalid")
        try: pointer = json.loads(row[1])
        except (ValueError, TypeError): raise Refusal("Native evidence pointer invalid") from None
        exact(pointer, {"reportHash"})
        doc = runs.document(db, pointer["reportHash"], KIND)
        require(doc["allocationId"] == allocation_id and doc["version"] == count, "Native evidence pointer changed")
        return doc

    def plan(self, token, allocation_id):
        with self.bridge.locked(token) as (db, meta), self.store.tx() as kernel:
            allocation, context = self.context_in(db, meta, kernel, allocation_id)
            endpoint = endpoint_in(self.ledger, db)
            require(endpoint["allocationId"] == allocation_id and endpoint["allocationFingerprint"] == allocation["fingerprint"], "Endpoint belongs to another phase")
            previous = self.current_in(db, allocation_id)
            return {"allocationId": allocation_id, "expectedRevision": meta["revision"], "contextHash": digest(context),
                    "endpointHash": digest(endpoint), "expectedHash": digest(previous) if previous else None,
                    "requiredSessions": context["required"], "issues": context["issues"]+GAPS,
                    "readOnlyNativeQueriesAttempted": False, **BOUNDARY}

    def collect(self, token, allocation_id, request):
        request = copy.deepcopy(request)
        fields = {"expectedHash", "contextHash", "endpointHash"}
        exact(request, {"id", "expectedRevision", *fields})
        sha(request.get("contextHash")); sha(request.get("endpointHash"))
        if request.get("expectedHash") is not None: sha(request["expectedHash"])
        with self.bridge.locked(token) as (db, meta), self.store.tx() as kernel:
            _, key, fp, prior = runs.request_in(self.ledger, db, request, "designated_brain", "native_evidence_collect", fields, token)
            if prior:
                require(prior["allocationId"] == allocation_id, "Foreign collection replay")
                runs.document(db, prior["reportHash"], KIND)
                return prior
            allocation, context = self.context_in(db, meta, kernel, allocation_id)
            endpoint = endpoint_in(self.ledger, db); previous = self.current_in(db, allocation_id)
            require(endpoint["allocationId"] == allocation_id and endpoint["allocationFingerprint"] == allocation["fingerprint"] and
                    request["endpointHash"] == digest(endpoint) and request["contextHash"] == digest(context) and
                    request["expectedHash"] == (digest(previous) if previous else None), "Collection context changed; inspect again")
            require(not previous or previous["version"] < 1000, "Native evidence history requires maintenance")
        # No ledger/kernel locks while talking to the explicitly reviewed server.
        result = read_metadata(endpoint["endpoint"], context)
        with self.bridge.locked(token) as (db, meta), self.store.tx() as kernel:
            _, key, fp, prior = runs.request_in(self.ledger, db, request, "designated_brain", "native_evidence_collect", fields, token)
            if prior: return prior
            _, current = self.context_in(db, meta, kernel, allocation_id)
            require(digest(current) == request["contextHash"] and digest(endpoint_in(self.ledger, db)) == request["endpointHash"],
                    "Collection context or endpoint changed during I/O")
            latest = self.current_in(db, allocation_id)
            require((digest(latest) if latest else None) == request["expectedHash"], "A newer collection already completed")
            doc = {"kind": KIND, "allocationId": allocation_id, "workspaceId": self.bridge.workspace_id,
                   "contextHash": request["contextHash"], "endpointHash": request["endpointHash"],
                   "version": previous["version"]+1 if previous else 1, "previousHash": request["expectedHash"],
                   "trustBoundary": "public_native_metadata_not_complete_host_attestation", **result, **BOUNDARY}
            doc["issues"] = sorted(set(doc["issues"]+context["issues"]+GAPS))
            value = runs.retain(db, KIND, doc)
            slot = digest({"kind": KIND, "allocationId": allocation_id})
            db.execute("INSERT OR REPLACE INTO snapshots VALUES(?,?,?)", (slot, KIND+"_latest", canonical({"reportHash": value})))
            return runs.receipt_in(self.ledger, db, key, fp, "native_evidence_collect", allocationId=allocation_id,
                                   reportHash=value, issues=doc["issues"])

    def state(self, token, allocation_id):
        with self.bridge.locked(token) as (db, meta), self.store.tx() as kernel:
            _, context = self.context_in(db, meta, kernel, allocation_id)
            doc = self.current_in(db, allocation_id)
            issues = list(doc["issues"]) if doc else ["native_evidence_not_collected"]+GAPS
            if doc:
                if doc["contextHash"] != digest(context): issues.append("native_evidence_context_changed")
                try:
                    endpoint = endpoint_in(self.ledger, db)
                    require(digest(endpoint) == doc["endpointHash"], "Endpoint changed")
                except Refusal: issues.append("native_evidence_endpoint_changed")
                oldest = min([doc["startedAt"]]+[s["observedAt"] for s in doc["samples"]])
                if not 0 <= time.time()-oldest <= 60: issues.append("native_evidence_stale")
            return {"allocationId": allocation_id, "reportHash": digest(doc) if doc else None, "report": doc,
                    "status": "needs_qualified_evidence", "issues": sorted(set(issues)),
                    "readOnlyNativeQueriesAttempted": False, **BOUNDARY}
