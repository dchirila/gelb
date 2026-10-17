"""Compare scalar/slice/array execution with independently compiled C++."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from gelb.tests.integration._toolchain import (
    HAS_GFORTRAN,
    HAS_NETCDF_C,
    requires_cpp_highway_compiler,
    requires_gpu_cuda_cpp_compiler,
)

from .cases import ACTIVE_SEED, CASES, RANDOM_COUNT, runtime_source
from .checks import check_values
from .known_failures import check_build, mark_known_failure

netCDF4 = pytest.importorskip("netCDF4")
REPO = Path(__file__).resolve().parents[3]
RUNTIME_CASES = tuple(case for case in CASES if case.runtime)
SURFACES = ("scalar", "slice", "declaration", "assignment")
BACKENDS = [
    pytest.param("cpu_fortran_serial", marks=pytest.mark.skipif(
        not (HAS_GFORTRAN and HAS_NETCDF_C), reason="gfortran or NetCDF-C unavailable")),
    pytest.param("cpu_highway", marks=requires_cpp_highway_compiler),
    pytest.param("gpu_cuda_cpp", marks=[pytest.mark.gpu, requires_gpu_cuda_cpp_compiler]),
]
MODES = {
    "optimized": "",
    "plain": "--no-collinearity-rewrite --no-scalar-cse --no-slice-simplify",
}
# ``GELB_NVCC_FLAGS`` replaces ``gelb-run``'s default flag string whole,
# so the arch has to be repeated here: without it ``GELB_NVCC_ARCH`` is
# inert, nvcc emits PTX for its own default arch and the driver has to
# JIT it.  On CUDA 13.2 with driver 580 that JIT fails outright ("the
# provided PTX was compiled with an unsupported toolchain"), so every
# CUDA case failed to build.  ``-arch`` makes nvcc emit SASS for the
# GPU instead.
NVCC_ARCH = os.environ.get("GELB_NVCC_ARCH", "-arch=sm_89")


@pytest.fixture(scope="module", params=BACKENDS)
def backend(request):
    return request.param


@pytest.fixture(scope="module", params=MODES)
def mode(request):
    return request.param


@pytest.fixture(scope="module")
def runtime_results(backend, mode, tmp_path_factory, numeric_oracle):
    # One build per backend/mode, shared by independently reported case checks.
    work = tmp_path_factory.mktemp(f"numeric_{backend}_{mode}")
    flags = {
        "GELBC_EXTRA": MODES[mode],
        "GELB_FFLAGS": "-O0 -fno-fast-math -ffp-contract=off -fno-range-check -ffree-line-length-none",
        "GELB_CXXFLAGS": "-std=c++17 -O0 -fno-fast-math -ffp-contract=off",
        "GELB_NVCC_FLAGS": f"-O0 {NVCC_ARCH} --fmad=false --ftz=false --prec-div=true "
                           "--prec-sqrt=true -std=c++17 --expt-relaxed-constexpr "
                           "-DNDEBUG -diag-suppress=177",
    }
    env = dict(os.environ, GELB_PYTHON=sys.executable, OMP_NUM_THREADS="2", **flags)
    (work / "manifest.json").write_text(json.dumps({
        "seed": ACTIVE_SEED, "random_count": RANDOM_COUNT,
        "flags": flags, "cases": [vars(case) for case in RUNTIME_CASES],
    }, indent=2) + "\n")
    results = {}

    def run_batch(cases, label):
        directory = work / label
        directory.mkdir()
        source = directory / "cases.gelb"
        source.write_text(runtime_source(cases))
        command = [str(REPO / "scripts" / "gelb-run"), "--keep", "-b", backend,
                   "-n", "1", "-w", "1", str(source)]
        try:
            run = subprocess.run(command, cwd=directory, env=env, capture_output=True,
                                 text=True, timeout=600, check=False)
            log = run.stdout + run.stderr
            (directory / "command.json").write_text(json.dumps(command) + "\n")
            (directory / "run.log").write_text(log)
            if run.returncode:
                # Isolate a rejected program so it cannot prevent numerical
                # checks for unrelated expressions. Never silently drop it.
                if len(cases) > 1:
                    middle = len(cases) // 2
                    run_batch(cases[:middle], label + "L")
                    run_batch(cases[middle:], label + "R")
                else:
                    results[cases[0].name] = {"error": log, "source": str(source)}
                return
            files = list(directory.glob("*.nc"))
            assert len(files) == 1, f"expected one NetCDF output: {files}"
            with netCDF4.Dataset(files[0]) as dataset:
                for i, case in enumerate(cases):
                    results[case.name] = {
                        "values": {surface: dataset[f"case{i}_{surface}"][1].filled().tolist()
                                   for surface in SURFACES}, "source": str(source)}
        finally:
            # Keep generated source with --keep; discard binaries and outputs.
            for path in directory.glob("*.nc"):
                path.unlink()
            (directory / "cases").unlink(missing_ok=True)
            for pattern in ("*.o", "*.mod"):
                for path in directory.glob(pattern):
                    path.unlink()

    for cells in sorted({case.cells for case in RUNTIME_CASES}):
        group = [case for case in RUNTIME_CASES if case.cells == cells]
        run_batch(group, f"batch{cells}")
        if backend == "cpu_highway" and cells == 67 and "error" not in results[group[0].name]:
            # The SIMD-sized all-real program does enter the vector body
            # (its coordinate-division block takes the scalar path).
            generated = Path(results[group[0].name]["source"]).with_suffix(".cpp").read_text()
            assert "hn::Iota(d, static_cast<double>(g_x))" in generated
    (work / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    assert set(results) == {case.name for case in RUNTIME_CASES}
    return results


@pytest.mark.parametrize("case", RUNTIME_CASES, ids=lambda c: c.name)
@pytest.mark.parametrize("surface", SURFACES)
def test_generated_runtime_matches_native_cpp(case, surface, backend, mode,
                                               runtime_results, numeric_oracle, request):
    mark_known_failure(request.node, case, backend, mode, surface)
    result = runtime_results[case.name]
    check_build(result, case, backend)
    expected = [numeric_oracle[case.name][x]["stored"] for x in range(case.cells)]
    ulps = case.reassociation_ulps if mode == "optimized" and surface == "slice" else 0
    check_values(result["values"][surface], expected, case=case,
                 context=f"{backend}/{mode}/{surface}", source=runtime_source((case,)), ulps=ulps)
