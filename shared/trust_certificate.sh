#!/bin/bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/common.sh"
cn_load_env
if [ "$(uname -s)" != Darwin ]; then echo 'This trust-store command is for macOS.' >&2; exit 1; fi
CERT="${1:-$CN_ROOT/shared/trusted/server.crt}"
[ -f "$CERT" ] || { echo "Missing public certificate: $CERT. Copy server.crt from Mac 2 first." >&2; exit 1; }
/usr/bin/openssl x509 -in "$CERT" -noout -subject -dates -fingerprint -sha256
echo "Installing the displayed self-signed project certificate as a trusted SSL root in the macOS System keychain."
echo "This modifies the system trust store and requires sudo. Verify its SHA-256 fingerprint matches Mac 2."
sudo /usr/bin/security add-trusted-cert -d -r trustRoot -p ssl -k /Library/Keychains/System.keychain "$CERT"
echo "Trusted certificate installed. Use /usr/bin/curl for macOS system-keychain verification."
echo "Expected names: $APP_DOMAIN and $API_DOMAIN"
