"""Owner-reviewed cooperative brain handoff; native creation remains in Codex."""
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time
import uuid

from .core import Refusal, canonical, digest, require
from .standard import PROTOCOL, TERMINAL, read_db, save
from .decisions import authorize_brain

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
RECEIPT_PREFIX = "CODEX_ORCHESTRATOR_HANDOFF_RECEIPT_V1 "
MEMBERSHIP_MAX_AGE = 3600


def receipt_marker(value):
    """The replacement emits this exact standalone line in its final answer."""
    return RECEIPT_PREFIX + canonical({key: value[key] for key in ("handoffId", "packageHash", "summary")})


def _native_receipt(path, task_id, marker, created_at):
    """Corroborate a bounded final native reply without retaining its transcript."""
    from .activity import HEADER_BYTES, TAIL_BYTES, open_regular
    from .observations import stamp
    with open_regular(path) as stream:
        first = stream.readline(HEADER_BYTES + 1)
        require(len(first) <= HEADER_BYTES and first.endswith(b"\n"), "Invalid native session header")
        try:
            header = json.loads(first)
        except (ValueError, UnicodeError):
            raise Refusal("Invalid native session header") from None
        if not isinstance(header, dict):
            return None
        payload = header.get("payload", {})
        if not isinstance(payload, dict):
            return None
        if header.get("type") != "session_meta" or payload.get("id") != task_id or payload.get("forked_from_id"):
            return None
        size = stream.seek(0, 2)
        start = max(len(first), size - TAIL_BYTES)
        stream.seek(start)
        if start > len(first):
            stream.readline(TAIL_BYTES + 1)  # Drop an incomplete leading record.
        raw = stream.read(TAIL_BYTES)
    matches = []
    for line in raw.splitlines(keepends=True):
        if not line.endswith(b"\n") or len(line) > 16_384:
            continue
        try:
            record = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        if not isinstance(record, dict):
            continue
        message = record.get("payload", {})
        if not isinstance(message, dict):
            continue
        if (record.get("type") != "response_item" or message.get("type") != "message"
                or message.get("role") != "assistant" or message.get("phase") not in ("final", "final_answer")):
            continue
        at = stamp(record.get("timestamp"))
        if at is None or at < created_at or at > time.time() + 5:
            continue
        content = message.get("content")
        for part in content if isinstance(content, list) else []:
            if isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str):
                if any(text == marker for text in part["text"].splitlines()):
                    matches.append({"observedAt": at, "recordHash": hashlib.sha256(line).hexdigest()})
    require(len(matches) <= 1, "Ambiguous native handoff receipt")
    return matches[0] if matches else None


def _project(registry, workspace, db=None):
    from .projects import _read
    if db is None:
        with registry.tx() as connection:
            return _project(registry, workspace, connection)
    catalog, bindings = _read(db)
    require(catalog is not None, "Native project catalog required")
    match = [(key, value) for key, value in bindings.items() if value["workspaceId"] == workspace]
    require(len(match) == 1, "Exactly one native project binding required")
    key, binding = match[0]
    owner = db.execute("SELECT brain FROM workspaces WHERE id=?", (workspace,)).fetchone()
    require(owner is not None and binding["brainId"] == owner["brain"], "Native project brain binding changed")
    project = next((p for p in catalog["projects"] if p["key"] == key), None)
    require(project is not None and project["locationHash"] == binding["locationHash"], "Native project identity changed")
    return {"key": key, "projectId": project["projectId"], "hostId": project["hostId"],
            "locationHash": project["locationHash"], "catalogHash": catalog["hash"]}


def _safe(ledger, db, allow_controller=False):
    meta = ledger.get(db, "meta", 1)
    run = meta.get("standardRun")
    require(run and run["protocol"] == PROTOCOL and run["brainId"] == meta["brainId"]
            and run["status"] in ("paused", "completed", "blocked") and run.get("checkpoint"),
            "A saved standard checkpoint is required")
    if not allow_controller:
        require(meta["controller"] is None and not (ledger.root / "standard-controller.json").exists(),
                "Release the old brain controller before handoff")
    require(all(t["status"] in TERMINAL for t in run["tasks"]), "Registered native tasks remain unsettled")
    require(not any(m["status"] in ("prepared", "issued", "uncertain") for m in run.get("merges", [])),
            "Unresolved merge handoff")
    require(not any(t.get("effectIssued") and not t.get("threadId") and t["status"] != "not_created" for t in run["tasks"]),
            "Unresolved native creation")
    require(meta.get("heartbeat", {}).get("status") in ("PAUSED", "not_configured"),
            "Pause the previous brain heartbeat and record its native status")
    from .conversation import pending as pending_message
    require(not any(pending_message(command) for command in ledger.all(db, "commands")),
            "Resolve pending brain conversation before handoff")
    require(not any(command["kind"] == "decision_response" and command["status"] in ("queued", "processing")
                    for command in ledger.all(db, "commands")), "Resolve in-flight decisions before handoff")
    from .enrollment import fence_exists
    require(not fence_exists(ledger.root) and "admissionBinding" not in meta,
            "Strict enrollment is outside cooperative handoff")
    return meta, run


def package(ledger, db, run, project):
    from . import project_knowledge
    knowledge_cfg = project_knowledge.config(ledger)
    references = []
    for repository in sorted((knowledge_cfg or {}).get("repositories", {})):
        manifest = project_knowledge._manifest(ledger, repository)
        references.append({"repository": repository, "indexHash": manifest["documentHash"] if manifest else None,
                           "commit": manifest["commit"] if manifest else None,
                           "observedAt": manifest["at"] if manifest else None,
                           "boundary": "Rebuildable search aid, not current source or authority"})
    open_decisions = sorted(({"id": decision["id"], "status": decision["status"]}
                             for decision in ledger.all(db, "decisions") if decision["status"] in ("open", "answered")),
                            key=lambda row: row["id"])
    require(len(open_decisions) <= 50, "Too many unresolved decisions for a bounded handoff")
    value = {"kind": "standard_brain_handoff_v1", "runId": run["id"], "oldBrainId": run["brainId"],
            "project": project, "missionHash": run["missionHash"], "reviewHash": run["reviewHash"],
            "phaseId": run["phaseId"], "checkpoint": run["checkpoint"], "limits": run["limits"],
            "usageHighWater": run.get("usageHighWater"), "closeoutHighWater": run.get("closeoutHighWater"),
            "closeoutDocumentHash": digest(run["closeoutReport"]) if run.get("closeoutReport") else None,
            "usageCoverage": (run.get("usageReport") or {}).get("coverage", "unknown"),
            "usageDocumentHash": digest(run["usageReport"]) if run.get("usageReport") else None,
            "tasks": [{key: task.get(key) for key in ("id", "title", "threadId", "status", "seedHash", "result")}
                      for task in run["tasks"]],
            "merges": [{key: merge.get(key) for key in ("requestId", "status", "bindingHash", "observationHash")}
                       for merge in run.get("merges", [])],
            "decisions": open_decisions,
            "memoryHash": run.get("memoryHash"),
            "knowledgeReferences": references,
            "boundary": "Checkpoint context only. Verify current ledger and Git state. No Play, Resume, budget reset, approval or native effect is granted."}
    require(len(canonical(value).encode()) <= 64_000, "Handoff package exceeds reviewed bound")
    return value


class Controls:
    def __init__(self):
        self.key = secrets.token_bytes(32)

    def sign(self, value):
        return hmac.new(self.key, canonical(value).encode(), hashlib.sha256).hexdigest()

    def preview(self, registry, ledger, session):
        workspace = ledger.workspace_id
        project = _project(registry, workspace)
        with read_db(ledger.db) as db:
            meta, run = _safe(ledger, db)
            require(not meta.get("brainHandoff") or meta["brainHandoff"]["status"] in ("cancelled", "complete"),
                    "Another brain handoff is pending")
            content = package(ledger, db, run, project)
            reviewed = {"id": str(uuid.uuid4()), "workspace": workspace, "sessionHash": digest(session),
                        "oldBrainId": meta["brainId"], "runId": run["id"], "runRevision": run["revision"],
                        "packageHash": digest(content), "project": project, "expiresAt": time.time()+300}
        return {"preview": reviewed, "package": content, "signature": self.sign(reviewed)}

    def confirm(self, registry, ledger, body, session):
        require(isinstance(body, dict) and set(body) == {"preview", "package", "signature", "confirmed"}
                and body["confirmed"] is True, "Exact owner confirmation required")
        doc = body["preview"]
        require(isinstance(doc, dict) and hmac.compare_digest(self.sign(doc), body["signature"])
                and doc["sessionHash"] == digest(session) and doc["workspace"] == ledger.workspace_id
                and time.time() < doc["expiresAt"], "Handoff preview expired or changed")
        require(digest(body["package"]) == doc["packageHash"], "Handoff package changed")
        with registry.tx() as registry_db, ledger.tx() as db:
            project = _project(registry, ledger.workspace_id, registry_db)
            meta, run = _safe(ledger, db)
            require(project == doc["project"] and meta["brainId"] == doc["oldBrainId"]
                    and run["id"] == doc["runId"] and run["revision"] == doc["runRevision"],
                    "Project or checkpoint changed")
            require(digest(package(ledger, db, run, project)) == doc["packageHash"], "Package is stale")
            prior = meta.get("brainHandoff")
            require(not prior or prior["status"] in ("cancelled", "complete"), "Handoff already pending")
            db.execute("INSERT OR IGNORE INTO snapshots VALUES(?,?,?)", (doc["packageHash"], "brain_handoff_package", canonical(body["package"])))
            handoff = {"id": doc["id"], "status": "prepared", "oldBrainId": doc["oldBrainId"],
                       "packageHash": doc["packageHash"], "project": project, "runId": run["id"],
                       "createdAt": time.time(), "candidate": None, "receipt": None}
            meta["brainHandoff"] = handoff
            ledger.put(db, "meta", 1, meta)
            command = {"id": doc["id"], "kind": "brain_handoff", "actor": "dashboard", "status": "queued",
                       "createdAt": time.time(), "payload": {"runId": run["id"], "packageHash": doc["packageHash"]},
                       "result": "Owner reviewed handoff package; designated brain must create one replacement task"}
            ledger.put(db, "commands", doc["id"], command)
            ledger.event(db, "brain_handoff_prepared", {"id": doc["id"], "packageHash": doc["packageHash"]})
        return command

    def finalize_preview(self, registry, ledger, session):
        with read_db(ledger.db) as db:
            meta, run = _safe(ledger, db)
            handoff = meta.get("brainHandoff")
            require(handoff and handoff["status"] == "received" and handoff["receipt"],
                    "Replacement task receipt is not recorded")
            _current_membership(handoff)
            project = _project(registry, ledger.workspace_id)
            require(project == handoff["project"], "Native project binding changed")
            review = {"workspace": ledger.workspace_id, "sessionHash": digest(session),
                      "handoffId": handoff["id"], "handoffHash": digest(handoff),
                      "runId": run["id"], "runRevision": run["revision"],
                      "oldBrainId": meta["brainId"], "newBrainId": handoff["candidate"]["taskId"],
                      "expiresAt": time.time()+300}
        return {"preview": review, "handoff": handoff, "signature": self.sign(review)}

    def finalize(self, registry, ledger, body, session):
        require(isinstance(body, dict) and set(body) == {"preview", "signature", "confirmed"}
                and body["confirmed"] is True, "Final owner confirmation required")
        doc = body["preview"]
        require(isinstance(doc, dict) and hmac.compare_digest(self.sign(doc), body["signature"])
                and doc["workspace"] == ledger.workspace_id and doc["sessionHash"] == digest(session)
                and time.time() < doc["expiresAt"], "Final handoff review expired")
        with registry.tx() as registry_db, ledger.tx() as db:
            meta, run = _safe(ledger, db)
            handoff = meta.get("brainHandoff")
            require(handoff and handoff["status"] == "received" and digest(handoff) == doc["handoffHash"]
                    and run["revision"] == doc["runRevision"] and run["id"] == doc["runId"]
                    and meta["brainId"] == doc["oldBrainId"] and handoff["candidate"]["taskId"] == doc["newBrainId"],
                    "Handoff or checkpoint changed; inspect again")
            _current_membership(handoff)
            require(_project(registry, ledger.workspace_id, registry_db) == handoff["project"], "Project binding changed")
            row = registry_db.execute("SELECT name,data FROM workspaces WHERE id=?", (ledger.workspace_id,)).fetchone()
            require(row is not None, "Registered project unavailable")
            new_id = doc["newBrainId"]
            require(not registry_db.execute("SELECT 1 FROM workspaces WHERE brain=?", (new_id,)).fetchone(),
                    "Replacement already owns another project")
            old = meta["brainId"]
            at = time.time()
            run.setdefault("brainSegments", [{"id": old, "start": run["startedAt"], "end": at}])
            if run["brainSegments"][-1]["id"] == old:
                run["brainSegments"][-1]["end"] = at
            run["brainSegments"].append({"id": new_id, "start": at, "end": None})
            run["brainId"] = new_id
            run.pop("usageReport", None)  # Old high-water and per-session evidence remain.
            meta["brainId"] = new_id
            handoff.update(status="complete", completedAt=at)
            meta["brainHandoff"] = handoff
            command = ledger.get(db, "commands", handoff["id"])
            command.update(status="completed", completedAt=at,
                           result="Owner confirmed exact replacement brain after native receipt; phase remains paused")
            ledger.put(db, "commands", handoff["id"], command)
            save(ledger, db, meta, run, "brain_handoff")
            row_data = json.loads(row["data"])
            row_data["brainId"] = new_id
            row_data.setdefault("brainHistory", []).append({"id": old, "endedAt": at, "handoffId": handoff["id"]})
            registry_db.execute("UPDATE workspaces SET brain=?,data=? WHERE id=?", (new_id, canonical(row_data), ledger.workspace_id))
            binding = registry_db.execute("SELECT project_key,data FROM project_bindings WHERE workspace=?", (ledger.workspace_id,)).fetchone()
            if binding:
                value = json.loads(binding["data"])
                value["brainId"] = new_id
                registry_db.execute("UPDATE project_bindings SET data=? WHERE project_key=?", (canonical(value), binding["project_key"]))
        return {"status": "complete", "oldBrainId": old, "newBrainId": new_id,
                "runId": run["id"], "projectId": handoff["project"]["projectId"],
                "boundary": "Checkpoint retained; Play and Resume remain separate owner controls"}


def candidate(ledger, token, value):
    require(isinstance(value, dict) and set(value) == {"handoffId", "taskId", "projectId", "hostId", "observation"},
            "Exact candidate and native observation required")
    require(isinstance(value["taskId"], str) and UUID.fullmatch(value["taskId"]), "Native task UUID required")
    require(isinstance(value["observation"], str) and 20 <= len(value["observation"]) <= 2000,
            "Describe the native project/task observation")
    with ledger.tx() as db:
        meta = authorize_brain(ledger, db, token)
        _safe(ledger, db, allow_controller=True)
        handoff = meta.get("brainHandoff")
        require(handoff and handoff["id"] == value["handoffId"] and handoff["status"] in ("prepared", "candidate"),
                "Exact prepared handoff required")
        require(value["taskId"] != meta["brainId"] and value["projectId"] == handoff["project"]["projectId"]
                and value["hostId"] == handoff["project"]["hostId"], "Replacement task belongs to another project")
        if handoff["candidate"]:
            require(handoff["candidate"] == value, "Native creation is one-shot; reconcile instead of retrying")
            return handoff
        handoff.update(candidate=value, candidateAt=time.time(), status="candidate")
        meta["brainHandoff"] = handoff
        ledger.put(db, "meta", 1, meta)
        ledger.event(db, "brain_handoff_candidate", {"id": value["handoffId"], "taskId": value["taskId"]})
        return handoff


def _current_membership(handoff):
    evidence = handoff.get("nativeMembership")
    reply = handoff.get("receiptEvidence")
    require(isinstance(evidence, dict) and evidence.get("source") == "codex.list_threads"
            and isinstance(reply, dict) and type(reply.get("observedAt")) in (int, float)
            and evidence.get("taskId") == handoff["candidate"]["taskId"]
            and evidence.get("projectId") == handoff["project"]["projectId"]
            and evidence.get("hostId") == handoff["project"]["hostId"]
            and evidence.get("status") == "idle"
            and type(evidence.get("observedAt")) in (int, float)
            and evidence["observedAt"] >= reply["observedAt"]
            and -30 <= time.time() - evidence.get("observedAt", 0) <= MEMBERSHIP_MAX_AGE,
            "Fresh native task-list project membership required before rebinding")
    return evidence


def native_observation(ledger, token, result, observed_at):
    """Retain only exact membership from a bounded native list_threads result."""
    require(isinstance(result, dict) and result.get("schemaVersion") == 4,
            "Expected Codex list_threads schemaVersion 4 result")
    require(isinstance(result.get("unavailableHosts"), list) and not result["unavailableHosts"],
            "Native task host inventory is incomplete")
    require(isinstance(result.get("unavailableSources"), list) and not result["unavailableSources"],
            "Native task source inventory is incomplete")
    groups = (result.get("pinnedThreads"), result.get("threads"))
    require(all(isinstance(group, list) for group in groups) and sum(map(len, groups)) <= 2000,
            "Bounded native task inventory required")
    try:
        raw = canonical(result).encode()
    except (TypeError, ValueError, UnicodeError):
        raise Refusal("Invalid native task inventory") from None
    require(len(raw) <= 1_000_000, "Native task inventory exceeds its bound")
    require(type(observed_at) in (int, float) and 0 < observed_at <= time.time() + 30,
            "Original native task observation time required")
    with ledger.tx() as db:
        meta = authorize_brain(ledger, db, token)
        _safe(ledger, db, allow_controller=True)
        handoff = meta.get("brainHandoff")
        require(handoff and handoff["status"] in ("candidate", "received") and handoff["candidate"],
                "Exact replacement candidate required")
        require(observed_at >= handoff.get("candidateAt", handoff["createdAt"])
                and time.time() - observed_at <= MEMBERSHIP_MAX_AGE,
                "Native task observation predates candidate or has expired")
        matches = [row for group in groups for row in group
                   if isinstance(row, dict) and row.get("id") == handoff["candidate"]["taskId"]]
        require(len(matches) == 1, "Exactly one replacement task must appear in native task inventory")
        row = matches[0]
        project = handoff["project"]
        require(row.get("kind") == "codex" and row.get("projectId") == project["projectId"]
                and row.get("hostId") == project["hostId"],
                "Native task-list project or host does not match the reviewed binding")
        require(row.get("status") in ("active", "idle"), "Replacement native task status is unavailable")
        evidence = {"source": "codex.list_threads", "taskId": row["id"],
                    "projectId": row["projectId"], "hostId": row["hostId"], "status": row["status"],
                    "observedAt": observed_at, "resultHash": hashlib.sha256(raw).hexdigest(),
                    "boundary": "Brain-imported native tool result, not cryptographic host attestation"}
        prior = handoff.get("nativeMembership")
        require(not prior or observed_at > prior["observedAt"] or evidence == prior,
                "Older or conflicting native task observation")
        if evidence == prior:
            return handoff
        handoff["nativeMembership"] = evidence
        meta["brainHandoff"] = handoff
        ledger.put(db, "meta", 1, meta)
        ledger.event(db, "brain_handoff_native_membership", {"id": handoff["id"],
                     "taskId": row["id"], "resultHash": evidence["resultHash"]})
        return handoff


def receipt(ledger, value):
    require(isinstance(value, dict) and set(value) == {"handoffId", "taskId", "packageHash", "summary"},
            "Exact replacement receipt required")
    require(isinstance(value["summary"], str) and 20 <= len(value["summary"]) <= 2000,
            "Bounded replacement understanding required")
    with ledger.tx() as db:
        meta, run = _safe(ledger, db)
        handoff = meta.get("brainHandoff")
        require(handoff and handoff["id"] == value["handoffId"] and handoff["status"] in ("candidate", "received")
                and handoff["candidate"]["taskId"] == value["taskId"]
                and handoff["packageHash"] == value["packageHash"], "Exact candidate/package receipt required")
        if handoff["receipt"]:
            require(handoff["receipt"] == value, "Replacement receipt changed")
            return handoff
        from .activity import HEADER_BYTES, candidates, open_regular
        from .observations import config as observation_config
        from .standard import git_root
        home = observation_config(ledger).get("codexHome")
        require(home and Path(home).is_absolute(), "Configured local Codex log root required")
        paths = candidates(Path(home), value["taskId"])
        require(paths, "Replacement native session has not been observed locally")
        observed = False
        native_evidence = None
        for path in paths:
            with open_regular(path) as stream:
                first = stream.readline(HEADER_BYTES + 1)
            require(len(first) <= HEADER_BYTES and first.endswith(b"\n"), "Invalid native session header")
            try:
                header = json.loads(first)
            except (ValueError, UnicodeError):
                raise Refusal("Invalid native session header") from None
            if not isinstance(header, dict):
                continue
            payload = header.get("payload", {})
            if not isinstance(payload, dict):
                continue
            if header.get("type") != "session_meta" or payload.get("id") != value["taskId"] or payload.get("forked_from_id"):
                continue
            cwd = payload.get("cwd")
            if isinstance(cwd, str) and Path(cwd).is_absolute():
                try:
                    if git_root(cwd) in run["identities"].values():
                        observed = True
                        evidence = _native_receipt(path, value["taskId"], receipt_marker(value), handoff["createdAt"])
                        if evidence is not None:
                            native_evidence = evidence
                            break
                except (OSError, Refusal, ValueError):
                    pass
        require(observed, "Replacement task checkout does not match the reviewed repository identity")
        require(native_evidence is not None, "Replacement task has not acknowledged the exact package in a final native reply")
        handoff.update(receipt=value, receiptEvidence={"source": "local_native_final_reply", **native_evidence,
                       "nativeProjectMembership": "brain_observed_not_independently_attested"},
                       status="received", receivedAt=time.time())
        meta["brainHandoff"] = handoff
        ledger.put(db, "meta", 1, meta)
        ledger.event(db, "brain_handoff_received", {"id": value["handoffId"], "taskId": value["taskId"]})
        return handoff


def status(ledger, registry=None):
    """Read-only owner gate summary; the signed previews still enforce every check."""
    project = None
    project_error = None
    if registry is not None:
        # Keep registry -> ledger order even on advisory reads. A final owner
        # confirmation writes both databases in that order.
        try:
            with read_db(registry.db) as registry_db:
                project = _project(registry, ledger.workspace_id, registry_db)
        except Refusal as error:
            project_error = str(error)
        except (ValueError, KeyError, OSError, sqlite3.Error):
            project_error = "Native project binding could not be inspected"
    with read_db(ledger.db) as db:
        meta = ledger.get(db, "meta", 1)
        handoff = meta.get("brainHandoff")
        phase = handoff["status"] if handoff else "not_prepared"
        blockers = []
        try:
            _safe(ledger, db)
        except (Refusal, ValueError, KeyError) as error:
            blockers.append(str(error))
        if registry is None:
            blockers.append("Native project binding was not checked")
        elif project_error:
            blockers.append(project_error)
        elif handoff and phase not in ("complete", "cancelled") and project != handoff["project"]:
            blockers.append("Native project binding changed")
        if phase == "prepared":
            blockers.append("Record the one native replacement task before receipt review")
        elif phase == "candidate":
            blockers.append("Record the exact package marker in a final native reply and import its receipt")
        elif phase == "received":
            if not handoff.get("candidate") or not handoff.get("receipt") or not handoff.get("receiptEvidence"):
                blockers.append("Exact replacement candidate and native final-reply receipt are required")
            else:
                try:
                    _current_membership(handoff)
                except (Refusal, ValueError, KeyError) as error:
                    blockers.append(str(error))
        elif phase not in ("not_prepared", "complete", "cancelled"):
            blockers.append("Handoff state needs reconciliation")
        return {"brainId": meta["brainId"], "handoff": handoff,
                "runId": (meta.get("standardRun") or {}).get("id"),
                "readiness": {"phase": phase,
                              "canPrepare": phase in ("not_prepared", "complete", "cancelled") and not blockers,
                              "canFinalize": phase == "received" and not blockers,
                              "blockers": blockers,
                              "boundary": "Read-only guidance; a fresh signed owner preview is still required"}}


def recover_registry(registry, workspace, handoff_id, confirmed):
    """Finish only a ledger-committed rebind after an interrupted second DB commit.

    The ledger commits first. An interruption can leave the registry on the old
    brain; root_for then fails closed. This exact repair makes no native effect.
    """
    require(confirmed is True and isinstance(handoff_id, str) and UUID.fullmatch(handoff_id),
            "Exact owner-confirmed handoff recovery required")
    from .core import Ledger
    from .workspaces import inspect_ledger
    with registry.tx() as db:
        row = db.execute("SELECT root,brain,data FROM workspaces WHERE id=?", (workspace,)).fetchone()
        require(row is not None, "Registered project unavailable")
        data = json.loads(row["data"])
        inspected = inspect_ledger(row["root"])
        require(inspected["databaseIdentity"] == data["databaseIdentity"], "Registered ledger identity changed")
        ledger = Ledger(row["root"])
        with read_db(ledger.db) as ledger_db:
            meta = ledger.get(ledger_db, "meta", 1)
            handoff = meta.get("brainHandoff")
            run = meta.get("standardRun")
            require(handoff and handoff["id"] == handoff_id and handoff["status"] == "complete"
                    and run and run["brainId"] == meta["brainId"]
                    and handoff["candidate"]["taskId"] == meta["brainId"],
                    "No exact ledger-committed brain handoff to recover")
            require(meta["controller"] is None and all(task["status"] in TERMINAL for task in run["tasks"]),
                    "Recovery requires the saved safe checkpoint")
            old, new = handoff["oldBrainId"], meta["brainId"]
        binding = db.execute("SELECT project_key,data FROM project_bindings WHERE workspace=?", (workspace,)).fetchone()
        require(binding is not None, "Native project binding unavailable")
        binding_data = json.loads(binding["data"])
        require(binding["project_key"] == handoff["project"]["key"]
                and binding_data["locationHash"] == handoff["project"]["locationHash"],
                "Native project binding changed")
        if row["brain"] == new:
            require(binding_data["brainId"] == new and data["brainId"] == new,
                    "Partial registry binding needs manual review")
            return {"status": "already_consistent", "brainId": new}
        require(row["brain"] == old and data["brainId"] == old and binding_data["brainId"] == old,
                "Registry is not at the reviewed old brain")
        require(not db.execute("SELECT 1 FROM workspaces WHERE brain=?", (new,)).fetchone(),
                "Replacement brain already owns another project")
        data["brainId"] = new
        data.setdefault("brainHistory", []).append({"id": old, "endedAt": handoff["completedAt"],
                                                     "handoffId": handoff_id})
        binding_data["brainId"] = new
        db.execute("UPDATE workspaces SET brain=?,data=? WHERE id=?", (new, canonical(data), workspace))
        db.execute("UPDATE project_bindings SET data=? WHERE project_key=?",
                   (canonical(binding_data), binding["project_key"]))
    return {"status": "recovered", "oldBrainId": old, "newBrainId": new,
            "boundary": "Registry rebind only; no Play, Resume, approval or native effect"}
