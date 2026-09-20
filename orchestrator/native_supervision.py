"""Brain-supplied native wait/limit observations; no polling loop or transport."""
from . import native_limits
from .admission import exact, identifier, sha, timestamp
from .core import digest, require
from .native_lifecycle import NativeLifecycle

KIND = "native_wait_observation"


def normalize_wait(result, observed_at, host_id, thread_id):
    """Accept one exact target's tool response; drop all conversational content."""
    timestamp(observed_at); source_hash = native_limits.bounded(result)
    require(isinstance(result, dict), "Native wait result must be an object")
    polls = result.get("polls", [])
    require(isinstance(polls, list) and len(polls) <= 1, "Single-target wait result required")
    issues = []; status = "unknown"; cursor = None; revision = None; turn = None
    if result.get("errors") or result.get("error") or result.get("isError"):
        issues.append("native_tool_error")
    if len(polls) != 1: issues.append("target_observation_missing")
    else:
        poll = polls[0]
        require(isinstance(poll, dict) and isinstance(poll.get("thread"), dict), "Native poll identity required")
        thread = poll["thread"]
        require(thread.get("id") == thread_id and thread.get("hostId") == host_id, "Native poll belongs to another task or host")
        if poll.get("schemaVersion") != 1 or type(poll.get("schemaVersion")) is not int:
            issues.append("unsupported_poll_schema")
        else:
            status_value = thread.get("status")
            status = status_value.get("type", "unknown") if isinstance(status_value, dict) else "unknown"
            if status not in ("active", "idle", "notLoaded", "systemError"):
                status = "unknown"; issues.append("unsupported_native_status")
            flags = status_value.get("activeFlags") if isinstance(status_value, dict) else None
            if status == "idle" and flags: issues.append("idle_with_active_flags")
            if status in ("notLoaded", "systemError"): issues.append("native_"+status)
            if isinstance(poll.get("cursor"), str) and 0 < len(poll["cursor"]) <= 256: cursor = poll["cursor"]
            if type(poll.get("revision")) is int and 0 <= poll["revision"] <= 1_000_000_000: revision = poll["revision"]
            latest = poll.get("latestTurn")
            if isinstance(latest, dict):
                tid = latest.get("id"); tstatus = latest.get("status")
                identifier(tid)
                turn = {"id": tid, "status": tstatus if tstatus in ("inProgress", "completed", "failed", "interrupted") else "unknown"}
                if status == "idle" and turn["status"] in ("inProgress", "unknown"):
                    issues.append("turn_activity_conflict")
    activity = ("running" if status == "active" else "idle" if status == "idle" else "unknown") if not issues else "unknown"
    return {"kind": KIND, "schemaVersion": 1, "observedAt": observed_at, "sourceHash": source_hash,
            "hostId": host_id, "threadId": thread_id, "nativeStatus": status, "activity": activity,
            "cursor": cursor, "revision": revision, "latestTurn": turn, "issues": sorted(set(issues)),
            "descendantsComplete": False, "taskUsageAvailable": False}


def validate_source(source, observation):
    exact(source, {"kind", "schemaVersion", "observedAt", "sourceHash", "hostId", "threadId", "nativeStatus",
                   "activity", "cursor", "revision", "latestTurn", "issues", "descendantsComplete", "taskUsageAvailable"})
    native_limits.bounded(source, 4000); sha(source["sourceHash"])
    require(source["kind"] == KIND and source["schemaVersion"] == 1 and
            source["descendantsComplete"] is False and source["taskUsageAvailable"] is False and
            observation["outcome"] == "confirmed" and digest(source) == observation["evidenceHash"] and
            all(source[k] == observation[k] for k in ("hostId", "threadId", "observedAt", "activity")),
            "Native observation provenance does not match its lifecycle binding")


class NativeSupervision:
    def __init__(self, bridge):
        self.bridge, self.ledger, self.store = bridge, bridge.ledger, bridge.store
        self.lifecycle = NativeLifecycle(bridge)

    def plan(self, token, worker_id):
        with self.bridge.locked(token) as (db, _):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel:
                claim, record, state = self.lifecycle.state_in(kernel, intent)
            creation = state["creation"]
            require(creation and creation["outcome"] == "confirmed" and creation["hostId"] == "local" and creation["threadId"],
                    "Exact confirmed local task required; pending client IDs cannot be observed as tasks")
            target = {"hostId": creation["hostId"], "threadId": creation["threadId"]}
            source = record.get("source")
            if source and source.get("cursor"): target["afterCursor"] = source["cursor"]
            return {"workerId": worker_id, "expectedHash": claim["nativeLifecycleHash"],
                    "tool": "wait_threads", "arguments": {"targets": [target], "timeoutMs": 0},
                    "nativeCallMade": False, "executionAuthorized": False, "descendantsComplete": False}

    def record(self, token, worker_id, request):
        exact(request, {"id", "expectedHash", "observedAt", "result"})
        identifier(request["id"]); sha(request["expectedHash"]); timestamp(request["observedAt"])
        with self.bridge.locked(token) as (db, _):
            _, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel:
                # Derive IDs from the immutable expected record, not mutable
                # current IDs: historical replay must reproduce the exact request.
                self.bridge.owned_claim_in(kernel, intent)
                prior = self.lifecycle.record_in(kernel, request["expectedHash"], intent)
            creation = prior["state"]["creation"]
            require(creation and creation["outcome"] == "confirmed" and creation["hostId"] == "local" and creation["threadId"],
                    "Confirmed local native binding required for supervision")
        source = normalize_wait(request["result"], request["observedAt"], creation["hostId"], creation["threadId"])
        observation = {"id": "supervision-"+digest({"id": request["id"], "workerId": worker_id}),
                       "expectedHash": request["expectedHash"], "outcome": "confirmed",
                       **{k: creation[k] for k in ("hostId", "threadId", "clientThreadId")},
                       "observedAt": request["observedAt"], "activity": source["activity"], "evidenceHash": digest(source)}
        return self.lifecycle.observe(token, worker_id, observation, source=source)

    def state(self, token, worker_id):
        with self.bridge.locked(token) as (db, _):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel:
                claim, record, state = self.lifecycle.state_in(kernel, intent)
                policy = self.store.get(kernel, "meta", 1)["policy"]
            observed = state["creation"]
            fresh = bool(observed and 0 <= self.store.clock()-observed["observedAt"] <= policy["maxObservationAgeSeconds"])
            return {"workerId": worker_id, "expectedHash": claim.get("nativeLifecycleHash"),
                    "attachedHash": worker.get("nativeLifecycleHash"), "fresh": fresh,
                    "activity": observed["activity"] if fresh else "unknown", "observation": observed,
                    "source": record.get("source") if record else None, "descendantsComplete": False,
                    "taskUsageAvailable": False, "ownershipReleased": False, "executionAuthorized": False}

    def account_record(self, token, request):
        with self.bridge.locked(token):
            with self.store.tx() as kernel:
                receipt = native_limits.retain(self.store, kernel, self.bridge.workspace_id, self.bridge.ledger_id, request)
                return {**receipt, "current": native_limits.status(self.store, kernel),
                        "executionAuthorized": False, "nativeCallMade": False}

    def account_state(self, token):
        with self.bridge.locked(token):
            with self.store.tx() as kernel: return native_limits.status(self.store, kernel)
