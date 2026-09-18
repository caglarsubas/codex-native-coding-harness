"""Synthetic lifecycle rehearsal: isolated temporary ledger, no native/tool calls."""
import json
from pathlib import Path
import tempfile
import time
import uuid

from .core import AXES, PREFLIGHT_CHECKS, Ledger, Refusal, require
from .observations import capture, save


def exercise():
    steps = []
    with tempfile.TemporaryDirectory(prefix="codex-lifecycle-rehearsal-") as folder:
        ledger = Ledger(Path(folder) / "state")
        ledger.initialize({"schemaVersion": 1, "brainId": "SYNTHETIC-BRAIN", "repositories": [{
            "id": "fixture", "path": None, "projectId": "SYNTHETIC-PROJECT", "ref": "HEAD", "mergePolicy": "manual", "policyProfile": "standard"}]})
        token = ledger.acquire("synthetic-rehearsal")
        def command(kind, payload=None):
            return ledger.submit({"id": str(uuid.uuid4()), "kind": kind,
                "expectedRevision": ledger.snapshot()["meta"]["revision"], "payload": payload or {}}, actor="SYNTHETIC-TEST")
        def refused(label, fn):
            try:
                fn()
            except Refusal:
                steps.append({"check": label, "status": "passed"})
            else:
                raise Refusal("Rehearsal safety assertion failed: " + label)
        seed = {"schemaVersion": 1, "repository": "fixture", "policyProfile": "standard", "packetId": "SYNTHETIC-ONLY",
            "packetDigest": "a" * 64, "packetPath": "fixtures/packet.json", "catalogCommit": "b" * 40,
            "baseSHA": "c" * 40, "branch": "codex/synthetic-only", "objective": "Exercise ledger transitions only", "rationale": "No real task or repository",
            "allowedPaths": ["fixtures/result.txt"], "contracts": ["No external effects"], "predecessors": [], "locks": [],
            "execution": {"wrapperArgv": ["NEVER-EXECUTE-FIXTURE"], "prefetchCommands": [], "offlineAcceptanceCommands": [["NEVER-EXECUTE-FIXTURE"]], "isolation": "REPOSITORY_POLICY"},
            "acceptance": ["Synthetic state assertions"], "stopConditions": ["Any real side effect"], "completionAxes": ["source", "ci"]}
        q = ledger.prepare(seed)
        refused("Paused dispatch refuses reservation", lambda: ledger.reserve(token, q["id"]))
        command("resume"); ledger.process(token)
        refused("Unapproved packet refuses reservation", lambda: ledger.reserve(token, q["id"]))
        command("approve", {"queueId": q["id"], "seedHash": q["seedHash"], "packetDigest": q["packetDigest"]})
        refused("Approval without preflight refuses reservation", lambda: ledger.reserve(token, q["id"]))
        ledger.preflight(token, q["id"], {"seedHash": q["seedHash"], "packetDigest": q["packetDigest"], "baseSHA": seed["baseSHA"],
            "projectId": "SYNTHETIC-PROJECT", "checks": {k: True for k in PREFLIGHT_CHECKS}, "evidence": ["SYNTHETIC-EVIDENCE-NOT-REAL"]})
        w = ledger.reserve(token, q["id"])
        # Returned arguments are checked then discarded; no native tool is invoked.
        action = ledger.begin_creation(token, w["id"])
        require(action["target"]["environment"] == {"type": "worktree"}, "Expected isolated worktree request")
        refused("One-shot creation cannot be retried", lambda: ledger.begin_creation(token, w["id"]))
        ledger = Ledger(Path(folder) / "state")
        ledger.recover("synthetic-rehearsal", "Synthetic simulated restart; no native tasks or processes were created.")
        recovered = ledger.snapshot()
        require(recovered["workers"][0]["status"] == "starting" and recovered["meta"]["paused"], "Restart must preserve uncertain ownership and pause")
        steps.append({"check": "Restart preserves uncertain ownership and pauses dispatch", "status": "passed"})
        token = ledger.acquire("synthetic-recovery")
        ledger.bind(token, w["id"], client_id="SYNTHETIC-PENDING")
        require(ledger.snapshot()["workers"][0]["threadId"] is None, "Pending ID must not become a confirmed task")
        ledger.bind(token, w["id"], thread_id="SYNTHETIC-NATIVE-NOT-REAL")
        ledger.transition(token, w["id"], "awaiting_acceptance", "Synthetic worker ready")
        ledger.runner(token, w["id"], "acquire", "Synthetic idle runner, no process")
        refused("Runner ownership blocks unsafe worker transitions", lambda: ledger.transition(token, w["id"], "blocked", "Fixture"))
        ledger.runner(token, w["id"], "release", "Synthetic exit and cleanup, no process")
        evidence = {a: {"status": "verified" if a in ("source", "ci") else "unverified",
            "reference": "SYNTHETIC-ASSERTION" if a in ("source", "ci") else None} for a in AXES}
        ledger.complete(token, w["id"], {"schemaVersion": 1, "seedHash": q["seedHash"], "commit": "d" * 40,
            "changedPaths": ["fixtures/result.txt"], "pr": "https://github.com/example/synthetic/pull/1", "evidence": evidence,
            "preserved": True, "reviewReference": "Synthetic review, not CI or product proof"})
        final = ledger.snapshot()
        require(not final["meta"]["pilotPassed"] and final["meta"]["concurrency"] == 1, "Rehearsal must not certify a pilot")
        require(final["workers"][0]["evidence"]["merge"]["status"] == "unverified", "Manual merge must remain separate")
        require(not final["workers"][0]["archived"], "Completion must not archive a native task")
        steps.append({"check": "Completion does not imply merge, archive or real pilot acceptance", "status": "passed"})
        ledger.release(token, "Synthetic lifecycle completed; no real actions.")
    return {"schemaVersion": 1, "at": time.time(), "status": "passed", "synthetic": True,
        "realPilotAccepted": False, "nativeCalls": 0, "modelCalls": 0, "steps": steps,
        "limits": "Tests ledger state transitions in a disposable fixture only. Does not verify native creation, worktree setup, actual CI, runner isolation or product acceptance."}


def run(ledger):
    result = exercise()
    with ledger.tx() as db:
        version = capture(db, "readiness:lifecycle-rehearsal", (json.dumps(result, indent=2) + "\n").encode(),
            {"name": "lifecycle-rehearsal.json", "repository": "@portfolio", "path": None, "references": [],
                "createdAt": result["at"], "orderAt": result["at"], "provenance": "synthetic_lifecycle_rehearsal"})
        result["artifactId"] = version["id"]
        save(db, "rehearsal", result)
    return result
