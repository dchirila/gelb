#!/bin/bash
# Remove regenerable build/run artifacts from the repository clone.
#
# Deletes ONLY known-regenerable artifact classes:
#   - Python bytecode caches (__pycache__/, *.pyc) and tool caches
#     (.pytest_cache/, .mypy_cache/, .ruff_cache/, .coverage, htmlcov/)
#   - Sphinx build output (docs/_build/)
#   - Packaging output (dist/, *.egg-info/)
#   - Simulation NetCDF outputs that git ignores, but ONLY at the repo
#     root and directly under docs/ (where gelb-run drops them). .nc files
#     anywhere else (tests/data fixtures, .venv, rb_sweep_results*/,
#     results_for_phd_thesis*/, .machine_notes/) are never touched.
#   - Root manual PDFs (regenerable release artifacts)
#   - A stray gelb/antlr_part/grammars/.antlr/ folder (left by running
#     ANTLR inside the grammars directory; see CONTRIBUTING.md)
#
# Never touches: .venv/, vscode-gelb/node_modules/,
# .machine_notes/, refs/, results_for_phd_thesis__*/, rb_sweep_results*/,
# tracked files, or untracked-but-unignored files (work in progress).
#
# Usage:
#   ./scripts/clean_artifacts.sh           # delete artifacts
#   ./scripts/clean_artifacts.sh --dry-run # show what would be deleted

set -euo pipefail
cd "$(dirname "$0")/.."

DRY_RUN=0
case "${1:-}" in
    -n|--dry-run) DRY_RUN=1 ;;
    "") ;;
    *) echo "Usage: $0 [-n|--dry-run]" >&2; exit 1 ;;
esac

remove() {
    local path=$1
    [ -e "$path" ] || return 0
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "would remove: $path"
    else
        echo "removing: $path"
        rm -rf -- "$path"
    fi
}

# --- Python bytecode and tool caches ---
# Prune .venv and node_modules so we never walk (or clean inside) them.
while IFS= read -r d; do
    remove "$d"
done < <(find . \( -path ./.venv -o -path ./vscode-gelb/node_modules \) -prune \
              -o -type d -name '__pycache__' -print)

remove .pytest_cache
remove .mypy_cache
remove .ruff_cache
remove .coverage
remove htmlcov

# --- Sphinx and packaging build output ---
remove docs/_build
remove dist
for d in *.egg-info gelb/*.egg-info; do
    remove "$d"
done

# --- Stray ANTLR output in the grammars directory (wrong location) ---
remove gelb/antlr_part/grammars/.antlr

# --- Regenerable manual PDFs (release artifacts; rebuilt for a release) ---
remove GeLB_User_Tutorial.pdf
remove GeLB_Developer_Manual.pdf

# --- Simulation NetCDF outputs ---
# Only files git already ignores (tracked fixtures and deliberate
# untracked work are never listed), and only in the locations where
# gelb-run / validation scripts drop outputs: the repo root and docs/.
# Ignored *directories* (.venv, rb_sweep_results*/, PhD results, ...)
# contain .nc files too -- the allowlist below keeps them safe.
while IFS= read -r f; do
    case "$f" in
        */*)
            case "$f" in
                docs/*.nc) [ "$(dirname "$f")" = "docs" ] && remove "$f" ;;
            esac
            ;;
        *.nc) remove "$f" ;;
    esac
done < <(git ls-files --others --ignored --exclude-standard -- '*.nc')

if [ "$DRY_RUN" -eq 1 ]; then
    echo "Dry run - nothing deleted."
else
    echo "Done."
fi
