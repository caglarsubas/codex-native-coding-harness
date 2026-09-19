"""Version-bound owner decisions. Data and receipts, never execution authority."""
import re
import time

from .core import ACTIVE, SHA, canonical, digest, require

FIELDS = {"key", "repository", "title", "question", "context", "scope", "nextStep",
          "options", "recommendedOptionId", "artifactIds"}
BOUNDARY = "Design/input only. No packet approval, dispatch, target access, privilege, merge or acceptance authority."


def text(value, name, limit=4000, empty=False):
    require(isinstance(value, str) and len(value) <= limit and (empty or value.strip()), "Invalid " + name)


def artifacts(ledger, db, ids, repository):
    require(isinstance(ids, list) and 1 <= len(ids) <= 8 and all(isinstance(i, str) and SHA.fullmatch(i) for i in ids), "Use 1–8 retained artifact IDs")
    require(len(set(ids)) == len(ids), "Duplicate artifact reference")
    for identity in ids:
        item = ledger.get(db, "artifact_versions", identity)
        require(item["repository"] == repository, "Artifact belongs to another repository")


def authorize_brain(ledger, db, token):
    meta = ledger.authorize(db, token)
    owner = meta["controller"]["owner"]
    require(meta["brainId"] and (owner == meta["brainId"] or owner.startswith(meta["brainId"] + ":")), "Only the designated brain can publish or resolve decisions")
    return meta


def publish(ledger, token, spec):
    require(isinstance(spec, dict) and set(spec) == FIELDS, "Decision fields must match the decision contract")
    for name in ("key", "repository", "title", "question", "context", "scope", "nextStep"):
        text(spec[name], name, 200 if name in ("key", "repository", "title") else 4000)
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", spec["key"]), "Invalid decision key")
    options = spec["options"]
    require(isinstance(options, list) and 2 <= len(options) <= 5, "Provide 2–5 bounded options")
    for option in options:
        require(isinstance(option, dict) and set(option) == {"id", "label", "implications", "requiresNote"}, "Invalid option fields")
        text(option["id"], "option ID", 64)
        require(re.fullmatch(r"[a-z0-9][a-z0-9_-]*", option["id"]), "Invalid option ID")
        text(option["label"], "option label", 200)
        text(option["implications"], "option implications", 2000)
        require(type(option["requiresNote"]) is bool, "requiresNote must be boolean")
    ids = [o["id"] for o in options]
    require(len(ids) == len(set(ids)) and spec["recommendedOptionId"] in [None, *ids], "Invalid recommendation or duplicate option")
    with ledger.tx() as db:
        meta = authorize_brain(ledger, db, token)
        ledger.get(db, "repos", spec["repository"])
        artifacts(ledger, db, spec["artifactIds"], spec["repository"])
        previous = sorted((d for d in ledger.all(db, "decisions") if d["spec"]["repository"] == spec["repository"] and d["spec"]["key"] == spec["key"]), key=lambda d: d["version"])
        if previous and previous[-1]["spec"] == spec:
            return previous[-1]  # Publishing twice never reopens an answered decision.
        if previous:
            old = previous[-1]
            require(old["status"] != "received", "Decision is in flight; reconcile and resolve before revising")
            if old["status"] in ("open", "answered"):
                old["status"] = "superseded"
                ledger.put(db, "decisions", old["id"], old)
                if old["response"]:
                    cmd = ledger.get(db, "commands", old["response"]["commandId"])
                    cmd.update(status="rejected", result="Decision revised; review the new version before answering.")
                    ledger.put(db, "commands", cmd["id"], cmd)
        version = len(previous) + 1
        document = {"schemaVersion": 1, "version": version, "brainId": meta["brainId"], "spec": spec, "boundary": BOUNDARY}
        identity = digest(document)
        record = {**document, "id": identity, "decisionHash": identity, "status": "open", "createdAt": time.time(), "response": None, "resolution": None}
        db.execute("INSERT INTO snapshots VALUES (?,?,?)", (identity, "decision", canonical(document)))
        ledger.put(db, "decisions", identity, record)
        ledger.event(db, "decision_published", {"id": identity, "key": spec["key"], "version": version})
        return record


def answer(ledger, db, command):
    p = command["payload"]
    require(set(p) == {"decisionId", "decisionHash", "optionId", "note", "confirmed"}, "Invalid decision response fields")
    for name in ("decisionId", "decisionHash"):
        text(p[name], name, 128)
    if p["optionId"] is not None:
        text(p["optionId"], "option ID", 64)
    text(p["note"], "decision note", 4000, empty=True)
    require(p["confirmed"] is True, "Explicit decision confirmation required")
    d = ledger.get(db, "decisions", p["decisionId"])
    require(d["status"] == "open" and d["decisionHash"] == p["decisionHash"], "Decision changed or already answered; review its current version")
    if p["optionId"] is None:
        require(bool(p["note"].strip()), "Write your answer or choose a suggested option")
    else:
        option = next((o for o in d["spec"]["options"] if o["id"] == p["optionId"]), None)
        require(option is not None, "Unknown decision option")
        require(not option["requiresNote"] or bool(p["note"].strip()), "This option needs the requested information in your note")
    d.update(status="answered", response={"commandId": command["id"], "answerKind": "free_text" if p["optionId"] is None else "option",
                                         "optionId": p["optionId"], "note": p["note"], "at": time.time()})
    ledger.put(db, "decisions", d["id"], d)


def receive(ledger, db, cmd):
    d = ledger.get(db, "decisions", cmd["payload"]["decisionId"])
    require(d["status"] == "answered" and d["response"]["commandId"] == cmd["id"], "Decision response is no longer current")
    d.update(status="received", receivedAt=time.time())
    ledger.put(db, "decisions", d["id"], d)
    cmd.update(status="processing", result="Received by the brain; continuation and evidence still pending.")
    return {"kind": "decision_response", "commandId": cmd["id"], "decision": d, "boundary": BOUNDARY}


def resolve(ledger, token, identity, result):
    require(isinstance(result, dict) and set(result) == {"commandId", "outcome", "summary", "artifactIds"}, "Invalid decision resolution")
    require(result["outcome"] in ("applied", "blocked"), "Outcome must be applied or blocked")
    text(result["summary"], "resolution summary")
    text(result["commandId"], "response command ID", 128)
    with ledger.tx() as db:
        authorize_brain(ledger, db, token)
        d = ledger.get(db, "decisions", identity)
        if d["resolution"]:
            require({k: d["resolution"][k] for k in result} == result, "Resolution already recorded differently")
            return d
        require(d["status"] == "received" and d["response"]["commandId"] == result["commandId"], "Exact received response required")
        artifacts(ledger, db, result["artifactIds"], d["spec"]["repository"])
        cmd = ledger.get(db, "commands", result["commandId"])
        require(cmd["status"] == "processing", "Response is not in flight")
        d.update(status=result["outcome"], resolution={**result, "at": time.time()})
        ledger.put(db, "decisions", identity, d)
        cmd.update(status="completed", result=result["summary"])
        ledger.put(db, "commands", cmd["id"], cmd)
        ledger.event(db, "decision_resolved", {"id": identity, "outcome": result["outcome"], "artifactIds": result["artifactIds"]})
        return d


def workflow(state):
    """Requested policy and observed native state are deliberately separate."""
    m, now = state["meta"], state["serverTime"]
    enabled = m.get("decisionListener", {}).get("enabled", False)
    heartbeat = m["heartbeat"]
    checked = m.get("inboxCheckedAt")
    observed = heartbeat.get("observedAt")
    recent = (checked is not None and 0 <= now - checked <= 35 * 60
              and observed is not None and 0 <= now - observed <= 35 * 60)
    pending = [c for c in state["commands"] if c["status"] in ("queued", "processing") or c.get("needsBrainReceipt")]
    active = any(w["status"] in ACTIVE for w in state["workers"])
    approved = not m["paused"] and not state.get("admission", {}).get("dispatchBlocked") and any(q["status"] == "approved" and not q["held"] for q in state["queue"])
    continuations = state.get("continuations", [])
    unplanned = sum(c["status"] in ("needs_proposal", "needs_revision") for c in continuations)
    reasons = []
    for needed, reason in ((active, "active_workers"), (bool(m.get("runner")), "runner_owned"),
                           (approved, "approved_dispatch"), (bool(pending), "pending_receipts"),
                           (bool(unplanned), "follow_up_planning")):
        if needed:
            reasons.append(reason)
    keep = enabled or bool(reasons)
    status = ("needs_activation" if heartbeat["status"] != "ACTIVE" else "listening" if recent else "unconfirmed") if keep else (
        "idle_pause_pending" if heartbeat["status"] == "ACTIVE" else "event_waiting")
    brain = m.get("brainControl", {})
    parked = brain.get("phase") == "parked"
    if parked:
        status = "brain_stopped"
    return {"listenerEnabled": enabled, "status": status, "lastCheckedAt": checked,
            "nativeStatus": heartbeat["status"], "nativeObservedAt": heartbeat.get("observedAt"),
            "intervalMinutes": 15, "pendingRequests": len(pending),
            "openDecisions": sum(d["status"] == "open" for d in state["decisions"]),
            "followUpsNeedingProposal": unplanned, "followUps": len(continuations),
            "schedulingMode": "periodic_idle" if enabled else "event_driven",
            "supervisionReasons": reasons, "shouldKeepHeartbeat": not parked and keep,
            "dispatchPaused": m["paused"], "boundary": BOUNDARY}


def inbox(state):
    """Compact native-cycle input: no token logs, artifact bodies or event history."""
    return {"meta":state["meta"], "workflow":state["workflow"], "continuations": state.get("continuations", []),
            "admission": state.get("admission"),
            "missionConfiguration": {k: state.get("mission", {}).get(k) for k in ("version", "effectiveStatus", "documentHash", "activation", "executionAuthority")},
            "decisions":[d for d in state["decisions"] if d["status"] in ("open", "answered", "received")],
            "commands":[c for c in state["commands"] if c["status"] in ("queued", "processing") or c.get("needsBrainReceipt")],
            "queue":[q for q in state["queue"] if q["status"] == "approved"],
            "workers":[w for w in state["workers"] if w["status"] in ACTIVE]}
