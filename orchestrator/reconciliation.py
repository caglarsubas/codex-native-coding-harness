"""Versioned review of admission evidence. No release, allocation or native calls."""
import contextlib
import json
import sqlite3
import time

from . import adoption, admission_legacy, enrollment
from .admission import AdmissionStore, exact, identifier, integer, timestamp
from .core import canonical, digest, require
from .reconciliation_evidence import assess, validate
from .workspaces import fingerprint

EFFECT = "Retain this exact evidence review and any consistent usage baseline. No ownership release, allocation, native action or activation."


def decode_record(raw):
    value = json.loads(raw)
    require(isinstance(value, dict) and value.get("recordHash") == digest({k: v for k, v in value.items() if k != "recordHash"}),
            "Evidence history hash mismatch; explicit recovery required")
    require(value["reviewHash"] == digest(value["reviewDocument"]), "Retained review document hash mismatch")
    return value


def records(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='admission_reconciliations'").fetchone():
        return []
    return list(reversed([decode_record(row[0]) for row in db.execute("SELECT data FROM admission_reconciliations ORDER BY version DESC LIMIT 20")]))


def anchor_in(db, before_version=10001):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='admission_reconciliations'").fetchone(): return None
    row = db.execute("SELECT data FROM admission_reconciliations WHERE version < ? AND json_extract(data,'$.report.baselineCandidate')=1 ORDER BY version DESC LIMIT 1", (before_version,)).fetchone()
    return decode_record(row[0]) if row else None


@contextlib.contextmanager
def locked_context(registry, db):
    """Registry -> workspace IDs -> kernel; never reacquire registry inside."""
    record = adoption.record_in(db)
    require(record and record["state"] == "quarantined", "Complete ownership adoption before evidence reconciliation")
    with enrollment.locked_ledgers(enrollment.members_in(db)) as locked:
        source = adoption.source(registry, db, locked)
        bundle = record["bundle"]
        require(source["registryIdentity"] == bundle["registryIdentity"] and source["membershipHash"] == bundle["membershipHash"],
                "Adopted scope changed; explicit migration required")
        admission_legacy.require_import_fences(registry.root, bundle, record["kernelIdentity"])
        store = AdmissionStore(registry.root, expected_identity=record["kernelIdentity"])
        with store.tx() as kernel:
            meta = store.get(kernel, "meta", 1)
            require(meta.get("legacyAdoption", {}).get("bundleHash") == digest(bundle) and meta["policy"] == bundle["policy"],
                    "Adopted kernel binding or policy changed")
            claims = store.rows(kernel, "legacy_claims")
            require(claims == sorted(bundle["claims"], key=lambda c: c["id"]), "Imported ownership changed; explicit migration required")
            require(not store.rows(kernel, "allocations") and not store.rows(kernel, "claims") and
                    not kernel.execute("SELECT 1 FROM resources").fetchone(),
                    "Unexpected allocations during quarantine")
            event = db.execute("SELECT data FROM ownership_adoption_events WHERE json_extract(data,'$.kind')='ownership_quarantined' ORDER BY seq LIMIT 1").fetchone()
            require(event is not None, "Adoption completion receipt missing")
            adopted_at = json.loads(event[0])["at"]
            context = {"adoptionHash": digest(bundle), "policy": meta["policy"], "adoptedAt": adopted_at,
                       "claims": claims, "currentOwners": source["owners"],
                       "workspaces": [{"workspaceId": m["id"], "brainId": m["brainId"]} for m, _, _ in locked]}
            binding = {"sourceHash": digest(source), "kernelHash": digest(fingerprint(kernel)),
                       "kernelIdentity": record["kernelIdentity"], "registryIdentity": source["registryIdentity"],
                       "adoptionHash": digest(bundle)}
            yield context, binding


def preview(registry, evidence):
    validate(evidence)
    with registry.tx() as db:
        history = records(db); anchor = anchor_in(db)
        with locked_context(registry, db) as (context, binding):
            now = time.time()
            report = assess(context, evidence, anchor["evidence"] if anchor else None, now)
            document = {"schemaVersion": 1, "kind": "admission_reconciliation_review", "createdAt": now,
                        "expiresAt": now + 300, "expectedVersion": history[-1]["version"] if history else 0,
                        "previousRecordHash": history[-1]["recordHash"] if history else None,
                        "baselineRecordHash": anchor["recordHash"] if anchor else None,
                        "binding": binding, "evidence": evidence, "report": report, "effect": EFFECT}
            require(len(canonical(document).encode()) <= 3_000_000, "Reconciliation review exceeds its bound")
            return {"documentHash": digest(document), "document": document}


def public(record):
    return {"id": record["id"], "version": record["version"], "recordHash": record["recordHash"],
            "recordedAt": record["recordedAt"], "statusAtReview": record["report"]["status"],
            "baselineRetained": record["report"]["baselineCandidate"], "receiptIsHistorical": True,
            "executionAuthorized": False, "ownershipReleased": False, "activationAvailable": False}


def record(registry, request):
    exact(request, {"id", "confirmed", "preview"}); identifier(request["id"])
    require(request["confirmed"] is True, "Explicit owner confirmation required for evidence review")
    exact(request["preview"], {"documentHash", "document"})
    document = request["preview"]["document"]
    require(isinstance(document, dict) and request["preview"]["documentHash"] == digest(document), "Evidence review hash mismatch")
    request_hash = digest(request)
    with registry.tx() as db:
        history = records(db)
        prior = db.execute("SELECT data FROM admission_reconciliations WHERE id=?", (request["id"],)).fetchone() if history else None
        if prior:
            prior = decode_record(prior[0])
            require(prior["requestHash"] == request_hash, "Evidence request ID reused with different content")
            return public(prior)
        exact(document, {"schemaVersion", "kind", "createdAt", "expiresAt", "expectedVersion", "previousRecordHash",
                         "baselineRecordHash", "binding", "evidence", "report", "effect"})
        require(type(document["schemaVersion"]) is int and document["schemaVersion"] == 1 and
                document["kind"] == "admission_reconciliation_review" and document["effect"] == EFFECT, "Invalid evidence review contract")
        integer(document["expectedVersion"], 0, 10000)
        version = history[-1]["version"] if history else 0
        require(version < 10000, "Evidence history limit reached; explicit archival migration required")
        require(document["expectedVersion"] == version and
                document["previousRecordHash"] == (history[-1]["recordHash"] if history else None), "Evidence history changed; review again")
        now = time.time(); timestamp(document["createdAt"]); timestamp(document["expiresAt"])
        require(0 <= now - document["createdAt"] <= 300 and document["expiresAt"] == document["createdAt"] + 300,
                "Fresh evidence review required")
        require(len(canonical(document).encode()) <= 3_000_000, "Reconciliation review exceeds its bound")
        anchor = anchor_in(db)
        require(document["baselineRecordHash"] == (anchor["recordHash"] if anchor else None), "Baseline anchor changed")
        with locked_context(registry, db) as (context, binding):
            require(binding == document["binding"], "Ownership or kernel changed; review fresh evidence")
            evidence = document["evidence"]
            prior_report = assess(context, evidence, anchor["evidence"] if anchor else None, document["createdAt"])
            require(prior_report == document["report"], "Evidence report changed or was edited")
            report = assess(context, evidence, anchor["evidence"] if anchor else None, now)
            # Do not silently replace the approved conclusions after time/reset
            # gates change. A stale diagnostic can be reviewed in a new preview.
            require(report["issues"] == prior_report["issues"], "Evidence freshness changed; preview again")
            value = {"id": request["id"], "version": version + 1, "recordedAt": now,
                     "requestHash": request_hash, "reviewHash": request["preview"]["documentHash"],
                     "previousRecordHash": document["previousRecordHash"], "baselineRecordHash": document["baselineRecordHash"],
                     "binding": binding, "evidence": evidence, "report": report, "reviewDocument": document}
            value["recordHash"] = digest(value)
            db.execute("CREATE TABLE IF NOT EXISTS admission_reconciliations(id TEXT PRIMARY KEY, version INTEGER UNIQUE NOT NULL, data TEXT NOT NULL)")
            db.execute("INSERT INTO admission_reconciliations VALUES(?,?,?)", (value["id"], value["version"], canonical(value)))
            db.commit()  # Receipt commits while source and kernel locks are held.
            return public(value)


def status(registry):
    with registry.tx() as db:
        history = records(db)
        if not history:
            return {"state": "not_reviewed", "version": 0, "activationAvailable": False, "executionAuthorized": False}
        latest, anchor = history[-1], anchor_in(db)
        result = {"state": "reviewed", "version": latest["version"], "receipt": public(latest),
                  "reviewedReport": latest["report"], "baselineRecordHash": anchor["recordHash"] if anchor else None,
                  "history": [public(r) for r in history], "olderVersions": max(0, latest["version"] - 20),
                  "activationAvailable": False, "executionAuthorized": False}
        try:
            with locked_context(registry, db) as (context, binding):
                # Compare against the anchor before this record, so its own
                # baseline flag is not used to validate itself.
                earlier = anchor_in(db, latest["version"])
                live = assess(context, latest["evidence"], earlier["evidence"] if earlier else None, time.time())
                result["sourceMatchesReview"] = binding == latest["binding"]
                if not result["sourceMatchesReview"]:
                    live["issues"].append({"code": "source_changed_since_review"})
                    live.update(status="needs_evidence", evidenceConsistent=False, baselineCandidate=False)
                result["currentEvaluation"] = live
        except (OSError, ValueError, KeyError, sqlite3.Error):
            # Never emit database paths, source payloads or arbitrary exception text.
            result.update(sourceMatchesReview=False, currentEvaluation={"status": "source_unavailable", "evidenceConsistent": False,
                           "issues": [{"code": "source_unavailable"}], "activationAvailable": False, "executionAuthorized": False})
        return result
