#!/bin/bash
set -euo pipefail
CN_DIR="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$CN_DIR/shared/checks.py" backend-b
bash "$CN_DIR/shared/test_dns.sh"
bash "$CN_DIR/shared/test_https.sh"
