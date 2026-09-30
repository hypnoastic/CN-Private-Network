#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))
from render_config import render

if __name__ == "__main__":
    try:
        render("nginx")
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        sys.exit(f"nginx configuration error: {exc}")
