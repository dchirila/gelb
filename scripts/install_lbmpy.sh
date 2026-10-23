#!/usr/bin/env bash
# Install lbmpy, pystencils and numpy into a self-contained venv for
# the lbmpy benchmark scripts, scripts/benchmark_lbmpy_tgv.py and
# scripts/benchmark_lbmpy_ldc.py.
#
# Default install location: $HOME/Soft/lbmpy/venv
#
# Works on Linux and macOS (Bash 3.2+).
#
# lbmpy and pystencils are not dependencies of GeLB: the project venv
# (.venv) does not contain them, and the benchmark scripts are run
# with the interpreter of the venv created here instead of `uv run`.
# The venv is built from a uv-managed Python, which ships the headers
# that pystencils' run-time kernel compilation needs.
#
# The packages are installed unpinned; the benchmark scripts record the
# lbmpy and pystencils versions they ran with in their results file.
# The script never deletes anything: an existing prefix is an error
# unless --keep asks to install into it.
#
# Usage:
#   ./scripts/install_lbmpy.sh                  # into $HOME/Soft/lbmpy (must not exist)
#   ./scripts/install_lbmpy.sh --keep           # into an existing prefix
#   ./scripts/install_lbmpy.sh --prefix /opt/lbmpy
#   ./scripts/install_lbmpy.sh --python 3.13
#
# After install, run a benchmark with:
#   $HOME/Soft/lbmpy/venv/bin/python scripts/benchmark_lbmpy_tgv.py

set -euo pipefail

DEFAULT_PREFIX="${HOME}/Soft/lbmpy"
DEFAULT_PYTHON="3.12"
PACKAGES="lbmpy pystencils numpy"

PREFIX="${LBMPY_PREFIX:-$DEFAULT_PREFIX}"
PYTHON_VERSION="$DEFAULT_PYTHON"
KEEP_EXISTING=0

usage() {
    cat <<EOF
Usage: $(basename "$0") [--prefix PATH] [--python VER] [--keep]

Install lbmpy + pystencils + numpy into a dedicated venv at
<PATH>/venv.  By default <PATH> is \$HOME/Soft/lbmpy.

Options:
  --prefix PATH   Install dir (default: \$HOME/Soft/lbmpy or
                  \$LBMPY_PREFIX env var if set)
  --python VER    Python version to provision via uv (default: 3.12)
  --keep          Install into PATH although it already exists (the
                  packages are refreshed in place). Without it an
                  existing PATH is an error: nothing is ever deleted.
  -h, --help      Show this help.

Requires: uv (https://docs.astral.sh/uv/)
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --prefix)
            if [ $# -lt 2 ]; then
                echo "Error: --prefix needs a value" >&2; exit 1
            fi
            PREFIX="$2"; shift 2;;
        --python)
            if [ $# -lt 2 ]; then
                echo "Error: --python needs a value" >&2; exit 1
            fi
            PYTHON_VERSION="$2"; shift 2;;
        --keep) KEEP_EXISTING=1; shift;;
        -h|--help) usage; exit 0;;
        *) echo "Error: unknown option: $1" >&2; usage >&2; exit 1;;
    esac
done

# --- Sanity checks ------------------------------------------------

if ! command -v uv >/dev/null 2>&1; then
    echo "Error: 'uv' not found on PATH." >&2
    echo "Install it first:" >&2
    echo "  Linux/macOS: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    echo "  Or: pipx install uv" >&2
    echo "Reference: https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi

# Refuse a few obviously wrong prefix values, so that --keep cannot
# install a venv into the home directory itself.
case "$PREFIX" in
    ""|/|/home|/home/*/|"$HOME"|"$HOME/")
        echo "Error: refusing to operate on prefix='$PREFIX'." >&2
        echo "Use a dedicated subdirectory (the default is \$HOME/Soft/lbmpy)." >&2
        exit 1;;
esac

# --- Detect platform (informational) ------------------------------

case "$(uname -s)" in
    Linux*)  PLATFORM=linux;;
    Darwin*) PLATFORM=macos;;
    *)       PLATFORM="$(uname -s)";;
esac
echo "==> Platform: $PLATFORM, target prefix: $PREFIX"

VENV_DIR="$PREFIX/venv"

# --- Prefix ---------------------------------------------------------

if [ -e "$PREFIX" ] && [ ! -d "$PREFIX" ]; then
    echo "Error: $PREFIX exists and is not a directory." >&2
    exit 1
fi

if [ -d "$PREFIX" ]; then
    if [ "$KEEP_EXISTING" -eq 1 ]; then
        echo "==> --keep: leaving existing $PREFIX in place"
    else
        echo "Error: $PREFIX already exists; nothing was changed." >&2
        echo "       Use --keep to install into it, or --prefix DIR (or LBMPY_PREFIX)" >&2
        echo "       for a fresh location. This script never deletes a directory." >&2
        exit 1
    fi
fi

mkdir -p "$PREFIX"

# --- Install Python + venv + packages -----------------------------

echo "==> Ensuring Python $PYTHON_VERSION is available (via uv)..."
uv python install "$PYTHON_VERSION"

# `uv venv` replaces an existing venv directory, which is what --keep
# means: the packages are refreshed in place.
echo "==> Creating venv at $VENV_DIR..."
uv venv --python "$PYTHON_VERSION" "$VENV_DIR"

VENV_PYTHON="$VENV_DIR/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
    echo "Error: venv interpreter not found at $VENV_PYTHON" >&2
    exit 1
fi

echo "==> Installing $PACKAGES..."
# shellcheck disable=SC2086
uv pip install --python "$VENV_PYTHON" $PACKAGES

# --- Verify -------------------------------------------------------

echo ""
echo "==> Verifying install..."
"$VENV_PYTHON" - <<'PYEOF'
import importlib, sys
print(f"Python:      {sys.version.split()[0]}")
print(f"Interpreter: {sys.executable}")
for name in ("lbmpy", "pystencils", "numpy"):
    mod = importlib.import_module(name)
    print(f"{name+':':<12} {getattr(mod, '__version__', '?')}")
PYEOF

cat <<EOF

Done.  Run the benchmarks with the new interpreter (not with uv run):

  $VENV_PYTHON scripts/benchmark_lbmpy_tgv.py
  $VENV_PYTHON scripts/benchmark_lbmpy_ldc.py

Both write their results into docs/benchmarks/lbmpy_results.json;
see docs/benchmarks/lbmpy_reproduction.md for the measurement
conditions.
EOF
