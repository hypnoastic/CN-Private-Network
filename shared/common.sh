#!/bin/bash
# Source this helper; paths are independent of the caller's working directory.
# Callers choose their shell options; sourcing this in Terminal must not enable
# errexit, especially when observing an intentionally failed demo command.
if [ -n "${BASH_VERSION:-}" ]; then
    CN_COMMON_FILE="${BASH_SOURCE[0]}"
else
    # macOS Terminal uses zsh by default; README source commands support it too.
    CN_COMMON_FILE="${(%):-%x}"
fi
CN_ROOT="$(cd "$(dirname "$CN_COMMON_FILE")/.." && pwd)"
cn_load_env() {
    local assignments
    assignments="$(python3 "$CN_ROOT/shared/env_loader.py" --shell)" || return
    eval "$assignments"
}
cn_brew_binary() {
    local formula="$1" binary="$2" prefix
    command -v brew >/dev/null || { echo 'Install Homebrew first: https://brew.sh' >&2; return 1; }
    prefix="$(brew --prefix "$formula")" || return
    if [ -x "$prefix/sbin/$binary" ]; then
        printf '%s\n' "$prefix/sbin/$binary"
    elif [ -x "$prefix/bin/$binary" ]; then
        printf '%s\n' "$prefix/bin/$binary"
    else
        echo "Missing $binary. Run: brew install $formula" >&2
        return 1
    fi
}
