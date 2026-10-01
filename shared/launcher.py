#!/usr/bin/env python3
"""Interactive setup and lifecycle menu for the four-Mac Phase 1 lab."""
import argparse
import contextlib
import fcntl
import hashlib
import ipaddress
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time

import client_dns
from env_loader import ROOT, load_env
from service_control import process_at

RUNTIME = ROOT / "shared/runtime"
ROLES = {1: "DNS + main client", 2: "nginx + HTTPS + load balancer", 3: "Backend A", 4: "Backend B + client"}
DIRECTORIES = {1: "mac1_dns_client", 2: "mac2_edge", 3: "mac3_backend_a", 4: "mac4_backend_b_client"}
CHILDREN = {}


def run(command, check=True, capture=False, timeout=None):
    result = subprocess.run(list(map(str, command)), cwd=ROOT, check=False, text=True,
                            capture_output=capture, timeout=timeout)
    if check and result.returncode:
        detail = result.stderr.strip() if capture else "See the command output above."
        raise ValueError(f"Command failed ({result.returncode}): {' '.join(map(str, command))}\n{detail}")
    return result


def script(relative, *args):
    return run(["bash", ROOT / relative, *args])


def prompt(message, default=None):
    answer = input(message + (f" [{default}]" if default is not None else "") + ": ").strip()
    return answer or (str(default) if default is not None else "")


def addresses():
    result = run(["/sbin/ifconfig"], capture=True)
    return list(dict.fromkeys(ip for ip in re.findall(r"\binet (\d+\.\d+\.\d+\.\d+)\b", result.stdout)
                             if not ipaddress.ip_address(ip).is_loopback))


def configuration_text(team, ips, https="8443", previous=None):
    text = (ROOT / "network.env.example").read_text()
    replacements = {"TEAM_NAME": team, "HTTPS_PORT": https, **{f"MAC{n}_IP": value for n, value in enumerate(ips, 1)}}
    for key in ("BACKEND_A_PORT", "BACKEND_B_PORT"):
        if previous and key in previous:
            replacements[key] = previous[key]
    for key, value in replacements.items():
        if "\n" in value or "\r" in value:
            raise ValueError("Configuration answers must each be one line")
        text = re.sub(r"^" + key + r"=.*$", lambda _: f"{key}={value}", text, flags=re.M)
    return text


def write_configuration(text):
    # Validate a temporary candidate before replacing the single shared config.
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=RUNTIME, suffix=".env", delete=False) as stream:
        stream.write(text)
        candidate = Path(stream.name)
    try:
        values = load_env(candidate)
        os.replace(candidate, ROOT / "network.env")
        return values
    finally:
        candidate.unlink(missing_ok=True)


def configure(role, force=False):
    if (ROOT / "network.env").exists() and not force:
        env = load_env()
        print("Using existing network.env; it will not be overwritten.")
    else:
        local = addresses()
        print(f"This Mac's IPv4 addresses: {', '.join(local) or 'none; connect to the LAN first'}")
        print("Enter the same four real LAN addresses on every Mac, or copy network.env between Macs.")
        previous = {}
        if (ROOT / "network.env").exists():
            try:
                previous = load_env()
            except ValueError:
                print("Existing configuration is invalid; the wizard will replace it only after validation.")
        while True:
            team = prompt("Team name", previous.get("TEAM_NAME", "team1"))
            ips = [prompt(f"Mac {n} IPv4", previous.get(f"MAC{n}_IP", local[0] if n == role and len(local) == 1 else None)) for n in range(1, 5)]
            port = prompt("HTTPS port", previous.get("HTTPS_PORT", "8443"))
            try:
                env = write_configuration(configuration_text(team, ips, port, previous))
                break
            except ValueError as exc:
                print(f"Please correct the configuration: {exc}")
        print(f"Saved {ROOT / 'network.env'}. Role aliases and both domains were filled automatically.")
    for n in range(1, 5):
        print(f"  Mac {n}: {env[f'MAC{n}_IP']} - {ROLES[n]}")
    print(f"  App: https://{env['APP_DOMAIN']}:{env['HTTPS_PORT']}")
    return env


def check_local_role(role, env):
    actual = addresses()
    if env[f"MAC{role}_IP"] not in actual:
        raise ValueError(f"You selected Mac {role}, configured as {env[f'MAC{role}_IP']}, but this Mac has {actual}. "
                         "Select the correct role or use menu option 5 to correct network.env.")


def find_brew():
    return shutil.which("brew") or next((str(p) for p in (Path("/opt/homebrew/bin/brew"), Path("/usr/local/bin/brew")) if p.is_file()), None)


def dependencies(role):
    formulas = {1: ["dnsmasq"], 2: ["nginx", "openssl@3"], 3: [], 4: []}[role]
    if not formulas:
        return
    brew = find_brew()
    if not brew:
        script("setup.sh", "--install-brew")
        brew = find_brew()
    if not brew:
        raise ValueError("Homebrew is unavailable after installation; rerun setup.sh after completing its installer")
    os.environ["PATH"] = str(Path(brew).parent) + os.pathsep + os.environ.get("PATH", "")
    missing = [name for name in formulas if run([brew, "list", "--versions", name], check=False, capture=True).returncode]
    if missing:
        print("Installing missing dependencies: " + ", ".join(missing))
        run([brew, "install", *missing])
    else:
        print("Required dependencies already installed.")


def running(role):
    directory = ROOT / DIRECTORIES[role]
    if role in (1, 2):
        name = "dnsmasq" if role == 1 else "nginx"
        return process_at(directory / f"runtime/{name}.pid", directory / f"runtime/{name}.conf", name)
    name = "backend_a.py" if role == 3 else "backend_b.py"
    return process_at(directory / "runtime/backend.pid", Path(DIRECTORIES[role]) / name, name)


def stop_service(role):
    script(f"{DIRECTORIES[role]}/" + ("stop_dns.sh" if role == 1 else "stop_nginx.sh" if role == 2 else "stop_backend.sh"))
    child = CHILDREN.pop(role, None)
    if child is not None:
        child.wait(timeout=5)


def start_backend(role, env):
    if running(role):
        stop_service(role)
    letter = "A" if role == 3 else "B"
    directory = ROOT / DIRECTORIES[role]
    runtime = directory / "runtime"
    runtime.mkdir(exist_ok=True)
    logfile = runtime / "backend.log"
    with logfile.open("a") as log:
        child = subprocess.Popen([sys.executable, "-u", str(directory / f"backend_{letter.lower()}.py")],
                                 cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    CHILDREN[role] = child
    for _ in range(100):
        if child.poll() is not None:
            raise ValueError(f"Backend {letter} exited. See {logfile}\n{logfile.read_text()[-2000:]}")
        if running(role):
            print(f"Backend {letter} started on {env[f'BACKEND_{letter}_IP']}:{env[f'BACKEND_{letter}_PORT']} (PID {child.pid}).")
            print(f"Log: {logfile}")
            return
        time.sleep(0.1)
    child.terminate()
    child.wait(timeout=5)
    raise ValueError(f"Backend {letter} did not become ready; see {logfile}")


def wait_for(description, probe, seconds):
    print(f"Waiting for {description}. Start the other Macs now if needed. (up to {seconds}s)", flush=True)
    deadline = time.monotonic() + seconds
    while True:
        if probe():
            print(f"Ready: {description}")
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError(f"Still waiting for {description}. Local services already started are left running. "
                             "Start the other Macs, then choose option 2 to finish clients / verify, or option 1 to retry full setup.")
        time.sleep(min(2, remaining))


def tcp_ready(ip, port):
    try:
        with socket.create_connection((ip, int(port)), timeout=1):
            return True
    except OSError:
        return False


def dns_ready(env):
    for name in (env["APP_DOMAIN"], env["API_DOMAIN"]):
        result = run(["/usr/bin/dig", f"@{env['DNS_IP']}", "+time=1", "+tries=1", "+short", name, "A"], check=False, capture=True, timeout=4)
        if result.returncode or result.stdout.strip() != env["EDGE_IP"]:
            return False
    return True


def fingerprint(path):
    der = ssl.PEM_cert_to_DER_cert(Path(path).read_text())
    return hashlib.sha256(der).hexdigest().upper()


def show_fingerprint(path):
    value = fingerprint(path)
    print("\nCompare this full SHA-256 fingerprint on the client Macs:")
    print(":".join(value[i:i + 2] for i in range(0, len(value), 2)), flush=True)
    return value


def fetch_certificate(env):
    # Bootstrap ONLY: read the presented certificate, without making an HTTP
    # request. It is untrusted until its fingerprint is compared with Mac 2.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((env["EDGE_IP"], int(env["HTTPS_PORT"])), timeout=5) as raw:
        with context.wrap_socket(raw, server_hostname=env["APP_DOMAIN"]) as tls:
            der = tls.getpeercert(binary_form=True)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    candidate = RUNTIME / "edge-candidate.crt"
    candidate.write_text(ssl.DER_cert_to_PEM_cert(der))
    certificate = run(["/usr/bin/openssl", "x509", "-in", candidate, "-noout", "-text"], capture=True).stdout
    names = set(re.findall(r"DNS:([^,\s]+)", certificate))
    if not {env["APP_DOMAIN"], env["API_DOMAIN"]}.issubset(names):
        raise ValueError("The certificate returned by Mac 2 is missing a required DNS SAN. Check Mac 2's network.env and certificate.")
    return candidate


def system_trusts(path, env):
    return all(run(["/usr/bin/security", "verify-cert", "-c", path, "-p", "ssl", "-s", env[key]],
                   check=False, capture=True, timeout=15).returncode == 0 for key in ("APP_DOMAIN", "API_DOMAIN"))


def trust_for_client(role, env):
    candidate = ROOT / "mac2_edge/certs/server.crt" if role == 2 else fetch_certificate(env)
    if system_trusts(candidate, env):
        print("Project certificate is already trusted for both domain names.")
    else:
        if role != 2:
            expected = show_fingerprint(candidate)
            print("The certificate was downloaded automatically, but has not been trusted yet.")
            print("Paste the full fingerprint DISPLAYED ON MAC 2 to verify its identity (q to finish later).")
            supplied = prompt("Mac 2 SHA-256 fingerprint")
            if re.sub(r"[:\s]", "", supplied).upper() != expected:
                raise ValueError("Fingerprint did not match; no trust changes made. Check Mac 2 and retry option 2.")
        print("Installing this project's certificate into the macOS System trust store; sudo may ask for your password.")
        script("shared/trust_certificate.sh", str(candidate))
        if not system_trusts(candidate, env):
            raise ValueError("Certificate installation finished, but macOS verification still failed. Inspect the trust-script output.")
    destination = ROOT / "shared/trusted/server.crt"
    destination.parent.mkdir(exist_ok=True)
    shutil.copyfile(candidate, destination)


def set_dns(role, env):
    matches = []
    for service in client_dns.services():
        result = run(["/usr/sbin/ipconfig", "getifaddr", service["device"]], check=False, capture=True)
        if result.stdout.strip() == env[f"MAC{role}_IP"]:
            matches.append(service["name"])
    args = ["--service", matches[0]] if len(matches) == 1 else []
    script("shared/set_client_dns.sh", *args)


def finish_client(role, env, wait_seconds):
    if role == 3:
        script("mac3_backend_a/verify.sh")
        return
    if role == 2 and not running(2):
        raise ValueError("nginx has not started yet. Choose option 1 after both backends are running.")
    wait_for("Mac 1 DNS with both records pointing to Mac 2", lambda: dns_ready(env), wait_seconds)
    wait_for("Mac 2 HTTPS edge", lambda: tcp_ready(env["EDGE_IP"], env["HTTPS_PORT"]), wait_seconds)
    trust_for_client(role, env)
    set_dns(role, env)
    script("shared/verify_phase1.sh")
    if role == 2:
        show_fingerprint(ROOT / "mac2_edge/certs/server.crt")
    print(f"Open in your browser: https://{env['APP_DOMAIN']}:{env['HTTPS_PORT']}/")


def setup(role, wait_seconds):
    env = configure(role)
    check_local_role(role, env)
    dependencies(role)
    if role in (3, 4):
        start_backend(role, env)
    elif role == 1:
        if running(role):
            stop_service(role)
        script("mac1_dns_client/start_dns.sh", "--background")
    else:
        run([sys.executable, ROOT / "mac2_edge/configure.py"])
        script("mac2_edge/generate_certificate.sh")
        show_fingerprint(ROOT / "mac2_edge/certs/server.crt")
        wait_for("Backend A on Mac 3 and Backend B on Mac 4", lambda: tcp_ready(env["BACKEND_A_IP"], env["BACKEND_A_PORT"]) and tcp_ready(env["BACKEND_B_IP"], env["BACKEND_B_PORT"]), wait_seconds)
        script("shared/test_backends.sh")
        if running(role):
            stop_service(role)
        script("mac2_edge/start_nginx.sh", "--background")
    # Inventory is useful even before all remote components become ready.
    result = run(["bash", ROOT / "shared/record_inventory.sh", str(role)], check=False)
    if result.returncode:
        print("Inventory capture needs attention; you can rerun shared/record_inventory.sh after checking the LAN interface.")
    finish_client(role, env, wait_seconds)
    print(f"\nPASS: Mac {role} setup completed. Services keep running after you exit this menu.")


def stop_and_restore(role):
    # Restore first; if restore fails, preserve the working DNS service.
    if role in (1, 2, 4):
        script("shared/restore_client_dns.sh")
    stop_service(role)
    print(f"Mac {role} stopped. Other Macs must use their own stop/restore menu.")


def status(role):
    pid = running(role)
    print(f"Mac {role} ({ROLES[role]}): {'running, PID ' + str(pid) if pid else 'stopped'}")
    for log in sorted((ROOT / DIRECTORIES[role] / "runtime").glob("*.log")):
        print(f"\n{log}\n" + "\n".join(log.read_text(errors="replace").splitlines()[-8:]))
    if (ROOT / "shared/runtime/client-dns.json").exists():
        print("Original DNS backup is present; option 4 restores it.")
    if role == 2 and (ROOT / "mac2_edge/certs/server.crt").exists():
        show_fingerprint(ROOT / "mac2_edge/certs/server.crt")


@contextlib.contextmanager
def action_lock():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with (RUNTIME / "launcher.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another setup action is running in this repository; finish it first.") from exc
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def perform(action, role, wait_seconds):
    if action == "status":
        status(role)
        return
    with action_lock():
        if action == "setup":
            setup(role, wait_seconds)
        elif action == "verify":
            env = load_env()
            check_local_role(role, env)
            finish_client(role, env, wait_seconds)
        elif action == "stop":
            stop_and_restore(role)
        else:
            if running(role):
                raise ValueError("Use option 4 to stop/restore this Mac before editing network.env, then option 1 to apply it.")
            configure(role, force=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", type=int, choices=ROLES, help="skip role selection (1, 2, 3, or 4)")
    parser.add_argument("--action", choices=("setup", "verify", "status", "stop", "configure"), help="perform one action instead of showing the menu")
    parser.add_argument("--wait-seconds", type=int, default=90, help="how long to wait for other Macs, per dependency (default: 90)")
    args = parser.parse_args()
    if platform.system() != "Darwin" or os.geteuid() == 0:
        raise ValueError("Run bash setup.sh on macOS as your normal user; it requests sudo when needed.")
    if args.wait_seconds < 0:
        raise ValueError("--wait-seconds cannot be negative")
    print("CN Private Network - Phase 1 setup")
    print(f"Repository: {ROOT}")
    print("Connect all four Macs to the same LAN. Run this launcher on all four; each starts only its own service.")
    if args.role is None:
        for role, label in ROLES.items():
            print(f"  {role}. Mac {role} - {label}")
        answer = prompt("Which Mac is this? Enter 1, 2, 3, or 4")
        if answer not in ("1", "2", "3", "4"):
            raise ValueError("Choose a Mac number from 1 to 4")
        role = int(answer)
    else:
        role = args.role
    if args.action:
        perform(args.action, role, args.wait_seconds)
        return
    actions = {"1": "setup", "2": "verify", "3": "status", "4": "stop", "5": "configure"}
    while True:
        print(f"\nMac {role} - {ROLES[role]}\n1. Full setup / start\n2. Finish client setup / run checks\n3. Status, logs, and certificate fingerprint\n4. Stop this Mac's service and restore its original DNS\n5. Create / edit shared network configuration\n0. Exit menu (services keep running)")
        choice = prompt("Choose", "1")
        if choice == "0":
            print("Services keep running. Reopen bash setup.sh and choose 4 when finished.")
            return
        if choice not in actions:
            print("Choose one of the displayed numbers.")
            continue
        try:
            perform(actions[choice], role, args.wait_seconds)
        except KeyboardInterrupt:
            print("\nSetup interrupted. Started services may still be running; use status or stop/restore.")
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            print(f"\nSetup needs attention: {exc}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nExited. Use bash setup.sh to check status or stop/restore any started services.")
        sys.exit(1)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        sys.exit(f"Setup error: {exc}")
