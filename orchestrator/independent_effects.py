"""Read-only import/correlation of original owned-stream captures.

An absent old capture is unavailable, not reconstructible. Positive typed results
can be corroborated, but neither this stream nor current trackers prove historical
descendant cleanup. The existing closeout/Play contracts are deliberately unchanged.
"""
import copy
import time

from .core import canonical, digest, require
from .admission import exact
from . import cleanup_collector as cleanup, effect_capture as capture, historical_effects as history

KIND = "independent_historical_effect_evidence_v1"


def _captures(context, ledger):
    state, pause, recovery, play, *_ = context
    values = []
    for command in (play, pause, recovery):
        value = capture.retained(ledger, command)
        values.append({"commandId": command["id"], "turnId": command["notification"]["nativeTurnId"],
                       "capture": value})
    return values


def plan(registry, ledger, wake, controls):
    context = history.inspection_context(registry, ledger, wake, controls)
    values = _captures(context, ledger)
    return {"version": 1, "kind": KIND, "cleanupPlan": cleanup._pins(context),
            "originalCaptureHashes": {row["commandId"]: digest(row["capture"]) for row in values},
            "captureSourceHash": capture.source_hash()}


def correlate(historical, values):
    """Exact positive item linkage only. Never erase a primary gap or infer absence."""
    native = {(row["turnId"], row["id"]): row for row in historical["native"]["effects"]}
    seen, rows, captured_turns = set(), [], set()
    for entry in values:
        value = entry["capture"]
        starts, completions, turn_completions = {}, {}, []
        for event in value["events"]:
            require(event["turnId"] == entry["turnId"], "Capture belongs to a different historical turn")
            if event["kind"] == "turn_completed":
                turn_completions.append(event)
                continue
            key = (event["turnId"], event["itemId"])
            target = starts if event["kind"] == "item_started" else completions
            require(key not in target, "Duplicate or conflicting independently captured item")
            target[key] = event
        require(len(turn_completions) <= 1, "Duplicate captured native turn completion")
        captured_turns.update([entry["turnId"]] if value["status"] in {"observed", "incomplete"} else [])
        for key, event in completions.items():
            require(key not in seen, "Historical effect is linked to more than one original capture")
            seen.add(key)
            effect, started = native.get(key), starts.get(key)
            if started:
                require(all(started[field] == event[field] for field in ("turnId", "itemId", "itemType", "commandHash", "cwdHash")),
                        "Captured item scope changed between start and completion")
            match = bool(effect and all(effect.get(field) == event[field] for field in
                ("status", "itemHash", "commandHash", "cwdHash", "exitCode"))
                and effect["type"] == event["itemType"] and event["itemType"] == "commandExecution"
                and (event["status"] == "declined" and event["exitCode"] is None
                     or event["status"] in {"completed", "failed"} and type(event["exitCode"]) is int))
            # A contrary observation is not an alternate result the owner may
            # choose. Refuse the inconsistent independent view altogether.
            if effect and event["itemType"] == "commandExecution":
                require(all(effect.get(field) == event[field] for field in
                    ("status", "itemHash", "commandHash", "cwdHash", "exitCode")),
                    "Independent native completion conflicts with persisted history")
            rows.append({"commandId": entry["commandId"], "turnId": key[0], "itemId": key[1],
                         "capturedItemHash": event["itemHash"], "capturedEventHash": digest(event),
                         "originalObservedAt": event["observedAt"], "matchesNativeResult": match,
                         "startObserved": started is not None, "historicalCleanup": "unknown"})
    missing = []
    for key in native:
        match = next((row for row in rows if (row["turnId"], row["itemId"]) == key and row["matchesNativeResult"]), None)
        if not match:
            missing.append({"turnId": key[0], "itemId": key[1], "need": "independent_original_result_capture",
                            "reason": "original_capture_missing" if key[0] not in captured_turns else "typed_capture_result_missing"})
    # Keep extra capture identities visible: an omitted persisted effect cannot
    # disappear merely because it has no current tracker or saved call result.
    for key in seen - native.keys():
        missing.append({"turnId": key[0], "itemId": key[1], "need": "independent_effect_history_link",
                        "reason": "captured_effect_missing_from_persisted_history"})
    return {"source": capture.SOURCE, "resultEvidence": rows, "missingIndependentEvidence": missing,
            "originalCaptureCoverage": [{"commandId": entry["commandId"], "turnId": entry["turnId"],
                "status": entry["capture"]["status"], "reason": entry["capture"]["reason"],
                "headerHash": entry["capture"].get("headerHash"),
                "fileHash": entry["capture"].get("fileHash")} for entry in values],
            "positiveResultsCorroborated": sum(row["matchesNativeResult"] for row in rows),
            "completeHistoricalInventorySource": False, "completeProcessLifecycleSource": False,
            "completeDescendantCleanupSource": False, "executedEffectDispositionAvailable": False}


def collect(registry, ledger, wake, controls, request):
    """Only explicit original-source reads. No importer write, HTTP control or attestation override."""
    exact(request, {"version", "kind", "cleanupPlan", "originalCaptureHashes", "captureSourceHash"})
    expected = plan(registry, ledger, wake, controls)
    require(canonical(request) == canonical(expected), "Original independent evidence scope changed")
    context = history.inspection_context(registry, ledger, wake, controls)
    values = _captures(context, ledger)
    result = cleanup.collect(registry, ledger, wake, controls, request["cleanupPlan"])
    require(values == _captures(history.inspection_context(registry, ledger, wake, controls), ledger)
            and expected == plan(registry, ledger, wake, controls),
            "Original capture, source, usage, requests or host provenance changed")
    independent = correlate(result["historicalEvidence"], values)
    report = {"kind": KIND, "request": copy.deepcopy(request), "observedAt": time.time(),
              "primaryCollection": result, "independentEvidence": independent,
              "boundary": copy.deepcopy(cleanup.BOUNDARY),
              "nextStep": ("Original capture was absent or incomplete: no new capture, confirmation or replay can backfill it. "
                           "Independent original-effect lifecycle and cleanup evidence remains required; the phase stays fenced.")}
    require(len(canonical(report).encode()) <= cleanup.MAX_REPORT_BYTES,
            "Independent evidence report exceeds its bound; no identities were truncated")
    return report
