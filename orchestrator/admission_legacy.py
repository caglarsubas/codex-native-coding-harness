"""Atomic quarantined ownership import; no release or execution authority."""
from .core import canonical, digest, require

FENCE_FILE = "adoption-fence.json"
REASON = "Legacy ownership adoption is quarantined; native inventory, usage baseline and run activation must be reconciled before new admission."


def fenced(root, meta):
    return "legacyAdoption" in meta or any((root / name).exists() or (root / name).is_symlink()
                                           for name in (FENCE_FILE, "adoption-kernel.json"))


def require_open(root, meta):
    require(not fenced(root, meta), REASON)


def require_import_fences(root, bundle, identity):
    from .enrollment import read_fence
    require(identity is not None, "Pinned database identity required for legacy import")
    expected = {"schemaVersion": 1, "adoptionId": bundle["id"], "bundleHash": digest(bundle),
                "registryIdentity": bundle["registryIdentity"], "enrollmentId": bundle["enrollmentId"]}
    require(read_fence(root / FENCE_FILE) == canonical(expected).encode(), "Exact platform adoption fence required")
    pin = {"schemaVersion": 1, "adoptionId": bundle["id"], "bundleHash": digest(bundle), "kernelIdentity": list(identity)}
    require(read_fence(root / "adoption-kernel.json") == canonical(pin).encode(), "Exact kernel identity pin required")


def validate(bundle):
    from .admission import AdmissionStore, exact, identifier, resource, sha
    exact(bundle, {"id", "enrollmentId", "registryIdentity", "membershipHash", "sourceHash", "policy", "claims"})
    identifier(bundle["id"]); identifier(bundle["enrollmentId"])
    for key in ("registryIdentity", "membershipHash", "sourceHash"):
        sha(bundle[key])
    AdmissionStore.validate_policy(bundle["policy"])
    require(isinstance(bundle["claims"], list) and len(bundle["claims"]) <= 2000,
            "Legacy ownership inventory exceeds the bounded import")
    seen = set()
    for claim in bundle["claims"]:
        exact(claim, {"id", "workspaceId", "workerId", "versions", "resourceKeys", "nativeIdentities",
                      "pendingClientIds", "mappingEvidence", "issues", "status", "usageKnown"})
        sha(claim["id"])
        require(claim["id"] == digest({"enrollmentId": bundle["enrollmentId"], "workspaceId": claim["workspaceId"],
                                      "workerId": claim["workerId"]}) and claim["id"] not in seen,
                "Duplicate or mismatched legacy claim identity")
        seen.add(claim["id"])
        require(claim["status"] == "quarantined" and claim["usageKnown"] is False,
                "Legacy import cannot grant authority or invent usage")
        require(isinstance(claim["versions"], list) and claim["versions"], "Retained owner versions required")
        require(isinstance(claim["resourceKeys"], list), "Invalid legacy resource list")
        for key in claim["resourceKeys"]:
            resource(key, "runner" if key.startswith("runner:") else "repo")
    require(len(canonical(bundle).encode()) <= 2_000_000, "Legacy adoption bundle is too large")


def install(store, db, bundle):
    """Called within initialization's transaction, after a durable platform fence."""
    validate(bundle)
    meta = store.get(db, "meta", 1)
    binding = {k: bundle[k] for k in ("id", "enrollmentId", "registryIdentity", "membershipHash", "sourceHash")}
    binding.update(bundleHash=digest(bundle), state="quarantined")
    if "legacyAdoption" in meta:
        require(meta["legacyAdoption"] == binding, "Admission store belongs to another adoption")
        require(store.rows(db, "legacy_claims") == sorted(bundle["claims"], key=lambda row: row["id"]),
                "Imported legacy ownership changed; explicit recovery required")
        return
    # Existing allocations/claims need their own migration, never overwrite or
    # silently import around a possibly in-flight global creation boundary.
    require(not store.rows(db, "allocations") and not store.rows(db, "claims") and
            not db.execute("SELECT 1 FROM resources").fetchone(),
            "Admission store is not empty; explicit existing-kernel migration required")
    require(meta["policy"] == bundle["policy"], "Adoption policy mismatch")
    require(not db.execute("SELECT 1 FROM sqlite_master WHERE name='legacy_claims'").fetchone(),
            "Unbound legacy ownership table requires explicit recovery")
    db.execute("CREATE TABLE legacy_claims(id TEXT PRIMARY KEY, data TEXT NOT NULL)")
    for claim in bundle["claims"]:
        db.execute("INSERT INTO legacy_claims VALUES(?,?)", (claim["id"], canonical(claim)))
    meta["legacyAdoption"] = binding
    store.put(db, "meta", 1, meta)
    store.event(db, "legacy_ownership_adopted", **binding, retainedSlots=len(bundle["claims"]))


def inventory(claims):
    groups = {}
    for claim in claims:
        for key in claim["resourceKeys"]:
            groups.setdefault(key, []).append(claim["id"])
    native = {}
    for claim in claims:
        for row in claim["nativeIdentities"]:
            native.setdefault((row["hostId"], row["threadId"]), []).append(claim["id"])
    return {"claims": claims, "retainedSlots": len(claims), "usageKnown": False,
            "resources": [{"key": key, "claimIds": ids} for key, ids in sorted(groups.items())],
            "resourceConflicts": [{"key": key, "claimIds": ids} for key, ids in sorted(groups.items()) if len(ids) > 1],
            "nativeConflicts": [{"hostId": pair[0], "threadId": pair[1], "claimIds": ids}
                                for pair, ids in sorted(native.items()) if len(ids) > 1],
            "issues": sum(len(c["issues"]) for c in claims)}


def projection(store, db):
    meta = store.get(db, "meta", 1)
    binding = meta.get("legacyAdoption")
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='legacy_claims'").fetchone()
    claims = store.rows(db, "legacy_claims") if exists else []
    return {**inventory(claims),
            "state": "quarantined" if binding else "fencing" if fenced(store.root, meta) else "not_adopted",
            "dispatchBlocked": fenced(store.root, meta), "activationAvailable": False,
            "binding": binding, "reason": REASON if fenced(store.root, meta) else None}
