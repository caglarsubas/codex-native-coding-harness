"""Create a clearly synthetic UI fixture in a fresh temporary directory.

Never points at a product checkout, emits native creation requests or approves
real work. Used for interactive dashboard control tests only.
"""
import json
from pathlib import Path
import tempfile
import sys

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
print(json.dumps({"fixtureState":str(folder),"label":"SYNTHETIC UI ONLY; no native dispatch or product authority"}))
