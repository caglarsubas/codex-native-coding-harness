"""Closed pre-Play catalog receipt IPC on the original owned subscription.

The sandbox touches only its checkout's private mailbox, never SQLite, the
registry, a controller credential or the protected native socket. This is not a
dispatcher: only the observer of the original, prospectively pinned turn may
relay the designated brain's explicit catalog/catalog_error result.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

from .core import Refusal, digest, require
from .standard_host_inspection import _read_private, _write_once

VERSION = 1
TRANSPORT = "preplay_catalog_observer_v1"
SOURCE = Path(__file__).resolve().parent.parent
BOUNDARY = {"playAuthorized": False, "nativeWriteAuthorized": False,
            "terminalSafety": "unknown", "usageMeasured": False}


def source_hash():
    files = sorted((SOURCE / "orchestrator").glob("*.py"))
    require(files and all(p.is_file() and not p.is_symlink() for p in files), "Pre-Play source changed")
    return digest({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files})


def path(root, command_id, kind):
    from .admission import identifier
    identifier(command_id)
    root = Path(root)
    info = root.stat()
    require(root.is_absolute() and root.resolve(strict=True) == root and
            root.is_dir() and info.st_uid == os.getuid() and not info.st_mode & 0o077,
            "Exact private pre-Play mailbox directory required")
    require(kind in ("handoff", "request", "claim", "reply", "capabilities", "capabilities-claim"), "Closed pre-Play mailbox required")
    return root / ("preplay-catalog-" + digest(command_id) + "-" + kind + ".json")


def _identity(file):
    info = file.stat(follow_symlinks=False)
    require(file.is_file() and not file.is_symlink() and info.st_uid == os.getuid() and
            info.st_nlink == 1 and not info.st_mode & 0o077, "Private pre-Play ledger identity required")
    return {"device": info.st_dev, "inode": info.st_ino}


def _eligible(ledger, db, command):
    from . import standard
    from .brain_control import stopped
    meta, mission = standard.eligible(ledger, db)
    require(meta.get("schemaVersion") == 1 and meta.get("standardRun") is None and meta.get("controller") is None and
            not stopped(meta) and not meta.get("brainHandoff"),
            "Pre-Play receipt requires an empty, unowned, unstopped standard project")
    require(command["kind"] == standard.CATALOG_REFRESH_KIND and command["status"] == "queued" and
            command["actor"] in ("dashboard", "assistant_owner_confirmed") and
            command["payload"]["brainId"] == meta["brainId"] and
            command["payload"]["missionHash"] == mission["documentHash"] and
            command["payload"]["contextHash"] == standard.projection(ledger, db)["contextHash"],
            "Exact unchanged pending pre-Play request required")
    from .readiness_disposition import retired_in
    require(not retired_in(ledger, db, command['id']), 'Disposed readiness cannot acquire a handoff')
    require(not any(c["id"] != command["id"] and (c["status"] in ("queued", "processing") or
                    c.get("needsBrainReceipt")) and not retired_in(ledger, db, c['id'])
                    for c in ledger.all(db, "commands")),
            "Another pending control fences the pre-Play receipt")
    require(not ledger.all(db, "workers") and not ledger.all(db, "queue"),
            "Pre-Play receipt requires no recorded tasks or packets")
    return meta


def prepare(ledger, db, command, binding):
    """Only the committed original notification may publish this before turn/start."""
    retained = ledger.get(db, "commands", command["id"])
    require(not retained.get("notification") and not retained.get("notificationHistory") and
            retained == command, "Pre-Play handoff cannot be added to an attempted or historical request")
    meta = _eligible(ledger, db, command)
    record = binding["brains"].get(meta["brainId"], {})
    require(record.get("workspaceId") == ledger.workspace_id and
            Path(record.get("cwd", "/")).resolve(strict=True) == Path(record.get("cwd", "/")) and
            ledger.root.is_relative_to(Path(record["cwd"])) and ledger.root != Path(record["cwd"]),
            "Pre-Play mailbox must be inside the exact bound checkout")
    value = {"version": VERSION, "transport": TRANSPORT, "workspaceId": ledger.workspace_id,
             "brainId": meta["brainId"], "commandId": command["id"],
             "missionHash": command["payload"]["missionHash"], "contextHash": command["payload"]["contextHash"],
             "bindingHash": digest(binding), "ledgerIdentity": _identity(ledger.db),
             "source": str(SOURCE), "sourceHash": source_hash(), "boundary": BOUNDARY}
    if record.get('nativeTaskBackend') is not None:
        from .public_native_tasks import validate_contract
        backend = validate_contract(record['nativeTaskBackend'], record.get('policyEvidence'))
        value.update(version=2, publicBackendHash=digest(backend))
        if command['payload'].get('readinessStart') is not None:
            from .readiness_owned import validate_review
            review = validate_review(command['payload']['readinessStart'])
            require(review['bindingHash'] == digest(binding) and review['commandId'] == command['id'],
                    'Original readiness-owned command required')
            value.update(version=3, readinessStartHash=digest(review))
    file = path(ledger.root, command["id"], "handoff")
    # No historical creation/backfill, even if a prior identical file exists.
    _write_once(file, value)
    return {"version": value['version'], "transport": TRANSPORT, "handoffHash": digest(value)}


def handoff(file):
    file = Path(file)
    require(file.is_absolute(), "Absolute original pre-Play handoff required")
    value = _read_private(file)
    fields = {
        "version", "transport", "workspaceId", "brainId", "commandId", "missionHash", "contextHash",
        "bindingHash", "ledgerIdentity", "source", "sourceHash", "boundary"}
    require(isinstance(value, dict) and type(value.get('version')) is int and ((value.get('version') == VERSION and set(value) == fields) or
        (value.get('version') == 2 and set(value) == fields | {'publicBackendHash'}) or
        (value.get('version') == 3 and set(value) == fields | {'publicBackendHash','readinessStartHash'})) and
        value["transport"] == TRANSPORT and value["boundary"] == BOUNDARY and
        value["source"] == str(SOURCE) and value["sourceHash"] == source_hash() and
        file == path(file.parent, value["commandId"], "handoff"), "Pre-Play handoff or source changed")
    return value


def state(file):
    file = Path(file)
    value = handoff(file)
    result = {k: value[k] for k in ("workspaceId", "brainId", "commandId", "missionHash", "boundary")} | {
        "status": "original_request_at_capture", "liveStateObserved": False,
        "instruction": "Return only catalog or catalog_error for this exact request; no shared registry access."}
    if value['version'] in (2,3):
        evidence = public_capture(file, value)
        result.update(publicReadiness={'evidenceHash': digest(evidence), 'models': evidence['models'],
            'backend': evidence['backend']['protocol'], 'schema': evidence['schema'],
            'observedAt': evidence['observedAt'], 'boundary': evidence['boundary']},
            instruction='Acknowledge this exact public evidenceHash using public_catalog_ack, or record catalog_error. '
                        'Do not discover desktop tools, invent values, select a model, load a brain or start work.')
    return result


def public_capture(file, value):
    from .public_readiness import validate
    evidence = validate(_read_private(path(Path(file).parent, value['commandId'], 'capabilities')),
        value['bindingHash'], value['brainId'], value['commandId'], digest(value))
    require(digest(evidence['backend']) == value['publicBackendHash'], 'Public task backend changed')
    return evidence


def capture_public(ledger, binding, command_id, brain_id, proxy):
    """Only the original sending command, before turn/start; never status/polling."""
    file = path(ledger.root, command_id, 'handoff')
    value = handoff(file)
    require(value['version'] in (2,3), 'Prospective public handoff required; never backfill')
    def check():
        from .standard import read_db
        with read_db(ledger.db) as db:
            command = ledger.get(db, 'commands', command_id)
            _eligible(ledger, db, command)
            note = command.get('notification') or {}
            require(note.get('status') == 'sending' and note.get('brainId') == brain_id and
                    not note.get('nativeTurnId') and not note.get('nativePublicReadinessHash') and
                    note.get('preplayCatalog') == {'version': value['version'], 'transport': TRANSPORT, 'handoffHash': digest(value)} and
                    digest(binding) == value['bindingHash'] and value['ledgerIdentity'] == _identity(ledger.db),
                    'Only original pre-turn sending scope can capture public readiness')
    check()
    _write_once(path(ledger.root, command_id, 'capabilities-claim'), {'handoffHash': digest(value)})
    from .public_readiness import collect
    evidence = collect(proxy, binding, brain_id, command_id, digest(value))
    check()
    _write_once(path(ledger.root, command_id, 'capabilities'), evidence)
    with ledger.tx() as db:
        command = ledger.get(db, 'commands', command_id)
        _eligible(ledger, db, command)
        note = command.get('notification') or {}
        require(note.get('status') == 'sending' and not note.get('nativeTurnId') and
                not note.get('nativePublicReadinessHash') and note.get('brainId') == brain_id and
                note.get('preplayCatalog') == {'version': value['version'], 'transport': TRANSPORT, 'handoffHash': digest(value)} and
                value['ledgerIdentity'] == _identity(ledger.db) and digest(binding) == value['bindingHash'],
                'Original public capture scope changed')
        note['nativePublicReadinessHash'] = digest(evidence)
        ledger.put(db, 'commands', command_id, command)
    return evidence


def public_send_check(ledger, binding, command_id, brain_id):
    from .standard import read_db
    value = handoff(path(ledger.root, command_id, 'handoff'))
    if value['version'] == 3:
        from .readiness_owned import check, catalog_proof
        review = check(ledger,binding,command_id)
        require(value['readinessStartHash'] == digest(review),'Original readiness-owned handoff changed')
        with read_db(ledger.db) as db: catalog_proof(ledger.get(db,'commands',command_id))
    evidence = public_capture(path(ledger.root, command_id, 'handoff'), value)
    with read_db(ledger.db) as db:
        command = ledger.get(db, 'commands', command_id)
        _eligible(ledger, db, command)
        note = command.get('notification') or {}
        require(value['bindingHash'] == digest(binding) and value['brainId'] == brain_id and
                note.get('status') == 'sending' and not note.get('nativeTurnId') and
                note.get('nativePublicReadinessHash') == digest(evidence) and
                not any(a.get('status') not in ('resolved', 'resolved_without_response') for a in note.get('nativeApprovals', [])),
                'Public readiness intent changed before native turn; no retry')


def status(file):
    file = Path(file)
    value = handoff(file)
    request_path = path(file.parent, value["commandId"], "request")
    if not request_path.exists():
        return {"status": "not_submitted", "boundary": BOUNDARY}
    request = _read_private(request_path)
    require(request.get("handoffHash") == digest(value), "Pre-Play request changed")
    reply_path = path(file.parent, value["commandId"], "reply")
    if not reply_path.exists():
        return {"status": "claimed_outcome_unknown" if path(file.parent, value["commandId"], "claim").exists()
                else "waiting_for_original_observer", "boundary": BOUNDARY}
    reply = _read_private(reply_path)
    require(isinstance(reply, dict) and set(reply) == {"requestHash", "status", "boundary"} and
            reply["requestHash"] == digest(request) and reply["boundary"] == BOUNDARY and
            reply["status"] in ("completed", "unavailable"), "Pre-Play reply changed")
    return reply


def submit(file, result_file):
    file = Path(file)
    value = handoff(file)
    result = _read_private(Path(result_file))
    allowed = ('public_catalog_ack', 'catalog_error') if value['version'] in (2,3) else ('catalog', 'catalog_error')
    require(isinstance(result, dict) and result.get("operation") in allowed and
            result.get("requestId") == value["commandId"], "Only this exact pre-Play catalog receipt is supported")
    if result['operation'] == 'public_catalog_ack':
        require(set(result) == {'operation', 'requestId', 'evidenceHash'} and
                result['evidenceHash'] == digest(public_capture(file, value)), 'Acknowledge exact captured public evidence')
    request = {"version": VERSION, "handoffHash": digest(value), "result": result}
    request_path = path(file.parent, value["commandId"], "request")
    try:
        _write_once(request_path, request)
    except FileExistsError:
        require(_read_private(request_path) == request, "Pre-Play result already submitted; never replace or retry it")
    # A bounded wait is not a review expiry. A later status read only follows
    # the same immutable request; it cannot claim, collect or resend anything.
    end = time.monotonic() + 30
    while time.monotonic() < end:
        reply = status(file)
        if reply["status"] not in ("waiting_for_original_observer", "claimed_outcome_unknown"):
            return reply
        time.sleep(0.1)
    return status(file)


def pending(ledger, command_id):
    if not path(ledger.root, command_id, "request").exists():
        return False
    from .standard import read_db
    with read_db(ledger.db) as db:
        note = ledger.get(db, "commands", command_id).get("notification") or {}
        # The observer can begin just before notify() commits its accepted
        # result. Wait for that commit without consuming or failing the query.
        return note.get("status") != "sending"


def service(ledger, binding, command_id, brain_id, turn_id):
    """One explicit receipt, atomically gated by the existing original observer."""
    request_path = path(ledger.root, command_id, "request")
    if not request_path.exists():
        return
    request = _read_private(request_path)
    try:
        _write_once(path(ledger.root, command_id, "claim"), {"requestHash": digest(request)})
    except FileExistsError:
        return  # Even interrupted/unknown application can never reapply.
    reply = {"requestHash": digest(request), "status": "unavailable", "boundary": BOUNDARY}
    try:
        from . import standard
        from .enrollment import record_in
        from .workspaces import Registry
        value = handoff(path(ledger.root, command_id, "handoff"))
        require(set(request) == {"version", "handoffHash", "result"} and request["version"] == VERSION and
                request["handoffHash"] == digest(value) and value["bindingHash"] == digest(binding) and
                value["brainId"] == brain_id and value["workspaceId"] == ledger.workspace_id and
                value["ledgerIdentity"] == _identity(ledger.db), "Pre-Play request identity changed")
        registry = Registry(ledger.platform_root)
        require(registry.root_for(ledger.workspace_id) == ledger.root, "Pre-Play registered ledger changed")
        with registry.tx() as registry_db, ledger.tx() as db:
            require(record_in(registry_db) is None, "Strict platform enrollment fences the pre-Play receipt")
            row = registry_db.execute("SELECT root,data FROM workspaces WHERE id=?", (ledger.workspace_id,)).fetchone()
            require(row is not None and row["root"] == str(ledger.root) and
                    json.loads(row["data"])["brainId"] == brain_id, "Registered pre-Play target changed")
            command = ledger.get(db, "commands", command_id)
            meta = _eligible(ledger, db, command)
            note = command.get("notification") or {}
            require(note.get("preplayCatalog") == {"version": value['version'], "transport": TRANSPORT,
                    "handoffHash": digest(value)} and note.get("brainId") == brain_id and
                    note.get("status") == "accepted" and note.get("nativeDelivery") == "owned_turn_start" and
                    note.get("nativeTurnId") == turn_id and
                    (note.get("nativeThreadObservation") or {}).get("rootThreadId") == brain_id and
                    (note.get("nativeThreadObservation") or {}).get("streamStatus") == "open" and
                    note.get("nativeTurnStatus") in (None, "inProgress") and
                    not any(a.get("status") not in ("resolved", "resolved_without_response")
                            for a in note.get("nativeApprovals", [])) and
                    command["payload"]["missionHash"] == value["missionHash"] and
                    command["payload"]["contextHash"] == value["contextHash"],
                    "Original subscribed pre-Play turn required; no historical handoff or continuation")
            owned = [c for c in ledger.all(db, "commands") if (c.get("notification") or {}).get("brainId") == brain_id]
            require(max(owned, key=lambda c: c["notification"].get("attemptedAt", 0))["id"] == command_id,
                    "A newer owned turn superseded this receipt")
            result = request["result"]
            allowed = ('public_catalog_ack', 'catalog_error') if value['version'] in (2,3) else ('catalog', 'catalog_error')
            require(isinstance(result, dict) and result.get("operation") in allowed and
                    result.get("requestId") == command_id, "Only the exact catalog receipt is permitted")
            public_evidence = None
            if result['operation'] == 'public_catalog_ack':
                if value['version'] == 3:
                    from .readiness_owned import catalog_proof
                    proof = catalog_proof(command)
                    require(proof['reviewHash'] == value['readinessStartHash'],'Readiness lifecycle receipt changed')
                public_evidence = public_capture(path(ledger.root, command_id, 'handoff'), value)
                require(set(result) == {'operation', 'requestId', 'evidenceHash'} and
                        result['evidenceHash'] == note.get('nativePublicReadinessHash') == digest(public_evidence) and
                        note.get('nativeTaskContract') == public_evidence['backend'] and
                        note.get('nativePublicReadinessProfile', {}).get('nativeTurnId') == turn_id,
                        'Public receipt must match the original native command/turn capture')
                result = {'operation': 'catalog', 'requestId': command_id,
                          'models': public_evidence['models'], 'source': 'Original public backend schema and runtime catalog; not entitlement'}
            # The designated brain's closed receipt is relayed in one existing
            # registry->ledger transaction. No reusable controller is granted,
            # acquired, released or exposed, and no task operation is reachable.
            standard.catalog_in(ledger, db, meta, result, public_evidence=public_evidence)
            saved = ledger.get(db, "commands", command_id)
            saved["preplayReceipt"] = {"requestHash": digest(request), "handoffHash": digest(value),
                                       "brainId": brain_id, "nativeTurnId": turn_id,
                                       "bindingHash": digest(binding)}
            ledger.put(db, "commands", command_id, saved)
            ledger.event(db, "standard_preplay_receipt", saved["preplayReceipt"])
        reply["status"] = "completed"
    except (OSError, sqlite3.Error, Refusal, ValueError, KeyError, TypeError):
        pass  # No private exception text, endpoint, token or native prompt is exposed.
    _write_once(path(ledger.root, command_id, "reply"), reply)
