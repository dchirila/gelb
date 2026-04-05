"""Shared compiler + NetCDF toolchain detection for integration tests.

Several integration-test modules need to compile generated source
against the matching language's compiler + NetCDF binding.  Each used
to duplicate the detection helpers; this module hosts the canonical
copies for both:

  * Fortran (``gfortran`` + NetCDF-Fortran via nf-config) -- covers the
    ``cpu_fortran_serial`` backend smoke.
  * C++ (``g++`` + NetCDF-C via nc-config + vendored Highway headers) --
    covers the ``cpu_highway`` backend smoke.

Exports:
    detect_nc_flags()   -> (fflags, flibs) | (None, None)   [Fortran]
    detect_nc_c_flags() -> (cflags, libs)  | (None, None)   [C++]
    HAS_GFORTRAN, HAS_NETCDF, NC_FFLAGS, NC_FLIBS
    HAS_GXX, HAS_NETCDF_C, NC_CFLAGS, NC_CLIBS
    requires_compiler             -- pytest.mark.skipif for Fortran toolchain
    requires_cpp_highway_compiler -- pytest.mark.skipif for C++/cpu_highway toolchain
"""

import pathlib
import shutil
import subprocess

import pytest


def detect_nc_flags():
    """Return (fflags, flibs) from nf-config, or (None, None) if unavailable.

    Also prepends ``-L<nc-prefix>/lib`` to flibs when nc-config reports a
    prefix that isn't already in the linker path.
    """
    try:
        fflags = subprocess.check_output(
            ['nf-config', '--fflags'], text=True).strip().split('\n')[0]
        flibs = subprocess.check_output(
            ['nf-config', '--flibs'], text=True).strip().split('\n')[0]
        try:
            nc_prefix = subprocess.check_output(
                ['nc-config', '--prefix'], text=True).strip()
            c_libdir = f'-L{nc_prefix}/lib'
            if c_libdir not in flibs:
                flibs = f'{c_libdir} {flibs}'
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        return fflags, flibs
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None, None


HAS_GFORTRAN = shutil.which('gfortran') is not None
NC_FFLAGS, NC_FLIBS = detect_nc_flags()
HAS_NETCDF = NC_FFLAGS is not None

_SKIP_REASON = (
    'gfortran not found' if not HAS_GFORTRAN else
    'NetCDF-Fortran not found' if not HAS_NETCDF else
    ''
)

requires_compiler = pytest.mark.skipif(
    not (HAS_GFORTRAN and HAS_NETCDF),
    reason=_SKIP_REASON or 'compiler toolchain not available',
)


# ----------------------------------------------------------------------
# C++ / cpu_highway backend toolchain
# ----------------------------------------------------------------------


def detect_nc_c_flags():
    """Return (cflags, libs) from nc-config (NetCDF-C), or
    (None, None) if unavailable.

    The cpu_highway backend emits C++ that links against NetCDF-C
    (not NetCDF-Fortran), so it needs separate detection from the
    Fortran toolchain above.
    """
    try:
        cflags = subprocess.check_output(
            ['nc-config', '--cflags'], text=True).strip().split('\n')[0]
        libs = subprocess.check_output(
            ['nc-config', '--libs'], text=True).strip().split('\n')[0]
        return cflags, libs
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None, None


HAS_GXX = shutil.which('g++') is not None
NC_CFLAGS, NC_CLIBS = detect_nc_c_flags()
HAS_NETCDF_C = NC_CFLAGS is not None

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_RUNTIME_INC_DIR = _REPO_ROOT / "gelb" / "backends"

# Google Highway headers are vendored at third_party/highway/.  The
# cpu_highway backend's emitted code includes them via
# ``#include "hwy/highway.h"``, ``#include "cpu_highway_runtime.hpp"``,
# and the shared ``cpp_runtime_common.hpp`` included by the runtime
# header.  Runtime headers live under gelb/backends/.
_HWY_INC_DIR = _REPO_ROOT / "third_party" / "highway"
HAS_HWY_HEADERS = (_HWY_INC_DIR / "hwy" / "highway.h").is_file()
HAS_CPP_RUNTIME_COMMON = (
    _RUNTIME_INC_DIR / "cpp_runtime_common.hpp").is_file()
HAS_CPU_HIGHWAY_RUNTIME = (
    _RUNTIME_INC_DIR / "cpu_highway_runtime.hpp").is_file()

CPP_HIGHWAY_INCLUDES = (f'-I{_HWY_INC_DIR} -I{_RUNTIME_INC_DIR}'
                        if (HAS_HWY_HEADERS
                            and HAS_CPU_HIGHWAY_RUNTIME
                            and HAS_CPP_RUNTIME_COMMON) else '')

# Highway's contrib PRNG + aligned allocator are not header-only --
# four small support .cc files need to be compiled inline alongside
# the generated source.  Mirrors the ``GELB_HWY_SUPPORT`` shape
# from ``scripts/gelb-run`` so the smoke harness and gelb-run
# produce equivalent binaries.
_HWY_DIR = _HWY_INC_DIR / "hwy"
CPP_HIGHWAY_SUPPORT = (
    f'{_HWY_DIR / "aligned_allocator.cc"} '
    f'{_HWY_DIR / "per_target.cc"} '
    f'{_HWY_DIR / "targets.cc"} '
    f'{_HWY_DIR / "abort.cc"}'
    if HAS_HWY_HEADERS else '')

_HIGHWAY_SKIP_REASON = (
    'g++ not found' if not HAS_GXX else
    'NetCDF-C not found' if not HAS_NETCDF_C else
    'Highway headers not at third_party/highway/'
        if not HAS_HWY_HEADERS else
    'cpu_highway_runtime.hpp missing'
        if not HAS_CPU_HIGHWAY_RUNTIME else
    'cpp_runtime_common.hpp missing'
        if not HAS_CPP_RUNTIME_COMMON else
    ''
)

requires_cpp_highway_compiler = pytest.mark.skipif(
    not (HAS_GXX and HAS_NETCDF_C and HAS_HWY_HEADERS
         and HAS_CPU_HIGHWAY_RUNTIME and HAS_CPP_RUNTIME_COMMON),
    reason=_HIGHWAY_SKIP_REASON or 'cpu_highway toolchain not available',
)


# ----------------------------------------------------------------------
# CUDA C++ backend toolchain (gpu_cuda_cpp)
# ----------------------------------------------------------------------

# nvcc from the CUDA toolkit (system package or NVIDIA HPC SDK).
HAS_NVCC = shutil.which('nvcc') is not None

# A CUDA-capable GPU + working driver.  ``nvidia-smi`` exits 0 only
# when the driver is loaded AND at least one GPU is enumerated;
# pure-software nvcc installs (e.g. macOS, headless CI runners
# without GPUs) skip cleanly.
def _has_nvidia_gpu() -> bool:
    if shutil.which('nvidia-smi') is None:
        return False
    try:
        rc = subprocess.run(
            ['nvidia-smi', '-L'],
            capture_output=True, timeout=5)
        return rc.returncode == 0 and len(rc.stdout) > 0
    except (subprocess.TimeoutExpired, OSError):
        return False

HAS_NVIDIA_GPU = _has_nvidia_gpu()

# Runtime headers ship under gelb/backends/ (same dir as the CPU runtime
# headers).  No third_party submodule needed -- gpu_cuda_cpp uses the same
# NetCDF-C as cpu_highway.
HAS_GPU_CUDA_CPP_RUNTIME = (
    _RUNTIME_INC_DIR / "gpu_cuda_cpp_runtime.cuh").is_file()

GPU_CUDA_CPP_INCLUDES = (f'-I{_RUNTIME_INC_DIR}'
                          if (HAS_GPU_CUDA_CPP_RUNTIME
                              and HAS_CPP_RUNTIME_COMMON) else '')

_GPU_CUDA_CPP_SKIP_REASON = (
    'nvcc not found' if not HAS_NVCC else
    'no NVIDIA GPU detected (nvidia-smi -L empty)'
        if not HAS_NVIDIA_GPU else
    'NetCDF-C not found' if not HAS_NETCDF_C else
    'gpu_cuda_cpp_runtime.cuh missing'
        if not HAS_GPU_CUDA_CPP_RUNTIME else
    'cpp_runtime_common.hpp missing'
        if not HAS_CPP_RUNTIME_COMMON else
    ''
)

requires_gpu_cuda_cpp_compiler = pytest.mark.skipif(
    not (HAS_NVCC and HAS_NVIDIA_GPU and HAS_NETCDF_C
         and HAS_GPU_CUDA_CPP_RUNTIME and HAS_CPP_RUNTIME_COMMON),
    reason=_GPU_CUDA_CPP_SKIP_REASON
        or 'gpu_cuda_cpp toolchain not available',
)
