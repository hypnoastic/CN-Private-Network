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
import tempfile
import time
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
    if state.get("ipv6_restore") not in (None, "Automatic"):
        raise ValueError("Malformed IPv6 restore setting in DNS backup")
    return state


def save_backup(state):
    # Record rollback before changing IPv6. Atomic replacement preserves the
    # original DNS entries even if setup is interrupted during the repair.
    with tempfile.NamedTemporaryFile("w", dir=STATE.parent, delete=False) as stream:
        json.dump(state, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
        candidate = Path(stream.name)
    try:
        os.replace(candidate, STATE)
    finally:
        candidate.unlink(missing_ok=True)


def ipv6_mode(service):
    info = run("/usr/sbin/networksetup", "-getinfo", service)
    match = re.search(r"^IPv6:\s*(.+)$", info, re.M)
    if not match:
        raise ValueError("Cannot read IPv6 mode; leaving it unchanged")
    return match[1].strip()


def set_ipv6(service, option, expected):
    subprocess.run(["sudo", "/usr/sbin/networksetup", option, service], check=True)
    actual = re.sub(r"[^a-z]", "", ipv6_mode(service).lower())
    if actual != re.sub(r"[^a-z]", "", expected.lower()):
        raise ValueError("IPv6 setting did not match; original backup retained")


def lookup_ok(env, direct=False):
    for key in ("APP_DOMAIN", "API_DOMAIN"):
        command = ["/usr/bin/dig", "+time=1", "+tries=1", "+noall", "+answer", "+comments", "+stats"]
        if direct:
            command.append("@" + env["DNS_IP"])
        result = subprocess.run(command + [env[key], "A"], capture_output=True, text=True, timeout=4)
        answers = re.findall(r"^" + re.escape(env[key]) + r"\.\s+\d+\s+IN\s+A\s+(\S+)", result.stdout, re.M)
        if (result.returncode or "status: NOERROR" not in result.stdout
                or f"SERVER: {env['DNS_IP']}#53" not in result.stdout or answers != [env["EDGE_IP"]]):
            return False
    return True


def wait_for_resolver(env):
    for attempt in range(3):
        if lookup_ok(env):
            return True
        if attempt < 2:
            time.sleep(1)
    return False


def ipv6_override_on_service(service):
    device = next((item["device"] for item in services() if item["name"] == service), None)
    config = run("/usr/sbin/scutil", "--dns")
    match = re.search(r"(?:^|\n)resolver #1\n(.*?)(?=\nresolver #|\nDNS configuration \(for|\Z)", config, re.S)
    if not device or not match:
        return False
    block = match[1]
    first = re.search(r"nameserver\[0\]\s*:\s*(\S+)", block)
    return bool(first and ":" in first[1] and re.search(r"if_index\s*:\s*\d+\s+\(" + re.escape(device) + r"\)", block))


def verify_active_dns(state, env):
    if wait_for_resolver(env):
        print("PASS: active default DNS resolves both project names through Yash.")
        return
    if not lookup_ok(env, direct=True):
        raise ValueError("Project DNS is not answering both records correctly. Start Yash's DNS and check network.env; no IPv6 change made")
    service = state["service"]
    if not ipv6_override_on_service(service) or ipv6_mode(service) != "Automatic":
        raise ValueError("Saved DNS differs from the active resolver. Inspect scutil --dns and /etc/resolv.conf. "
                         "No automatic IPv6 workaround applies; original backup retained")
    print(f"Detected an IPv6 resolver overriding project DNS on {service}. "
          "Temporarily using IPv6 Link-local only for this IPv4 lab; IPv6 internet access may be affected. "
          "Stop/restore will return IPv6 to Automatic.")
    state["ipv6_restore"] = "Automatic"
    save_backup(state)
    try:
        set_ipv6(service, "-setv6LinkLocal", "Link-local only")
        change(service, [env["DNS_IP"]])
        if not wait_for_resolver(env):
            raise ValueError("Default DNS still differs after the IPv6 workaround; inspect scutil --dns")
    except (ValueError, OSError, subprocess.SubprocessError, KeyboardInterrupt):
        # An unsuccessful workaround must not leave a broader network change.
        set_ipv6(service, "-setv6automatic", "Automatic")
        state.pop("ipv6_restore")
        save_backup(state)
        flush()
        raise
    print("PASS: active project DNS verified after repair; DNS and IPv6 rollback saved.")


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
        if state.get("ipv6_restore"):
            print("Restoring the IPv6 mode saved before automatic DNS repair: Automatic")
            set_ipv6(state["service"], "-setv6automatic", "Automatic")
            flush()
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
    print(f"Saved DNS setting for {service!r}: {destination}. Active resolver still needs the DNS test.")
    print("Restore: bash shared/restore_client_dns.sh")
    if args.action in ("set", "repair-project"):
        verify_active_dns(state, env)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        sys.exit(f"DNS settings error: {exc}. Any saved backup has been retained.")
