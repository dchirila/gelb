#!/usr/bin/env bash
#
# install-vscode-ext.sh -- Install or update the GeLB VSCode extension.
#
# Builds and copies vscode-gelb/ to the VSCode extensions folder, without
# what only building and testing need (node_modules, test/), as the VSIX
# packaging leaves them out too. Reload the VSCode window after
# installation. Designed for rapid iteration during development: edit the
# grammar/snippets, re-run this script, and the changes appear immediately.
#
# Usage (from the gelb/ project root):
#   ./scripts/install-vscode-ext.sh          # build + install
#   ./scripts/install-vscode-ext.sh --check  # compare versions, don't install
#   ./scripts/install-vscode-ext.sh --extensions-dir DIR
#       # into DIR instead of ~/.vscode/extensions: for a VSCode started
#       # with `code --extensions-dir DIR` (a scratch profile, for testing)
#
# Works on macOS and Linux. Requires Node.js, npm and Python 3.

set -euo pipefail

# -- Paths ------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
EXT_SRC="$PROJECT_ROOT/vscode-gelb"

# -- Arguments --------------------------------------------------------
CHECK=false
EXT_DIR="$HOME/.vscode/extensions"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --check) CHECK=true; shift ;;
        --extensions-dir)
            [[ $# -ge 2 ]] || { echo "Error: --extensions-dir needs a folder" >&2; exit 2; }
            EXT_DIR="$2"; shift 2 ;;
        -h|--help) sed -n '3,20p' "$0"; exit 0 ;;
        *) echo "Unknown argument: $1 (see --help)" >&2; exit 2 ;;
    esac
done

if [[ "$OSTYPE" != darwin* && "$OSTYPE" != linux* ]]; then
    echo "Unsupported platform: $OSTYPE" >&2
    exit 1
fi
EXT_DST="$EXT_DIR/vscode-gelb"

# -- Helpers ----------------------------------------------------------
get_version() {
    python3 -c "import json, sys; print(json.load(open(sys.argv[1]))['version'])" "$1" 2>/dev/null || echo "unknown"
}

# -- --check mode -----------------------------------------------------
if $CHECK; then
    src_ver=$(get_version "$EXT_SRC/package.json")
    if [[ -f "$EXT_DST/package.json" ]]; then
        dst_ver=$(get_version "$EXT_DST/package.json")
        if [[ "$src_ver" == "$dst_ver" ]]; then
            echo "Up to date: v${dst_ver}"
        else
            echo "Update available: installed v${dst_ver} → source v${src_ver}"
        fi
    else
        echo "Not installed (source v${src_ver})"
    fi
    exit 0
fi

# -- Install ----------------------------------------------------------
if [[ ! -d "$EXT_SRC" ]]; then
    echo "Error: extension source not found at $EXT_SRC" >&2
    exit 1
fi

src_ver=$(get_version "$EXT_SRC/package.json")
old_ver="(none)"
if [[ -f "$EXT_DST/package.json" ]]; then
    old_ver=$(get_version "$EXT_DST/package.json")
fi

# Build before replacing the installed extension so a failed build leaves
# the existing installation intact.
(
    cd "$EXT_SRC"
    npm ci
    npm run compile
)

# Remove old installation and copy fresh
rm -rf "$EXT_DST"
mkdir -p "$EXT_DST"
tar -C "$EXT_SRC" --exclude=node_modules --exclude=.vscode-test --exclude=test \
    -chf - . | tar -C "$EXT_DST" -xf -

echo "Installed GeLB VSCode extension: v${old_ver} → v${src_ver}"
echo "  Source: $EXT_SRC"
echo "  Target: $EXT_DST"

# -- Reload VSCode ----------------------------------------------------
echo ""
if [[ "$OSTYPE" == darwin* ]]; then
    echo "Reload VSCode: Cmd+Shift+P → Developer: Reload Window"
else
    echo "Reload VSCode: Ctrl+Shift+P → Developer: Reload Window"
fi
