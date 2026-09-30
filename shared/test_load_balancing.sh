#!/bin/bash
set -euo pipefail
CN_DIR="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$CN_DIR/shared/checks.py" balancing "$@"
