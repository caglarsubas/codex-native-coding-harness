"""Non-waking reconciliation of exhausted recovery history, never a retry.

Native persisted items are cross-checked against the exact configured rollout's
call inventory. Only typed declined commands can prove non-execution here.
Executed/failed/unsupported effects need independent cleanup evidence: this
adapter deliberately cannot invent it from an ended turn or an empty tracker.
"""
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import time

from .core import Refusal, canonical, digest, require
from .admission import exact
from . import ended_recovery_record as record, turn_host_continuity as continuity, historical_hosts
from .enrollment import fence_exists, record_in
from .native_read_client import ReadProxy, validate_endpoint, file_identity, decode
from .turn_recovery import observe, membership
from .observations import config
from .activity import candidates, open_regular

WORKFLOW = "phase_historical_effects"
CLOSE_WORKFLOW = "phase_terminal_closeout"
KIND = "standard_historical_effects"
CLOSE_KIND = "standard_terminal_closeout"
BOUNDARY = ("Retain independently read historical effect evidence, including every unknown. "
            "No brain receipt, safe checkpoint, load, wake, approval response, effect replay, Play, Resume, "
            "usage reset, expiry change or pilot acceptance. Closeout is a separate review.")
CLOSE_BOUNDARY = ("Close only this empty stopped phase as blocked and unqualified after exact historical "
                  "non-execution and fresh loaded-idle, empty current tracker evidence. Preserve original "
                  "requests, missing receipts, usage/gaps and expiry. No wake, Play, Resume or pilot acceptance.")
INFO = {"userMessage", "agentMessage", "plan", "reasoning", "webSearch"}
MAX_TURNS = 64
MAX_ITEMS = 512


def eligible(state):
    original, recovery = record.eligible(state, allow_record=True)
    run = state["meta"]["standardRun"]
    play = [c for c in state["commands"] if c.get("kind") == "standard_play" and
            c.get("payload", {}).get("runId") == run["id"]]
    require(len(play) == 1, "One exact original Play is required for historical coverage")
    note = play[0].get("notification") or {}
    require(note.get("status") == "accepted" and note.get("nativeDelivery") == "owned_turn_start" and
            note.get("brainId") == run["brainId"] and note.get("hostRunId") == run["id"] and
            isinstance(note.get("nativeTurnId"), str) and note["nativeTurnId"] and
            isinstance(note.get("hostBindingHash"), str) and len(note["hostBindingHash"]) == 64 and
            (note.get("nativeThreadObservation") or {}).get("streamStatus") in ("closed", "unconfirmed"),
            "Original Play identity/delivery/ended observer must be pinned; unknown delivery is not absence")
    # No native response claim, child observation or uncertain permission delivery
    # can be silently retired through the narrow non-execution closeout.
    require(not note.get("nativeApprovals") and
            (note.get("nativeThreadObservation") or {}).get("events") == [],
            "Historical approval intents or descendants need their own reconciliation")
    return original, recovery, play[0]


def inspection_context(registry, ledger, wake, controls):
    chain = getattr(controls, "host_chain", None)
    if chain is None:
        state, original, recovery, binding, scope, proof, retired = record.inspection_context(
            registry, ledger, wake, controls, allow_record=True)
        _, _, play = eligible(state)
        require(play["notification"]["hostBindingHash"] == recovery["notification"]["hostBindingHash"] and
                play["notification"]["nativeThreadObservation"]["streamStatus"] == "closed",
                "Preserved multi-host launch provenance is required; do not retry Play or recovery")
        return state, original, recovery, play, binding, scope, proof, retired, None
    state = record.saved_state(ledger)
    original, recovery, play = eligible(state)
    require(wake is not None and wake.orphan_recovery_idle() and not fence_exists(ledger.root),
            "Active observer, prompt or maintenance blocks historical inspection")
    with registry.tx() as db:
        require(record_in(db) is None, "Platform maintenance blocks historical inspection")
    binding = copy.deepcopy(wake.binding)
    scope = record._scope(registry, ledger.workspace_id, binding)
    require(scope["root"] == ledger.root and scope["brainId"] == state["meta"]["brainId"] and
            scope["ledgerRevision"] == state["meta"]["revision"] and scope["hostId"] == "local",
            "Registered project, brain or ledger changed")
    from .app_server_wake import NATIVE_APPROVAL_POLICY
    require(set(binding["brains"]) == {scope["brainId"]} and
            binding["brains"][scope["brainId"]].get("nativePolicy") == NATIVE_APPROVAL_POLICY,
            "One exact restricted brain binding required")
    retained_chain = historical_hosts.inspect(chain, binding, scope, (play, original, recovery), ledger.workspace_id)
    previous = next((h["binding"] for h in chain["hosts"] if
                    digest(h["binding"]) == recovery["notification"]["hostBindingHash"]), binding)
    if previous != binding:
        proof = continuity.proof(previous, binding, recovery, scope)
        retired = next(h["retiredHost"] for h in chain["hosts"] if h["binding"] == previous)
    else:
        proof = {"version": 1, "previousBinding": binding, "candidateBinding": binding,
                 **{k: scope[k] for k in ("ledgerIdentity", "catalogHash", "hostId")},
                 "projectLocationHash": scope["locationHash"]}
        retired = None
    return state, original, recovery, play, binding, scope, proof, retired, retained_chain


def availability(state):
    try:
        _, recovery, _ = eligible(state)
        return {"available": True, "recoveryId": recovery["id"], "reason": None}
    except (Refusal, KeyError, TypeError) as error:
        return {"available": False, "reason": str(error)}


def saved_view(ledger, state):
    """Saved evidence projection only: no host/log read and no fresh timestamp."""
    value = availability(state)
    run = state["meta"].get("standardRun") or {}
    rows = [c for c in state.get("commands", []) if c.get("kind") == KIND and
            c.get("payload", {}).get("runId") == run.get("id") and c.get("status") == "completed"]
    if rows and run.get("status") == "stopping":
        command = max(rows, key=lambda c:(c["createdAt"], c["id"]))
        with contextlib.closing(ledger.connect()) as db:
            snapshot = ledger.get(db, "snapshots", command["payload"]["recordHash"])
            retained(ledger, db, command, snapshot["request"])
        value["latestRecord"] = {"id":command["id"], "recordHash":command["payload"]["recordHash"],
                                 "at":snapshot["at"], "current":snapshot["preservedRun"] == run,
                                 "report":snapshot["request"]["evidence"]["report"]}
    return value


class HistoryProxy(record.MetadataProxy):
    """Only fixed metadata and cursor-linked full historical reads. No write permit."""
    def __init__(self, endpoint, scope):
        super().__init__(endpoint, scope)
        self.cursor = None
        self.pages = 0
        self.history_turns = set()
        self.item_cursors = {}
        self.item_pages = 0

    def _rpc(self, method, params):
        if method == "thread/turns/list" and params.get("itemsView") == "full":
            require(params == {"threadId": self.scope["brainId"], "cursor": self.cursor,
                               "limit": 1, "sortDirection": "desc", "itemsView": "full"} and
                    self.pages < MAX_TURNS*2, "Only exact bounded cursor-linked historical reads permitted")
            self.pages += 1
            page = ReadProxy._rpc(self, method, params)
            require(isinstance(page, dict) and "nextCursor" in page, "Historical pagination is unknown")
            self.cursor = page["nextCursor"]
            for turn in page.get("data", []):
                if isinstance(turn, dict) and isinstance(turn.get("id"), str):
                    self.history_turns.add(turn["id"])
            return page
        if method == "thread/items/list":
            turn = params.get("turnId")
            require(turn in self.history_turns and params == {
                "threadId": self.scope["brainId"], "turnId": turn,
                "cursor": self.item_cursors.get(turn), "limit": 64, "sortDirection": "asc"} and
                self.item_pages < MAX_ITEMS*2, "Only exact historical-turn item pagination permitted")
            self.item_pages += 1
            page = ReadProxy._rpc(self, method, params)
            require(isinstance(page, dict) and "nextCursor" in page, "Persisted item pagination is unknown")
            self.item_cursors[turn] = page["nextCursor"]
            return page
        return super()._rpc(method, params)


def persisted_items(proxy, brain, turn):
    """A second persisted view, not a load or a substitute for missing results."""
    proxy.item_cursors[turn] = None
    cursor, seen, result, entries = None, set(), [], []
    for _ in range(MAX_ITEMS//64+1):
        try:
            page = proxy._rpc("thread/items/list", {"threadId": brain, "turnId": turn,
                "cursor": cursor, "limit": 64, "sortDirection": "asc"})
        except Refusal as error:
            # Unsupported stores / read errors are unavailable, never empty.
            # No fallback thread load, command, discovery or RPC resend.
            # Once a page was observed, never discard it and fall back to a
            # smaller primary inventory: it may already contain contrary work.
            if result or cursor is not None:
                raise Refusal("Persisted item coverage interrupted; observed pages cannot be discarded") from error
            return None
        require(isinstance(page, dict) and isinstance(page.get("data"), list) and
                len(page["data"]) <= 64 and "nextCursor" in page, "Malformed persisted item history")
        for entry in page["data"]:
            require(isinstance(entry, dict) and entry.get("turnId") == turn and isinstance(entry.get("item"), dict),
                    "Persisted item belongs to another turn")
            item = entry["item"]
            ident = item.get("id")
            require(isinstance(ident, str) and 0 < len(ident) <= 200 and ident not in seen,
                    "Duplicate or unknown persisted item identity")
            seen.add(ident); result.append(item)
            entries.append(entry)
            require(len(result) <= MAX_ITEMS, "Persisted item bound exceeded; no truncation permitted")
        cursor = page["nextCursor"]
        if cursor is None: return {"items":result, "entriesHash":digest(entries)}
        require(page["data"] and isinstance(cursor, str) and 0 < len(cursor) <= 4096 and
                cursor not in seen, "Persisted item pagination is stalled or unknown")
        seen.add(cursor)
    raise Refusal("Persisted item pagination exceeds its bound")


def native_history(proxy, brain, first, last):
    turns, effects, gaps, ids, cursors = [], [], [], set(), set()
    cursor = None
    proxy.cursor = None
    for _ in range(MAX_TURNS):
        page = proxy._rpc("thread/turns/list", {"threadId": brain, "cursor": cursor,
             "limit": 1, "sortDirection": "desc", "itemsView": "full"})
        require(isinstance(page, dict) and isinstance(page.get("data"), list) and len(page["data"]) == 1 and
                "nextCursor" in page, "Exact historical turn coverage is missing or truncated")
        turn = page["data"][0]
        require(isinstance(turn, dict) and isinstance(turn.get("id"), str) and 0 < len(turn["id"]) <= 200 and turn["id"] not in ids and
                turn.get("status") in ("completed", "failed", "interrupted") and
                turn.get("itemsView") == "full" and
                isinstance(turn.get("items"), list) and len(turn["items"]) <= MAX_ITEMS,
                "Unknown, active, duplicated or incomplete historical turn")
        require(turns or turn["id"] == last, "A later native turn prevents historical reconciliation")
        ids.add(turn["id"])
        completion = turn.get("completedAt")
        if not (record.receipt.finite(completion) and 0 < completion <= time.time()):
            completion = None
            gaps.append("historical_turn_completion_unknown:"+turn["id"])
        paged = persisted_items(proxy, brain, turn["id"])
        items = turn["items"]
        if paged is not None:
            original_items = {i.get("id"): i for i in items if isinstance(i, dict)}
            paged_map = {i["id"]: i for i in paged["items"]}
            require(len(original_items) == len(items) and
                    all(ident in paged_map and original_items[ident] == paged_map[ident] for ident in original_items),
                    "Independent persisted item views conflict or omit a known item")
            items = paged["items"]
        turns.append({"id": turn["id"], "status": turn["status"], "completedAt": completion,
                      "itemsHash": digest(turn["items"]), "itemCount": len(turn["items"])})
        turns[-1].update(persistedItemsHash=paged["entriesHash"] if paged is not None else None,
                         persistedItemsCoverage="observed" if paged is not None else "unavailable")
        item_ids = set()
        for item in items:
            require(isinstance(item, dict) and isinstance(item.get("id"), str) and 0 < len(item["id"]) <= 200 and
                    item["id"] not in item_ids, "Historical item identity is missing or duplicated")
            item_ids.add(item["id"])
            if item.get("type") in INFO:
                continue
            require(not any(e["id"] == item["id"] for e in effects), "Historical effect ID reused across turns")
            status = item.get("status") if item.get("status") in ("completed", "failed", "declined", "inProgress") else "unknown"
            command = item.get("command")
            effect = {"turnId": turn["id"], "id": item["id"],
                      "type": item.get("type") if item.get("type") in ("commandExecution", "fileChange", "mcpToolCall", "dynamicToolCall", "collabAgentToolCall") else "unsupported",
                      "status": status, "itemHash": digest(item), "commandHash": digest(command),
                      "cwdHash": digest(item.get("cwd")), "exitCode": item.get("exitCode") if type(item.get("exitCode")) is int else None,
                      "outcome": "unknown", "terminalCoverage": "unknown"}
            if item.get("type") == "commandExecution" and isinstance(command, str) and command:
                if status == "declined" and item.get("exitCode") is None:
                    effect.update(outcome="not_executed", terminalCoverage="native_declined")
                elif status in ("completed", "failed") and type(item.get("exitCode")) is int:
                    effect["outcome"] = "executed"  # NOT cleanup proof or permission evidence.
            if effect["outcome"] == "unknown": gaps.append("unknown_effect:"+item["id"])
            if effect["terminalCoverage"] == "unknown": gaps.append("historical_terminal_unknown:"+item["id"])
            effects.append(effect)
            require(len(effects) <= MAX_ITEMS, "Historical effect inventory exceeds its bound")
        if turn["id"] == first:
            return {"turns": list(reversed(turns)), "effects": list(reversed(effects)), "gaps": sorted(set(gaps))}
        cursor = page["nextCursor"]
        require(isinstance(cursor, str) and 0 < len(cursor) <= 4096 and cursor not in cursors,
                "Historical Play boundary is absent; no absence or non-execution can be inferred")
        cursors.add(cursor)
    raise Refusal("Historical turn range exceeds its bound; coverage remains unknown")


def rollout_inventory(ledger, scope, turns, effects=()):
    """Exact configured session only; hash bodies but never retain or expose them."""
    home = config(ledger).get("codexHome")
    require(isinstance(home, str) and Path(home).is_absolute(), "Configured local effect inventory is unavailable")
    paths = candidates(Path(home), scope["brainId"])
    require(len(paths) == 1, "Missing or segmented historical inventory remains unknown")
    calls, results, completed_items, seen, current, gaps, file_hash = [], [], [], [], None, [], hashlib.sha256()
    wanted = [t["id"] for t in turns]
    native_effects = {(e["turnId"], e["id"]): e for e in effects}
    with open_regular(paths[0]) as stream:
        before = os.fstat(stream.fileno())
        require(before.st_size <= 32*1024*1024, "Historical inventory exceeds its byte bound")
        header = decode(stream.readline(65537))
        require(isinstance(header, dict) and isinstance(header.get("payload"), dict) and
                header.get("type") == "session_meta" and header.get("payload", {}).get("id") == scope["brainId"] and
                header["payload"].get("cwd") == scope["cwd"] and not header["payload"].get("forked_from_id"),
                "Historical log identity, checkout or lineage changed")
        stream.seek(0)
        consumed = 0
        for line in stream:
            consumed += len(line)
            require(len(line) <= 16*1024*1024, "Historical inventory line exceeds its bound")
            require(consumed <= 32*1024*1024, "Historical inventory grew beyond its bound")
            file_hash.update(line)
            row = decode(line)
            require(isinstance(row, dict), "Malformed historical inventory")
            payload = row.get("payload") or {}
            require(isinstance(payload, dict), "Malformed historical inventory payload")
            if row.get("type") == "turn_context":
                current = payload.get("turn_id")
                if current in wanted:
                    require(payload.get("cwd") == scope["cwd"] and (current not in seen or current == seen[-1]),
                            "Ambiguous historical turn inventory")
                    if current in seen: gaps.append("repeated_historical_turn_context")
                    else: seen.append(current)
                elif seen:
                    gaps.append("unlisted_historical_turn_context")
            if current not in wanted: continue
            if row.get("type") == "compacted": gaps.append("compacted_effect_inventory")
            if row.get("type") == "event_msg":
                # Nested Code Mode execution may have its own completed item,
                # outside the outer tool-call result. Never ignore that axis.
                if payload.get("type") == "item_completed":
                    item = payload.get("item")
                    require(isinstance(item, dict), "Malformed completed native item inventory")
                    if item.get("type") == "ContextCompaction": gaps.append("compacted_effect_inventory")
                    elif item.get("type") not in ("UserMessage", "AgentMessage", "Reasoning", "Plan", "WebSearch"):
                        ident = item.get("id")
                        require(isinstance(ident, str) and 0 < len(ident) <= 200 and
                                payload.get("thread_id") == scope["brainId"] and payload.get("turn_id") == current,
                                "Ambiguous completed native effect inventory")
                        native = native_effects.get((current, ident))
                        status = item.get("status")
                        normalized = status[:1].lower()+status[1:] if isinstance(status, str) else None
                        matches = (item.get("type") == "CommandExecution" and native and
                                   normalized == native["status"] and
                                   item.get("exit_code") == native["exitCode"] and
                                   digest(item.get("command")) == native["commandHash"] and
                                   digest(item.get("cwd")) == native["cwdHash"])
                        completed_items.append({"turnId":current, "id":ident, "itemHash":digest(item), "matchesNative":bool(matches)})
                        require(len(completed_items) <= MAX_ITEMS, "Completed item inventory exceeds its bound")
                        require(sum(i["turnId"] == current and i["id"] == ident for i in completed_items) == 1,
                                "Duplicate native completion in rollout inventory")
                        if not matches:
                            gaps.append("additional_native_effect:"+ident)
                elif payload.get("type") not in ("token_count", "thread_settings_applied", "task_started", "task_complete",
                                                  "agent_message", "agent_reasoning", "user_message"):
                    gaps.append("unsupported_native_event")
            elif row.get("type") not in ("turn_context", "response_item", "compacted", "session_meta"):
                gaps.append("unsupported_rollout_record")
            if row.get("type") != "response_item": continue
            kind = payload.get("type")
            if kind in ("function_call", "custom_tool_call", "local_shell_call"):
                ident, name = payload.get("call_id", payload.get("id")), payload.get("name")
                require(isinstance(ident, str) and 0 < len(ident) <= 200 and not any(c["id"] == ident for c in calls),
                        "Ambiguous historical call identity")
                command = None
                if kind in ("function_call", "custom_tool_call") and name in ("exec_command", "functions.exec_command"):
                    args = decode(payload.get("arguments" if kind == "function_call" else "input", "{}"))
                    if isinstance(args, dict) and isinstance(args.get("cmd"), str): command = args["cmd"]
                calls.append({"turnId": current, "id": ident, "callHash": digest(payload),
                              "commandHash": digest(command) if command else None})
                require(len(calls) <= MAX_ITEMS, "Historical call inventory exceeds its bound")
            elif kind in ("function_call_output", "custom_tool_call_output"):
                ident = payload.get("call_id")
                require(isinstance(ident, str) and 0 < len(ident) <= 200 and
                        any(c["turnId"] == current and c["id"] == ident for c in calls) and
                        not any(r["id"] == ident for r in results), "Orphaned, reordered or duplicate historical call result")
                # Opaque output and model prose cannot attest a native decision.
                # Keep only its exact association and body hash, never parse or
                # execute Code Mode programs or infer cleanup from exit code.
                results.append({"turnId": current, "id":ident, "resultHash":digest(payload)})
            elif kind not in ("message", "reasoning", "function_call_output", "custom_tool_call_output",
                               "web_search_call"):
                gaps.append("unsupported_rollout_item")
        require(file_identity(before) == file_identity(os.fstat(stream.fileno())) == file_identity(paths[0].stat()),
                "Historical inventory changed during read")
    require(seen == wanted, "Historical log turn coverage is incomplete or reordered")
    return {"fileHash": file_hash.hexdigest(), "turnIds": seen, "calls": calls, "results": results,
            "completedItems":completed_items, "gaps": sorted(set(gaps))}


def cross_check(history, inventory):
    gaps = history["gaps"] + inventory["gaps"]
    native = {(e["turnId"], e["id"]): e for e in history["effects"]}
    local = {(c["turnId"], c["id"]): c for c in inventory["calls"]}
    nested = {(e["turnId"], e["id"]):e for e in inventory.get("completedItems", [])}
    outputs = {(r["turnId"], r["id"]):r for r in inventory.get("results", [])}
    for key in native.keys() | local.keys():
        e, c = native.get(key), local.get(key)
        linked_nested = not c and nested.get(key, {}).get("matchesNative")
        linked_call = e and c and c["commandHash"] is not None and c["commandHash"] == e["commandHash"]
        if not (linked_nested or linked_call):
            gaps.append("unmatched_effect:"+key[1])
        if "results" in inventory and c and key not in outputs and not (linked_call and e["outcome"] == "not_executed"):
            gaps.append("missing_call_result:"+key[1])
    report = {"version": 2 if "results" in inventory else 1, "native": history, "inventory": inventory, "gaps": sorted(set(gaps)),
            "effectOutcome": "unknown" if gaps else "not_executed",
            "historicalTerminalCoverage": "unknown" if gaps else "native_non_execution",
            "taskTreeComplete": False}
    if report["version"] == 2:
        report["missingEvidence"] = missing_evidence(report["gaps"], history, inventory)
    return report


def missing_evidence(gaps, history, inventory):
    ids = {e["id"]:e["turnId"] for e in history["effects"]}
    ids.update({c["id"]:c["turnId"] for c in inventory["calls"]})
    needs = {"missing_call_result":"saved_call_result", "unmatched_effect":"typed_effect_link",
             "unknown_effect":"conclusive_native_result", "additional_native_effect":"conclusive_native_result",
             "historical_terminal_unknown":"historical_terminal_cleanup", "historical_turn_completion_unknown":"turn_completion_time"}
    return [{"id":gap.partition(":")[2] or None,
             "turnId":gap.partition(":")[2] if gap.startswith("historical_turn_completion_unknown:") else ids.get(gap.partition(":")[2]),
             "need":needs.get(gap.partition(":")[0], "complete_historical_inventory")} for gap in gaps]


def inspect(registry, ledger, wake, controls, *, closing=False):
    state, original, recovery, play, binding, scope, proof, retired, chain = inspection_context(
        registry, ledger, wake, controls)
    with HistoryProxy(binding["endpoint"], scope) as proxy:
        before = observe(proxy, scope, recovery["notification"]["nativeTurnId"],
                         require_loaded=closing, allow_unloaded=not closing)
        require(before["status"] == "completed", "The exact recovery must remain completed")
        first = native_history(proxy, scope["brainId"], play["notification"]["nativeTurnId"], before["turnId"])
        inventory = rollout_inventory(ledger, scope, first["turns"], first["effects"])
        second = native_history(proxy, scope["brainId"], play["notification"]["nativeTurnId"], before["turnId"])
        require(original["notification"]["nativeTurnId"] in [t["id"] for t in first["turns"]],
                "Original Pause is absent from historical coverage")
        require(first == second and inventory == rollout_inventory(ledger, scope, second["turns"], second["effects"]),
                "Historical effect evidence changed during inspection")
        after = observe(proxy, scope, before["turnId"], require_loaded=closing, allow_unloaded=not closing)
        require({k:v for k,v in before.items() if k != "observedAt"} ==
                {k:v for k,v in after.items() if k != "observedAt"}, "Native activity changed during historical reads")
    validate_endpoint(binding["endpoint"])
    membership(registry, ledger, binding, scope)
    require(wake.binding == binding and wake.orphan_recovery_idle() and
            record.context(record.saved_state(ledger)) == record.context(state), "Project or host changed")
    if chain:
        require(chain == historical_hosts.inspect(controls.host_chain, binding, scope, (play, original, recovery), ledger.workspace_id),
                "Historical host provenance changed during inspection")
    elif retired:
        require(controls.prior_binding == proof["previousBinding"] and controls.retired_host == retired,
                "Reviewed host continuity changed")
        continuity.retirement(retired, proof["previousBinding"])
    report = cross_check(first, inventory)
    require(len(canonical(report).encode()) <= 20000, "Historical report exceeds the signed review bound; coverage is not truncated")
    if closing:
        require(report["effectOutcome"] == "not_executed" and not report["gaps"],
                "Historical effects or terminal outcomes remain unknown; closeout is refused")
    return {"contextHash": record.context(state), "runHash": digest(state["meta"]["standardRun"]),
            "pauseHash": digest(original), "recoveryHash": digest(recovery), "playHash": digest(play),
            "bindingHash": digest(binding), "scopeHash": digest({k: str(v) for k,v in scope.items()}),
            "observation": after, "report": report,
            "hostContinuity": continuity.for_browser(proof), "retiredHost": retired,
            **({"hostChain": chain} if chain else {})}


def latest_record(ledger, db, state):
    run = state["meta"]["standardRun"]
    rows = [c for c in state["commands"] if c.get("kind") == KIND and c.get("status") == "completed" and
            c.get("payload", {}).get("runId") == run["id"]]
    require(rows, "Retain the historical reconciliation record before terminal closeout")
    command = max(rows, key=lambda c:(c["createdAt"], c["id"]))
    snapshot = ledger.get(db, "snapshots", command["payload"]["recordHash"])
    require(digest(snapshot) == command["payload"]["recordHash"] and snapshot["preservedRun"] == run,
            "Historical reconciliation record is unavailable or run changed")
    require(not snapshot["request"]["evidence"]["report"]["gaps"] and
            snapshot["request"]["evidence"]["report"]["effectOutcome"] == "not_executed",
            "Historical effects remain unknown; inspect the exact missing evidence, never replay it")
    return command, snapshot


def close_available(ledger, state):
    try:
        eligible(state)
        from .phase_closeout import stop_basis
        stop_basis(state["meta"]["standardRun"])
        with contextlib.closing(ledger.connect()) as db: latest_record(ledger, db, state)
        return {"available": True, "reason": None}
    except (Refusal, KeyError, TypeError) as error:
        return {"available": False, "reason": str(error)}


def retained(ledger, db, command, request):
    kind = CLOSE_KIND if request.get("closing") else KIND
    require(command.get("kind") == kind and command.get("status") == "completed" and
            command.get("payload", {}).get("requestHash") == digest(request), "Reconciliation ID reused")
    snapshot = ledger.get(db, "snapshots", command["payload"]["recordHash"])
    require(digest(snapshot) == command["payload"]["recordHash"] and snapshot.get("request") == request and
            snapshot.get("qualification") == "unqualified" and snapshot.get("outcome") == "blocked" and
            snapshot.get("boundary") == (CLOSE_BOUNDARY if request["closing"] else BOUNDARY),
            "Historical record integrity changed; nothing will be resent")
    return command


def confirm(registry, ledger, request, fresh, expires_at):
    exact(request, {"id", "expectedRevision", "recoveryId", "closing", "reconciliationHash", "evidence"})
    require(type(request["closing"]) is bool, "Closeout must be separately reviewed")
    with registry.tx() as registry_db, ledger.tx() as db:
        old = db.execute("SELECT data FROM commands WHERE id=?", (request["id"],)).fetchone()
        if old: return retained(ledger, db, json.loads(old[0]), request)
        require(record_in(registry_db) is None and not fence_exists(ledger.root), "Maintenance blocks reconciliation")
        state = record.state_in(ledger, db)
        original, recovery, play = eligible(state)
        evidence = request["evidence"]
        exact(evidence, {"contextHash", "runHash", "pauseHash", "recoveryHash", "playHash", "bindingHash",
                         "scopeHash", "observation", "report", "hostContinuity", "retiredHost"} |
                         ({"hostChain"} if "hostChain" in evidence else set()))
        record.same_evidence(evidence, fresh)
        require(state["meta"]["revision"] == request["expectedRevision"] and
                record.context(state) == evidence["contextHash"] and recovery["id"] == request["recoveryId"] and
                digest(original) == evidence["pauseHash"] and digest(recovery) == evidence["recoveryHash"] and
                digest(play) == evidence["playHash"] and digest(state["meta"]["standardRun"]) == evidence["runHash"],
                "Original records, usage, expiry or ownership changed; review again")
        proof = continuity.from_browser(evidence["hostContinuity"])
        from .pause_host_continuity import check_catalog
        check_catalog(ledger, proof)
        validate_endpoint(proof["candidateBinding"]["endpoint"])
        require(digest(proof["candidateBinding"]) == evidence["bindingHash"] and
                digest(proof["previousBinding"]) == recovery["notification"]["hostBindingHash"] and
                proof["previousBinding"]["brains"] == proof["candidateBinding"]["brains"], "Exact host continuity required")
        if evidence["retiredHost"]: continuity.retirement(evidence["retiredHost"], proof["previousBinding"])
        else: require(proof["candidateBinding"] == proof["previousBinding"], "Reviewed original-host retirement required")
        if "hostChain" in evidence:
            historical_hosts.check_retained(evidence["hostChain"], proof, (play, original, recovery), ledger)
        else:
            require(play["notification"]["hostBindingHash"] == recovery["notification"]["hostBindingHash"] and
                    play["notification"]["nativeThreadObservation"]["streamStatus"] == "closed",
                    "Exact multi-host provenance is required")
        observed, report_value = fresh["observation"], fresh["report"]
        require(observed["turnId"] == recovery["notification"]["nativeTurnId"] and observed["status"] == "completed" and
                record.receipt.finite(observed["observedAt"]) and 0 <= time.time()-observed["observedAt"] <= 300 and
                record.receipt.finite(expires_at) and time.time() <= expires_at, "Exact historical review expired")
        require(cross_check(report_value["native"], report_value["inventory"]) == report_value,
                "Historical report integrity changed")
        if request["closing"]:
            from .phase_closeout import stop_basis
            stop_basis(state["meta"]["standardRun"])
            _, prior = latest_record(ledger, db, state)
            require(len(state["meta"].get("historicalEffectClosures", [])) < 128,
                    "Historical closure retention limit reached; nothing was discarded")
            require(digest(prior) == request["reconciliationHash"] and
                    prior["request"]["evidence"]["report"] == report_value and
                    prior["request"]["evidence"]["bindingHash"] == evidence["bindingHash"] and
                    prior["request"]["evidence"]["hostContinuity"] == evidence["hostContinuity"] and
                    prior["request"]["evidence"].get("hostChain") == evidence.get("hostChain") and
                    not report_value["gaps"] and report_value["effectOutcome"] == "not_executed" and
                    observed["activity"] == "idle" and type(observed["trackedTerminals"]) is int and
                    observed["trackedTerminals"] == 0 and observed["terminalCoverage"] == "observed_current_host",
                    "Fresh known historical non-execution and loaded-idle complete empty tracker required")
        else: require(request["reconciliationHash"] is None, "A reconciliation cannot close the phase")
        now, kind = time.time(), CLOSE_KIND if request["closing"] else KIND
        snapshot = {"version": 1, "request": copy.deepcopy(request), "confirmationEvidence": copy.deepcopy(fresh),
                    "at": now, "outcome": "blocked", "qualification": "unqualified",
                    "originalPause": original, "exhaustedRecovery": recovery, "originalPlay": play,
                    "preservedRun": copy.deepcopy(state["meta"]["standardRun"]),
                    "boundary": CLOSE_BOUNDARY if request["closing"] else BOUNDARY}
        key = digest(snapshot)
        db.execute("INSERT INTO snapshots VALUES (?,?,?)", (key, kind, canonical(snapshot)))
        command = {"id": request["id"], "kind": kind, "actor": "assistant_owner_confirmed", "status": "completed",
                   "createdAt": now, "completedAt": now,
                   "payload": {"runId": state["meta"]["standardRun"]["id"], "recoveryId": recovery["id"],
                               "requestHash": digest(request), "recordHash": key},
                   "result": ("Phase closed as blocked and unqualified. Next: Help me continue development prepares a successor; Review and Play remain separate."
                              if request["closing"] else "Historical evidence recorded. "+
                              ("Unknown effects or terminals still block closeout. No request was replayed."
                               if report_value["gaps"] else "Historical non-execution is reconciled; review terminal closeout separately."))}
        ledger.put(db, "commands", command["id"], command)
        if request["closing"]:
            meta, run = state["meta"], state["meta"]["standardRun"]
            from .standard import save
            run["ownerCloseout"] = {"requestId": command["id"], "at": now, "outcome": "blocked",
                "qualification": "unqualified", "recordHash": key, "originalExpiresAt": run["expiresAt"],
                "previousCheckpoint": copy.deepcopy(run.get("checkpoint")), "boundary": CLOSE_BOUNDARY}
            run["status"] = "blocked"  # No fabricated brain checkpoint; preserve it verbatim.
            meta.setdefault("historicalEffectClosures", []).append({"requestId": command["id"], "recordHash": key})
            save(ledger, db, meta, run, "terminal_closeout")
        ledger.event(db, kind, {"id": command["id"], "recordHash": key})
        return command


def historical_ids(ledger, db):
    """Validated sidecar retirement, not a forged receipt or edit of an old request."""
    meta, result = ledger.get(db, "meta", 1), set()
    entries = meta.get("historicalEffectClosures") or []
    require(isinstance(entries, list) and len(entries) <= 128, "Historical closure inventory is invalid")
    for entry in entries:
        exact(entry, {"requestId", "recordHash"})
        command = ledger.get(db, "commands", entry["requestId"])
        snapshot = ledger.get(db, "snapshots", entry["recordHash"])
        retained(ledger, db, command, snapshot["request"])
        require(command["kind"] == CLOSE_KIND and command["payload"]["recordHash"] == entry["recordHash"] and
                snapshot["request"]["closing"] is True and
                snapshot["request"]["evidence"]["report"]["effectOutcome"] == "not_executed" and
                not snapshot["request"]["evidence"]["report"]["gaps"], "Historical closure integrity changed")
        for key in ("originalPause", "exhaustedRecovery"):
            old = snapshot[key]
            require(ledger.get(db, "commands", old["id"]) == old, "Historical original request changed")
            result.add(old["id"])
    return result


def closed_run(ledger, db, run):
    """An exact validated owner closeout permits future catalog preparation only."""
    close = run.get("ownerCloseout") or {}
    entries = ledger.get(db, "meta", 1).get("historicalEffectClosures") or []
    match = [e for e in entries if e.get("requestId") == close.get("requestId")]
    if not match: return False
    historical_ids(ledger, db)
    command = ledger.get(db, "commands", close["requestId"])
    require(run["status"] == "blocked" and command["payload"]["runId"] == run["id"] and
            close.get("recordHash") == match[0]["recordHash"], "Historical closed-run identity changed")
    return True
