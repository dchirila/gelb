#!/bin/bash

# Bootstrap script for GeLB development environment
# Removes existing venv, creates a new one, and installs requirements using uv.
#
# Checks system prerequisites (Python >= 3.10, git, curl, gcc, gfortran) and
# fails fast with actionable hints when anything is missing. Java is NOT
# required at bootstrap time -- it's only needed by ./scripts/regenerate_antlr.sh
# (and only when the ANTLR4 generated_code/ files are missing or out of date).

set -e  # Exit on error

echo "Setting up GeLB development environment with uv..."

# Get the root directory (parent of scripts directory)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Define venv path
VENV_PATH="$ROOT_DIR/.venv"

# -- Prerequisite checks -----------------------------------------------
#
# We treat git and curl as hard requirements (the script literally cannot
# run without them -- git for the project, curl to fetch the uv installer
# if uv itself is missing). Python >= 3.10 is also hard (matches the
# `requires-python` in pyproject.toml). gcc and gfortran are soft: missing
# them doesn't break the bootstrap itself, but the user will hit cryptic
# errors later when gelb-run tries to compile generated Fortran, so we
# warn loudly here while we still have their attention.
check_prereqs() {
    local missing_hard=()
    local missing_soft=()

    # Hard: git
    command -v git >/dev/null 2>&1 || missing_hard+=("git")

    # Hard: curl (used below if uv needs to be installed)
    command -v curl >/dev/null 2>&1 || missing_hard+=("curl")

    # Hard: python >= 3.10
    if ! command -v python3 >/dev/null 2>&1; then
        missing_hard+=("python3 (>= 3.10)")
    else
        local pyver
        pyver=$(python3 -c 'import sys; print("{}.{}".format(*sys.version_info[:2]))' 2>/dev/null || echo "0.0")
        # Compare X.Y as two integers.
        local pymaj pymin
        pymaj=${pyver%%.*}
        pymin=${pyver#*.}
        if (( pymaj < 3 || (pymaj == 3 && pymin < 10) )); then
            missing_hard+=("python3 >= 3.10 (found $pyver)")
        fi
    fi

    # Soft: gcc (system C compiler -- needed transitively by some Python
    # wheels and by the cpu_fortran_serial backend at gelb-run time)
    command -v gcc >/dev/null 2>&1 || missing_soft+=("gcc")

    # Soft: gfortran (default Fortran compiler for the cpu_fortran_serial
    # backend)
    command -v gfortran >/dev/null 2>&1 || missing_soft+=("gfortran")

    if (( ${#missing_hard[@]} > 0 )); then
        echo ""
        echo "ERROR: the following required tools are missing:" >&2
        printf '  - %s\n' "${missing_hard[@]}" >&2
        echo "" >&2
        echo "Install them and re-run this script. On Ubuntu/Debian/Pop!_OS:" >&2
        echo "  sudo apt install git curl python3 python3-venv" >&2
        echo "On Fedora/RHEL:" >&2
        echo "  sudo dnf install git curl python3" >&2
        echo "On macOS (with Homebrew):" >&2
        echo "  brew install git curl python@3.12" >&2
        exit 1
    fi

    if (( ${#missing_soft[@]} > 0 )); then
        echo ""
        echo "WARNING: the following recommended tools are missing:" >&2
        printf '  - %s\n' "${missing_soft[@]}" >&2
        echo "" >&2
        echo "Bootstrap will continue, but you'll need them later when running" >&2
        echo "gelb-run with the CPU backend. On Ubuntu/Debian/Pop!_OS:" >&2
        echo "  sudo apt install build-essential gfortran" >&2
        echo "On Fedora/RHEL:" >&2
        echo "  sudo dnf install gcc gcc-gfortran" >&2
        echo "On macOS (with Homebrew):" >&2
        echo "  brew install gcc" >&2
        echo ""
    fi
}

check_prereqs

# -- uv detection / install --------------------------------------------
#
# Newer uv installers (>= 0.4) drop the binary into ~/.local/bin, while
# older ones used ~/.cargo/bin. Search both, plus a few other common
# locations, before falling back to the official installer script.
ensure_uv_on_path() {
    if command -v uv >/dev/null 2>&1; then
        return 0
    fi
    # Try the standard install locations in case uv is present but not
    # yet on PATH (common on fresh installs and in non-interactive shells).
    for dir in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
        if [ -x "$dir/uv" ]; then
            export PATH="$dir:$PATH"
            return 0
        fi
    done
    return 1
}

if ! ensure_uv_on_path; then
    echo "uv is not installed. Installing uv via the official installer..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # The installer prints the install location at the end; the binary
    # may land in either ~/.local/bin (newer) or ~/.cargo/bin (older).
    if ! ensure_uv_on_path; then
        echo "ERROR: uv was installed but isn't on PATH." >&2
        echo "Add ~/.local/bin (or ~/.cargo/bin) to your PATH and re-run." >&2
        exit 1
    fi
fi

echo "uv: $(uv --version) at $(command -v uv)"

# Remove existing venv if it exists
if [ -d "$VENV_PATH" ]; then
    echo "Removing existing virtual environment..."
    rm -rf "$VENV_PATH"
fi

# Create new virtual environment and install dependencies
echo "Creating virtual environment and installing dependencies..."
cd "$ROOT_DIR"
uv venv
uv sync --all-extras

# Initialise submodules (third_party/highway).  A fresh ``git
# clone`` does not pull these by default, and the cpu_highway
# backend needs the headers at build time.  Skipped silently if
# we're not in a git checkout (e.g. a tarball).
if [ -d "$ROOT_DIR/.git" ]; then
    echo "Initialising git submodules (third_party/highway)..."
    ( cd "$ROOT_DIR" && git submodule update --init --recursive )
fi

echo "GeLB development environment setup complete!"
echo "To activate the environment, run: source .venv/bin/activate"
