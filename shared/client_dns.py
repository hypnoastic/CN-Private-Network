#!/usr/bin/env python3
"""Back up, set, and restore this Mac's DNS settings without sourcing shell text."""
import argparse
import ipaddress
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from env_loader import ROOT, load_env

STATE = ROOT / "shared/runtime/client-dns.json"


def run(*args):
    result = subprocess.run(list(args), text=True, capture_output=True, check=True)
    return result.stdout.strip()


def machine_id():
    value = run("/usr/sbin/ioreg", "-rd1", "-c", "IOPlatformExpertDevice")
    match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', value)
    if not match:
        raise ValueError("Cannot identify this Mac; refusing to use a potentially foreign DNS backup")
    return match[1]


def services():
    value = run("/usr/sbin/networksetup", "-listnetworkserviceorder")
    records = []
    lines = value.splitlines()
    for index, line in enumerate(lines[:-1]):
        match = re.match(r"\((\d+)\) (.+)", line)
        device = re.search(r"Hardware Port: (.+), Device: ([^)]+)", lines[index + 1])
        if match and device and not match[2].startswith("*"):
            records.append({"name": match[2], "hardware": device[1], "device": device[2]})
    return records


def choose_service(requested=None):
    candidates = services()
    if requested:
        if requested not in [item["name"] for item in candidates]:
            raise ValueError(f"Unknown/disabled network service {requested!r}")
        return requested
    active = []
    for item in candidates:
        result = subprocess.run(["/usr/sbin/ipconfig", "getifaddr", item["device"]], text=True, capture_output=True)
        if result.returncode == 0 and result.stdout.strip():
            active.append(item)
    wifi = [item for item in active if item["hardware"] in ("Wi-Fi", "AirPort")]
    if len(wifi) == 1:
        print(f"Detected active Wi-Fi service: {wifi[0]['name']}")
        return wifi[0]["name"]
    if len(active) == 1:
        print(f"Detected active LAN service: {active[0]['name']}")
        return active[0]["name"]
    print("Available network services:")
    for index, item in enumerate(candidates, 1):
        print(f"  {index}. {item['name']} ({item['device']})")
    if not sys.stdin.isatty():
        raise ValueError("Specify the LAN service with --service 'Wi-Fi' (use the name shown above)")
    selected = input("Select your project Wi-Fi/LAN service number: ").strip()
    if not selected.isdigit() or not 1 <= int(selected) <= len(candidates):
        raise ValueError("Invalid service selection")
    return candidates[int(selected) - 1]["name"]


def read_dns(service):
    value = run("/usr/sbin/networksetup", "-getdnsservers", service)
    if "There aren't any DNS Servers set on" in value:
        return [], value
    entries = value.splitlines()
    if not entries:
        raise ValueError("Empty DNS response; refusing to guess current settings")
    for entry in entries:
        ipaddress.ip_address(entry)
    return entries, value


def flush():
    for command in (["sudo", "/usr/bin/dscacheutil", "-flushcache"], ["sudo", "/usr/bin/killall", "-HUP", "mDNSResponder"]):
        result = subprocess.run(command)
        if result.returncode:
            print("DNS settings saved, but cache flushing failed; retry that command manually.", file=sys.stderr)


def read_backup(identity):
    state = json.loads(STATE.read_text())
    if state.get("machine") != identity:
        raise ValueError(f"{STATE} belongs to a different Mac. Use this Mac's original backup, never a copied runtime folder.")
    if not isinstance(state.get("service"), str) or not isinstance(state.get("servers"), list):
        raise ValueError("Malformed DNS backup")
    for value in state["servers"]:
        ipaddress.ip_address(value)
    return state


def change(service, entries):
    subprocess.run(["sudo", "/usr/sbin/networksetup", "-setdnsservers", service, *(entries or ["Empty"])], check=True)
    actual, _ = read_dns(service)
    if actual != entries:
        raise ValueError(f"DNS settings did not match requested values; backup remains at {STATE}")
    flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("set", "restore", "wrong-server", "repair-project"))
    parser.add_argument("--service", help="explicit macOS network service name")
    args = parser.parse_args()
    if platform.system() != "Darwin":
        raise ValueError("Client DNS changes require macOS")
    if os.geteuid() == 0:
        raise ValueError("Run this script without sudo; it requests sudo only for the network change")
    identity = machine_id()
    if args.action == "restore":
        if not STATE.exists():
            print("No active DNS backup; nothing to restore.")
            return
        state = read_backup(identity)
        current, raw = read_dns(state["service"])
        print(f"Current DNS on {state['service']}:\n{raw}")
        print(f"Restoring: {state['servers'] or 'automatic/DHCP (Empty)'}")
        change(state["service"], state["servers"])
        restored = STATE.with_name("client-dns.last-restored.json")
        os.replace(STATE, restored)
        print(f"Original settings restored and verified. Audit copy: {restored}")
        return
    env = load_env()
    if STATE.exists():
        state = read_backup(identity)
        service = state["service"]
        if args.service and args.service != service:
            raise ValueError("Restore the previously selected service before changing another")
        print(f"Preserving original backup: {STATE}")
    else:
        if args.action != "set":
            raise ValueError("Run set_client_dns.sh first so original DNS is safely backed up")
        service = choose_service(args.service)
        entries, raw = read_dns(service)
        state = {"machine": identity, "service": service, "servers": entries, "raw": raw}
        STATE.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation guarantees repeated setup never overwrites the original.
        fd = os.open(STATE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(state, stream, indent=2)
        print(f"Original DNS backed up: {STATE}")
    _, raw = read_dns(service)
    print(f"Current DNS on {service}:\n{raw}")
    destination = env["MAC3_IP"] if args.action == "wrong-server" else env["DNS_IP"]
    print(f"Changing ONLY service {service!r} DNS to: {destination}")
    change(service, [destination])
    print(f"Verified DNS now points to {destination}. Restore: bash shared/restore_client_dns.sh")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        sys.exit(f"DNS settings error: {exc}. Any saved backup has been retained.")
