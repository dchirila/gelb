#!/usr/bin/env python3
"""End-to-end smoke tests for every ``.gelb`` example in the repo.

For each example x backend pair, the test:

  1. Compiles GeLB -> Fortran / C++ / CUDA C++ via ``gelbc``.
  2. Compiles the generated source with the matching native
     toolchain (``gfortran -O2`` for cpu_fortran_serial,
     ``g++ -O0 -march=native -fopenmp`` for cpu_highway, or ``nvcc
     -O0`` for gpu_cuda_cpp), linked against NetCDF.
  3. Runs the resulting binary for ``--smoke-iters`` timesteps.
  4. Asserts the process exits with code 0 (i.e. no crash, no
     numerical explosion that halts execution).

The goal is not to verify numerical accuracy -- that is the job of
the targeted e2e tests (``test_cpu_fortran_serial_e2e.py``,
``test_rayleigh_benard_mrt_e2e.py``, etc.).  This suite is a broad
regression guard: *all examples still compile and run without
blowing up*.  It is gated behind ``--run-smoke`` (see
``conftest.py``) because compiling every example for every backend
takes ~2 minutes even at N=10.

Usage::

    # Default: the smoke tests are skipped
    uv run pytest gelb/tests/integration/test_examples_smoke.py

    # Quick smoke run (default N=10)
    uv run pytest gelb/tests/integration/test_examples_smoke.py --run-smoke

    # Peace-of-mind run at N=50
    uv run pytest gelb/tests/integration/test_examples_smoke.py \\
        --run-smoke --smoke-iters=50

    # Serial Fortran only
    uv run pytest gelb/tests/integration/test_examples_smoke.py \\
        --run-smoke --smoke-backends=serial
"""

import os
import pathlib
import platform
import subprocess
import tempfile

import pytest


# macOS-26-SDK compatibility for Homebrew GCC.  See
# ``scripts/gelb-run`` for the same logic -- Homebrew GCC built
# against the macOS-26 SDK chokes on the new
# ``xnu_static_assert_struct_size`` macros in ``<mach/message.h>``.
# Falling back to the macOS-15 SDK is the documented workaround.
# Only applies if the user hasn't already pinned SDKROOT.
if (platform.system() == 'Darwin'
        and not os.environ.get('SDKROOT')
        and pathlib.Path('/Library/Developer/CommandLineTools/SDKs/'
                         'MacOSX15.sdk').is_dir()):
    os.environ['SDKROOT'] = ('/Library/Developer/CommandLineTools/'
                             'SDKs/MacOSX15.sdk')

from gelb.tests.integration._toolchain import (
    NC_FFLAGS as _NC_FFLAGS,
    NC_FLIBS as _NC_FLIBS,
    NC_CFLAGS as _NC_CFLAGS,
    NC_CLIBS as _NC_CLIBS,
    CPP_HIGHWAY_INCLUDES as _CPP_HIGHWAY_INCLUDES,
    CPP_HIGHWAY_SUPPORT as _CPP_HIGHWAY_SUPPORT,
    GPU_CUDA_CPP_INCLUDES as _GPU_CUDA_CPP_INCLUDES,
    HAS_GXX as _HAS_GXX,
    HAS_NETCDF_C as _HAS_NETCDF_C,
    HAS_HWY_HEADERS as _HAS_HWY_HEADERS,
    HAS_CPP_RUNTIME_COMMON as _HAS_CPP_RUNTIME_COMMON,
    HAS_CPU_HIGHWAY_RUNTIME as _HAS_CPU_HIGHWAY_RUNTIME,
    HAS_NVCC as _HAS_NVCC,
    HAS_NVIDIA_GPU as _HAS_NVIDIA_GPU,
    HAS_GPU_CUDA_CPP_RUNTIME as _HAS_GPU_CUDA_CPP_RUNTIME,
    requires_compiler,
)


# ---------------------------------------------------------------------------
# Example discovery
# ---------------------------------------------------------------------------

# Anchor at the repo root (two levels up from this file, gelb/tests/integration/)
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_EXAMPLES_DIR = _REPO_ROOT / "examples"


def _discover_examples():
    """Return a sorted list of all .gelb paths under examples/."""
    if not _EXAMPLES_DIR.is_dir():
        return []
    return sorted(_EXAMPLES_DIR.rglob("*.gelb"))


_EXAMPLES = _discover_examples()


def _example_id(path: pathlib.Path) -> str:
    """Readable pytest parametrize id for an example path."""
    return str(path.relative_to(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Compile & run
# ---------------------------------------------------------------------------

def _gelbc_compile(example_path: pathlib.Path, out_src: pathlib.Path,
                   num_timesteps: int,
                   backend: str = 'cpu_fortran_serial'
                   ) -> subprocess.CompletedProcess:
    """Invoke gelbc (the Click CLI) in-process to lower a .gelb file.

    ``backend`` selects ``cpu_fortran_serial`` (writes Fortran 90,
    .f90 extension) or ``cpu_highway`` (writes C++17, .cpp extension).
    The caller is responsible for picking a matching ``out_src``
    extension.

    Using ``cli.main(..., standalone_mode=False)`` avoids the overhead
    of spawning a Python interpreter per example -- worth it when
    exercising dozens of files in a single test session.
    """
    from gelb.gelbc import cli as gelbc_cli

    args = [
        str(example_path),
        "--backend", backend,
        "-o", str(out_src),
        "--num-timesteps", str(num_timesteps),
        "--write-every", str(max(num_timesteps, 1)),
        "--nc-output", "smoke.nc",
    ]
    try:
        gelbc_cli.main(args=args, standalone_mode=False)
    except Exception as exc:  # Click-raised or compiler-raised
        return subprocess.CompletedProcess(
            args, 1, b"", f"gelbc raised {type(exc).__name__}: {exc}".encode())
    return subprocess.CompletedProcess(args, 0, b"", b"")


def _gfortran_compile(src: pathlib.Path, exe: pathlib.Path,
                      ) -> subprocess.CompletedProcess:
    """Compile the generated Fortran with gfortran + NetCDF.

    The cpu_fortran_serial backend is single-threaded by design;
    no ``-fopenmp`` here.  ``-ffree-line-length-none`` matches the
    default gelb-run behaviour and lifts the gfortran 132-char
    free-form line limit (long ``simulation_description`` strings
    with non-ASCII punctuation occasionally exceed it)."""
    fflags = "-O2 -ffree-line-length-none"
    cmd = f"gfortran {fflags} {_NC_FFLAGS} -o {exe} {src} {_NC_FLIBS}"
    return subprocess.run(
        cmd, shell=True, capture_output=True, timeout=60)


def _gpp_compile(src: pathlib.Path, exe: pathlib.Path,
                 *,
                 includes: str = '',
                 extra_sources: str = '',
                 ) -> subprocess.CompletedProcess:
    """Compile cpu_highway-generated C++ with g++ + OpenMP.

    Mirrors the flag shape used by ``scripts/gelb-run`` for the
    cpu_highway backend, minus the perf-tuning flags
    (``-march=native -O3 -fno-trapping-math -fno-unroll-loops``).
    A smoke test only verifies "compiles + exits cleanly", so
    plain ``-O0`` keeps compile time bounded (relevant: Highway
    target dispatch inflates compile times under -O3).

    cpu_highway needs ``-march=native`` even at -O0 because
    Highway's ``#pragma GCC target`` block expects native-target
    intrinsics to be available -- otherwise the AVX-512 / AVX-2
    intrinsics referenced by ``hwy/ops/x86_*-inl.h`` are
    undeclared.

    ``-fopenmp`` is mandatory because the cpu_highway emit
    contains ``#pragma omp parallel for`` directives in every dyn
    body.

    ``extra_sources`` lists additional .cc files to compile inline
    (e.g. Highway's aligned-allocator / abort / target-dispatch
    support TUs, needed because ``hwy/contrib/random/`` and
    ``hwy/aligned_allocator.h`` aren't header-only).
    """
    cxxflags = "-std=c++17 -O0 -march=native -fopenmp -DNDEBUG"
    # Honour ``GELB_CXX`` (matches ``scripts/gelb-run``).  On macOS
    # the system ``g++`` is apple-clang, which has no OpenMP -- the
    # caller is expected to point GELB_CXX at Homebrew GCC.
    cxx = os.environ.get('GELB_CXX', 'g++')
    cmd = (f"{cxx} {cxxflags} {includes} {_NC_CFLAGS} "
           f"-o {exe} {src} {extra_sources} {_NC_CLIBS}")
    return subprocess.run(
        cmd, shell=True, capture_output=True, timeout=120)


def _nvcc_compile(src: pathlib.Path, exe: pathlib.Path,
                   *, includes: str = '',
                   ) -> subprocess.CompletedProcess:
    """Compile gpu_cuda_cpp-generated CUDA C++ with nvcc + NetCDF-C.

    Mirrors ``scripts/gelb-run``'s gpu_cuda_cpp branch.  Uses
    ``-O0`` (smoke goal: "compiles + exits cleanly", not perf).
    Default ``-arch=sm_89`` matches the CUDA tuning baseline;
    overrideable via ``GELB_NVCC_ARCH``.

    Translates ``-Wl,-rpath,DIR`` from ``nc-config --libs`` into
    nvcc's native ``-Xlinker -rpath -Xlinker DIR`` pairs (nvcc
    rejects ``-Wl,X`` directly).
    """
    import re
    nvcc = os.environ.get('GELB_NVCC', 'nvcc')
    arch = os.environ.get('GELB_NVCC_ARCH', '-arch=sm_89')
    nvccflags = (f'-O0 {arch} -std=c++17 --expt-relaxed-constexpr '
                 f'-DNDEBUG -diag-suppress=177')
    nc_libs = re.sub(
        r'-Wl,-rpath,(\S+)', r'-Xlinker -rpath -Xlinker \1',
        re.sub(r'-Wl,(\S+)', r'-Xlinker \1', _NC_CLIBS))
    cmd = (f"{nvcc} {nvccflags} {includes} {_NC_CFLAGS} "
           f"-o {exe} {src} {nc_libs}")
    return subprocess.run(
        cmd, shell=True, capture_output=True, timeout=180)


def _run_exe(exe: pathlib.Path, cwd: pathlib.Path,
             openmp: bool) -> subprocess.CompletedProcess:
    """Run the compiled binary, bounded by timeout.

    For OpenMP builds (cpu_highway only -- cpu_fortran_serial is
    strictly single-threaded, gpu_cuda_cpp runs on the GPU), lift
    the main-thread stack limit before exec as a safety belt.  With
    ``g++ -fopenmp`` the per-cell arrays in the dyn body go on
    worker-thread stacks (sized via ``OMP_STACKSIZE``, default
    4 MB on libgomp) and our arrays are only a few KB, so the
    unlimited main stack is defence in depth rather than strictly
    required; it insulates the smoke suite from libgomp / glibc
    version drift.  The branch can go once the smoke matrix passes
    without it.
    """
    if openmp:
        cmd = f"ulimit -s unlimited 2>/dev/null || ulimit -s hard; exec {exe}"
        return subprocess.run(
            cmd, shell=True, executable="/bin/bash",
            capture_output=True, timeout=90, cwd=str(cwd))
    return subprocess.run(
        [str(exe)], capture_output=True, timeout=90, cwd=str(cwd))


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

if not _EXAMPLES:
    # If the examples directory isn't found, emit a single placeholder
    # test so pytest's "no tests collected" doesn't mask the real issue.
    @pytest.mark.smoke
    def test_examples_directory_missing():
        pytest.skip(f"Examples directory not found at {_EXAMPLES_DIR}")
else:
    # Per-backend toolchain skip reasons.  ``serial`` needs gfortran +
    # NetCDF-Fortran (handled by ``requires_compiler`` at test-class
    # level -- applied below via marker indirection).  ``cpu_highway``
    # needs g++ + NetCDF-C + vendored Highway + runtime headers.
    _CPP_HIGHWAY_TOOLCHAIN_OK = (_HAS_GXX and _HAS_NETCDF_C
                                  and _HAS_HWY_HEADERS
                                  and _HAS_CPU_HIGHWAY_RUNTIME
                                  and _HAS_CPP_RUNTIME_COMMON)
    _GPU_CUDA_CPP_TOOLCHAIN_OK = (_HAS_NVCC and _HAS_NVIDIA_GPU
                                   and _HAS_NETCDF_C
                                   and _HAS_GPU_CUDA_CPP_RUNTIME
                                   and _HAS_CPP_RUNTIME_COMMON)

    @pytest.mark.smoke
    @requires_compiler
    @pytest.mark.parametrize(
        "example_path",
        _EXAMPLES,
        ids=[_example_id(p) for p in _EXAMPLES],
    )
    @pytest.mark.parametrize(
        "backend",
        ["serial", "cpu_highway", "gpu_cuda_cpp"])
    def test_example_compiles_and_runs(
            example_path, backend, smoke_backends, smoke_iters):
        """Compile and run one example for N timesteps on one backend.

        Backends:
          * ``serial``        -- Fortran (gfortran + NetCDF-Fortran).
                                cpu_fortran_serial is single-threaded
                                by design (educational + correctness
                                reference; perf is cpu_highway's job).
          * ``cpu_highway``   -- C++17 (g++ + NetCDF-C + Google Highway).
                                Always runs with OpenMP (the backend
                                emits OMP pragmas in its SIMD loops by
                                default).
          * ``gpu_cuda_cpp``  -- CUDA C++ (nvcc + NetCDF-C).  Skipped on
                                machines without ``nvcc`` or without an
                                NVIDIA GPU.
        """
        if backend not in smoke_backends:
            pytest.skip(f"backend '{backend}' not in --smoke-backends")

        is_cpu_highway = (backend == "cpu_highway")
        is_gpu_cuda_cpp = (backend == "gpu_cuda_cpp")
        if is_cpu_highway and not _CPP_HIGHWAY_TOOLCHAIN_OK:
            pytest.skip(
                "cpu_highway backend requires g++, NetCDF-C, and "
                "Highway/C++ runtime headers")
        if is_gpu_cuda_cpp and not _GPU_CUDA_CPP_TOOLCHAIN_OK:
            pytest.skip(
                "gpu_cuda_cpp backend requires nvcc, an NVIDIA GPU, "
                "NetCDF-C, and CUDA C++ runtime headers")

        is_cpp = is_cpu_highway
        # cpu_highway is the only OMP backend; cpu_fortran_serial is
        # always serial; gpu_cuda_cpp runs on the GPU.
        openmp = is_cpu_highway

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = pathlib.Path(tmp)
            if is_gpu_cuda_cpp:
                src_ext = ".cu"
            elif is_cpp:
                src_ext = ".cpp"
            else:
                src_ext = ".f90"
            out_src = tmpdir / f"sim{src_ext}"
            exe = tmpdir / "sim"

            # 1) GeLB -> Fortran or C++ or CUDA C++.
            if is_cpu_highway:
                gelbc_backend = 'cpu_highway'
            elif is_gpu_cuda_cpp:
                gelbc_backend = 'gpu_cuda_cpp'
            else:
                gelbc_backend = 'cpu_fortran_serial'
            rc = _gelbc_compile(
                example_path, out_src,
                num_timesteps=smoke_iters,
                backend=gelbc_backend)
            if rc.returncode != 0:
                pytest.fail(
                    f"gelbc failed on {example_path.name} "
                    f"[{backend}]:\n{rc.stderr.decode()[:600]}")
            assert out_src.is_file(), \
                f"gelbc did not produce {out_src}"

            # 2) Source -> binary.
            if is_gpu_cuda_cpp:
                rc = _nvcc_compile(out_src, exe,
                                    includes=_GPU_CUDA_CPP_INCLUDES)
                native_name = 'nvcc'
            elif is_cpp:
                rc = _gpp_compile(out_src, exe,
                                   includes=_CPP_HIGHWAY_INCLUDES,
                                   extra_sources=_CPP_HIGHWAY_SUPPORT)
                native_name = 'g++'
            else:
                rc = _gfortran_compile(out_src, exe)
                native_name = 'gfortran'
            if rc.returncode != 0:
                pytest.fail(
                    f"{native_name} failed on {example_path.name} "
                    f"[{backend}]:\n{rc.stderr.decode()[:800]}")

            # 3) Run for smoke_iters steps.
            try:
                rc = _run_exe(exe, cwd=tmpdir, openmp=openmp)
            except subprocess.TimeoutExpired:
                pytest.fail(
                    f"Execution timed out after 90s on "
                    f"{example_path.name} [{backend}]")
            if rc.returncode != 0:
                stderr = rc.stderr.decode()[:800]
                stdout = rc.stdout.decode()[-400:]
                pytest.fail(
                    f"Execution failed on {example_path.name} "
                    f"[{backend}] (rc={rc.returncode}):\n"
                    f"--- stderr ---\n{stderr}\n"
                    f"--- stdout (tail) ---\n{stdout}")
