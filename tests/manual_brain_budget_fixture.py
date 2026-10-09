"""Disposable budget UI: synthetic ended turn, no native transport or inference.

Run: python3 tests/manual_brain_budget_fixture.py --port 8802
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from orchestrator.server import Dashboard
from test_standard_budget import BrainBudgetTest

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8802)
    args = parser.parse_args()
    fixture = BrainBudgetTest(methodName="runTest"); fixture.setUp()
    server = Dashboard(fixture.ledger, args.port, registry=fixture.registry, runtime_root=fixture.fixture.root,
                       inference_env=fixture.fixture.root/".env")
    server.bootstrap = "disposable-brain-budget-ui-preview"
    print(server.origin + "/#token=" + server.bootstrap, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close(); fixture.doCleanups()
