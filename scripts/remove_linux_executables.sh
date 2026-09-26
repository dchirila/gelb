#!/usr/bin/env bash
# remove_linux_executables.sh <directory>
# Finds all ELF64 Linux executables in the given directory (recursively),
# excluding shared libs and a hard-coded set of off-limits subtrees
# (third-party venv, VCS, caches, the thesis archive). Optionally
# deletes them.

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $(basename "$0") <directory>" >&2
    exit 1
fi

SEARCH_DIR="$1"

if [[ ! -d "$SEARCH_DIR" ]]; then
    echo "Error: '$SEARCH_DIR' is not a directory." >&2
    exit 1
fi

# Directory names to skip entirely (anywhere in the tree). These either
# host third-party binaries we must not touch (.venv, node_modules) or
# are off-limits per project policy (results_for_phd_thesis__Nov_2017).
PRUNE_NAMES=(
    .git
    .venv
    venv
    node_modules
    __pycache__
    .pytest_cache
    .mypy_cache
    .ruff_cache
    .antlr
    results_for_phd_thesis__Nov_2017
)

# Build the find prune expression: \( -name a -o -name b -o ... \)
prune_expr=()
for name in "${PRUNE_NAMES[@]}"; do
    if [[ ${#prune_expr[@]} -gt 0 ]]; then
        prune_expr+=( -o )
    fi
    prune_expr+=( -name "$name" )
done

mapfile -t BINS < <(
    find "$SEARCH_DIR" \
        \( -type d \( "${prune_expr[@]}" \) -prune \) -o \
        \( -type f ! -name '*.so' ! -name '*.so.*' -print0 \) \
    | xargs -0 file --mime-type 2>/dev/null \
    | awk -F': ' '
        /application\/x-executable/     { print $1 }
        /application\/x-pie-executable/ { print $1 }
    ' \
    | while IFS= read -r f; do
        header=$(readelf -h "$f" 2>/dev/null || true)
        class=$(echo "$header" | awk '/Class:/ { print $2 }')
        etype=$(echo "$header" | awk '/Type:/  { print $2 }')
        if [[ "$class" == "ELF64" && ( "$etype" == "EXEC" || "$etype" == "DYN" ) ]]; then
            if [[ "$etype" == "DYN" ]]; then
                # `|| true`: grep returning 1 for "no SONAME" is the
                # GOOD case (it means this DYN is a real PIE
                # executable, not a shared library). Without the
                # guard, pipefail+set-e would kill the loop subshell
                # the first time we hit one and silently drop every
                # subsequent file.
                soname=$(readelf -d "$f" 2>/dev/null | grep SONAME || true)
                [[ -n "$soname" ]] && continue
            fi
            echo "$f"
        fi
    done
)

if [[ ${#BINS[@]} -eq 0 ]]; then
    echo "No ELF64 executables found in '$SEARCH_DIR'."
    exit 0
fi

echo "Found ${#BINS[@]} ELF64 executable(s):"
printf '  %s\n' "${BINS[@]}"

echo
read -r -p "Delete all of the above? [y/N] " REPLY
if [[ "${REPLY,,}" == "y" ]]; then
    for f in "${BINS[@]}"; do
        rm -f -- "$f"
        echo "Deleted: $f"
    done
    echo "Done."
else
    echo "Aborted. No files were deleted."
fi
