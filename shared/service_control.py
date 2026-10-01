#!/usr/bin/env python3
"""Operate only this repository's foreground dnsmasq/nginx process."""
import argparse
import os
import re
import signal
import subprocess
import sys
import time
from env_loader import ROOT, load_env
from render_config import brew_binary


def process_at(pidfile, config, binary):
    if not pidfile.exists():
        return None
    value = pidfile.read_text().strip()
    if not value.isdigit() or int(value) <= 1:
        raise ValueError(f"Invalid PID file: {pidfile}")
    pid = int(value)
    result = subprocess.run(["/bin/ps", "-ww", "-p", str(pid), "-o", "stat=", "-o", "command="], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    fields = result.stdout.strip().split(maxsplit=1)
    if not fields or fields[0].startswith("Z"):
        return None  # Exited child awaiting its parent, not a running service.
    command = fields[1] if len(fields) == 2 else ""
    if binary not in command or str(config) not in command:
        raise ValueError(f"PID {pid} belongs to another process. Refusing to signal it. Inspect {pidfile}. Observed command: {command}")
    return pid


def signal_process(pid, sig):
    try:
        os.kill(pid, sig)
    except PermissionError:
        subprocess.run(["sudo", "/bin/kill", f"-{sig.name.removeprefix('SIG')}", str(pid)], check=True)


def configure_dns_logging(config, background):
    # dnsmasq reads this directive from the config after command-line options.
    # Use the generated config itself so a daemon cannot retain stderr logging.
    destination = str(config.parent / "dnsmasq.log") if background else "-"
    text, count = re.subn(r"^log-facility=.*$", lambda _: "log-facility=" + destination,
                          config.read_text(), flags=re.M)
    if count != 1:
        raise ValueError("DNS config must contain one log-facility directive; rerun configure.py")
    config.write_text(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=("dns", "nginx"))
    parser.add_argument("action", choices=("start", "stop", "reload", "check-stopped"))
    parser.add_argument("--background", action="store_true", help="start as a native daemon; used by setup.sh")
    args = parser.parse_args()
    dns = args.service == "dns"
    directory = ROOT / ("mac1_dns_client" if dns else "mac2_edge")
    name = "dnsmasq" if dns else "nginx"
    config = directory / "runtime" / f"{name}.conf"
    pidfile = directory / "runtime" / f"{name}.pid"
    pid = process_at(pidfile, config, name)
    if args.action in ("check-stopped", "start") and pid:
        raise ValueError(f"Project {name} already runs as PID {pid}. Stop it first, or reload nginx.")
    if args.action == "check-stopped":
        return 0
    if args.action == "stop":
        if not pid:
            print(f"Project {name} is already stopped.")
            return 0
        signal_process(pid, signal.SIGTERM if dns else signal.SIGQUIT)
        for _ in range(100):
            if process_at(pidfile, config, name) is None:
                print(f"Stopped project {name}.")
                return 0
            time.sleep(0.1)
        raise ValueError(f"Graceful stop sent to {pid}; still draining. Check its terminal and try stop again.")
    if args.action == "reload" and not pid:
        raise ValueError("Project nginx is not running. Use start_nginx.sh.")
    binary = brew_binary(name, name)
    if not config.is_file():
        raise ValueError(f"Missing {config}; run the role's configure.py first")
    env = load_env()
    if dns:
        if args.action == "start":
            configure_dns_logging(config, args.background)
        check = [binary, "--test", f"--conf-file={config}"]
        command = [binary, f"--conf-file={config}"]
        if not args.background:
            command.append("--keep-in-foreground")
    else:
        base = [binary, "-p", str(directory) + "/", "-c", str(config), "-e", str(directory / "runtime/error.log")]
        check = base + ["-t"]
        command = base if args.background else base + ["-g", "daemon off;"]
    # Never exec or signal a server after a failed native configuration test.
    privileged = dns or int(env["HTTPS_PORT"]) < 1024
    prefix = ["sudo"] if privileged and os.geteuid() != 0 else []
    subprocess.run(prefix + check, check=True)
    if args.action == "reload":
        signal_process(pid, signal.SIGHUP)
        print("nginx configuration validated; reload sent. Check runtime/error.log.")
        return 0
    if args.background:
        subprocess.run(prefix + command, check=True)
        for _ in range(50):
            pid = process_at(pidfile, config, name)
            if pid:
                print(f"Started project {name} in the background (PID {pid}). Logs: {directory / 'runtime'}")
                return 0
            time.sleep(0.1)
        raise ValueError(f"{name} did not create a live PID; inspect {directory / 'runtime'}")
    print(f"Starting project {name} in the foreground. Keep this terminal open; Ctrl+C stops it.", flush=True)
    os.execvp((prefix + command)[0], prefix + command)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        sys.exit(f"Service error: {exc}")
