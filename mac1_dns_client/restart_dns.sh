#!/bin/bash
set -euo pipefail
CN_DIR="$(cd "$(dirname "$0")" && pwd)"
bash "$CN_DIR/stop_dns.sh"
exec bash "$CN_DIR/start_dns.sh" "$@"
