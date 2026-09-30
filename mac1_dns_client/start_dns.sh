#!/bin/bash
set -euo pipefail
CN_DIR="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$CN_DIR/shared/service_control.py" dns check-stopped
python3 "$CN_DIR/mac1_dns_client/configure.py"
exec python3 "$CN_DIR/shared/service_control.py" dns start
