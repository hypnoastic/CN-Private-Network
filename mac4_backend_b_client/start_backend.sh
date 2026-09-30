#!/bin/bash
set -euo pipefail
exec python3 "$(cd "$(dirname "$0")" && pwd)/backend_b.py"
