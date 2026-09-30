# IP and service inventory

This table is a map of settings, not a second place to enter IP addresses.

| Machine | Address setting | Service | Transport / listening port | Client role |
|---|---|---|---|---|
| Mac 1 | `MAC1_IP` / `DNS_IP` | dnsmasq | UDP 53 and TCP 53 | Main client |
| Mac 2 | `MAC2_IP` / `EDGE_IP` | nginx TLS edge | TCP `HTTPS_PORT` (8443 default; 443 allowed) | Additional DNS verification client |
| Mac 3 | `MAC3_IP` / `BACKEND_A_IP` | Python Backend A | TCP `BACKEND_A_PORT` (3001 default) | Direct verification only |
| Mac 4 | `MAC4_IP` / `BACKEND_B_IP` | Python Backend B | TCP `BACKEND_B_PORT` (3002 default) | Secondary client |

Record these five values for **each** physical Mac: private IPv4 address; subnet mask/prefix; default gateway; active interface; MAC address. Run `bash shared/record_inventory.sh 1` on Mac 1, then the corresponding number on each other Mac. Pass your LAN interface as a second argument when needed. The script records `ipconfig`, `ifconfig`, routing, and hardware-port output in `evidence/collected/macN-inventory.txt`.

On macOS, `ifconfig` may show a hexadecimal netmask. To convert the actual LAN interface's mask into dotted decimal and a prefix, run from the repository root:

```bash
LAN_IFACE="$(route -n get default | awk '/interface:/ {print $2; exit}')"
MASK_HEX="$(ifconfig "$LAN_IFACE" | awk '/inet / {print $4; exit}')"
python3 -c 'import ipaddress,sys; m=str(ipaddress.IPv4Address(int(sys.argv[1],16))); n=ipaddress.IPv4Network("0.0.0.0/"+m); print("mask:",m,"prefix:",n.prefixlen)' "$MASK_HEX"
```

If a VPN supplies the default route, use the actual LAN interface from `networksetup -listallhardwareports`. All four Macs must reach each other's configured addresses. Save `bash shared/ping_all.sh` output from all four machines to show every pair.

Display the configured service addresses with `python3 shared/env_loader.py`. Keep real inventory evidence private if the course submission is public.
