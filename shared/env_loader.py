#!/usr/bin/env python3
"""Strict, dependency-free configuration loader. It never executes network.env."""
import argparse
import ipaddress
import json
import re
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = {"BACKEND_A_PORT": "3001", "BACKEND_B_PORT": "3002", "HTTPS_PORT": "8443"}
KEYS = set("TEAM_NAME MAC1_IP MAC2_IP MAC3_IP MAC4_IP DNS_IP EDGE_IP BACKEND_A_IP BACKEND_B_IP APP_DOMAIN API_DOMAIN".split()) | set(DEFAULTS)
PRIVATE = tuple(ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def load_env(path=None):
    path = Path(path) if path is not None else ROOT / "network.env"
    if not path.is_file():
        raise ValueError(f"Missing {path}. From {ROOT}, run: cp network.env.example network.env; then edit network.env with your real LAN IPs.")
    raw = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"{path}:{number}: expected KEY=value")
        key, value = (part.strip() for part in line.split("=", 1))
        if key not in KEYS or key in raw:
            raise ValueError(f"{path}:{number}: unknown or duplicate key {key!r}")
        if value[:1] in ("'", '"') and value[-1:] == value[:1]:
            value = value[1:-1]
        raw[key] = value
    for key, value in DEFAULTS.items():
        raw.setdefault(key, value)
    missing = KEYS - raw.keys()
    if missing:
        raise ValueError("Missing settings: " + ", ".join(sorted(missing)))
    resolved = {}

    def expand(key, stack=()):
        if key not in raw:
            raise ValueError(f"Unknown variable reference: {key}")
        if key in stack:
            raise ValueError(f"Circular reference involving {key}")
        if key not in resolved:
            resolved[key] = re.sub(r"\$\{([A-Z0-9_]+)\}", lambda m: expand(m[1], stack + (key,)), raw[key])
        return resolved[key]

    for key in raw:
        expand(key)
    label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    if not re.fullmatch(label, resolved["TEAM_NAME"]):
        raise ValueError("TEAM_NAME must be a lowercase DNS label, e.g. team1")
    for key in (k for k in KEYS if k.endswith("_IP")):
        try:
            addr = ipaddress.IPv4Address(resolved[key])
        except ipaddress.AddressValueError as exc:
            raise ValueError(f"{key}: invalid IPv4 address {resolved[key]!r}") from exc
        if not any(addr in subnet for subnet in PRIVATE):
            raise ValueError(f"{key}: use an RFC1918 private LAN IPv4 address")
    if len({resolved[f"MAC{n}_IP"] for n in range(1, 5)}) != 4:
        raise ValueError("The four physical Macs must have four different IP addresses")
    for alias, mac in {"DNS_IP": "MAC1_IP", "EDGE_IP": "MAC2_IP", "BACKEND_A_IP": "MAC3_IP", "BACKEND_B_IP": "MAC4_IP"}.items():
        if resolved[alias] != resolved[mac]:
            raise ValueError(f"{alias} must equal {mac} for the required four-Mac architecture")
    for key in DEFAULTS:
        if not resolved[key].isdigit() or not 1 <= int(resolved[key]) <= 65535:
            raise ValueError(f"{key}: port must be an integer from 1 to 65535")
        resolved[key] = str(int(resolved[key]))
    for key, prefix in (("APP_DOMAIN", "app"), ("API_DOMAIN", "api")):
        expected = f"{prefix}.{resolved['TEAM_NAME']}.test"
        if resolved[key] != expected:
            raise ValueError(f"{key} must be {expected} (assignment's .test namespace)")
    return resolved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shell", action="store_true", help="emit validated, shell-quoted assignments")
    args = parser.parse_args()
    try:
        env = load_env()
        if args.shell:
            print("\n".join(f"export {key}={shlex.quote(value)}" for key, value in sorted(env.items())))
        else:
            print(json.dumps(env, indent=2))
    except (ValueError, OSError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
