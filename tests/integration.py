#!/usr/bin/env python3
"""Real nginx/dnsmasq loopback checks in a disposable copy; no OS DNS/trust changes.

Developer test only. The official demo uses shared/test_*.sh on the four Macs.
"""
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))
from env_loader import load_env
from render_config import brew_binary


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def available_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run(command, cwd, ok=True):
    result = subprocess.run(list(map(str, command)), cwd=cwd, capture_output=True, text=True, timeout=30)
    if ok and result.returncode:
        raise RuntimeError(f"Command failed: {command}\n{result.stdout}\n{result.stderr}")
    return result


def wait_port(process, port):
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError(f"Server exited early with {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"Server never opened port {port}")


def main():
    nginx = brew_binary("nginx", "nginx")
    dnsmasq = brew_binary("dnsmasq", "dnsmasq")
    openssl = brew_binary("openssl@3", "openssl")
    with tempfile.TemporaryDirectory(prefix="cn phase1 integration ") as temporary:
        root = Path(temporary).resolve() / "CN Private Network"
        shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns("runtime", "__pycache__", "certs", "trusted", "collected", "network.env", ".git"))
        (root / "mac2_edge/certs").mkdir()
        env = load_env(ROOT / "network.env.example")
        ports = set()
        while len(ports) < 4:
            ports.add(available_port())
        backend_a, backend_b, edge_port, dns_port = sorted(ports)
        env.update(BACKEND_A_PORT=str(backend_a), BACKEND_B_PORT=str(backend_b), HTTPS_PORT=str(edge_port))
        (root / "network.env").write_text("\n".join(f"{k}={v}" for k, v in env.items()) + "\n")
        python = sys.executable
        processes, logs = [], []

        def start(command, label):
            log = open(root / f"{label}.log", "w+")
            logs.append(log)
            process = subprocess.Popen(list(map(str, command)), cwd=root, stdout=log, stderr=subprocess.STDOUT)
            processes.append(process)
            return process

        def curl(path="/api/status", domain=None, extra=(), verify=True):
            name = domain or env["APP_DOMAIN"]
            command = ["/usr/bin/curl", "--disable", "--noproxy", "*", "--silent", "--show-error", "--connect-timeout", "2", "--max-time", "15",
                       "--resolve", f"{name}:{edge_port}:127.0.0.1", "-i"]
            if verify:
                command.extend(["--cacert", str(root / "mac2_edge/certs/server.crt")])
            command.extend(extra)
            command.append(f"https://{name}:{edge_port}{path}")
            return run(command, root, ok=False)

        try:
            # Independent of working directory and containing spaces.
            run([python, root / "mac1_dns_client/configure.py"], Path(temporary))
            run([python, root / "mac2_edge/configure.py"], Path(temporary))
            for shell in ("/bin/bash", "/bin/zsh"):
                result = run([shell, "-c", 'source "$1/shared/common.sh"; cn_load_env; printf "%s" "$EDGE_IP"', "cn-test", root], Path(temporary))
                require(result.stdout == env["EDGE_IP"], f"{shell} configuration sourcing failed")
            dns_config = root / "mac1_dns_client/runtime/dnsmasq.conf"
            original_dns = dns_config.read_text()
            for name in (env["APP_DOMAIN"], env["API_DOMAIN"]):
                require(f"host-record={name},{env['EDGE_IP']}" in original_dns, "DNS generated wrong edge mapping")
            run([dnsmasq, "--test", f"--conf-file={dns_config}"], root)
            native = root / "mac2_edge/runtime/nginx.conf"
            original_nginx = native.read_text()
            for role in ("A", "B"):
                require(f"server {env[f'BACKEND_{role}_IP']}:{env[f'BACKEND_{role}_PORT']};" in original_nginx, "Incorrect upstream configuration")
            print("PASS: template role mapping, native DNS syntax, paths with spaces, bash and zsh loading", flush=True)

            run(["bash", "mac2_edge/generate_certificate.sh"], root)
            cert = root / "mac2_edge/certs/server.crt"
            before = cert.read_bytes()
            run(["bash", "mac2_edge/generate_certificate.sh"], root)
            require(cert.read_bytes() == before, "Repeat generation replaced certificate")
            config_file = root / "network.env"
            original_env_text = config_file.read_text()
            changed = dict(env)
            changed["TEAM_NAME"] += "renamed"
            changed["APP_DOMAIN"] = f"app.{changed['TEAM_NAME']}.test"
            changed["API_DOMAIN"] = f"api.{changed['TEAM_NAME']}.test"
            config_file.write_text("\n".join(f"{k}={v}" for k, v in changed.items()) + "\n")
            mismatch = run(["bash", "mac2_edge/generate_certificate.sh"], root, ok=False)
            config_file.write_text(original_env_text)
            require(mismatch.returncode != 0 and cert.read_bytes() == before, "Certificate reuse accepted a renamed domain")
            run([openssl, "verify", "-purpose", "sslserver", "-CAfile", cert, cert], root)
            for name in (env["APP_DOMAIN"], env["API_DOMAIN"]):
                run([openssl, "x509", "-in", cert, "-noout", "-checkhost", name], root)
            require((root / "mac2_edge/certs/server.key").stat().st_mode & 0o777 == 0o600, "Private key permission is not 600")
            print("PASS: real SAN certificate, both names, SSL purpose, private permissions, safe reuse", flush=True)

            a = start([python, "mac3_backend_a/backend_a.py"], "backend-a")
            b = start(["bash", "mac4_backend_b_client/start_backend.sh"], "backend-b")
            wait_port(a, backend_a)
            wait_port(b, backend_b)
            for port, name in ((backend_a, "A"), (backend_b, "B")):
                result = run(["/usr/bin/curl", "--disable", "--noproxy", "*", "-si", f"http://127.0.0.1:{port}/api/status"], root)
                require(f"X-Backend: {name}" in result.stdout, "Backend header missing")
                require(json.loads(result.stdout.split("\n\n", 1)[1]) == {"backend": name, "status": "ok"}, "Backend body mismatch")
                listener = run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"], root)
                require(f"*:{port}" in listener.stdout, "Backend is not bound to all interfaces")
            print("PASS: both real backend entry points, wildcard LAN binding, headers and JSON", flush=True)

            # Exercise the actual start wrapper and graceful stop before loopback adaptation.
            edge = start(["bash", "mac2_edge/start_nginx.sh"], "nginx-start-wrapper")
            wait_port(edge, edge_port)
            run(["bash", "mac2_edge/stop_nginx.sh"], root)
            edge.wait(timeout=10)
            native.write_text(original_nginx.replace(env["BACKEND_A_IP"], "127.0.0.1").replace(env["BACKEND_B_IP"], "127.0.0.1"))
            edge = start([python, "shared/service_control.py", "nginx", "start"], "nginx-loopback")
            wait_port(edge, edge_port)
            observed = set()
            for _ in range(10):
                result = curl(extra=("--http1.1",))
                require(result.returncode == 0 and "HTTP/1.1 200" in result.stdout, result.stderr + result.stdout)
                observed.add(json.loads(result.stdout.split("\n\n", 1)[1])["backend"])
            require(observed == {"A", "B"}, "Real nginx did not distribute to both backends")
            require(curl(domain=env["API_DOMAIN"]).returncode == 0, "API SAN did not validate")
            require(curl(domain="wrong-name.test").returncode == 60, "Wrong certificate hostname was accepted")
            require(curl(verify=False).returncode == 60, "Untrusted certificate unexpectedly accepted")
            result = curl(extra=("--http2",))
            if "http2 on;" in original_nginx or "ssl http2;" in original_nginx:
                require(result.returncode == 0 and "HTTP/2 200" in result.stdout, "HTTP/2 did not negotiate")
            result = curl(extra=("--tlsv1.2", "--tls-max", "1.2"))
            require(result.returncode == 0 and "200" in result.stdout, "TLS 1.2 evidence connection failed")
            print("PASS: nginx -t/start/stop, round robin, trusted file verification, wrong-name/untrusted rejection, HTTP/1.1/2, TLS 1.2", flush=True)

            result = curl("/cache-demo")
            require('Cache-Control: public, max-age=60'.lower() in result.stdout.lower() and 'ETag: "cn-project-v1"'.lower() in result.stdout.lower(), "Missing cache headers")
            conditional = curl("/cache-demo", extra=("-H", 'If-None-Match: "cn-project-v1"'))
            require("304" in conditional.stdout.splitlines()[0], "Conditional request did not return 304")
            require(conditional.stdout.split("\n\n", 1)[1] == "", "304 contained a body")
            run([python, "shared/service_control.py", "nginx", "reload"], root)
            require(curl().returncode == 0, "Reload failed")
            print("PASS: cache headers, 304 without body, validated nginx reload", flush=True)

            run(["bash", "mac3_backend_a/stop_backend.sh"], root)
            a.wait(timeout=10)
            for _ in range(3):
                result = curl()
                require('"backend": "B"' in result.stdout and "200" in result.stdout.splitlines()[0], "Default one-backend retry failed")
            run(["bash", "mac4_backend_b_client/stop_backend.sh"], root)
            b.wait(timeout=10)
            result = curl()
            require("502" in result.stdout.splitlines()[0], "Both stopped backends did not produce 502")
            print("PASS: safe backend stop scripts, one-backend default retry, both-stopped 502", flush=True)
            a = start([python, "mac3_backend_a/backend_a.py"], "backend-a-restored")
            b = start([python, "mac4_backend_b_client/backend_b.py"], "backend-b-restored")
            wait_port(a, backend_a)
            wait_port(b, backend_b)
            time.sleep(11)
            restored = set()
            for _ in range(10):
                result = curl(extra=("--http1.1",))
                require(result.returncode == 0 and "HTTP/1.1 200" in result.stdout, "Restored backend response failed")
                restored.add(json.loads(result.stdout.split("\n\n", 1)[1])["backend"])
            require(restored == {"A", "B"}, "Backend restart did not restore round robin")
            print("PASS: both backend restart commands restore round robin after the default retry interval", flush=True)

            # Only this disposable config uses loopback and an unprivileged DNS port.
            def local_dns():
                dns_config.write_text(dns_config.read_text().replace("port=53\n", f"port={dns_port}\n").replace(f"127.0.0.1,{env['DNS_IP']}", "127.0.0.1"))

            # A separate local resolver proves forwarding without external
            # internet access. It deliberately knows a .test name too, so we
            # can prove that the project keeps that namespace local.
            forward_port = available_port()
            forward_config = root / "forward-test.conf"
            forward_config.write_text(f"port={forward_port}\nlisten-address=127.0.0.1\nbind-interfaces\nno-resolv\nno-hosts\n"
                                      "host-record=outside.example,192.0.2.45\n"
                                      "host-record=should-stay-private.test,192.0.2.46\n")
            forwarder = start([dnsmasq, "--keep-in-foreground", f"--conf-file={forward_config}"], "forward-test")
            wait_port(forwarder, forward_port)
            dns_config.write_text(dns_config.read_text().replace(f"server={env['UPSTREAM_DNS']}", f"server=127.0.0.1#{forward_port}"))
            local_dns()
            dns = start([dnsmasq, "--keep-in-foreground", f"--conf-file={dns_config}"], "dns")
            wait_port(dns, dns_port)
            for name in (env["APP_DOMAIN"], env["API_DOMAIN"]):
                for transport in ([], ["+tcp"]):
                    result = run(["/usr/bin/dig", "@127.0.0.1", "-p", dns_port, "+short", *transport, name, "A"], root)
                    require(result.stdout.strip() == env["EDGE_IP"], "dnsmasq UDP/TCP A response incorrect")
            forwarded = run(["/usr/bin/dig", "@127.0.0.1", "-p", dns_port, "+short", "outside.example", "A"], root)
            require(forwarded.stdout.strip() == "192.0.2.45", "Ordinary DNS query was not forwarded")
            private = run(["/usr/bin/dig", "@127.0.0.1", "-p", dns_port, "+noall", "+comments", "should-stay-private.test", "A"], root)
            require("status: NXDOMAIN" in private.stdout, ".test query leaked to the upstream resolver")
            print("PASS: ordinary DNS forwarding and .test namespace stays local", flush=True)
            run(["bash", "mac1_dns_client/stop_dns.sh"], root)
            dns.wait(timeout=10)
            run([python, "shared/failure_injection.py", "wrong-record"], root)
            dns = start([dnsmasq, "--keep-in-foreground", f"--conf-file={dns_config}"], "dns-wrong")
            wait_port(dns, dns_port)
            result = run(["dig", "@127.0.0.1", "-p", dns_port, "+short", env["APP_DOMAIN"]], root)
            require(result.stdout.strip() == env["MAC3_IP"], "Wrong-record experiment not applied")
            run(["bash", "mac1_dns_client/stop_dns.sh"], root)
            dns.wait(timeout=10)
            run([python, "shared/failure_injection.py", "restore-record"], root)
            require(dns_config.read_text() == original_dns, "DNS restore did not reproduce original config")
            print("PASS: real UDP/TCP DNS for both names, DNS stop, wrong-record injection and exact restoration", flush=True)

            local_dns()
            dns_log = root / "mac1_dns_client/runtime/dnsmasq.log"
            run([python, "-c", "import sys; from pathlib import Path; sys.path.insert(0,'shared'); from service_control import configure_dns_logging; configure_dns_logging(Path('mac1_dns_client/runtime/dnsmasq.conf').resolve(), True)"], root)
            run([dnsmasq, f"--conf-file={dns_config}"], root)
            result = run(["dig", "@127.0.0.1", "-p", dns_port, "+short", env["APP_DOMAIN"]], root)
            require(result.stdout.strip() == env["EDGE_IP"], "Background DNS response incorrect")
            require(dns_log.exists() and "started" in dns_log.read_text(), "Background DNS log is missing")
            run(["bash", "mac1_dns_client/stop_dns.sh"], root)
            print("PASS: native background DNS, project-local logs, safe daemon stop", flush=True)

            # A bad native config must never result in a listening service.
            run(["bash", "mac2_edge/stop_nginx.sh"], root)
            edge.wait(timeout=10)
            run([python, "shared/service_control.py", "nginx", "start", "--background"], root)
            require(curl().returncode == 0, "Background nginx HTTPS failed")
            bootstrap = run([python, "-c", "import sys; sys.path.insert(0, 'shared'); import launcher; from env_loader import load_env; env=load_env(); env['EDGE_IP']='127.0.0.1'; cert=launcher.fetch_certificate(env); assert launcher.fingerprint(cert)==launcher.fingerprint('mac2_edge/certs/server.crt'); print('Certificate bootstrap fingerprint matches the edge')"], root)
            require("matches" in bootstrap.stdout, "Certificate bootstrap check did not complete")
            run(["bash", "mac2_edge/stop_nginx.sh"], root)
            print("PASS: native background nginx and automatic public-certificate retrieval with matching fingerprint", flush=True)
            native.write_text("invalid_directive;\n")
            result = run([python, "shared/service_control.py", "nginx", "start"], root, ok=False)
            require(result.returncode != 0, "Bad nginx configuration was accepted")
            print("PASS: invalid nginx configuration prevents startup", flush=True)
        except Exception:
            for log in logs:
                log.flush()
                log.seek(0)
                print(f"\n--- {Path(log.name).name} ---\n{log.read()[-6000:]}", file=sys.stderr)
            raise
        finally:
            # Native daemon tests outlive their launching subprocess; stop only
            # this disposable repository's recorded processes before cleanup.
            for role, name, stop in (("mac1_dns_client", "dnsmasq", "stop_dns.sh"), ("mac2_edge", "nginx", "stop_nginx.sh")):
                if (root / role / "runtime" / f"{name}.pid").exists():
                    run(["bash", root / role / stop], root, ok=False)
            for process in reversed(processes):
                if process.poll() is None:
                    process.send_signal(signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            for log in logs:
                log.close()
    print("PASS: all isolated integration checks; no system DNS or trust settings changed.")


if __name__ == "__main__":
    main()
