#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))
from backend_server import serve

if __name__ == "__main__":
    sys.exit(serve("B"))
