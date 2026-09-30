#!/bin/bash
set -euo pipefail
CN_DIR="$(cd "$(dirname "$0")/.." && pwd)"
bash "$CN_DIR/shared/test_backends.sh"
bash "$CN_DIR/shared/test_dns.sh"
bash "$CN_DIR/shared/test_https.sh"
