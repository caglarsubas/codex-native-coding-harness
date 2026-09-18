"""Install the bundled personal skill; refuse to overwrite different skill files."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--destination", type=Path, default=Path(os.environ.get("CODEX_HOME", str(Path.home()/".codex"))) / "skills" / "codex-orchestrator")
args = parser.parse_args()
source = root / "skills" / "codex-orchestrator"
for file in source.rglob("*"):
    if file.is_file() and "__pycache__" not in file.parts:
        dest = args.destination / file.relative_to(source)
        if dest.exists() and dest.read_bytes() != file.read_bytes():
            raise SystemExit(f"Refusing to overwrite a modified installed skill: {dest}")
for file in source.rglob("*"):
    if file.is_file() and "__pycache__" not in file.parts:
        dest = args.destination / file.relative_to(source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, dest)
installation = args.destination / "installation.json"
with open(installation, "w") as stream:
    json.dump({"schemaVersion": 1, "workspace": str(root), "python": sys.executable}, stream, indent=2)
os.chmod(installation, 0o600)
print(json.dumps({"installed": str(args.destination), "workspace": str(root)}))
