#!/bin/bash
# Regenerate ANTLR4 files for GeLB
# This script should be run from the root of the GeLB repository.
#
# Supported platforms: macOS (Homebrew), Ubuntu/Debian, Fedora/RHEL.
# Java is required; the script will detect common install locations.

set -e

echo "Regenerating ANTLR4 files..."

# --- Virtual environment ---
if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Please run gelb_bootstrap.sh first." >&2
    exit 1
fi

# Add venv bin to PATH so that the `antlr4` CLI (from antlr4-tools) is found
# by subprocess.run inside invoke_antlr4_tool()
export PATH="$(pwd)/.venv/bin:$PATH"

# --- Java detection ---
# Probe with `java -version`, not `command -v java`: macOS ships
# /usr/bin/java as a stub launcher that is on PATH even when no JDK is
# installed. With a Homebrew-only JDK (which doesn't register itself
# under /Library/Java/JavaVirtualMachines/), the stub doesn't error
# out -- it spins in a CPU loop forever when handed classpath args, so
# `command -v java` would silently steer us into a wedged invocation.
# `java -version` exits non-zero on the stub, letting us fall through
# to the Homebrew search below.
if ! java -version >/dev/null 2>&1; then
    FOUND_JAVA=""

    # macOS -- Homebrew OpenJDK
    if [ -d "/opt/homebrew/opt/openjdk" ]; then
        FOUND_JAVA="/opt/homebrew/opt/openjdk"
    elif [ -d "/usr/local/opt/openjdk" ]; then
        # Intel Mac Homebrew
        FOUND_JAVA="/usr/local/opt/openjdk"

    # Linux -- common JDK locations
    elif [ -d "/usr/lib/jvm/default-java" ]; then
        FOUND_JAVA="/usr/lib/jvm/default-java"
    elif [ -d "/usr/lib/jvm" ]; then
        # Pick the newest JDK directory
        FOUND_JAVA=$(find /usr/lib/jvm -maxdepth 1 -type d -name "java-*" | sort -V | tail -1)
    fi

    if [ -n "$FOUND_JAVA" ]; then
        export JAVA_HOME="$FOUND_JAVA"
        export PATH="$JAVA_HOME/bin:$PATH"
    else
        echo "Error: Java not found." >&2
        echo "" >&2
        echo "Install a JDK for your platform:" >&2
        echo "  macOS:        brew install openjdk" >&2
        echo "  Ubuntu/Debian: sudo apt install default-jdk" >&2
        echo "  Fedora/RHEL:  sudo dnf install java-latest-openjdk" >&2
        exit 1
    fi
elif [ -z "$JAVA_HOME" ]; then
    # `java` is on PATH but JAVA_HOME is not set -- some tools need it.
    # Derive JAVA_HOME from the java binary location.
    JAVA_BIN=$(command -v java)
    # Resolve symlinks (common on Linux: /usr/bin/java -> /etc/alternatives/java -> /usr/lib/jvm/...)
    JAVA_BIN=$(readlink -f "$JAVA_BIN" 2>/dev/null || realpath "$JAVA_BIN" 2>/dev/null || echo "$JAVA_BIN")
    # Strip /bin/java to get JAVA_HOME
    export JAVA_HOME="${JAVA_BIN%/bin/java}"
fi

# --- Regenerate ---
./.venv/bin/python -c "from gelb.utils.misc import invoke_antlr4_tool; invoke_antlr4_tool()"

if [ $? -eq 0 ]; then
    echo "ANTLR4 files regenerated successfully."
else
    echo "Failed to regenerate ANTLR4 files." >&2
    exit 1
fi
