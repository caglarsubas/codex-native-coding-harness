"""Retained next steps for blocked decisions; proposals never grant authority."""
import time

from .core import canonical, digest, require
from .decisions import artifacts, authorize_brain, text

FIELDS = {"expectedVersion", "summary", "artifactIds", "decisionIds", "queueIds", "externalBlocker"}


def publish(ledger, token, source_id, spec):
    require(isinstance(spec, dict) and set(spec) == FIELDS, "Invalid continuation fields")
    require(type(spec["expectedVersion"]) is int and spec["expectedVersion"] >= 0, "Expected continuation version required")
    text(spec["summary"], "continuation summary")
    for name in ("decisionIds", "queueIds"):
        ids = spec[name]
        require(isinstance(ids, list) and len(ids) <= 8 and all(isinstance(i, str) and 0 < len(i) <= 256 for i in ids), "Invalid continuation links")
        require(len(set(ids)) == len(ids), "Duplicate continuation link")
    blocker = spec["externalBlocker"]
    if blocker is not None:
        require(isinstance(blocker, dict) and set(blocker) == {"reason", "resumeWhen"}, "Explain the external blocker and the event that resumes work")
        for name in blocker:
            text(blocker[name], name, 2000)
    linked = bool(spec["decisionIds"] or spec["queueIds"])
    require(linked != (blocker is not None), "Link a concrete next decision/packet OR record an external dependency")
    with ledger.tx() as db:
        meta = authorize_brain(ledger, db, token)
        require(meta.get("brainControl", {}).get("desired") != "stopped", "Brain is stopping or stopped")
        source = ledger.get(db, "decisions", source_id)
        require(source["status"] == "blocked" and source["resolution"], "A retained blocked outcome is required")
        previous = sorted((r for r in ledger.all(db, "continuations") if r["sourceDecisionId"] == source_id), key=lambda r: r["version"])
        if previous and previous[-1]["spec"] == spec:
            return previous[-1]
        require(spec["expectedVersion"] == (previous[-1]["version"] if previous else 0), "Continuation changed; review its current version")
        repo, at = source["spec"]["repository"], source["resolution"]["at"]
        artifacts(ledger, db, spec["artifactIds"], repo)
        require(any(ledger.get(db, "artifact_versions", i).get("observedAt", 0) >= at for i in spec["artifactIds"]), "Retain a new proposal artifact after the blocked outcome")
        decisions = []
        for identity in spec["decisionIds"]:
            d = ledger.get(db, "decisions", identity)
            require(d["spec"]["repository"] == repo and d["createdAt"] > at and d["status"] == "open", "Link a new open decision in the same repository")
            require(d["spec"]["key"] != source["spec"]["key"], "Do not reopen the answered question; ask for the missing next choice")
            decisions.append({"id": identity, "decisionHash": d["decisionHash"]})
        queue = []
        for identity in spec["queueIds"]:
            q = ledger.get(db, "queue", identity)
            require(q["repository"] == repo and q["createdAt"] > at and q["status"] == "proposed", "Link a newly prepared, unapproved packet in the same repository")
            queue.append({"id": identity, "seedHash": q["seedHash"], "packetDigest": q["packetDigest"]})
        document = {"schemaVersion": 1, "sourceDecisionId": source_id,
                    "sourceResolutionHash": digest(source["resolution"]), "version": spec["expectedVersion"] + 1,
                    "spec": spec, "decisions": decisions, "queue": queue}
        identity = digest(document)
        record = {**document, "id": identity, "createdAt": time.time()}
        db.execute("INSERT INTO snapshots VALUES (?,?,?)", (identity, "continuation", canonical(document)))
        ledger.put(db, "continuations", identity, record)
        ledger.event(db, "continuation_published", {"id": identity, "sourceDecisionId": source_id, "version": record["version"]})
        return record


def project(state, records):
    """Read-only compatibility projection: old blocked answers remain actionable."""
    latest = {}
    for record in records:
        key = record["sourceDecisionId"]
        if key not in latest or record["version"] > latest[key]["version"]:
            latest[key] = record
    decisions = {d["id"]: d for d in state["decisions"]}
    queue = {q["id"]: q for q in state["queue"]}
    rows = []
    for d in state["decisions"]:
        if d["status"] != "blocked" or not d.get("resolution"):
            continue
        r = latest.get(d["id"])
        links, packets = [], []
        stale = bool(r and r["sourceResolutionHash"] != digest(d["resolution"]))
        if r:
            for link in r["decisions"]:
                current = decisions.get(link["id"])
                stale |= not current or current["decisionHash"] != link["decisionHash"] or current["status"] == "superseded"
                links.append({**link, "status": current["status"] if current else "missing", "title": current["spec"]["title"] if current else "Missing decision"})
            for link in r["queue"]:
                current = queue.get(link["id"])
                stale |= not current or any(current[k] != link[k] for k in ("seedHash", "packetDigest"))
                packets.append({**link, "status": current["status"] if current else "missing"})
        status = "needs_proposal" if not r else "needs_revision" if stale else "waiting_external" if r["spec"]["externalBlocker"] else "proposal_published"
        rows.append({"sourceDecisionId": d["id"], "repository": d["spec"]["repository"], "title": d["spec"]["title"],
                     "response": d["response"], "outcome": d["resolution"], "status": status,
                     "proposal": r, "decisions": links, "queue": packets})
    return rows
