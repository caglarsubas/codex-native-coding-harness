"""Explicit, read-only cleanup evidence collection and source qualification.

The documented app-server source supplies persisted effects and a loaded thread's
current tracked terminals, NOT historical OS lifecycle/descendant coverage. This
collector does not turn those observations into cleanup or a disposition permit.
There is deliberately no supplied-attestation, load, kill, wake or ledger-write path.
"""
import copy
import os
from pathlib import Path
import stat
import time

from .admission import exact
from .core import Refusal, canonical, digest, require
from .native_read_client import NativeReadFailure, ReadProxy, decode, file_identity, validate_endpoint
from .native_project_assignment import _native_identity
from . import historical_effects as history

KIND = "historical_cleanup_collection_v1"
MAX_TERMINALS = 512
MAX_REPORT_BYTES = 65536  # Private operator output, not a signed HTTP preview.
BOUNDARY = {
    "nativeMutationMade": False, "ledgerMutationMade": False,
    "processTreeCleanupVerified": False, "ownershipReleased": False,
    "executionAuthorized": False, "pilotAccepted": False,
}
PROCESS_FIELDS = ("processId", "osPid", "parentProcessId", "processStartTime",
                  "startedAt", "completedAt", "descendants", "descendantCoverage")


def read_request(path):
    from .observations import read_regular
    path = Path(path).absolute()
    before = path.lstat()
    require(str(path.resolve(strict=True)) == str(path) and before.st_uid == os.getuid() and
            before.st_nlink == 1 and not before.st_mode & 0o077 and stat.S_ISREG(before.st_mode),
            "Cleanup request must be one canonical private regular owner file")
    raw = read_regular(path, path.parent, 16000)
    require(file_identity(before) == file_identity(path.lstat()), "Cleanup request changed while reading")
    return decode(raw)


def _pins(context):
    state, pause, recovery, play, binding, scope, _, _, chain = context
    return {"version": 1, "workspaceId": binding["brains"][scope["brainId"]]["workspaceId"],
            "brainId": scope["brainId"], "runId": state["meta"]["standardRun"]["id"],
            "expectedRevision": state["meta"]["revision"], "contextHash": history.record.context(state),
            "runHash": digest(state["meta"]["standardRun"]),
            "originalCommandHashes": {"play": digest(play), "pause": digest(pause), "recovery": digest(recovery)},
            "bindingHash": digest(binding), "scopeHash": digest({k: str(v) for k, v in scope.items()}),
            "hostChainHash": digest(chain)}


def plan(registry, ledger, wake, controls):
    """Existing identity/ownership/provenance only. No connection or confirmation."""
    return _pins(history.inspection_context(registry, ledger, wake, controls))


def item_projection(turn_id, item):
    require(isinstance(item, dict) and isinstance(item.get("id"), str) and
            0 < len(item["id"]) <= 200, "Unknown cleanup effect identity")
    # A native process handle is not an OS PID; even an osPid is not birth proof.
    handle = item.get("processId")
    pid = item.get("osPid")
    return {"turnId": turn_id, "itemId": item["id"], "itemHash": digest(item),
            "nativeHandleHash": digest(handle) if isinstance(handle, str) and 0 < len(handle) <= 200 else None,
            "osPidHash": digest(pid) if type(pid) is int and pid > 0 else None,
            "fieldTypes": {key: type(item.get(key)).__name__ for key in PROCESS_FIELDS},
            "historicalCleanup": "unknown"}


class CleanupProxy(history.HistoryProxy):
    """Fixed historical reads plus complete exact-brain current terminal pages."""
    def __init__(self, endpoint, scope):
        super().__init__(endpoint, scope)
        self.terminal_cursor = None
        self.terminal_pages = 0
        self.fields = {}
        self.sources = []

    def _rpc(self, method, params):
        if method == "thread/backgroundTerminals/list":
            require(params == {"threadId": self.scope["brainId"], "cursor": self.terminal_cursor,
                               "limit": 64} and self.terminal_pages < 16,
                    "Only bounded exact-brain cursor-linked terminal reads permitted")
            self.terminal_pages += 1
            value = ReadProxy._rpc(self, method, params)
            require(isinstance(value, dict) and "nextCursor" in value, "Terminal cursor unavailable")
            self.terminal_cursor = value["nextCursor"]
        else:
            value = super()._rpc(method, params)
        self.sources.append({"method": method, "paramsHash": digest(params),
                             "responseHash": digest(value), "observedAt": time.time()})
        require(len(self.sources) <= 128, "Cleanup source query bound exceeded")
        views = []
        if method == "thread/turns/list" and params.get("itemsView") == "full":
            for turn in value.get("data", []):
                views.extend((turn["id"], item, "full_turn") for item in turn.get("items", []))
        elif method == "thread/items/list":
            views.extend((entry["turnId"], entry["item"], "persisted_item") for entry in value.get("data", []))
        for turn, item, view in views:
            if item.get("type") in history.INFO:
                continue
            projection = item_projection(turn, item)
            key = (turn, item["id"], view)
            require(key not in self.fields or self.fields[key] == projection,
                    "Effect process metadata changed between independent reads")
            self.fields[key] = projection
            require(len(self.fields) <= history.MAX_ITEMS * 2, "Cleanup effect metadata bound exceeded")
        return value


def terminals(proxy, brain):
    """Complete current returned inventory. It never claims historical coverage."""
    proxy.terminal_cursor = None
    cursor, cursors, handles, items, rows = None, set(), set(), set(), []
    for _ in range(8):
        try:
            page = proxy._rpc("thread/backgroundTerminals/list", {"threadId": brain, "cursor": cursor, "limit": 64})
        except NativeReadFailure as error:
            if rows or cursor is not None:
                raise Refusal("Current terminal coverage interrupted; observed identities cannot be discarded") from error
            raise
        require(isinstance(page, dict) and isinstance(page.get("data"), list) and
                len(page["data"]) <= 64 and "nextCursor" in page, "Unknown terminal page coverage")
        for item in page["data"]:
            require(isinstance(item, dict), "Unknown current terminal metadata")
            handle, ident, pid = item.get("processId"), item.get("itemId"), item.get("osPid")
            require(isinstance(handle, str) and 0 < len(handle) <= 200 and handle not in handles and
                    isinstance(ident, str) and 0 < len(ident) <= 200 and ident not in items and
                    (pid is None or type(pid) is int and pid > 0),
                    "Duplicate or invalid terminal identity; native handles are not OS PIDs")
            handles.add(handle); items.add(ident)
            rows.append({"itemId": ident, "nativeHandleHash": digest(handle),
                         "osPidHash": digest(pid) if pid is not None else None,
                         "metadataHash": digest(item)})
            require(len(rows) <= MAX_TERMINALS, "Terminal inventory bound exceeded; nothing truncated")
        cursor = page["nextCursor"]
        if cursor is None:
            return sorted(rows, key=lambda row: row["itemId"])
        require(page["data"] and isinstance(cursor, str) and 0 < len(cursor) <= 4096 and
                cursor not in cursors, "Stalled or repeated terminal cursor")
        cursors.add(cursor)
    raise Refusal("Terminal page bound exceeded; coverage remains unknown")


def sample(proxy, scope, recovery_turn):
    thread, roots = _native_identity(proxy, scope, require_idle=False)
    require(thread.get("projectId") == scope["projectId"] and
            thread["status"]["type"] in ("idle", "notLoaded"), "Current brain is active or unknown")
    page = proxy._rpc("thread/turns/list", {"threadId": scope["brainId"], "cursor": None,
                     "limit": 1, "sortDirection": "desc", "itemsView": "notLoaded"})
    require(isinstance(page, dict) and isinstance(page.get("data"), list) and len(page["data"]) == 1 and
            page["data"][0].get("id") == recovery_turn and page["data"][0].get("status") == "completed",
            "The exact latest completed recovery must remain unchanged")
    tracker = {"coverage": "unknown", "rows": None, "reason": "thread_unloaded", "rpcCode": None}
    if thread["status"]["type"] == "idle":
        try:
            tracker = {"coverage": "observed_current_host", "rows": terminals(proxy, scope["brainId"]),
                       "reason": None, "rpcCode": None}
        except NativeReadFailure as error:
            # Do not retry the method, load the brain, or erase observed pages.
            # RPC failure remains unknown; validation/cursor failures refuse.
            tracker.update(reason=error.reason, rpcCode=error.rpc_code)
    after, after_roots = _native_identity(proxy, scope, require_idle=False)
    require(thread == after and roots == after_roots, "Native membership/activity changed during terminal reads")
    return {"activity": thread["status"]["type"], "latestTurnId": recovery_turn,
            "metadataHash": digest({"thread": thread, "roots": roots, "latest": page}), "tracker": tracker}


def qualify(historical_report, fields, current, replaced):
    """Qualify ONLY the fixed documented source, never caller-authored facts.

    Unknown extra fields, model prose, OS PID presence and source hashes cannot
    extend that source's coverage contract. A future attestor needs a separate
    qualified implementation with from-first-effect lifecycle provenance.
    """
    projections = {(row["turnId"], row["itemId"]): row for row in fields}
    rows = []
    current_rows = current["tracker"]["rows"]
    for effect in historical_report["native"]["effects"]:
        key = (effect["turnId"], effect["id"])
        field = projections.get(key)
        require(field is not None and field["itemHash"] == effect["itemHash"], "Cleanup metadata omits a known effect")
        linked = [row for row in current_rows or [] if row["itemId"] == effect["id"]]
        if linked and field["nativeHandleHash"] is not None:
            require(linked[0]["nativeHandleHash"] == field["nativeHandleHash"],
                    "Native process handle changed; process reuse cannot establish continuity")
        needs = [] if effect["terminalCoverage"] == "native_declined" else [
            "effect_process_birth_identity", "from_first_effect_lifecycle_coverage", "historical_descendant_cleanup"]
        if needs and replaced:
            needs.append("original_host_cleanup_provenance")
        rows.append({"turnId": effect["turnId"], "itemId": effect["id"],
                     "outcome": effect["outcome"], "nativeHandleHash": field["nativeHandleHash"],
                     "osPidHash": field["osPidHash"], "nativeFieldTypes": field["fieldTypes"],
                     "currentTrackedTerminal": "running" if linked else
                         "not_listed_current_host" if current_rows is not None else "unknown",
                     "historicalCleanup": "not_required_native_declined" if not needs else "unknown",
                     "missingCleanupEvidence": needs})
    # Historical call linkage/compaction/result gaps remain independent blockers.
    no_execution = historical_report["effectOutcome"] == "not_executed" and not historical_report["gaps"]
    return {"source": "documented_app_server_v2_metadata", "persistedHistory": "observed",
            "currentTerminals": current["tracker"]["coverage"],
            "historicalCleanup": "not_required_non_execution" if no_execution else "unqualified",
            "completeProcessLifecycleSource": False, "completeDescendantCleanupSource": False,
            "executedEffectDispositionAvailable": False, "effects": rows}


def collect(registry, ledger, wake, controls, request):
    """Explicit operator check. No local control submission, retention or native writes."""
    started = time.time()
    context = history.inspection_context(registry, ledger, wake, controls)
    expected = _pins(context)
    exact(request, set(expected))
    require(canonical(request) == canonical(expected), "Cleanup plan changed; preserve original requests and review the current read scope")
    state, pause, recovery, play, binding, scope, _, _, _ = context
    last = recovery["notification"]["nativeTurnId"]
    with CleanupProxy(binding["endpoint"], scope) as proxy:
        before = sample(proxy, scope, last)
        first = history.native_history(proxy, scope["brainId"], play["notification"]["nativeTurnId"], last)
        inventory = history.rollout_inventory(ledger, scope, first["turns"], first["effects"])
        second = history.native_history(proxy, scope["brainId"], play["notification"]["nativeTurnId"], last)
        require(first == second and inventory == history.rollout_inventory(ledger, scope, second["turns"], second["effects"]),
                "Historical effects changed during cleanup collection")
        require(pause["notification"]["nativeTurnId"] in [turn["id"] for turn in first["turns"]],
                "Original Pause is absent from cleanup coverage")
        after = sample(proxy, scope, last)
        require(before == after, "Current terminal inventory or native metadata changed during collection")
        fields = sorted(proxy.fields.values(), key=lambda row: (row["turnId"], row["itemId"]))
        sources = copy.deepcopy(proxy.sources)
    validate_endpoint(binding["endpoint"])
    require(plan(registry, ledger, wake, controls) == expected, "Run, usage, expiry, ownership, host or historical provenance changed")
    historical = history.cross_check(first, inventory)
    # Never bypass the existing historical signed-report limit.
    require(len(canonical(historical).encode()) <= 20000, "Historical report bound exceeded; nothing truncated")
    replaced = any(command["notification"]["hostBindingHash"] != digest(binding) for command in (play, pause, recovery))
    qualification = qualify(historical, fields, after, replaced)
    report = {"kind": KIND, "request": copy.deepcopy(request), "startedAt": started, "observedAt": time.time(),
              "historicalReportHash": digest(historical), "historicalEvidence": historical,
              "currentObservation": after, "sourceObservations": sources,
              "qualification": qualification, "boundary": copy.deepcopy(BOUNDARY),
              "nextStep": "A qualified original-effect lifecycle/cleanup source is required; no replay or confirmation can create missing historical facts."}
    require(len(canonical(report).encode()) <= MAX_REPORT_BYTES, "Cleanup report bound exceeded; coverage is not truncated")
    return report
