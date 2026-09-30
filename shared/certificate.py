#!/usr/bin/env python3
"""Create the PDF's self-signed server certificate, including both DNS SANs."""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from env_loader import ROOT, load_env
from render_config import brew_binary


def run(openssl, *args, **kwargs):
    return subprocess.run([openssl, *map(str, args)], check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--renew", action="store_true", help="replace the certificate; clients must trust the new public certificate")
    args = parser.parse_args()
    env = load_env()
    openssl = brew_binary("openssl@3", "openssl")
    directory = ROOT / "mac2_edge/certs"
    directory.mkdir(exist_ok=True)
    cert, key = directory / "server.crt", directory / "server.key"
    if (cert.exists() or key.exists()) and not args.renew:
        if not cert.exists() or not key.exists():
            raise ValueError("Certificate/key pair incomplete. Run generate_certificate.sh --renew.")
        for domain in (env["APP_DOMAIN"], env["API_DOMAIN"]):
            run(openssl, "verify", "-purpose", "sslserver", "-CAfile", cert, "-verify_hostname", domain, cert)
        run(openssl, "x509", "-in", cert, "-noout", "-checkend", "86400")
        public_cert = run(openssl, "x509", "-in", cert, "-pubkey", "-noout", capture_output=True).stdout
        public_key = run(openssl, "pkey", "-in", key, "-pubout", capture_output=True).stdout
        if public_cert != public_key:
            raise ValueError("Certificate and key do not match. Run generate_certificate.sh --renew.")
        print("Reusing existing certificate and key.")
    else:
        with tempfile.TemporaryDirectory(prefix=".generate-", dir=directory) as tmp:
            work = Path(tmp)
            config = work / "openssl.cnf"
            config.write_text(f"""[req]
prompt = no
distinguished_name = dn
x509_extensions = server_ext
[dn]
CN = {env['APP_DOMAIN']}
O = CN Phase 1 {env['TEAM_NAME']}
[server_ext]
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @names
[names]
DNS.1 = {env['APP_DOMAIN']}
DNS.2 = {env['API_DOMAIN']}
""")
            run(openssl, "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-noenc", "-days", "365", "-config", config,
                "-keyout", work / "server.key", "-out", work / "server.crt")
            (work / "server.key").chmod(0o600)
            (work / "server.crt").chmod(0o644)
            os.replace(work / "server.key", key)
            os.replace(work / "server.crt", cert)
    run(openssl, "x509", "-in", cert, "-noout", "-subject", "-dates", "-ext", "subjectAltName", "-fingerprint", "-sha256")
    print(f"Public certificate: {cert}\nPrivate key stays on Mac 2: {key}")
    print("Copy ONLY server.crt to client Macs, then run shared/trust_certificate.sh.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        sys.exit(f"Certificate error: {exc}")
