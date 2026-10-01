#!/usr/bin/env python3
"""Observable Phase 1 checks: failures always exit nonzero."""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from env_loader import load_env


def require(condition, message):
    if not condition:
        raise ValueError(message)


def request(url, headers=(), version="--http1.1", show=True):
    # macOS curl uses the System keychain. Ignore personal curlrc and proxies.
    with tempfile.TemporaryDirectory(prefix="cn-check-") as tmp:
        head, body = Path(tmp) / "headers", Path(tmp) / "body"
        command = ["/usr/bin/curl", "--disable", "--noproxy", "*", "--ipv4", version,
                   "--silent", "--show-error", "--connect-timeout", "4", "--max-time", "15",
                   "--dump-header", str(head), "--output", str(body), "--write-out", "%{http_code} %{http_version}"]
        for header in headers:
            command.extend(["--header", header])
        # Remove inherited CA overrides: official checks prove system trust.
        environment = {k: v for k, v in os.environ.items() if k not in ("CURL_CA_BUNDLE", "SSL_CERT_FILE", "SSL_CERT_DIR")}
        result = subprocess.run(command + [url], capture_output=True, text=True, env=environment)
        if result.returncode:
            raise ValueError(f"curl failed for {url}: {result.stderr.strip()} (check DNS, TCP reachability, and installed certificate trust)")
        text = head.read_text()
        payload = body.read_bytes()
        if show:
            for header in headers:
                print(f"Request header: {header}")
            print(f"\n{url}\n{text.strip()}")
            if payload:
                print(payload.decode(errors="replace").strip())
        status, protocol = result.stdout.split()
        parsed = {}
        for line in text.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                parsed[key.lower()] = value.strip()
        return int(status), protocol, parsed, payload


def status_response(url, backend=None, show=True):
    code, version, headers, body = request(url, show=show)
    require(code == 200, f"Expected 200, got {code}")
    data = json.loads(body)
    actual = headers.get("x-backend")
    require(actual in ("A", "B"), "Missing or invalid X-Backend header")
    require(data == {"backend": actual, "status": "ok"}, "Backend JSON does not match X-Backend/status")
    require(backend is None or actual == backend, f"Expected Backend {backend}, got {actual}")
    require(headers.get("content-type", "").startswith("application/json"), "Missing JSON Content-Type")
    require(headers.get("content-length") == str(len(body)), "Wrong Content-Length")
    return actual


def test_dns(env):
    for resolver in (f"@{env['DNS_IP']}", None):
        for key in ("APP_DOMAIN", "API_DOMAIN"):
            command = ["/usr/bin/dig", "+time=2", "+tries=1", "+noall", "+answer", "+comments", "+stats"]
            if resolver:
                command.append(resolver)
            result = subprocess.run(command + [env[key], "A"], capture_output=True, text=True)
            print("\n$ " + " ".join(command + [env[key], "A"]))
            print(result.stdout.strip())
            require(result.returncode == 0, result.stderr or "dig could not contact the resolver")
            require(f"SERVER: {env['DNS_IP']}#53" in result.stdout,
                    f"This query used a resolver other than project DNS {env['DNS_IP']}. "
                    "The saved service setting may differ from the active resolver. "
                    "Retry bash shared/set_client_dns.sh, then bash shared/test_dns.sh. "
                    "If it persists, inspect: scutil --dns; cat /etc/resolv.conf; "
                    "networksetup -listnetworkserviceorder. Keep the original DNS backup.")
            require("status: NOERROR" in result.stdout, f"DNS did not return NOERROR for {env[key]}")
            answers = re.findall(r"^" + re.escape(env[key]) + r"\.\s+\d+\s+IN\s+A\s+(\S+)", result.stdout, re.M)
            require(answers == [env["EDGE_IP"]], f"{env[key]} should resolve only to {env['EDGE_IP']}; got {answers}")
    print("PASS: both names resolve to Mac 2 via direct and configured Mac 1 DNS.")


def test_caching(url):
    code, _, headers, body = request(url + "/cache-demo")
    require(code == 200 and bool(body), "Normal cache request must return 200 with a body")
    require(headers.get("cache-control") == "public, max-age=60", "Incorrect Cache-Control")
    require(headers.get("etag") == '"cn-project-v1"', "Incorrect ETag")
    code, _, conditional, body = request(url + "/cache-demo", [f"If-None-Match: {headers['etag']}"])
    require(code == 304, f"Expected 304 Not Modified; received {code}")
    require(body == b"", "304 must not contain a response body")
    require(conditional.get("etag") == headers["etag"], "304 validator changed")
    require(conditional.get("cache-control") == headers["cache-control"], "304 cache policy changed")
    print("PASS: full 200 response, Cache-Control, ETag, conditional request, and bodyless 304 Not Modified.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("check", choices=("backends", "backend-a", "backend-b", "dns", "https", "balancing", "caching"))
    parser.add_argument("--http2", action="store_true", help="require HTTP/2 for the HTTPS test")
    parser.add_argument("--count", type=int, default=10, help="load-balancing request count, at least 2")
    args = parser.parse_args()
    env = load_env()
    url = f"https://{env['APP_DOMAIN']}:{env['HTTPS_PORT']}"
    if args.check in ("backends", "backend-a", "backend-b"):
        names = ("A", "B") if args.check == "backends" else (args.check[-1].upper(),)
        for name in names:
            status_response(f"http://{env[f'BACKEND_{name}_IP']}:{env[f'BACKEND_{name}_PORT']}/api/status", name)
            print(f"PASS: direct Backend {name} JSON and X-Backend.")
    elif args.check == "dns":
        test_dns(env)
    elif args.check == "https":
        for domain in (env["APP_DOMAIN"], env["API_DOMAIN"]):
            target = f"https://{domain}:{env['HTTPS_PORT']}/api/status"
            status_response(target)
            if args.http2:
                code, version, _, _ = request(target, version="--http2")
                require(code == 200 and version == "2", "HTTP/2 not negotiated; check nginx -V and curl --version")
        print("PASS: HTTPS by both DNS names, system certificate trust, HTTP/1.1" + (", and HTTP/2." if args.http2 else "."))
    elif args.check == "balancing":
        require(args.count >= 2, "Use --count of at least 2")
        observed = set()
        for number in range(1, args.count + 1):
            backend = status_response(url + "/api/status", show=False)
            observed.add(backend)
            print(f"Request {number:02d}: X-Backend: {backend}")
        require(observed == {"A", "B"}, f"Both backends required, observed only {sorted(observed)}")
        print("PASS: both Backend A and Backend B observed through nginx.")
    else:
        test_caching(url)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
