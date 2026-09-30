#!/bin/bash
set -euo pipefail
exec python3 "$(cd "$(dirname "$0")/.." && pwd)/shared/stop_backend.py" B
