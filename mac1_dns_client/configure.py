#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))
from render_config import render

if __name__ == "__main__":
    try:
        render("dns")
    except (ValueError, OSError) as exc:
        sys.exit(f"DNS configuration error: {exc}")
