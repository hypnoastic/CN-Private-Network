#!/bin/bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/common.sh"
cn_load_env
result=0
for ip in "$MAC1_IP" "$MAC2_IP" "$MAC3_IP" "$MAC4_IP"; do
    echo "Testing $ip"
    if ping -c 3 "$ip"; then echo "PASS: $ip"; else echo "FAIL: $ip"; result=1; fi
done
exit "$result"
