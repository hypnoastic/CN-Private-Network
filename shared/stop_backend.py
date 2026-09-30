#!/usr/bin/env python3
"""Stop the PID recorded by the selected project backend, after identity checks."""
import argparse
import os
import signal
import subprocess
import sys
import time
from env_loader import ROOT


def stop(backend):
    role = "mac3_backend_a" if backend == "A" else "mac4_backend_b_client"
    pidfile = ROOT / role / "runtime/backend.pid"
    if not pidfile.exists():
        print(f"Backend {backend} is already stopped.")
        return
    value = pidfile.read_text().strip()
    if not value.isdigit() or int(value) <= 1:
        raise ValueError(f"Invalid backend PID file: {pidfile}")
    pid = int(value)
    result = subprocess.run(["/bin/ps", "-ww", "-p", str(pid), "-o", "command="], capture_output=True, text=True)
    if result.returncode:
        print(f"Backend {backend} is not running; removing stale PID record.")
        pidfile.unlink()
        return
    if f"{role}/backend_{backend.lower()}.py" not in result.stdout:
        raise ValueError(f"PID {pid} does not match Backend {backend}; no signal sent")
    os.kill(pid, signal.SIGINT)
    for _ in range(50):
        if not pidfile.exists():
            print(f"Backend {backend} stopped cleanly.")
            return
        time.sleep(0.1)
    raise ValueError("Interrupt sent but backend has not exited; inspect its Terminal")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backend", choices=("A", "B"))
    try:
        stop(parser.parse_args().backend)
    except (ValueError, OSError) as exc:
        sys.exit(f"Stop error: {exc}")
