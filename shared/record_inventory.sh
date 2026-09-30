#!/bin/bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/common.sh"
cn_load_env
MAC_NUMBER="${1:-}"
case "$MAC_NUMBER" in 1|2|3|4) ;; *) echo 'Usage: bash shared/record_inventory.sh 1 (or 2, 3, 4)' >&2; exit 1;; esac
IFACE="${2:-$(/sbin/route -n get "$EDGE_IP" | awk '/interface:/ {print $2; exit}')}"
# A route to this machine's own IP may select lo0; use the default LAN interface.
if [ "$IFACE" = lo0 ]; then IFACE="$(/sbin/route -n get default | awk '/interface:/ {print $2; exit}')"; fi
[ -n "$IFACE" ] || { echo 'Pass the LAN interface as the second argument, e.g. en0.' >&2; exit 1; }
mkdir -p "$CN_ROOT/evidence/collected"
{
    echo "MAC $MAC_NUMBER - $(date)"
    echo "Active LAN interface: $IFACE"
    /usr/sbin/ipconfig getifaddr "$IFACE"
    /sbin/ifconfig "$IFACE"
    /sbin/route -n get default
    /usr/sbin/networksetup -listallhardwareports
} | tee "$CN_ROOT/evidence/collected/mac${MAC_NUMBER}-inventory.txt"
echo 'Saved IPv4, hexadecimal netmask, interface/MAC address, and default gateway.'
