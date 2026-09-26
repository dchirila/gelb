#!/usr/bin/env bash
#
# build_bundle.sh -- build the relocatable macOS bundle of GeLB and pack
# it into a versioned installer package
# (GeLB-<ver>-arm64-macos14-<date>-<sha>.pkg) for Installer.app.
#
# The bundle installs into ~/gelb on the target Mac and carries its own
# Python (python-build-standalone plus every package, GUI viewer
# included), the OpenMP runtime, HDF5 and NetCDF-C, the Highway headers,
# all examples, the user tutorial and the VS Code extension.  The target
# machine supplies only Apple clang (Xcode or the Command Line Tools).
#
# Usage, on an Apple-Silicon build host with Xcode:
#   scripts/mac_bundle/build_bundle.sh                # every phase
#   scripts/mac_bundle/build_bundle.sh native python  # selected phases
#
# Phases, in order:
#   native    libomp, HDF5, NetCDF-C from source, deployment target 14.0
#   python    interpreter + locked packages (netCDF4 built against the
#             bundled NetCDF-C) + gelb from this tree
#   assemble  wrappers, scripts, headers, Highway, examples, docs, VSIX,
#             guide, VERSION; prune what the target never needs
#   check     the gates of check_bundle.sh
#   pkg       component packages + product archive (pkg/distribution.xml)
#             into $OUT; the Installer walkthrough with the shell choices
#   dmg       optional: a disk image holding the .pkg and START_HERE.md
#
# Each phase skips work that is already done, so re-running after a fix
# only redoes what is missing.  CLEAN=1 removes the stage first (the
# downloads under $BUNDLE_ROOT/work/dl are kept).
#
# Build-host prerequisites: Xcode (clang, pkgbuild, productbuild), cmake,
# curl, uv, node 20+ (npx).
# cmake and node may come from Homebrew; nothing Homebrew-built is
# copied into the bundle, and check_bundle.sh verifies that.

set -euo pipefail

# -- Parameters (override in the environment) -------------------------
TARGET_MIN="${TARGET_MIN:-14.0}"        # minimum macOS of every Mach-O file
ARCH="${ARCH:-arm64}"
PY_VERSION="${PY_VERSION:-3.12.14}"
PY_BUILD="${PY_BUILD:-20260901}"        # python-build-standalone release tag
OMP_VERSION="${OMP_VERSION:-21.1.8}"    # last LLVM with a standalone openmp tarball
HDF5_VERSION="${HDF5_VERSION:-2.2.0}"
NETCDF_VERSION="${NETCDF_VERSION:-4.10.1}"  # 4.10.0 is the first that builds against HDF5 2.x
# Newest PySide6 whose arm64 extension modules load on macOS 14: from
# 6.10 on they are built for macOS 15 although the wheel tag still says
# macosx_13_0, so pip cannot tell.  The minimum-OS gate is what catches
# a bad choice here.
PYSIDE6_VERSION="${PYSIDE6_VERSION:-6.9.3}"
OUT="${OUT:-$HOME/Research/gelb}"       # where the .dmg is written
BUNDLE_ROOT="${BUNDLE_ROOT:-$HOME/gelb-bundle}"
NJOBS="${NJOBS:-$(sysctl -n hw.ncpu)}"

# -- Derived paths ----------------------------------------------------
SCRIPT_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -P "$SCRIPT_DIR/../.." && pwd)"
GELB_VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$REPO_ROOT/gelb/__init__.py")"
VSIX_VERSION="$(sed -n 's/^  "version": "\(.*\)",$/\1/p' "$REPO_ROOT/vscode-gelb/package.json")"
BUNDLE_NAME="GeLB-$GELB_VERSION"
WORK="$BUNDLE_ROOT/work"
DL="$WORK/dl"
STAGE="$BUNDLE_ROOT/stage/$BUNDLE_NAME"   # the payload of the core package (~/gelb)
PY_MM="${PY_VERSION%.*}"
PY="$STAGE/python/bin/python$PY_MM"

die() { echo "build_bundle: error: $*" >&2; exit 1; }
log() { printf '\n==> %s\n' "$*" >&2; }

[[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "$ARCH" ]] || die "must run on macOS $ARCH"
[[ -n "$GELB_VERSION" ]] || die "cannot read __version__ from gelb/__init__.py"
[[ -n "$VSIX_VERSION" ]] || die "cannot read version from vscode-gelb/package.json"
[[ -f "$REPO_ROOT/third_party/highway/hwy/highway.h" ]] \
    || die "Highway submodule missing: git submodule update --init --recursive"
for tool in /usr/bin/clang++ cmake curl uv npx vtool codesign pkgbuild productbuild installer hdiutil ditto; do
    command -v "$tool" >/dev/null 2>&1 || die "$tool not found on the build host"
done

fetch() {   # fetch URL NAME -> $DL/NAME (skipped when already present)
    local url="$1" name="$2"
    [[ -f "$DL/$name" ]] && return 0
    log "Downloading $name"
    curl -fL --retry 3 -o "$DL/$name.part" "$url"
    mv "$DL/$name.part" "$DL/$name"
}

# -- Phase: native libraries ------------------------------------------
#
# Everything is built with Apple's compiler against the deployment
# target, with @rpath install names and an @loader_path rpath so the
# three libraries find each other inside lib/ and the generated program
# finds them through -Wl,-rpath,$GELB_HOME/lib (set by bin/gelb-env.sh).
# CMAKE_IGNORE_PREFIX_PATH keeps CMake from picking up Homebrew's HDF5
# or zlib through the /opt/homebrew/bin entry on PATH.
phase_native() {
    export MACOSX_DEPLOYMENT_TARGET="$TARGET_MIN"
    export CC=/usr/bin/clang CXX=/usr/bin/clang++
    unset SDKROOT
    local common=(
        -DCMAKE_BUILD_TYPE=Release
        -DCMAKE_C_COMPILER=/usr/bin/clang
        -DCMAKE_CXX_COMPILER=/usr/bin/clang++
        -DCMAKE_OSX_DEPLOYMENT_TARGET="$TARGET_MIN"
        -DCMAKE_OSX_ARCHITECTURES="$ARCH"
        -DCMAKE_INSTALL_PREFIX="$STAGE"
        -DCMAKE_INSTALL_LIBDIR=lib
        -DCMAKE_MACOSX_RPATH=ON
        -DCMAKE_INSTALL_NAME_DIR=@rpath
        -DCMAKE_INSTALL_RPATH=@loader_path
        -DCMAKE_IGNORE_PREFIX_PATH="/opt/homebrew;/usr/local"
        -DBUILD_SHARED_LIBS=ON
    )

    if [[ -f "$STAGE/lib/libomp.dylib" && -f "$STAGE/include/omp.h" ]]; then
        log "libomp $OMP_VERSION already staged"
    else
        log "Building the OpenMP runtime (LLVM $OMP_VERSION)"
        local base="https://github.com/llvm/llvm-project/releases/download/llvmorg-$OMP_VERSION"
        fetch "$base/openmp-$OMP_VERSION.src.tar.xz" "openmp-$OMP_VERSION.src.tar.xz"
        fetch "$base/cmake-$OMP_VERSION.src.tar.xz"  "cmake-$OMP_VERSION.src.tar.xz"
        rm -rf "$WORK/openmp-$OMP_VERSION.src" "$WORK/cmake" "$WORK/build-omp"
        tar xf "$DL/openmp-$OMP_VERSION.src.tar.xz" -C "$WORK"
        tar xf "$DL/cmake-$OMP_VERSION.src.tar.xz" -C "$WORK"
        mv "$WORK/cmake-$OMP_VERSION.src" "$WORK/cmake"   # standalone builds expect ../cmake
        cmake -S "$WORK/openmp-$OMP_VERSION.src" -B "$WORK/build-omp" "${common[@]}" \
              -DOPENMP_ENABLE_LIBOMPTARGET=OFF -DOPENMP_ENABLE_OMPD=OFF \
              -DLIBOMP_OMPT_SUPPORT=OFF -DLIBOMP_INSTALL_ALIASES=OFF \
              -DOPENMP_STANDALONE_BUILD=ON
        cmake --build "$WORK/build-omp" -j"$NJOBS"
        cmake --install "$WORK/build-omp"
        [[ -f "$STAGE/lib/libomp.dylib" && -f "$STAGE/include/omp.h" ]] \
            || die "libomp build did not produce lib/libomp.dylib + include/omp.h"
    fi

    if [[ -f "$STAGE/lib/libhdf5.dylib" && -f "$STAGE/lib/libhdf5_hl.dylib" ]]; then
        log "HDF5 $HDF5_VERSION already staged"
    else
        log "Building HDF5 $HDF5_VERSION"
        # Release tags are hdf5_<version> up to 1.14.x and <version> from 2.0 on.
        local hdf5_tag="$HDF5_VERSION"
        [[ "$HDF5_VERSION" == 1.* ]] && hdf5_tag="hdf5_$HDF5_VERSION"
        fetch "https://github.com/HDFGroup/hdf5/releases/download/$hdf5_tag/hdf5-$HDF5_VERSION.tar.gz" \
              "hdf5-$HDF5_VERSION.tar.gz"
        rm -rf "$WORK/hdf5-$HDF5_VERSION" "$WORK/build-hdf5"
        tar xf "$DL/hdf5-$HDF5_VERSION.tar.gz" -C "$WORK"
        # Option names valid from 1.14.4 on, 2.x included.  zlib is the
        # SDK's (HDF5_ALLOW_EXTERNAL_SUPPORT stays NO: nothing is fetched).
        cmake -S "$WORK/hdf5-$HDF5_VERSION" -B "$WORK/build-hdf5" "${common[@]}" \
              -DBUILD_STATIC_LIBS=OFF \
              -DHDF5_BUILD_HL_LIB=ON -DHDF5_BUILD_CPP_LIB=OFF -DHDF5_BUILD_FORTRAN=OFF \
              -DHDF5_BUILD_JAVA=OFF -DHDF5_BUILD_TOOLS=OFF -DHDF5_BUILD_UTILS=OFF \
              -DHDF5_BUILD_EXAMPLES=OFF -DBUILD_TESTING=OFF \
              -DHDF5_ENABLE_ZLIB_SUPPORT=ON -DHDF5_ENABLE_SZIP_SUPPORT=OFF
        cmake --build "$WORK/build-hdf5" -j"$NJOBS"
        cmake --install "$WORK/build-hdf5"
        [[ -f "$STAGE/lib/libhdf5.dylib" ]] || die "HDF5 build did not produce lib/libhdf5.dylib"
    fi

    if [[ -f "$STAGE/lib/libnetcdf.dylib" && -f "$STAGE/include/netcdf.h" ]]; then
        log "NetCDF-C $NETCDF_VERSION already staged"
    else
        log "Building NetCDF-C $NETCDF_VERSION"
        fetch "https://github.com/Unidata/netcdf-c/archive/refs/tags/v$NETCDF_VERSION.tar.gz" \
              "netcdf-c-$NETCDF_VERSION.tar.gz"
        rm -rf "$WORK/netcdf-c-$NETCDF_VERSION" "$WORK/build-nc"
        tar xf "$DL/netcdf-c-$NETCDF_VERSION.tar.gz" -C "$WORK"
        cmake -S "$WORK/netcdf-c-$NETCDF_VERSION" -B "$WORK/build-nc" "${common[@]}" \
              -DCMAKE_PREFIX_PATH="$STAGE" -DHDF5_ROOT="$STAGE" \
              -DNETCDF_ENABLE_HDF5=ON -DNETCDF_ENABLE_HDF4=OFF \
              -DNETCDF_ENABLE_REMOTE_FUNCTIONALITY=OFF -DNETCDF_ENABLE_DAP=OFF -DNETCDF_ENABLE_BYTERANGE=OFF \
              -DNETCDF_ENABLE_NCZARR=OFF -DNETCDF_ENABLE_PLUGINS=OFF -DNETCDF_ENABLE_LIBXML2=OFF \
              -DNETCDF_ENABLE_TESTS=OFF -DNETCDF_ENABLE_FILTER_TESTING=OFF \
              -DNETCDF_BUILD_UTILITIES=OFF -DNETCDF_ENABLE_EXAMPLES=OFF
        cmake --build "$WORK/build-nc" -j"$NJOBS"
        cmake --install "$WORK/build-nc"
        [[ -f "$STAGE/lib/libnetcdf.dylib" && -f "$STAGE/include/netcdf.h" ]] \
            || die "NetCDF-C build did not produce lib/libnetcdf.dylib + include/netcdf.h"
    fi

    log "Link test: Apple clang + bundled omp.h/netcdf.h"
    cat > "$WORK/linktest.cpp" <<'CPP'
#include <netcdf.h>
#include <omp.h>
#include <cstdio>
int main() {
    int n = 0;
#pragma omp parallel
    {
#pragma omp atomic
        n++;
    }
    std::printf("netcdf %s threads=%d\n", nc_inq_libvers(), n);
    return 0;
}
CPP
    /usr/bin/clang++ -std=c++17 -Xclang -fopenmp -I"$STAGE/include" "$WORK/linktest.cpp" \
        -L"$STAGE/lib" -lnetcdf -lomp -Wl,-rpath,"$STAGE/lib" -o "$WORK/linktest"
    "$WORK/linktest"
    log "Native phase done"
}

# -- Phase: Python ----------------------------------------------------
phase_python() {
    local tarball="cpython-$PY_VERSION+$PY_BUILD-aarch64-apple-darwin-install_only_stripped.tar.gz"
    if [[ -x "$PY" ]]; then
        log "Python $PY_VERSION already staged"
    else
        log "Unpacking python-build-standalone $PY_VERSION+$PY_BUILD"
        fetch "https://github.com/astral-sh/python-build-standalone/releases/download/$PY_BUILD/${tarball//+/%2B}" \
              "$tarball"
        rm -rf "$STAGE/python"
        tar xzf "$DL/$tarball" -C "$STAGE"     # yields $STAGE/python/
        [[ -x "$PY" ]] || die "no $PY after unpacking"
    fi

    # Locked package set from uv.lock (runtime + gui extra, no dev
    # tools), installed as wheels only so no compiler-dependent build
    # sneaks in.  The stamp keys on the requirements text so a changed
    # lock triggers a reinstall; gelb itself is always refreshed from
    # the tree (cheap, and it follows edits in the checkout).
    local req="$WORK/requirements-bundle.txt" stamp="$STAGE/python/.gelb-bundle-requirements"
    (cd "$REPO_ROOT" && uv export --no-dev --extra gui --no-hashes --no-emit-project -q -o "$req")
    if [[ -f "$stamp" ]] && cmp -s "$req" "$stamp"; then
        log "Locked packages already installed"
    else
        log "Installing locked packages"
        "$PY" -m pip install --upgrade --quiet pip
        "$PY" -m pip install --only-binary=:all: --no-cache-dir --quiet -r "$req"
        cp "$req" "$stamp"
    fi

    # netCDF4's wheel carries its own HDF5, NetCDF-C and HDF4 plus curl,
    # OpenSSL, libxml2, libssh2, Kerberos and more (54 MB), which no
    # update of the lock refreshes, as the wheel is the newest there is.
    # Rebuilt from its sdist against the bundled NetCDF-C and HDF5, it
    # leaves one HDF5/NetCDF stack to keep patched and no network code
    # (remote access is off in the NetCDF-C build).  The sdist finds both
    # through NETCDF4_DIR's bin/nc-config and include/H5public.h, which
    # only exist between the native and the assemble phase.
    local sp="$STAGE/python/lib/python$PY_MM/site-packages" nc4 ext
    if [[ -d "$sp/netCDF4/.dylibs" ]]; then
        [[ -x "$STAGE/bin/nc-config" && -f "$STAGE/include/H5public.h" ]] \
            || die "building netCDF4 needs nc-config and the HDF5 headers, which assemble prunes: rerun with CLEAN=1"
        nc4="$("$PY" -c 'import importlib.metadata as m; print(m.version("netCDF4"))')"
        log "Building netCDF4 $nc4 from source against the bundled NetCDF-C and HDF5"
        env CC=/usr/bin/clang MACOSX_DEPLOYMENT_TARGET="$TARGET_MIN" ARCHFLAGS="-arch $ARCH" \
            NETCDF4_DIR="$STAGE" HDF5_DIR="$STAGE" \
            "$PY" -m pip install --no-deps --no-cache-dir --quiet --force-reinstall \
            --no-binary netCDF4 "netCDF4==$nc4"
        [[ ! -d "$sp/netCDF4/.dylibs" ]] || die "netCDF4 still carries the wheel's libraries"
        # setup.py links @rpath/libnetcdf with an absolute rpath to
        # $STAGE/lib (dropped below with the others); from
        # python/lib/python3.x/site-packages/netCDF4/ the bundle's lib/ is
        # five levels up.
        ext="$(ls "$sp"/netCDF4/_netCDF4*.so)"
        install_name_tool -add_rpath @loader_path/../../../../../lib "$ext"
        codesign -s - -f "$ext"
    fi
    log "Pinning PySide6 $PYSIDE6_VERSION (see the note at the top)"
    "$PY" -m pip install --only-binary=:all: --no-cache-dir --quiet \
        "pyside6==$PYSIDE6_VERSION" "pyside6-essentials==$PYSIDE6_VERSION" \
        "pyside6-addons==$PYSIDE6_VERSION" "shiboken6==$PYSIDE6_VERSION"
    log "Installing gelb $GELB_VERSION from $REPO_ROOT"
    "$PY" -m pip install --no-deps --no-cache-dir --quiet --force-reinstall "$REPO_ROOT"
    "$PY" -m pip check

    # Trim PySide6 to what the viewer uses.  GeLB imports QtCore, QtGui
    # and QtWidgets (matplotlib's QtAgg backend uses the same three); a
    # dependency walk from those modules and the platform, image, style
    # and icon plugins reaches the nine frameworks kept below.  The other
    # fifty frameworks, the QML tree, translations, developer tools,
    # headers, stubs and the ffmpeg libraries of QtMultimedia go: from
    # about 340 MB down to about 85 MB.  The GUI stack test further down
    # is what proves the whitelist sufficient.
    local ps d n
    ps="$sp/PySide6"
    local keep_fw=" QtCore QtDBus QtGui QtNetwork QtPrintSupport QtSvg QtSvgWidgets QtWidgets "
    local keep_mod=" QtCore QtGui QtWidgets QtSvg QtSvgWidgets QtPrintSupport QtNetwork "
    for d in "$ps"/Qt/lib/*.framework; do
        n="$(basename "$d" .framework)"
        [[ "$keep_fw" == *" $n "* ]] || rm -rf "$d"
    done
    rm -f "$ps"/Qt/lib/*.dylib                        # ffmpeg, only QtMultimedia used it
    for f in "$ps"/Qt*.abi3.so "$ps"/Qt*.pyi; do
        [[ -e "$f" ]] || continue
        n="$(basename "$f")"; n="${n%%.*}"
        [[ "$keep_mod" == *" $n "* ]] || rm -f "$f"
    done
    for d in "$ps"/Qt/plugins/*; do
        [[ -d "$d" ]] || continue
        case "$(basename "$d")" in
            platforms|imageformats|styles|iconengines|generic|platformthemes) ;;
            *) rm -rf "$d" ;;
        esac
    done
    rm -f "$ps"/Qt/plugins/imageformats/libqpdf.dylib   # would pull QtPdf (9 MB) back in
    rm -rf "$ps"/Qt/qml "$ps"/Qt/translations "$ps"/Qt/libexec "$ps"/Qt/metatypes "$ps"/Qt/mkspecs \
           "$ps"/Qt/modules "$ps"/Qt/sbom "$ps"/include "$ps"/typesystems "$ps"/glue "$ps"/scripts \
           "$ps"/*.app "$ps"/libpyside6qml* "$ps"/*.pyi "$ps"/QtAsyncio "$ps"/QtExampleIcons* \
           "$sp"/shiboken6/*.pyi "$STAGE"/python/bin/pyside6-*
    # Command-line tools shipped next to the modules (qmlls, balsam,
    # uic, ...) link frameworks that are gone now; the viewer runs none
    # of them.  Gate 2 checks that every remaining relative dependency
    # resolves, which is what catches a leftover like these.
    for f in "$ps"/*; do
        [[ -f "$f" && -x "$f" ]] || continue
        case "$f" in *.so|*.dylib|*.py) continue ;; esac
        if file -b "$f" | grep -q 'Mach-O.*executable'; then rm -f "$f"; fi
    done

    # Thin universal binaries to $ARCH and re-sign them.  PySide6 and a
    # few other wheels ship universal2 Mach-O files; the x86_64 slices
    # are dead weight on an Apple-Silicon-only bundle and roughly
    # double the size of python/.  Writing through cat keeps each
    # file's mode, which lipo's output would not.
    log "Thinning universal binaries to $ARCH"
    local n=0 f
    while IFS= read -r f; do
        lipo -info "$f" 2>/dev/null | grep -q '^Architectures in the fat file' || continue
        lipo -thin "$ARCH" -output "$f.thin" "$f"
        cat "$f.thin" > "$f"
        rm -f "$f.thin"
        codesign -s - -f "$f" 2>/dev/null
        n=$((n + 1))
    done < <(find "$STAGE/python" -type f \( -name '*.so' -o -name '*.dylib' -o -perm +111 \) ! -name '*.py')
    log "Thinned $n files"

    # Qt's SQL client plugins link against libraries of the build box
    # (ODBC and Mimer from Homebrew, libpq from Postgres.app) that the
    # target does not have.  GeLB never touches QtSql; keep only the
    # self-contained sqlite driver.
    find "$sp/PySide6/Qt/plugins/sqldrivers" -name '*.dylib' ! -name 'libqsqlite.dylib' -delete 2>/dev/null || true
    # Some wheels (scipy, Pillow) keep LC_RPATH entries that point into
    # the build box's file system.  They are dead on the target; drop
    # every absolute rpath and re-sign, so nothing in the bundle names a
    # path that only exists on the machine that built the wheel.
    log "Dropping absolute rpaths"
    n=0
    while IFS= read -r f; do
        for rp in $(otool -l "$f" 2>/dev/null \
                    | awk '/LC_RPATH/ {r=1} r && /^ *path / {print $2; r=0}' \
                    | grep -E '^/' || true); do
            install_name_tool -delete_rpath "$rp" "$f" 2>/dev/null
            codesign -s - -f "$f" 2>/dev/null
            n=$((n + 1))
        done
    done < <(find "$STAGE/python" -type f \( -name '*.so' -o -name '*.dylib' \))
    log "Dropped $n absolute rpaths"
    log "GUI stack test (offscreen Qt)"
    QT_QPA_PLATFORM=offscreen "$PY" -c \
        'from PySide6 import QtCore, QtGui, QtWidgets; app = QtWidgets.QApplication([]); import gelb.visualization.gui.app; from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg; print("Qt", QtCore.qVersion(), "+ QtAgg + gelb GUI import OK")'

    # pip's console scripts carry build-host shebangs.  The wrappers in
    # bin/ replace gelbc and gelb-view; the rest (pip, ncinfo, f2py, ...)
    # get the relocatable header pip itself writes when a shebang would
    # be too long: sh runs the '''exec' line with the interpreter next to
    # the script, while Python reads lines 2-3 as one triple-quoted
    # string and moves on.  Every launcher is then run once.
    rm -f "$STAGE/python/bin/gelbc" "$STAGE/python/bin/gelb-view"
    local f
    for f in "$STAGE"/python/bin/*; do
        [[ -f "$f" && ! -L "$f" ]] || continue
        if head -n 1 "$f" | grep -q '^#!.*/python'; then
            { printf '#!/bin/sh\n'
              printf '%s\n' "'''exec' \"\$(dirname -- \"\$(realpath -- \"\$0\")\")/python$PY_MM\" \"\$0\" \"\$@\""
              printf "' '''\n"
              tail -n +2 "$f"; } > "$f.tmp"
            mv "$f.tmp" "$f"
            chmod 755 "$f"
        fi
    done
    # Self-test: every launcher must still parse as Python (a wrong
    # header shows up as a SyntaxError at line 2), and the sh side is
    # the same for all of them, so one real run (pip) covers it.  Tools
    # such as antlr4 exit non-zero without Java even for --help, so
    # running each one is not a valid check.
    for f in "$STAGE"/python/bin/*; do
        [[ -f "$f" && ! -L "$f" ]] || continue
        head -n 1 "$f" | grep -q '^#!/bin/sh' || continue
        "$PY" -m py_compile "$f" >/dev/null 2>&1 \
            || die "launcher broken: $(basename "$f") is not valid Python after the header rewrite"
    done
    rm -rf "$STAGE"/python/bin/__pycache__
    "$STAGE/python/bin/pip3" --version >/dev/null \
        || die "launcher broken: python/bin/pip3 does not run"

    # Test suites of the scientific packages (about 80 MB), Tk and IDLE,
    # the C headers and the pip-independent developer scripts: nothing
    # in GeLB runs them.  pip itself stays (11 MB): this phase needs it
    # to stay idempotent, and it lets the user add packages.
    log "Pruning test suites, Tk, IDLE, headers"
    find "$sp" -type d \( -name tests -o -name test \) -prune -exec rm -rf {} + 2>/dev/null || true
    rm -rf "$STAGE"/python/lib/python"$PY_MM"/{idlelib,lib2to3,tkinter} \
           "$STAGE"/python/lib/tcl* "$STAGE"/python/lib/tk* "$STAGE"/python/lib/libtcl* "$STAGE"/python/lib/libtk* \
           "$STAGE"/python/lib/python"$PY_MM"/lib-dynload/_tkinter*.so "$STAGE"/python/include \
           "$STAGE"/python/bin/idle* "$STAGE"/python/bin/2to3* "$STAGE"/python/bin/python*-config \
           "$sp"/matplotlib/mpl-data/sample_data
    # pip records where gelb was installed from; the path is the build
    # host's checkout and means nothing on the target.
    rm -f "$STAGE"/python/lib/python"$PY_MM"/site-packages/gelb-*.dist-info/direct_url.json

    # python/ and lib/ are copied: netCDF4 loads the bundle's NetCDF-C.
    log "Relocatability test (copy of python/ and lib/ in a temporary directory)"
    local tmp; tmp="$(mktemp -d "${TMPDIR:-/tmp}/gelb-reloc.XXXXXX")"
    cp -Rc "$STAGE/python" "$tmp/python" 2>/dev/null || cp -R "$STAGE/python" "$tmp/python"
    cp -R "$STAGE/lib" "$tmp/lib"
    "$tmp/python/bin/python$PY_MM" -c \
        'import gelb, numpy, scipy, matplotlib, netCDF4, sympy, PySide6; print("gelb", gelb.__version__, "imports OK from", __import__("sys").prefix)'
    "$tmp/python/bin/python$PY_MM" - "$NETCDF_VERSION" "$HDF5_VERSION" "$tmp" <<'PYTEST'
import os, sys
import numpy as np, netCDF4
want_nc, want_h5, tmp = sys.argv[1:]
got = (netCDF4.__netcdf4libversion__.split()[0], netCDF4.__hdf5libversion__)
assert got == (want_nc, want_h5), f"netCDF4 uses NetCDF-C/HDF5 {got}, not the bundled {want_nc}/{want_h5}"
assert os.path.realpath(netCDF4.__file__).startswith(os.path.realpath(tmp)), netCDF4.__file__
path = os.path.join(tmp, "t.nc")
with netCDF4.Dataset(path, "w") as d:
    d.createDimension("x", 4)
    d.createVariable("v", "f8", ("x",), compression="zlib")[:] = np.arange(4.0)
with netCDF4.Dataset(path) as d:
    assert d["v"][:].tolist() == [0.0, 1.0, 2.0, 3.0]
print("netCDF4", netCDF4.__version__, "on NetCDF-C", got[0], "+ HDF5", got[1], ": write/read OK")
PYTEST
    rm -rf "$tmp"

    # Bytecode caches last: the tests above regenerate a few.  Python
    # rebuilds them on first import (a second on the first gelbc run, a
    # few tens of MB over a session); shipping without them takes about
    # 70 MB off the install and 13 MB off the package.
    find "$STAGE/python" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
    log "Python phase done: $(du -sh "$STAGE/python" | cut -f1) in python/"
}

# -- Phase: assemble --------------------------------------------------
phase_assemble() {
    local hwy_src="$REPO_ROOT/third_party/highway" hwy_dst="$STAGE/third_party/highway"

    log "Wrappers, gelb-run, runtime headers"
    mkdir -p "$STAGE/bin" "$STAGE/scripts" "$STAGE/gelb/backends"
    rm -f "$STAGE"/bin/nc-config "$STAGE"/bin/h5*        # leftovers of the library builds
    install -m 755 "$SCRIPT_DIR"/wrappers/* "$STAGE/bin/"
    install -m 755 "$REPO_ROOT/scripts/gelb-run" "$STAGE/scripts/gelb-run"
    install -m 644 "$REPO_ROOT"/gelb/backends/*.hpp "$STAGE/gelb/backends/"

    log "Highway headers + the four support sources gelb-run compiles"
    rm -rf "$hwy_dst"
    mkdir -p "$hwy_dst/hwy"
    (cd "$hwy_src/hwy" && find . -name '*.h' -print0 \
        | (cd "$hwy_dst/hwy" && xargs -0 -I{} sh -c 'mkdir -p "$(dirname "{}")" && cp "'"$hwy_src"'/hwy/{}" "{}"'))
    for f in aligned_allocator.cc per_target.cc targets.cc abort.cc; do
        install -m 644 "$hwy_src/hwy/$f" "$hwy_dst/hwy/$f"
    done
    install -m 644 "$hwy_src/LICENSE" "$hwy_dst/LICENSE"
    [[ -f "$hwy_dst/hwy/highway.h" ]] || die "Highway copy failed"

    log "Examples"
    rm -rf "$STAGE/examples"
    ditto "$REPO_ROOT/examples" "$STAGE/examples"
    # Files git ignores there are outputs of local runs (*.nc, ...), not examples.
    git -C "$REPO_ROOT" ls-files -z --others --ignored --exclude-standard -- examples \
        | (cd "$STAGE" && xargs -0 rm -f --)
    find "$STAGE/examples" -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true

    log "Manual (sphinx-build -W)"
    rm -rf "$STAGE/docs/html"
    mkdir -p "$STAGE/docs"
    (cd "$REPO_ROOT" && uv run --extra docs -q sphinx-build -q -W -b html \
        -D html_copy_source=0 -d "$WORK/doctrees" docs "$STAGE/docs/html")
    [[ -f "$STAGE/docs/html/index.html" ]] || die "sphinx-build produced no index.html"
    rm -rf "$STAGE/docs/html/_sources"      # left empty by html_copy_source=0

    log "VS Code extension (gelb-lang $VSIX_VERSION)"
    mkdir -p "$STAGE/vscode-gelb"
    rm -f "$STAGE"/vscode-gelb/*.vsix
    (cd "$REPO_ROOT/vscode-gelb" \
        && { [[ -d node_modules ]] || npm ci --silent; } \
        && npm run --silent compile \
        && npx --yes @vscode/vsce package --out "$STAGE/vscode-gelb/gelb-lang-$VSIX_VERSION.vsix")
    [[ -f "$STAGE/vscode-gelb/gelb-lang-$VSIX_VERSION.vsix" ]] || die "vsce produced no .vsix"

    log "Guide, licence, metadata"
    install -m 644 "$SCRIPT_DIR/START_HERE.md" "$STAGE/START_HERE.md"
    for f in LICENSE README.md CITATION.cff CHANGELOG.md; do
        install -m 644 "$REPO_ROOT/$f" "$STAGE/$f"
    done
    local dirty="" branch sha hwy_sha
    git -C "$REPO_ROOT" diff --quiet HEAD -- . ':!MACOS_PACKAGING.md' 2>/dev/null || dirty="-dirty"
    branch="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)"
    sha="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
    hwy_sha="$(git -C "$hwy_src" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    cat > "$STAGE/VERSION" <<VER
gelb $GELB_VERSION
branch: $branch
commit: $sha$dirty
built: $(date +%F)
target: macOS $TARGET_MIN $ARCH
python: $PY_VERSION (python-build-standalone $PY_BUILD)
pyside6: $PYSIDE6_VERSION
openmp: LLVM $OMP_VERSION
hdf5: $HDF5_VERSION
netcdf-c: $NETCDF_VERSION
netcdf4-python: $("$PY" -B -c 'import importlib.metadata as m; print(m.version("netCDF4"))') (built against the bundled NetCDF-C)
highway: $hwy_sha
vscode extension: gelb-lang $VSIX_VERSION
VER

    log "Pruning what the target never needs"
    rm -rf "$STAGE/share" "$STAGE/cmake" "$STAGE/lib/cmake" "$STAGE/lib/pkgconfig" \
           "$STAGE/lib/libhdf5.settings" "$STAGE/lib/libnetcdf.settings"
    rm -f "$STAGE"/lib/*.a
    find "$STAGE/include" -mindepth 1 \
        ! -name omp.h ! -name ompt.h ! -name omp-tools.h ! -name netcdf.h ! -name netcdf_meta.h \
        -delete
    find "$STAGE" -name '.DS_Store' -delete
    log "Assemble phase done: $(du -sh "$STAGE" | cut -f1) staged at $STAGE"
}

# -- Phase: check -----------------------------------------------------
phase_check() {
    log "Gates"
    bash "$SCRIPT_DIR/check_bundle.sh" "$STAGE" "$TARGET_MIN"
}

# -- Phase: pkg -------------------------------------------------------
#
# A product archive for Installer.app: one component carries the payload
# and installs it at ~/gelb through the current-user-home domain (no
# administrator password); four payload-free components carry the
# postinstall scripts that set up zsh, bash, tcsh and the VS Code
# extension.  pkg/distribution.xml turns them into checkboxes on the
# Installation Type page, with the login shell preselected.  The
# archive is unsigned: on the target, Gatekeeper wants a right-click +
# Open (or `installer -pkg ... -target CurrentUserHomeDirectory`); a
# Developer ID signature plus notarization would remove that step.
product_path() {
    local sha; sha="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
    printf '%s' "$OUT/$BUNDLE_NAME-$ARCH-macos${TARGET_MIN%%.*}-$(date +%F)-$sha.pkg"
}
phase_pkg() {
    local pw="$WORK/pkg" pkg sh f
    rm -rf "$pw"
    mkdir -p "$pw/scripts/core" "$pw/scripts/vscode" "$pw/out" "$pw/resources"
    install -m 755 "$SCRIPT_DIR/pkg/scripts/core-preinstall" "$pw/scripts/core/preinstall"
    install -m 755 "$SCRIPT_DIR/pkg/scripts/core-postinstall" "$pw/scripts/core/postinstall"
    install -m 755 "$SCRIPT_DIR/pkg/scripts/vscode-postinstall" "$pw/scripts/vscode/postinstall"
    for sh in zsh bash tcsh; do
        mkdir -p "$pw/scripts/$sh"
        sed "s/@SHELL@/$sh/g" "$SCRIPT_DIR/pkg/scripts/shell-postinstall.in" > "$pw/scripts/$sh/postinstall"
        chmod 755 "$pw/scripts/$sh/postinstall"
    done
    log "Component packages"
    # --compression latest needs a minimum OS and packs about a third
    # tighter than the default; the target is macOS $TARGET_MIN anyway.
    pkgbuild --quiet --root "$STAGE" --install-location /gelb \
             --identifier org.gelb.pkg.core --version "$GELB_VERSION" \
             --compression latest --min-os-version "$TARGET_MIN" \
             --scripts "$pw/scripts/core" "$pw/out/core.pkg"
    for sh in zsh bash tcsh; do
        pkgbuild --quiet --nopayload --identifier "org.gelb.pkg.shell.$sh" --version "$GELB_VERSION" \
                 --scripts "$pw/scripts/$sh" "$pw/out/shell-$sh.pkg"
    done
    pkgbuild --quiet --nopayload --identifier org.gelb.pkg.vscode --version "$GELB_VERSION" \
             --scripts "$pw/scripts/vscode" "$pw/out/vscode.pkg"
    log "Product archive"
    sed -e "s/@VERSION@/$GELB_VERSION/g" -e "s/@TARGET_MIN@/$TARGET_MIN/g" \
        "$SCRIPT_DIR/pkg/distribution.xml" > "$pw/distribution.xml"
    for f in welcome.html readme.html conclusion.html; do
        sed "s/@VERSION@/$GELB_VERSION/g" "$SCRIPT_DIR/pkg/resources/$f" > "$pw/resources/$f"
    done
    install -m 644 "$REPO_ROOT/LICENSE" "$pw/resources/license.txt"
    pkg="$(product_path)"
    mkdir -p "$OUT"
    rm -f "$pkg"
    productbuild --quiet --distribution "$pw/distribution.xml" --resources "$pw/resources" \
                 --package-path "$pw/out" "$pkg"
    # Let the installer itself evaluate the distribution: choices present,
    # login-shell defaults working (SHELL is what the choice logic reads).
    SHELL=/bin/tcsh installer -pkg "$pkg" -target CurrentUserHomeDirectory -showChoicesXML > "$pw/choices-tcsh.xml" \
        || die "installer cannot read the product archive"
    for f in core shell_zsh shell_bash shell_tcsh vscode; do
        grep -q "<string>$f</string>" "$pw/choices-tcsh.xml" || die "choice '$f' missing from the product archive"
    done
    # choiceIsSelected sits a few keys after choiceIdentifier in the plist
    awk '/<string>shell_tcsh<\/string>/ {f=1} f && /choiceIsSelected/ {getline; print; exit}' "$pw/choices-tcsh.xml" \
        | grep -q '<integer>1</integer>' \
        || die "the tcsh choice is not preselected for a tcsh login shell"
    log "PKG: $pkg ($(du -h "$pkg" | cut -f1))"
}

# -- Phase: dmg (optional) --------------------------------------------
phase_dmg() {
    local pkg dmg root
    pkg="$(product_path)"
    [[ -f "$pkg" ]] || die "no $pkg: run the pkg phase first"
    root="$WORK/dmgroot"
    rm -rf "$root"; mkdir -p "$root"
    cp "$pkg" "$root/$BUNDLE_NAME.pkg"
    install -m 644 "$STAGE/START_HERE.md" "$root/START_HERE.md"
    dmg="${pkg%.pkg}.dmg"
    rm -f "$dmg"
    log "Creating $dmg"
    hdiutil create -volname "GeLB $GELB_VERSION" -srcfolder "$root" -ov -format UDZO "$dmg"
    hdiutil verify "$dmg"
    rm -rf "$root"
    log "DMG: $dmg ($(du -h "$dmg" | cut -f1))"
}

# -- Main -------------------------------------------------------------
if [[ "${CLEAN:-0}" == "1" ]]; then
    log "CLEAN=1: removing $STAGE and the build trees"
    rm -rf "$STAGE" "$WORK"/build-* "$WORK"/openmp-* "$WORK"/cmake "$WORK"/hdf5-* "$WORK"/netcdf-c-*
fi
mkdir -p "$STAGE" "$WORK" "$DL"

phases=("$@")
[[ ${#phases[@]} -gt 0 ]] || phases=(native python assemble check pkg)
for p in "${phases[@]}"; do
    case "$p" in
        native|python|assemble|check|pkg|dmg) "phase_$p" ;;
        *) die "unknown phase '$p' (native python assemble check pkg dmg)" ;;
    esac
done
