"""Locate the local installation without baking private paths into public skills."""
import json
from pathlib import Path
import subprocess
import sys

config = json.loads((Path(__file__).resolve().parents[1] / "installation.json").read_text())
root = Path(config["workspace"])
if not (root / "orchestrator" / "cli.py").is_file():
    raise SystemExit("Orchestrator installation unavailable; do not substitute another runtime.")
raise SystemExit(subprocess.call([config["python"], "-m", "orchestrator.cli", *sys.argv[1:]], cwd=root))
