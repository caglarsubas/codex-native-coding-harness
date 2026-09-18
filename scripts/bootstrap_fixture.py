"""Create a clearly synthetic UI fixture in a fresh temporary directory.

Never points at a product checkout, emits native creation requests or approves
real work. Used for interactive dashboard control tests only.
"""
import json
from pathlib import Path
import tempfile
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from orchestrator.core import Ledger

folder = Path(tempfile.mkdtemp(prefix="codex-orchestrator-ui-"))
ledger = Ledger(folder)
ledger.initialize({"schemaVersion":1,"brainId":"SYNTHETIC-UI-FIXTURE-NOT-A-NATIVE-TASK","repositories":[
    {"id":"synthetic-ui-fixture","path":None,"projectId":None,"ref":"HEAD","mergePolicy":"manual","policyProfile":"standard"}]})
seed = {"schemaVersion":1,"repository":"synthetic-ui-fixture","policyProfile":"standard","packetId":"UI-FIXTURE-ONLY",
    "packetDigest":"a"*64,"packetPath":"fixture/packet.json","catalogCommit":"b"*40,"baseSHA":"c"*40,
    "branch":"codex/ui-fixture","objective":"Exercise local dashboard controls only; no real task creation",
    "rationale":"Synthetic UI acceptance fixture, not a product task or native integration pilot",
    "allowedPaths":["fixture/example.txt"],"contracts":["No external effects or native task creation"],"predecessors":[],"locks":[],
    "execution":{"wrapperArgv":["fixture-only"],"prefetchCommands":[],"offlineAcceptanceCommands":[["fixture-only"]],"isolation":"REPOSITORY_POLICY"},
    "acceptance":["Review, approval, hold and priority controls persist correctly"],"stopConditions":["Any real task or repository action"],"completionAxes":["source","ci"]}
ledger.prepare(seed)
from orchestrator.decisions import publish
from orchestrator.observations import capture

with ledger.tx() as db:
    artifact = capture(db, "synthetic-decision-design", b"Synthetic decision UI fixture. No real project or native authority.",
        {"name":"synthetic-design.md", "repository":"synthetic-ui-fixture", "orderAt":time.time(), "references":[]})
token = ledger.acquire("SYNTHETIC-UI-FIXTURE-NOT-A-NATIVE-TASK:bootstrap")
publish(ledger, token, {"key":"SYNTHETIC-DECISION-001", "repository":"synthetic-ui-fixture",
    "title":"Synthetic decision · UI verification only", "question":"Which fixture direction should be recorded?",
    "context":"This tests the interface only. Literal text stays inert: <script>alert('fixture')</script>.",
    "scope":"Synthetic temporary ledger only. No real work or native actions.",
    "nextStep":"A test operator records a synthetic outcome artifact.",
    "options":[{"id":"bounded", "label":"Bounded fixture", "implications":"Exercise answer receipt without executing anything.", "requiresNote":False},
               {"id":"input", "label":"Supply fixture input", "implications":"A note is required and remains data only.", "requiresNote":True}],
    "recommendedOptionId":"bounded", "artifactIds":[artifact["id"]]})
ledger.release(token,"Synthetic UI fixture prepared; no native pilot or work authorized.")
print(json.dumps({"fixtureState":str(folder),"label":"SYNTHETIC UI ONLY; no native dispatch or product authority"}))
