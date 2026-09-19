"""Explicit owner-reviewed import of fenced legacy ownership, without activation."""
import contextlib
import json
import math
import os
import sqlite3
import stat
import time

from . import enrollment
from .admission import AdmissionStore, exact, identifier, resource, sha
from .admission_legacy import FENCE_FILE, REASON, inventory, validate as validate_bundle
from .core import canonical, digest, require
from .workspaces import fingerprint

EFFECT = "Import retained ownership as quarantined claims. New admission stays fenced; no native action, budget allocation or unfence."


def record_in(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='ownership_adoption'").fetchone():
        return None
    row = db.execute("SELECT data FROM ownership_adoption WHERE id=1").fetchone()
    return json.loads(row[0]) if row else None


def kernel_state(registry):
    """Read-only exact fingerprint; never construct or initialize the kernel."""
    path = registry.root / "admission.sqlite3"
    require(not path.is_symlink(), "Admission database symlink refused")
    if not path.exists():
        return None
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_mode & 0o077 == 0
            and info.st_nlink == 1, "Admission database must be private and regular")
    with contextlib.closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("BEGIN")
        tables = fingerprint(db)
        meta = json.loads(db.execute("SELECT data FROM meta WHERE id=1").fetchone()[0]) if "meta" in tables else None
    can_import = not tables or bool(meta and meta.get("schemaVersion") == 1 and "legacyAdoption" not in meta
                    and "legacy_claims" not in tables and all(t in tables and tables[t]["rows"] == 0
                                                              for t in ("allocations", "claims", "resources")))
    return {"identity": [info.st_dev, info.st_ino], "contentHash": digest(tables),
            "canImport": can_import, "policy": meta.get("policy") if meta else None}


def require_importable(kernel, policy):
    require(kernel is None or (kernel["canImport"] and kernel["policy"] in (None, policy)),
            "Kernel must be empty with the exact policy; existing allocations need explicit migration")


def configuration(value):
    exact(value, {"policy", "repositories", "runners"})
    AdmissionStore.validate_policy(value["policy"])
    repos, runners = {}, {}
    require(isinstance(value["repositories"], list) and len(value["repositories"]) <= 2000,
            "Invalid adoption repository mappings")
    require(isinstance(value["runners"], list) and len(value["runners"]) <= 2000,
            "Invalid adoption runner mappings")
    for row in value["repositories"]:
        exact(row, {"bindingHash", "keys", "evidenceHash"})
        sha(row["bindingHash"]); sha(row["evidenceHash"])
        require(row["bindingHash"] not in repos, "Duplicate repository binding mapping")
        require(isinstance(row["keys"], list) and 1 <= len(row["keys"]) <= 4, "Map 1–4 canonical repository keys")
        for key in row["keys"]: resource(key)
        require(row["keys"] == sorted(set(row["keys"])), "Repository keys must be sorted and unique")
        repos[row["bindingHash"]] = row
    for row in value["runners"]:
        exact(row, {"recordHash", "key", "evidenceHash"})
        sha(row["recordHash"]); sha(row["evidenceHash"]); resource(row["key"], "runner")
        require(row["recordHash"] not in runners, "Duplicate runner record mapping")
        runners[row["recordHash"]] = row
    return repos, runners


def source(registry, db, locked):
    record = enrollment.record_in(db)
    require(record and record["state"] == "fenced", "Complete explicit enrollment before ownership adoption")
    require(record["registryIdentity"] == enrollment.registry_identity(registry), "Enrollment registry identity changed")
    require(record["membershipHash"] == digest([m for m, _, _ in locked]), "Enrollment membership changed")
    observations = []
    for member, ledger, conn in locked:
        meta = ledger.get(conn, "meta", 1)
        require(meta["paused"] is True and meta["controller"] is None,
                "Pause dispatch and release controllers before ownership adoption or recovery")
        expected = {"schemaVersion": 1, "enrollmentId": record["id"], "workspaceId": member["id"],
                    "registryIdentity": record["registryIdentity"], "membershipHash": record["membershipHash"],
                    "state": "fenced", "activationAvailable": False}
        require(meta.get("admissionBinding") == expected and
                enrollment.read_fence(ledger.root / enrollment.FENCE_FILE) == canonical(expected).encode(),
                "Workspace enrollment fence changed; recover enrollment first")
        observations.append(enrollment.observe(ledger, conn, member))
    combined = {"retainedOwnership": list(record["retainedOwnership"])}
    enrollment.retain_owners(combined, observations)
    owners = sorted(combined["retainedOwnership"], key=digest)
    require(len(owners) <= 4000, "Retained ownership exceeds bounded adoption scope")
    return {"enrollmentId": record["id"], "registryIdentity": record["registryIdentity"],
            "membershipHash": record["membershipHash"], "owners": owners, "observations": observations}


def claims_for(source, config):
    repos, runners = configuration(config)
    used_repos, used_runners, groups = set(), set(), {}
    for owner in source["owners"]:
        key = digest({"enrollmentId": source["enrollmentId"], "workspaceId": owner["workspaceId"], "workerId": owner["workerId"]})
        groups.setdefault(key, []).append(owner)
    claims = []
    for key, versions in sorted(groups.items()):
        keys, native, pending, evidence, issues = set(), {}, set(), set(), set()
        for owner in versions:
            if owner["kind"] == "worker":
                binding = owner.get("repositoryBindingHash")
                mapped = repos.get(binding)
                if mapped:
                    used_repos.add(binding); keys.update(mapped["keys"]); evidence.add(mapped["evidenceHash"])
                else: issues.add("repository_mapping_unknown")
                if owner.get("hostId") and owner.get("threadId"):
                    value = {"hostId": owner["hostId"], "threadId": owner["threadId"]}
                    native[digest(value)] = value
                else: issues.add("native_identity_unresolved")
                if owner.get("clientThreadId"): pending.add(owner["clientThreadId"])
            elif owner["kind"] == "runner":
                mapped = runners.get(owner["recordHash"])
                if mapped:
                    used_runners.add(owner["recordHash"]); keys.add(mapped["key"]); evidence.add(mapped["evidenceHash"])
                else: issues.add("runner_mapping_unknown")
            else:
                raise ValueError("Unknown retained ownership kind")
        if not any(v["kind"] == "worker" for v in versions): issues.add("runner_without_worker_record")
        if len(native) > 1: issues.add("conflicting_native_bindings")
        claims.append({"id": key, "workspaceId": versions[0]["workspaceId"], "workerId": versions[0]["workerId"],
                       "versions": versions, "resourceKeys": sorted(keys),
                       "nativeIdentities": [native[k] for k in sorted(native)], "pendingClientIds": sorted(pending),
                       "mappingEvidence": sorted(evidence), "issues": sorted(issues),
                       "status": "quarantined", "usageKnown": False})
    require(used_repos == set(repos) and used_runners == set(runners), "Mapping does not reference retained ownership")
    return claims


def preview(registry, config):
    configuration(config)
    with registry.tx() as db:
        require(record_in(db) is None, "Ownership adoption already started; use its exact recovery receipt")
        members = enrollment.members_in(db)
        with enrollment.locked_ledgers(members) as locked:
            current = source(registry, db, locked)
            claims = claims_for(current, config)
            kernel = kernel_state(registry)
            require_importable(kernel, config["policy"])
    now = time.time()
    document = {"schemaVersion": 1, "kind": "ownership_adoption_preview", "observedAt": now, "expiresAt": now + 300,
                "enrollmentId": current["enrollmentId"], "registryIdentity": current["registryIdentity"],
                "membershipHash": current["membershipHash"], "sourceHash": digest(current),
                "configuration": config, "claims": claims, "kernel": kernel, "effect": EFFECT}
    require(len(canonical(document).encode()) <= 2_000_000, "Adoption preview is too large")
    return {"documentHash": digest(document), "document": document}


def public(record):
    if not record: return {"state": "not_adopted", "activationAvailable": False, "executionAuthorized": False}
    bundle = record["bundle"]
    return {"id": record["id"], "state": record["state"], "enrollmentId": bundle["enrollmentId"],
            "bundleHash": digest(bundle), "createdAt": record["createdAt"], "kernelIdentity": record.get("kernelIdentity"),
            "retainedSlots": len(bundle["claims"]), "claimVersionCount": sum(len(c["versions"]) for c in bundle["claims"]),
            "mappingIssues": sum(len(c["issues"]) for c in bundle["claims"]), "usageKnown": False,
            "activationAvailable": False, "executionAuthorized": False, "reason": REASON}


def pin_kernel(registry, record):
    path = registry.root / "admission.sqlite3"
    pin = registry.root / "adoption-kernel.json"
    expected = {"schemaVersion": 1, "adoptionId": record["id"], "bundleHash": digest(record["bundle"])}
    if pin.exists() or pin.is_symlink():
        saved = json.loads(enrollment.read_fence(pin))
        require(isinstance(saved, dict) and set(saved) == {*expected, "kernelIdentity"} and
                all(saved[k] == v for k, v in expected.items()), "Kernel identity pin belongs to another adoption")
        current = kernel_state(registry)
        require(current and current["identity"] == saved["kernelIdentity"], "Pinned kernel identity changed")
        return saved["kernelIdentity"]
    current = kernel_state(registry)
    if record["kernelBefore"] is not None:
        require(current == record["kernelBefore"], "Existing kernel changed before identity pin")
    elif current:
        # A crash can leave only the newly created empty SQLite file. A populated
        # unpinned store is never assumed to belong to this import.
        require(current["contentHash"] == digest({}), "Unpinned populated kernel requires explicit recovery")
    else:
        handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try: os.fsync(handle)
        finally: os.close(handle)
        current = kernel_state(registry)
    identity = current["identity"]
    enrollment.durable_fence(registry.root, {**expected, "kernelIdentity": identity}, filename="adoption-kernel.json")
    return identity


def finish(registry, record):
    bundle = record["bundle"]
    fence = {"schemaVersion": 1, "adoptionId": record["id"], "bundleHash": digest(bundle),
             "registryIdentity": bundle["registryIdentity"], "enrollmentId": bundle["enrollmentId"]}
    enrollment.durable_fence(registry.root, fence, filename=FENCE_FILE)
    identity = pin_kernel(registry, record)
    store = AdmissionStore(registry.root, policy=bundle["policy"], legacy_bundle=bundle, expected_identity=identity)
    receipt = store.snapshot()["legacy"]
    require(receipt["binding"]["bundleHash"] == digest(bundle), "Kernel import receipt mismatch")
    record.update(state="quarantined", kernelIdentity=list(store.database_identity))
    return record


def complete(db, record):
    # No global lock is claimed between databases. A concurrent exact recovery
    # either observes this receipt or repeats the idempotent kernel import.
    # Workspace locks must be released before reacquiring the registry lock.
    db.execute("BEGIN IMMEDIATE")
    prior = record_in(db)
    require(prior and prior["requestHash"] == record["requestHash"], "Adoption journal identity changed")
    if prior["state"] != "quarantined":
        db.execute("UPDATE ownership_adoption SET data=? WHERE id=1", (canonical(record),))
        db.execute("INSERT INTO ownership_adoption_events(data) VALUES(?)",
                   (canonical({"at": time.time(), "kind": "ownership_quarantined", "bundleHash": digest(record["bundle"]),
                               "kernelIdentity": record["kernelIdentity"]}),))
    return public(record)


def apply(registry, request):
    exact(request, {"id", "confirmed", "preview"}); identifier(request["id"])
    require(request["confirmed"] is True, "Explicit owner confirmation required")
    exact(request["preview"], {"documentHash", "document"})
    document = request["preview"]["document"]
    require(isinstance(document, dict) and digest(document) == request["preview"]["documentHash"], "Adoption preview hash mismatch")
    request_hash = digest(request)
    with registry.tx() as db:
        prior = record_in(db)
        if prior:
            require(prior["id"] == request["id"] and prior["requestHash"] == request_hash, "Adoption already exists; recover its exact ID")
            return public(prior)
        exact(document, {"schemaVersion", "kind", "observedAt", "expiresAt", "enrollmentId", "registryIdentity",
                         "membershipHash", "sourceHash", "configuration", "claims", "kernel", "effect"})
        require(type(document["schemaVersion"]) is int and document["schemaVersion"] == 1
                and document["kind"] == "ownership_adoption_preview" and document["effect"] == EFFECT,
                "Invalid ownership adoption contract")
        require(len(canonical(document).encode()) <= 2_000_000, "Adoption preview is too large")
        at, until, now = document["observedAt"], document["expiresAt"], time.time()
        require(type(at) in (int, float) and type(until) in (int, float) and math.isfinite(at) and math.isfinite(until)
                and 0 <= now - at <= 300 and until == at + 300 and now <= until, "Fresh adoption preview required")
        with enrollment.locked_ledgers(enrollment.members_in(db)) as locked:
            current = source(registry, db, locked)
            require(all(current[k] == document[k] for k in ("enrollmentId", "registryIdentity", "membershipHash"))
                    and digest(current) == document["sourceHash"], "Ownership changed; review a new adoption preview")
            require(claims_for(current, document["configuration"]) == document["claims"], "Reviewed ownership mappings changed")
            require(kernel_state(registry) == document["kernel"], "Admission store changed since review")
            require_importable(document["kernel"], document["configuration"]["policy"])
            bundle = {k: document[k] for k in ("enrollmentId", "registryIdentity", "membershipHash", "sourceHash", "claims")}
            bundle.update(id=request["id"], policy=document["configuration"]["policy"])
            validate_bundle(bundle)
            record = {"id": request["id"], "state": "prepared", "createdAt": now, "bundle": bundle,
                      "requestHash": request_hash, "previewHash": request["preview"]["documentHash"], "kernelBefore": document["kernel"]}
            db.execute("CREATE TABLE ownership_adoption(id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)")
            db.execute("CREATE TABLE ownership_adoption_events(seq INTEGER PRIMARY KEY, data TEXT NOT NULL)")
            db.execute("INSERT INTO ownership_adoption VALUES(1,?)", (canonical(record),))
            db.execute("INSERT INTO ownership_adoption_events(data) VALUES(?)",
                       (canonical({"at": now, "kind": "ownership_adoption_prepared", "preview": request["preview"]}),))
            db.commit()
            record = finish(registry, record)
        return complete(db, record)


def recover(registry, adoption_id, *, confirmed=False):
    require(confirmed is True, "Explicit owner confirmation required for adoption recovery")
    with registry.tx() as db:
        record = record_in(db)
        require(record and record["id"] == adoption_id, "Unknown adoption ID")
        with enrollment.locked_ledgers(enrollment.members_in(db)) as locked:
            current = source(registry, db, locked)
            require(digest(current) == record["bundle"]["sourceHash"],
                    "Retained ownership changed; keep quarantine and use an explicit migration")
            kernel = kernel_state(registry)
            if record.get("kernelIdentity"):
                require(kernel and kernel["identity"] == record["kernelIdentity"], "Adopted kernel identity changed")
            elif record["kernelBefore"]:
                require(kernel and kernel["identity"] == record["kernelBefore"]["identity"], "Existing kernel identity changed")
            db.commit()
            record = finish(registry, record)
        return complete(db, record)


def status(registry):
    with registry.tx() as db:
        record = record_in(db)
        result = public(record)
        if record:
            require(record["bundle"]["registryIdentity"] == enrollment.registry_identity(registry), "Registry identity changed")
            result["historyEntries"] = db.execute("SELECT count(*) FROM ownership_adoption_events").fetchone()[0]
            result["kernel"] = kernel_state(registry)
            result["kernelIdentityMatches"] = bool(result["kernel"] and result["kernel"]["identity"] == record.get("kernelIdentity"))
            result["receiptIsHistorical"] = True
            result["reviewedInventory"] = inventory(record["bundle"]["claims"])
        return result
