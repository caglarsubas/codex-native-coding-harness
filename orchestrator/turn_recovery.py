"""Exact owner cancellation of one orphaned standard brain turn.

No reconnect of its lost subscription, approval response, wake or effect replay.
The durable cancellation claim precedes the native boundary. Later reconciliation
only reads that same turn; controller recovery is conditional on fresh inactivity.
"""
import copy
import contextlib
import hmac
import math
import time
import uuid

from .admission import exact
from .app_server_wake import NATIVE_APPROVAL_POLICY
from .core import Refusal, digest, require
from .enrollment import fence_exists, record_in
from .native_project_assignment import _scope, _native_identity
from .native_read_client import ReadProxy, validate_endpoint
from .retention_controls import RetentionControls, identity
from .standard import PROTOCOL, save

TTL = 300
BOUNDARY = ("Cancel only this existing brain turn if it is still active. Recover its abandoned controller only "
            "after repeated exact ended-turn reads and no tracked terminals. Preserve every effect, receipt, "
            "usage gap and the original phase expiry. No permission response, checkpoint, wake, Resume, Play or pilot acceptance.")
DETAIL = "The original request is still retained. Review recovery here; do not repeat Play or send its instruction again."


def state_in(ledger, db):
    return {"meta": ledger.get(db, "meta", 1), **{name: ledger.all(db, table) for name, table in
            (("repositories", "repos"), ("commands", "commands"), ("workers", "workers"), ("queue", "queue"))}}


def saved_state(ledger):
    # Internal hash context must retain the controller token. The public snapshot
    # deliberately redacts it and adds diagnostic clocks; neither belongs here.
    with contextlib.closing(ledger.connect()) as db:
        db.execute("BEGIN")
        return state_in(ledger, db)


def eligible(state):
    meta = state["meta"]
    run = meta.get("standardRun") or {}
    brain = meta.get("brainId")
    require(meta.get("schemaVersion") == 4 and meta.get("paused") is True and
            run.get("protocol") == PROTOCOL and run.get("brainId") == brain and
            run.get("status") in ("running", "stopping") and not run.get("ownerCloseout"),
            "An unresolved cooperative standard phase is required")
    require(state["repositories"] and all(r["policyProfile"] == "standard" for r in state["repositories"]),
            "Strict Harness cannot use standard turn recovery")
    require(not run.get("tasks") and not run.get("merges") and not state["workers"] and
            not state["queue"] and not meta.get("runner") and not meta.get("admissionBinding"),
            "Tasks, packets, runners and managed ownership require separate reconciliation")
    require((meta.get("brainControl") or {}).get("desired") != "stopped" and
            not meta.get("brainHandoff"), "Brain Stop or replacement needs its own recovery")
    controller = meta.get("controller")
    require(isinstance(controller, dict) and isinstance(controller.get("owner"), str) and
            controller["owner"].startswith(brain + ":"), "The exact abandoned brain controller is required")
    commands = state["commands"]
    require(not any(c.get("status") in ("queued", "processing") or c.get("needsBrainReceipt") or
                    (c.get("notification") or {}).get("status") in ("sending", "uncertain")
                    for c in commands), "A pending control or uncertain delivery requires its own reconciliation")
    owned = [c for c in commands if (c.get("notification") or {}).get("brainId") == brain]
    require(owned, "No retained owned request is available")
    command = max(owned, key=lambda c: c["notification"].get("attemptedAt", c.get("createdAt", 0)))
    note = command["notification"]
    require(controller["owner"].endswith(command["id"]),
            "The abandoned controller must belong to this exact received request")
    stream = note.get("nativeThreadObservation") or {}
    profile = note.get("nativeResumeProfile") or {}
    require(command.get("status") == "completed" and note.get("status") == "accepted" and
            note.get("nativeDelivery") == "owned_turn_start" and note.get("hostRunId") == run.get("id") and
            isinstance(note.get("nativeTurnId"), str) and note["nativeTurnId"] and
            note.get("nativeTurnStatus") in ("native_attention_required", "native_approval_response_uncertain",
                                             "connection_lost", "unconfirmed"),
            "The latest received request must retain its exact unresolved native turn")
    require(stream.get("version") == 1 and stream.get("rootThreadId") == brain and
            type(stream.get("monitoringEndedAt")) in (int, float) and
            math.isfinite(stream["monitoringEndedAt"]) and 0 < stream["monitoringEndedAt"] <= time.time() and
            stream.get("streamStatus") != "open" and stream.get("events") == [],
            "Wait for the original observer to end; observed child threads need separate reconciliation")
    require(not note.get("nativeApprovals"), "A native decision intent cannot use orphaned-turn recovery")
    require(profile.get("version") == 1 and profile.get("brainId") == brain and
            profile.get("commandId") == command["id"] and profile.get("nativeTurnId") == note["nativeTurnId"] and
            profile.get("bindingHash") == note.get("hostBindingHash") and
            profile.get("requested") == NATIVE_APPROVAL_POLICY and profile.get("resumeAcknowledged") is True,
            "The original reviewed host and native profile are required")
    return command


def context(state):
    value = copy.deepcopy({k: state[k] for k in ("meta", "repositories", "commands", "workers", "queue")})
    for command in value["commands"]:
        (command.get("notification") or {}).pop("turnRecovery", None)
    return digest(value)


def membership(registry, ledger, binding, scope):
    current = _scope(registry, ledger.workspace_id, binding)
    require({k: v for k, v in current.items() if k != "ledgerRevision"} ==
            {k: v for k, v in scope.items() if k != "ledgerRevision"},
            "Registered catalog, project or ledger identity changed")


def inspect(ledger, wake):
    """Saved metadata only; GET and polling never connect or recover ownership."""
    state = saved_state(ledger)
    run = state["meta"].get("standardRun") or {}
    entries = [c for c in state["commands"] if (c.get("notification") or {}).get("brainId") == state["meta"]["brainId"] and
               (c.get("notification") or {}).get("hostRunId") == run.get("id") and
               (c.get("notification") or {}).get("turnRecovery")]
    if entries:
        last = max(entries, key=lambda c: c["notification"]["turnRecovery"]["claimedAt"])
        entry = last["notification"]["turnRecovery"]
        return {"status": entry["status"], "commandId": last["id"], "delivery": entry["delivery"],
                "detail": ("The abandoned controller was recovered. Development remains stopped. Next: request a safe phase checkpoint."
                           if entry["status"] == "controller_recovered" else
                           "Recovery was claimed once. Check the existing turn again; cancellation will not be resent."),
                "boundary": BOUNDARY}
    try:
        require(wake is not None, "No reviewed owned host is configured")
        command = eligible(state)
        return {"status": "review_available", "commandId": command["id"], "detail": DETAIL, "boundary": BOUNDARY}
    except (Refusal, KeyError, TypeError) as error:
        return {"status": "unavailable", "detail": str(error), "boundary": BOUNDARY}


class RecoveryProxy(ReadProxy):
    """One fixed interrupt permit, exact metadata reads; no resume/start/response."""
    def __init__(self, endpoint, scope, turn_id):
        super().__init__(endpoint, timeout=15)
        self.scope, self.turn_id, self.interrupt_permit = scope, turn_id, False

    def _rpc(self, method, params):
        brain = self.scope["brainId"]
        if method == "initialize":
            require(self.sequence == 0, "Only the initial native handshake is permitted")
        elif method == "project/read":
            require(params == {"projectId": self.scope["projectId"]}, "Exact project metadata required")
        elif method == "thread/read":
            require(params == {"threadId": brain, "includeTurns": False}, "Exact brain metadata required")
        elif method == "thread/turns/list":
            require(params == {"threadId": brain, "cursor": None, "limit": 1,
                              "sortDirection": "desc", "itemsView": "notLoaded"}, "Exact latest-turn metadata required")
        elif method == "thread/backgroundTerminals/list":
            require(params == {"threadId": brain, "cursor": None, "limit": 64}, "Exact tracked-terminal metadata required")
        elif method == "turn/interrupt":
            require(self.interrupt_permit and params == {"threadId": brain, "turnId": self.turn_id},
                    "Only one claimed exact-turn cancellation is permitted")
            self.interrupt_permit = False  # Consume before attempting the frame.
        else:
            raise Refusal("Unsupported recovery RPC; no wake, approval response or process command")
        return super()._rpc(method, params)


def observe(proxy, scope, turn_id):
    def one():
        thread, _ = _native_identity(proxy, scope, require_idle=False)
        require(thread.get("projectId") == scope["projectId"], "Native project identity changed")
        page = proxy._rpc("thread/turns/list", {"threadId": scope["brainId"], "cursor": None,
                         "limit": 1, "sortDirection": "desc", "itemsView": "notLoaded"})
        require(isinstance(page, dict) and isinstance(page.get("data"), list) and len(page["data"]) == 1,
                "The exact latest native turn is unavailable")
        row = page["data"][0]
        require(isinstance(row, dict) and row.get("id") == turn_id and
                row.get("status") in ("inProgress", "completed", "interrupted", "failed"),
                "Another or unknown turn exists; recovery cannot target it")
        terminals = proxy._rpc("thread/backgroundTerminals/list", {"threadId": scope["brainId"], "cursor": None, "limit": 64})
        require(isinstance(terminals, dict) and terminals.get("data") == [] and
                "nextCursor" in terminals and terminals["nextCursor"] is None,
                "Tracked terminals are active or unknown; they need separate supervision")
        activity = thread["status"]["type"]
        require((row["status"] == "inProgress" and activity == "active") or
                (row["status"] != "inProgress" and activity in ("idle", "notLoaded")),
                "Native activity and turn history disagree")
        return {"turnId": turn_id, "status": row["status"], "completedAt": row.get("completedAt"),
                "activity": activity, "trackedTerminals": 0}
    before, after = one(), one()
    require(before == after, "Native turn changed during inspection; no cancellation was sent")
    return {**after, "observedAt": time.time(), "effectOutcome": "unknown", "taskTreeComplete": False}


class TurnRecoveryControls(RetentionControls):
    def _bound(self, registry, ledger, wake, state):
        command = eligible(state)
        require(wake is not None and wake.orphan_recovery_idle(), "The original observer or native prompt is still active")
        binding = copy.deepcopy(wake.binding)
        require(digest(binding) == command["notification"]["hostBindingHash"],
                "The original host binding changed; no replacement or reconnect is authorized")
        require(not fence_exists(ledger.root), "Strict maintenance blocks turn recovery")
        with registry.tx() as db:
            require(record_in(db) is None, "Strict platform maintenance blocks turn recovery")
        scope = _scope(registry, ledger.workspace_id, binding)
        require(scope["root"] == ledger.root and scope["brainId"] == state["meta"]["brainId"] and
                scope["ledgerRevision"] == state["meta"]["revision"] and scope["hostId"] == "local",
                "Registered recovery identity changed")
        return command, binding, scope

    def preview(self, registry, ledger, wake, body, session):
        exact(body, {"commandId"})
        state = saved_state(ledger)
        command, binding, scope = self._bound(registry, ledger, wake, state)
        require(command["id"] == body["commandId"] and not command["notification"].get("turnRecovery"),
                "This turn already has a recovery claim; check its existing outcome instead")
        turn_id = command["notification"]["nativeTurnId"]
        with RecoveryProxy(binding["endpoint"], scope, turn_id) as proxy:
            observed = observe(proxy, scope, turn_id)
        validate_endpoint(binding["endpoint"])
        membership(registry, ledger, binding, scope)
        require(context(saved_state(ledger)) == context(state) and wake.binding == binding and wake.orphan_recovery_idle(),
                "Project or host changed during recovery inspection")
        now = time.time()
        doc = {"kind": "orphaned_turn_recovery", "id": str(uuid.uuid4()), "workspaceId": ledger.workspace_id,
               "ledgerIdentity": identity(ledger), "session": digest(session), "contextHash": context(state),
               "commandId": command["id"], "brainId": scope["brainId"], "turnId": turn_id,
               "bindingHash": digest(binding), "scopeHash": digest({k: str(v) for k, v in scope.items()}),
               "action": "cancel_then_reconcile" if observed["status"] == "inProgress" else "reconcile_ended_turn",
               "observation": observed, "createdAt": now, "expiresAt": now + TTL, "boundary": BOUNDARY}
        return {"document": doc, "signature": self.sign(doc)}

    def confirm(self, registry, ledger, wake, body, session):
        exact(body, {"proposal", "confirmed"})
        require(body["confirmed"] is True, "Confirm this exact cancellation and conditional controller recovery")
        proposal = body["proposal"]
        exact(proposal, {"document", "signature"})
        doc = proposal["document"]
        require(isinstance(proposal["signature"], str) and hmac.compare_digest(proposal["signature"], self.sign(doc)),
                "Recovery preview changed or dashboard restarted")
        require(doc["workspaceId"] == ledger.workspace_id and doc["ledgerIdentity"] == identity(ledger) and
                doc["session"] == digest(session) and doc["kind"] == "orphaned_turn_recovery",
                "Recovery review belongs to another project or session")
        # An identical HTTP retry returns its existing receipt without native I/O,
        # even after expiry. It never retries the cancellation.
        existing = next((c for c in saved_state(ledger)["commands"] if c["id"] == doc["commandId"]), None)
        entry = ((existing or {}).get("notification") or {}).get("turnRecovery")
        if entry:
            require(entry.get("reviewHash") == digest(doc), "Another recovery already owns this turn")
            return inspect(ledger, wake)
        require(0 <= time.time() - doc["createdAt"] <= TTL and time.time() <= doc["expiresAt"],
                "Recovery review expired. Refresh review; nothing was sent")
        state = saved_state(ledger)
        command, binding, scope = self._bound(registry, ledger, wake, state)
        require(context(state) == doc["contextHash"] and digest(binding) == doc["bindingHash"] and
                digest({k: str(v) for k, v in scope.items()}) == doc["scopeHash"] and
                command["id"] == doc["commandId"] and command["notification"]["nativeTurnId"] == doc["turnId"],
                "Recovery scope changed; review the current request")
        with RecoveryProxy(binding["endpoint"], scope, doc["turnId"]) as proxy:
            observed = observe(proxy, scope, doc["turnId"])
            require(doc["action"] == "cancel_then_reconcile" or observed["status"] != "inProgress",
                    "The ended turn became active; no cancellation is authorized")
            with registry.tx() as registry_db, ledger.tx() as db:
                require(record_in(registry_db) is None and not fence_exists(ledger.root), "Maintenance changed")
                current = state_in(ledger, db)
                require(context(current) == doc["contextHash"] and wake.binding == binding and wake.orphan_recovery_idle(),
                        "Recovery context changed before claim")
                membership(registry, ledger, binding, scope)
                eligible(current)
                meta, run = current["meta"], current["meta"]["standardRun"]
                run["status"] = "stopping"
                save(ledger, db, meta, run, "orphaned_turn_recovery_claimed")
                command = ledger.get(db, "commands", doc["commandId"])
                entry = {"id": doc["id"], "reviewHash": digest(doc), "bindingHash": doc["bindingHash"],
                         "controllerHash": digest(meta["controller"]), "claimedAt": time.time(),
                         "status": "awaiting_end", "delivery": "unknown", "observation": observed}
                command["notification"]["turnRecovery"] = entry
                ledger.put(db, "commands", command["id"], command)
                entry["contextHash"] = context(state_in(ledger, db))
                ledger.put(db, "commands", command["id"], command)
            if observed["status"] == "inProgress":
                # Keep local safety context locked through this sole native send.
                # Claim above is already committed; any lost result stays owned.
                try:
                    with registry.tx() as registry_db, ledger.tx() as db:
                        require(record_in(registry_db) is None and not fence_exists(ledger.root) and
                                context(state_in(ledger, db)) == entry["contextHash"] and
                                wake.binding == binding and wake.orphan_recovery_idle(), "Recovery send was fenced")
                        validate_endpoint(binding["endpoint"])
                        membership(registry, ledger, binding, scope)
                        proxy.interrupt_permit = True
                        result = proxy._rpc("turn/interrupt", {"threadId": doc["brainId"], "turnId": doc["turnId"]})
                        require(result == {}, "Native cancellation acknowledgment is unknown")
                    delivery = "acknowledged"
                except (OSError, Refusal, ValueError):
                    delivery = "unknown"  # Never reconstruct or resend.
            else:
                delivery = "not_needed"
        with ledger.tx() as db:
            command = ledger.get(db, "commands", doc["commandId"])
            command["notification"]["turnRecovery"]["delivery"] = delivery
            ledger.put(db, "commands", command["id"], command)
        return self.reconcile(registry, ledger, wake, {"commandId": doc["commandId"]})

    def reconcile(self, registry, ledger, wake, body):
        """Explicit check or completion of the confirmed transaction; never resend."""
        exact(body, {"commandId"})
        state = saved_state(ledger)
        command = next((c for c in state["commands"] if c["id"] == body["commandId"]), None)
        entry = ((command or {}).get("notification") or {}).get("turnRecovery")
        require(entry, "No owner-confirmed recovery exists; review recovery first")
        if entry["status"] == "controller_recovered":
            return inspect(ledger, wake)
        try:
            command, binding, scope = self._bound(registry, ledger, wake, state)
            require(command["id"] == body["commandId"] and context(state) == entry["contextHash"],
                    "New project activity fenced the old recovery")
            with RecoveryProxy(binding["endpoint"], scope, command["notification"]["nativeTurnId"]) as proxy:
                observed = observe(proxy, scope, command["notification"]["nativeTurnId"])
            validate_endpoint(binding["endpoint"])
            require(observed["status"] != "inProgress", "The existing turn has not ended yet")
            with registry.tx() as registry_db, ledger.tx() as db:
                require(record_in(registry_db) is None and not fence_exists(ledger.root) and
                        context(state_in(ledger, db)) == entry["contextHash"] and wake.binding == binding and
                        wake.orphan_recovery_idle(), "Recovery context changed during ended-turn inspection")
                current = state_in(ledger, db)
                membership(registry, ledger, binding, scope)
                eligible(current)
                meta = current["meta"]
                require(digest(meta["controller"]) == entry["controllerHash"], "Controller ownership changed")
                meta.update(controller=None, paused=True)
                from .run_authority import fence_in
                fence_in(ledger, db, meta, "orphaned_turn_recovery")
                ledger.put(db, "meta", 1, meta)
                command = ledger.get(db, "commands", command["id"])
                command["notification"]["turnRecovery"].update(status="controller_recovered", observation=observed)
                ledger.put(db, "commands", command["id"], command)
                ledger.event(db, "orphaned_turn_controller_recovered", {"commandId": command["id"], "turnId": observed["turnId"]})
        except (Refusal, OSError, ValueError):
            result = inspect(ledger, wake)
            result["detail"] = "The turn or host could not be confirmed inactive. Ownership stays retained. Repair the reviewed host, then check this same recovery; do not repeat Play."
            return result
        return inspect(ledger, wake)
