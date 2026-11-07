"""Every example compiles with GeLB's optional passes off.

The plain build (``--no-slice-simplify --no-scalar-cse``) is the
reference for those two passes (user manual, Numerical semantics), so
it must compile wherever the default build does.  The examples gate,
the smoke runs and the emission snapshots build only the default code;
this test generates every example's plain build on each backend and
runs the native compiler's syntax check on it, with gelb-run's default
flags on Linux.
"""

import concurrent.futures
import os
import pathlib
import subprocess
import sys

import pytest

from gelb.tests.integration._toolchain import (
    CPP_HIGHWAY_INCLUDES,
    GPU_CUDA_CPP_INCLUDES,
    NC_CFLAGS,
    NC_FFLAGS,
    requires_compiler,
    requires_cpp_highway_compiler,
    requires_gpu_cuda_cpp_compiler,
)

_ROOT = pathlib.Path(__file__).resolve().parents[3]
EXAMPLES = sorted((_ROOT / "examples").rglob("*.gelb"))
PLAIN = ("--no-slice-simplify", "--no-scalar-cse")


def _syntax_command(backend, source):
    if backend == "cpu_highway":
        return [os.environ.get("GELB_CXX", "g++"), "-std=c++17", "-fopenmp",
                "-march=native", "-fsyntax-only", *CPP_HIGHWAY_INCLUDES.split(),
                *NC_CFLAGS.split(), str(source)]
    if backend == "gpu_cuda_cpp":
        return ["nvcc", os.environ.get("GELB_NVCC_ARCH", "-arch=sm_89"),
                "-std=c++17", "--expt-relaxed-constexpr", "-diag-suppress=177",
                "--cuda", *GPU_CUDA_CPP_INCLUDES.split(), *NC_CFLAGS.split(),
                str(source), "-o", os.devnull]
    return ["gfortran", "-fsyntax-only", "-fno-range-check",
            "-ffree-line-length-none", *NC_FFLAGS.split(), str(source)]


def _check(directory, backend, example):
    """None if ``example``'s plain build compiles, else the first error."""
    directory.mkdir()
    source = directory / ("prog" + {"cpu_highway": ".cpp",
                                    "gpu_cuda_cpp": ".cu"}.get(backend, ".f90"))
    gen = subprocess.run(
        [sys.executable, "-c", "from gelb.gelbc import cli; cli()",
         str(example), "-b", backend, "-o", str(source), *PLAIN],
        cwd=directory, capture_output=True, text=True, timeout=600)
    if gen.returncode != 0:
        return f"gelbc: {(gen.stdout + gen.stderr).strip()[-300:]}"
    build = subprocess.run(_syntax_command(backend, source), cwd=directory,
                           capture_output=True, text=True, timeout=600)
    if build.returncode != 0:
        output = build.stdout + build.stderr
        return next((line for line in output.splitlines() if "error" in line),
                    output.strip()[-300:])
    return None


@pytest.mark.parametrize("backend", [
    pytest.param("cpu_highway", marks=requires_cpp_highway_compiler),
    pytest.param("gpu_cuda_cpp", marks=requires_gpu_cuda_cpp_compiler),
    pytest.param("cpu_fortran_serial", marks=requires_compiler),
])
def test_every_example_compiles_in_the_plain_build(tmp_path, backend):
    assert EXAMPLES
    with concurrent.futures.ThreadPoolExecutor(os.cpu_count() or 2) as pool:
        results = pool.map(
            lambda i_example: _check(tmp_path / str(i_example[0]), backend,
                                     i_example[1]),
            enumerate(EXAMPLES))
        failures = [f"{example.relative_to(_ROOT)}: {error}"
                    for example, error in zip(EXAMPLES, results) if error]
    assert not failures, "\n".join(failures)
