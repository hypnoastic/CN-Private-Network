#!/bin/bash
set -euo pipefail
CN_DIR="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$CN_DIR/mac2_edge/configure.py"
exec python3 "$CN_DIR/shared/service_control.py" nginx reload
