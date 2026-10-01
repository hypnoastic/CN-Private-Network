#!/bin/bash
# One entry point for all four macOS machines.
set -euo pipefail
CN_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ "$(uname -s)" != Darwin ]; then
    echo 'This setup launcher requires macOS.' >&2
    exit 1
fi
if [ "$(id -u)" -eq 0 ]; then
    echo 'Run: bash setup.sh (without sudo). Setup requests sudo only when needed.' >&2
    exit 1
fi
find_brew() {
    if command -v brew >/dev/null 2>&1; then command -v brew; return; fi
    # Only bootstrap discovery needs these two Homebrew entry points.
    for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
        if [ -x "$candidate" ]; then printf '%s\n' "$candidate"; return; fi
    done
    return 1
}
ensure_brew() {
    if ! CN_BREW="$(find_brew)"; then
        echo 'Installing Homebrew from its official installer. Follow any macOS developer-tools prompts.'
        CN_INSTALLER="$(mktemp -t cn-homebrew)"
        trap 'rm -f "$CN_INSTALLER"' EXIT
        /usr/bin/curl --disable -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o "$CN_INSTALLER"
        /bin/bash "$CN_INSTALLER"
        CN_BREW="$(find_brew)" || { echo 'Homebrew installation did not finish; rerun setup.sh after the installer completes.' >&2; exit 1; }
        rm -f "$CN_INSTALLER"
        trap - EXIT
    fi
    eval "$("$CN_BREW" shellenv)"
}
# Used internally by the Python launcher when only Homebrew is missing.
if [ "${1:-}" = --install-brew ]; then
    ensure_brew
    exit 0
fi
if CN_BREW="$(find_brew)"; then eval "$("$CN_BREW" shellenv)"; fi
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; sys.exit(sys.version_info < (3,9))' 2>/dev/null; then
    ensure_brew
    echo 'Installing Python 3 for the project.'
    "$CN_BREW" install python
    export PATH="$("$CN_BREW" --prefix)/bin:$PATH"
fi
exec python3 "$CN_DIR/shared/launcher.py" "$@"
