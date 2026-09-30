#!/bin/bash
# Run on Mac 1 or Mac 4 after the four machines are set up.
set -euo pipefail
CN_DIR="$(cd "$(dirname "$0")/.." && pwd)"
bash "$CN_DIR/shared/test_dns.sh"
bash "$CN_DIR/shared/test_https.sh"
bash "$CN_DIR/shared/test_load_balancing.sh"
bash "$CN_DIR/shared/test_caching.sh"
echo 'PASS: Phase 1 DNS, trusted HTTPS, both backends, and caching. Collect the LAN packet evidence separately.'
