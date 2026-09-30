#!/usr/bin/env python3
import os
import re
import shutil
import subprocess
from pathlib import Path
from env_loader import ROOT, load_env


def brew_binary(formula, name):
    if shutil.which("brew"):
        result = subprocess.run(["brew", "--prefix", formula], capture_output=True, text=True)
        if result.returncode == 0:
            for directory in ("sbin", "bin"):
                candidate = Path(result.stdout.strip()) / directory / name
                if candidate.is_file():
                    return str(candidate)
    raise ValueError(f"Homebrew {name} not found. Run: brew install {formula}")


def render(role):
    values = load_env()
    directory = ROOT / ("mac1_dns_client" if role == "dns" else "mac2_edge")
    runtime = directory / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    # Reject characters which have special meanings in native config paths.
    if any(c in str(ROOT) for c in '\n\r"\\$;#'):
        raise ValueError("Move the repository to a path without newline, quote, backslash, dollar, semicolon, or # characters. Spaces are supported.")
    if role == "dns":
        filename = "dnsmasq.conf"
        values["PID_FILE"] = str(runtime / "dnsmasq.pid")
    else:
        filename = "nginx.conf"
        nginx = brew_binary("nginx", "nginx")
        info = subprocess.run([nginx, "-V"], capture_output=True, text=True, check=True).stderr
        version = re.search(r"nginx/(\d+)\.(\d+)\.(\d+)", info)
        supports_h2 = "--with-http_v2_module" in info
        modern = version and tuple(map(int, version.groups())) >= (1, 25, 1)
        values["HTTP2_LISTEN"] = " http2" if supports_h2 and not modern else ""
        values["HTTP2_DIRECTIVE"] = "http2 on;" if supports_h2 and modern else "# HTTP/2 directive not needed for this build."
        values["RUNTIME"] = str(runtime)
        values["CERTS"] = str(directory / "certs")
        for name in ("client_body", "proxy_temp", "fastcgi_temp", "uwsgi_temp", "scgi_temp"):
            (runtime / name).mkdir(exist_ok=True)
        for name in ("error.log", "access.log"):
            (runtime / name).touch(exist_ok=True)
        print(f"HTTP/2 {'enabled' if supports_h2 else 'unavailable in installed nginx; HTTP/1.1 enabled'}")
    template = (directory / (filename + ".template")).read_text()
    rendered = re.sub(r"@@([A-Z0-9_]+)@@", lambda m: values[m[1]], template)
    destination = runtime / filename
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(rendered)
    os.replace(temporary, destination)
    print(f"Generated {destination}")
    return destination
