#!/usr/bin/env python3
"""Only the Phase 1 wrong-record experiment; restore before the next experiment."""
import argparse
import sys
from env_loader import ROOT, load_env
from render_config import brew_binary, render
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("wrong-record", "restore-record"))
    args = parser.parse_args()
    env = load_env()
    path = ROOT / "mac1_dns_client/runtime/dnsmasq.conf"
    if args.action == "restore-record":
        render("dns")
        print("Correct records restored from network.env. Start DNS normally.")
    else:
        if not path.exists():
            raise ValueError("Run mac1_dns_client/configure.py first")
        original = f"host-record={env['APP_DOMAIN']},{env['EDGE_IP']}"
        content = path.read_text()
        if original not in content:
            raise ValueError("Correct record not found; restore-record before repeating")
        path.write_text(content.replace(original, f"host-record={env['APP_DOMAIN']},{env['MAC3_IP']}", 1))
        print(f"Temporary Phase 1 error: {env['APP_DOMAIN']} now points to Mac 3. network.env is unchanged.")
    subprocess.run([brew_binary("dnsmasq", "dnsmasq"), "--test", f"--conf-file={path}"], check=True)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        sys.exit(f"Failure demonstration error: {exc}")
