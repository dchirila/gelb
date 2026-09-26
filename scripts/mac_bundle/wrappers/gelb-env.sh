# gelb-env.sh -- sourced by the wrappers next to it; not meant to be run.
#
# Points scripts/gelb-run at the bundled Python, OpenMP runtime and
# NetCDF-C, so nothing is looked up on the host except the C++ compiler.
# GELB_HOME is the bundle root (the parent of this bin/ directory).
GELB_HOME="$(cd "$(dirname "$0")/.." && pwd -P)"
export GELB_HOME
export GELB_PYTHON="$GELB_HOME/python/bin/python3.12"
export GELB_CXX="${GELB_CXX:-clang++}"
export GELB_OMP_ROOT="$GELB_HOME"
export GELB_NETCDF_C_ROOT="$GELB_HOME"
