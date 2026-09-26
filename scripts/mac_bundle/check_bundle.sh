#!/usr/bin/env bash
#
# check_bundle.sh -- the gates a staged GeLB macOS bundle must pass
# before it is packed into a disk image.
#
#     check_bundle.sh STAGE_DIR [TARGET_MIN]        (TARGET_MIN: 14.0)
#
# Gates (every offender is printed; exit status 1 if any gate fails):
#   1. every Mach-O file (dylib, .so, executable, Qt framework binary)
#      has a minimum macOS at or below TARGET_MIN -- dyld on an older
#      macOS refuses to load anything built for a newer one;
#   2. every dynamic-link target of every Mach-O is @rpath/@loader_path/
#      @executable_path-relative or under /usr/lib or /System, no
#      LC_RPATH is absolute, and every relative target resolves inside
#      the bundle (@rpath through the file's own rpaths): anything else
#      (Homebrew, Postgres.app, a wheel builder's home, a tool whose
#      framework was pruned) exists only on the build machine, or nowhere.  Neither bin/ nor the installer's postinstall scripts
#      (pkg/scripts next to this file) may mention /opt/homebrew or
#      /usr/local; scripts/gelb-run may, its Homebrew fallbacks are dead
#      code once bin/gelb-env.sh pins the bundle's roots (gate 7);
#   3. every Mach-O carries a valid code signature (ad-hoc is fine;
#      arm64 refuses unsigned code);
#   4. no build-host path (this user's $HOME, the stage) in bin/,
#      scripts/, the postinstall scripts, VERSION or the shebangs under
#      python/bin;
#   5. no shebang in bin/ or scripts/ points at a system python;
#   6. the bundled libraries in lib/ have @rpath install names;
#   7. bin/gelb-env.sh pins GELB_PYTHON, GELB_OMP_ROOT and
#      GELB_NETCDF_C_ROOT to the bundle;
#   8. every file the wrappers and gelb-run need is present.

set -euo pipefail
export LC_ALL=C     # head/tr/grep on binaries must not trip over UTF-8

STAGE="${1:?usage: check_bundle.sh STAGE_DIR [TARGET_MIN]}"
TARGET_MIN="${2:-14.0}"
STAGE="$(cd "$STAGE" && pwd -P)"
PKG_SCRIPTS="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)/pkg/scripts"
FAILED=0

gate() { printf '\n== gate %s: %s\n' "$1" "$2"; }
bad()  { printf '   FAIL %s\n' "$*"; FAILED=1; }
ok()   { printf '   ok   %s\n' "$*"; }
rel()  { printf '%s' "${1#"$STAGE"/}"; }

LIST="$(mktemp)"; MACHO="$(mktemp)"
trap 'rm -f "$LIST" "$MACHO"' EXIT

# Mach-O inventory: one file(1) process over every regular file that is
# not obviously text; thin and fat binaries both say "Mach-O".
find "$STAGE" -type f ! -name '*.py' ! -name '*.pyc' ! -name '*.pyi' ! -name '*.html' \
     ! -name '*.h' ! -name '*.hpp' ! -name '*.gelb' ! -name '*.txt' ! -name '*.md' \
     ! -name '*.json' ! -name '*.js' ! -name '*.css' ! -name '*.svg' > "$LIST"
file -f "$LIST" | grep -E '^[^:]*: +Mach-O' | grep -v ' object' \
    | sed -E 's/: +Mach-O.*$//' > "$MACHO" || true
N_MACHO="$(wc -l < "$MACHO" | tr -d ' ')"
[[ "$N_MACHO" -gt 0 ]] || bad "no Mach-O files found under $STAGE"

# -- 1. minimum OS ----------------------------------------------------
gate 1 "minimum macOS <= $TARGET_MIN on every Mach-O file ($N_MACHO files)"
minos_of() {   # arm64 minos of FILE, or "" when it carries no build version
    local v
    v="$(vtool -arch arm64 -show-build "$1" 2>/dev/null | awk '/^ *minos/ {print $2; exit}')"
    if [[ -z "$v" ]]; then
        v="$(otool -arch arm64 -l "$1" 2>/dev/null | awk '
            /LC_BUILD_VERSION/ {b=1}  b && /minos/   {print $2; exit}
            /LC_VERSION_MIN_MACOSX/ {m=1}  m && /version/ {print $2; exit}')"
    fi
    printf '%s' "$v"
}
version_le() {   # version_le A B: A <= B on major.minor
    awk -v a="$1" -v b="$2" 'BEGIN {
        split(a, x, "."); split(b, y, ".");
        exit !((x[1]+0 < y[1]+0) || (x[1]+0 == y[1]+0 && x[2]+0 <= y[2]+0)) }'
}
n=0
while IFS= read -r f; do
    v="$(minos_of "$f")"
    if [[ -z "$v" ]]; then
        bad "no arm64 build version: $(rel "$f")"
    elif ! version_le "$v" "$TARGET_MIN"; then
        bad "minos $v: $(rel "$f")"
    else
        n=$((n + 1))
    fi
done < "$MACHO"
ok "$n files at or below $TARGET_MIN"

# -- 2. links that only resolve on the build machine ------------------
gate 2 "every link target relative and resolvable, or under /usr/lib, /System; no absolute rpath"
# resolves DEP for FILE (dir DIR, rpaths RPATHS, one per line): 0 = found
resolves() {
    local f="$1" dir="$2" rpaths="$3" dep="$4" rp cand
    case "$dep" in
        /usr/lib/*|/System/*) return 0 ;;
        @loader_path/*)     [[ -e "$dir/${dep#@loader_path/}" ]]; return ;;
        @executable_path/*) [[ -e "$dir/${dep#@executable_path/}" || -e "$STAGE/python/bin/${dep#@executable_path/}" ]]; return ;;
        @rpath/*)
            while IFS= read -r rp; do
                [[ -n "$rp" ]] || continue
                case "$rp" in
                    @loader_path*)     cand="$dir${rp#@loader_path}" ;;
                    @executable_path*) cand="$dir${rp#@executable_path}" ;;
                    *)                 cand="$rp" ;;
                esac
                [[ -e "$cand/${dep#@rpath/}" ]] && return 0
            done <<< "$rpaths"
            return 1 ;;
        *) return 1 ;;
    esac
}
n=0
while IFS= read -r f; do
    info="$(otool -l "$f" 2>/dev/null)"
    loads="$(printf '%s\n' "$info" | awk '
        /^ *cmd LC_(LOAD|LOAD_WEAK|REEXPORT|LAZY_LOAD)_DYLIB/ {want=1}
        want && /^ *name / {print $2; want=0}')"
    rpaths="$(printf '%s\n' "$info" | awk '/LC_RPATH/ {r=1} r && /^ *path / {print $2; r=0}')"
    leak="$(printf '%s\n' "$loads" | grep -vE '^@|^/usr/lib/|^/System/' | grep -v '^$' || true)"
    arp="$(printf '%s\n' "$rpaths" | grep '^/' || true)"
    dangling=""
    dir="$(dirname "$f")"
    while IFS= read -r dep; do
        [[ -n "$dep" ]] || continue
        resolves "$f" "$dir" "$rpaths" "$dep" || dangling="$dangling $dep"
    done <<< "$loads"
    if [[ -n "$leak" ]]; then
        bad "links outside the OS: $(rel "$f"): $(printf '%s' "$leak" | tr '\n' ' ')"
    elif [[ -n "$arp" ]]; then
        bad "absolute rpath: $(rel "$f"): $(printf '%s' "$arp" | tr '\n' ' ')"
    elif [[ -n "$dangling" ]]; then
        bad "unresolved dependency: $(rel "$f"):$dangling"
    else
        n=$((n + 1))
    fi
done < "$MACHO"
ok "$n files clean and resolvable"
if grep -rnE '/opt/homebrew|/usr/local' "$STAGE/bin" "$PKG_SCRIPTS" 2>/dev/null; then
    bad "text above mentions Homebrew paths"
else
    ok "bin/ and the postinstall scripts never mention them"
fi

# -- 3. signatures ----------------------------------------------------
gate 3 "valid code signature on every Mach-O file"
n=0
while IFS= read -r f; do
    if codesign -v "$f" >/dev/null 2>&1; then
        n=$((n + 1))
    else
        bad "signature: $(rel "$f")"
    fi
done < "$MACHO"
ok "$n files signed"

# -- 4. build-host paths ----------------------------------------------
gate 4 "no build-host paths ($HOME, $STAGE)"
if grep -rnE "$HOME|$STAGE" "$STAGE/bin" "$STAGE/scripts" "$PKG_SCRIPTS" "$STAGE/VERSION" 2>/dev/null; then
    bad "text above carries a build-host path"
else
    ok "bin/, scripts/, postinstall scripts, VERSION"
fi
n=0
for f in "$STAGE"/python/bin/*; do
    [[ -f "$f" && ! -L "$f" ]] || continue
    line="$( (head -n 1 "$f" | tr -d '\0' | cut -c1-200) 2>/dev/null || true)"
    case "$line" in
        '#!'*"$HOME"*|'#!'*"$STAGE"*|'#!/install/'*) bad "shebang: $(rel "$f"): $line" ;;
        *) n=$((n + 1)) ;;
    esac
done
ok "$n entries under python/bin carry no build-host shebang"

# -- 5. shebangs ------------------------------------------------------
gate 5 "wrappers and scripts never start with a system python"
n=0
for f in "$STAGE"/bin/* "$STAGE"/scripts/*; do
    [[ -f "$f" ]] || continue
    line="$(head -n 1 "$f")"
    case "$line" in
        '#!/usr/bin/env python'*|'#!/usr/bin/python'*|*python3*) bad "shebang: $(rel "$f"): $line" ;;
        *) n=$((n + 1)) ;;
    esac
done
ok "$n files"

# -- 6. install names -------------------------------------------------
gate 6 "@rpath install names in lib/"
n=0
for f in "$STAGE"/lib/*.dylib; do
    [[ -f "$f" && ! -L "$f" ]] || continue
    id="$(otool -D "$f" | tail -n 1)"
    case "$id" in
        @rpath/*) n=$((n + 1)) ;;
        *) bad "install name $id: $(rel "$f")" ;;
    esac
done
ok "$n libraries"

# -- 7. wrapper pins --------------------------------------------------
gate 7 "bin/gelb-env.sh pins the bundled Python, OpenMP and NetCDF"
for var in GELB_PYTHON GELB_OMP_ROOT GELB_NETCDF_C_ROOT; do
    if grep -qE "^export $var=\"[^\"]*\\\$GELB_HOME" "$STAGE/bin/gelb-env.sh" 2>/dev/null; then
        ok "$var"
    else
        bad "$var is not pinned to \$GELB_HOME in bin/gelb-env.sh"
    fi
done

# -- 8. required files ------------------------------------------------
gate 8 "required files"
for f in START_HERE.md VERSION LICENSE README.md CITATION.cff CHANGELOG.md \
         bin/gelb-env.sh bin/gelb-run bin/gelbc bin/gelb-view \
         python/bin/python3.12 lib/libomp.dylib lib/libnetcdf.dylib lib/libhdf5.dylib \
         include/omp.h include/netcdf.h include/netcdf_meta.h \
         scripts/gelb-run gelb/backends/cpu_highway_runtime.hpp gelb/backends/cpp_runtime_common.hpp \
         third_party/highway/hwy/highway.h third_party/highway/hwy/aligned_allocator.cc \
         third_party/highway/hwy/per_target.cc third_party/highway/hwy/targets.cc \
         third_party/highway/hwy/abort.cc third_party/highway/LICENSE \
         examples/lbm/2d/taylor_green_vortex_2d_bgk.gelb docs/html/index.html; do
    if [[ -e "$STAGE/$f" ]]; then n=$((n + 1)); else bad "missing: $f"; fi
done
ls "$STAGE"/vscode-gelb/*.vsix >/dev/null 2>&1 || bad "missing: vscode-gelb/*.vsix"
for f in bin/gelb-run bin/gelbc bin/gelb-view scripts/gelb-run python/bin/python3.12; do
    [[ -x "$STAGE/$f" ]] || bad "not executable: $f"
done
for d in share cmake lib/cmake lib/pkgconfig lib/libhdf5.settings lib/libnetcdf.settings docs/html/_sources install.sh; do
    [[ ! -e "$STAGE/$d" ]] || bad "not pruned: $d"
done
for f in core-preinstall core-postinstall vscode-postinstall shell-postinstall.in; do
    [[ -f "$PKG_SCRIPTS/$f" ]] || bad "missing installer script: pkg/scripts/$f"
done
# the PySide6 whitelist and the pruning of the Python phase
SP="$STAGE/python/lib/python3.12/site-packages"
for f in PySide6/Qt/lib/QtWidgets.framework PySide6/Qt/lib/QtSvg.framework PySide6/Qt/plugins/platforms/libqcocoa.dylib \
         PySide6/Qt/plugins/imageformats PySide6/QtWidgets.abi3.so PySide6/QtGui.abi3.so PySide6/QtCore.abi3.so; do
    [[ -e "$SP/$f" ]] || bad "missing (PySide6 whitelist too tight): $f"
done
for d in PySide6/Qt/qml PySide6/Qt/translations PySide6/Qt/lib/QtQuick.framework PySide6/Qt/lib/QtWebEngineCore.framework \
         PySide6/QtQuick.abi3.so numpy/_core/tests scipy/stats/tests matplotlib/tests sympy/core/tests; do
    [[ ! -e "$SP/$d" ]] || bad "not pruned: site-packages/$d"
done
[[ ! -e "$STAGE/python/lib/python3.12/tkinter" ]] || bad "not pruned: python/lib/python3.12/tkinter"
n_pyc="$(find "$STAGE/python" -type d -name __pycache__ | wc -l | tr -d ' ')"
[[ "$n_pyc" == 0 ]] || bad "$n_pyc __pycache__ directories left under python/"
ok "checked"

echo
if [[ "$FAILED" == 0 ]]; then
    echo "check_bundle: all gates passed"
else
    echo "check_bundle: GATES FAILED" >&2
    exit 1
fi
