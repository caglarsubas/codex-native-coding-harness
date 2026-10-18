"""Checkout-local data client for one prospective forward-planning turn."""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from orchestrator.canceled_continuation import main
from orchestrator.core import Refusal, canonical

if __name__=='__main__':
    try: main()
    except (Refusal,OSError,ValueError,KeyError,TypeError) as error:
        print(canonical({'error':str(error)})); raise SystemExit(2)
