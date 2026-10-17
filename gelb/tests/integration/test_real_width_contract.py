"""``real`` is double precision in every backend, whatever the lattices'
type, and a ``real32`` expression is single precision (user manual,
Numerical semantics: Types and promotion), and a numeric kind, the
evaluation order and a value survive simplification and CSE.  Two
programs with real32
lattices, run on both CPU backends through ``scripts/gelb-run``:

* ``real`` widening: ``u + 1.0 - u`` with u = 2^24 in real32 is 1.0
  when the addition is double precision (2^24 + 1 is exact there) and
  0.0 when it is single precision (2^24 + 1 rounds to 2^24).  The
  Fortran backend used to pick a "dominant" real kind per program and
  spell ``real`` as real(4) in a real32 program, giving 0.0.
* ``real32`` narrowness: ``(u * w) * w`` in real32 is rounded after each
  product; a backend that spells the real32 constant as a C++ double
  literal evaluates the chain in double and rounds once.  The pair
  u = 1.3, w = 0.1 was chosen because the two results differ; the
  expected value is computed here with NumPy's binary32 arithmetic.
"""

import math
import os
import pathlib
import shutil
import subprocess
import sys

import numpy as np
import pytest

from gelb.tests.integration._toolchain import (
    HAS_NETCDF_C,
    requires_cpp_highway_compiler,
    requires_gpu_cuda_cpp_compiler,
)

netCDF4 = pytest.importorskip("netCDF4")

_REPO = pathlib.Path(__file__).resolve().parents[3]
_GELB_RUN = _REPO / "scripts" / "gelb-run"

_requires_gfortran = pytest.mark.skipif(
    not (shutil.which("gfortran") and HAS_NETCDF_C),
    reason="gfortran or NetCDF-C not found")

BACKENDS = [
    pytest.param("cpu_fortran_serial", marks=_requires_gfortran),
    pytest.param("cpu_highway", marks=requires_cpp_highway_compiler),
    pytest.param("gpu_cuda_cpp",
                 marks=[pytest.mark.gpu, requires_gpu_cuda_cpp_compiler]),
]

# Every CUDA run here is a strict build.  A default CUDA build keeps
# nvcc's fusion (user manual, Numerical semantics: Build modes), so the
# default-versus-plain
# comparisons below are bit-exact only with ``--fmad=false``.  The arch
# has to be spelled out because ``GELB_NVCC_FLAGS`` replaces
# ``gelb-run``'s whole default string, which is where ``GELB_NVCC_ARCH``
# would otherwise be read; without it the driver has to JIT the PTX,
# which fails on CUDA 13.2 with driver 580.  Mirrors the battery's flags
# (``gelb/tests/numeric/test_generated_runtime.py``).
_NVCC_ARCH = os.environ.get("GELB_NVCC_ARCH", "-arch=sm_89")
_STRICT_NVCC_FLAGS = (
    f"-O0 {_NVCC_ARCH} --fmad=false --ftz=false --prec-div=true"
    " --prec-sqrt=true -std=c++17 --expt-relaxed-constexpr -DNDEBUG"
    " -diag-suppress=177")

_REAL_IS_REAL64 = """simulation_description("real is real64");
lattices { lattice u(1, 1, real32, 4, false); }
initializer I { u.out[x | 0] = 16777216.0; }
dynamic D { u.out[x | 0] = u.in[x | 0]; }
gauge G -> (real via_real, real literal_sum) {
    via_real = real(u.in[x | 0]) + 1.0 - real(u.in[x | 0]);
    literal_sum = u.in[x | 0] + 1.0 - u.in[x | 0];
}
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""

_U, _W = 1.3, 0.1
_REAL32_CHAIN = """simulation_description("real32 stays single");
global_constants { const real32 W32 = 0.1; }
lattices { lattice u(1, 1, real32, 4, false); }
initializer I { u.out[x | 0] = 1.3; }
dynamic D { u.out[x | 0] = u.in[x | 0]; }
gauge G -> (real chain) {
    real32 prod = (u.in[x | 0] * W32) * W32;
    chain = prod;
}
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""

# The slice expansion must keep the widths and the store
# conversion.  Q = 9, both source forms (a full slice, which the pass
# expands, and a single direction, which it leaves alone) must agree.
_SLICE_LITERAL = """simulation_description("slice literal width");
lattices { lattice u(1, 9, real32, 4, false); }
initializer I { u.out[x | :] = 1.1; }
dynamic D {
    u.out[x | :] = 0.1 * u.in[x | :];
    u.out[x | 0] = 0.1 * u.in[x | 0];
}
gauge G -> (real expanded, real scalar) {
    expanded = u.in[x | 1];
    scalar = u.in[x | 0];
}
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""

# A real32 product inside a `real` expression is a single-precision
# product, widened: the promotion around a composite keeps its width.
_SLICE_COMPOSITE = """simulation_description("slice composite width");
lattices { lattice u(1, 9, real32, 4, false); }
initializer I { u.out[x | :] = 2.3; }
dynamic D {
    u.out[x | :] = 3.0 * (u.in[x | :] * u.in[x | :]);
    u.out[x | 0] = 3.0 * (u.in[x | 0] * u.in[x | 0]);
}
gauge G -> (real expanded, real scalar) {
    expanded = u.in[x | 1];
    scalar = u.in[x | 0];
}
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""

# An integer sum converted to real32 is added in integers and
# converted once; rebuilt as real32 arithmetic, 16777217 rounds to 2^24
# before the addition.  An integer division truncates before
# the product; SymPy's exact division would give 0.5*x - 3.5.
_SLICE_INTEGER_SUM = """simulation_description("slice integer conversion");
lattices { lattice u(1, 9, real32, 4, false); }
initializer I { u.out[x | :] = 0.5; }
dynamic D {
    u.out[x | :] = u.in[x | :] * (x + 16777217);
    u.out[x | 0] = u.in[x | 0] * (x + 16777217);
}
gauge G -> (real expanded, real scalar) {
    expanded = u.in[x | 1];
    scalar = u.in[x | 0];
}
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""

_SLICE_INTEGER_QUOTIENT = """simulation_description("slice integer division");
lattices { lattice u(1, 9, real32, 4, false); }
initializer I { u.out[x | :] = 0.5; }
dynamic D {
    u.out[x | :] = u.in[x | :] * ((x - 7) / 2);
    u.out[x | 0] = u.in[x | 0] * ((x - 7) / 2);
}
gauge G -> (real expanded, real scalar) {
    expanded = u.in[x | 1];
    scalar = u.in[x | 0];
}
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""

# Each integer literal is converted before the algebra combines
# them.  In real32, 16777217 is 16777216, so the result is u, i.e. 0;
# combined first they are 1.
_SLICE_LITERAL_CONVERSION = """simulation_description("literal conversion before algebra");
lattices { lattice u(1, 9, real32, 4, false); }
initializer I { u.out[x | :] = 0.0; }
dynamic D {
    u.out[x | :] = (u.in[x | :] + 16777217) - 16777216;
    u.out[x | 0] = (u.in[x | 0] + 16777217) - 16777216;
}
gauge G -> (real expanded, real scalar) {
    expanded = u.in[x | 1];
    scalar = u.in[x | 0];
}
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""

# The minimum int64 value has no representable magnitude; both emitters
# must spell it as the negative maximum minus one.
_MINIMUM_INT64 = """simulation_description("minimum int64 literal");
lattices { lattice u(1, 1, real, 4, false); }
initializer I { u.out[x | 0] = 0.5; }
dynamic D { u.out[x | 0] = u.in[x | 0] * (-9223372036854775807 - 1); }
gauge G -> (real v) { v = u.in[x | 0]; }
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""

# A coordinate is a GeLB int, int64: its arithmetic must not wrap at
# 32 bits in any backend, in a dynamic or in a gauge.
_COORDINATE_WIDTH = """simulation_description("int64 coordinates");
lattices { lattice u(1, 1, real, 4, false); }
initializer I { u.out[x | 0] = 0.0; }
dynamic D { u.out[x | 0] = x + 2147483647; }
gauge G -> (real total, real product, real sized) {
    total = u.in[x | 0];
    product = x * 1073741824;
    sized = (Nx + t) * 1073741824;
}
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""

# An integer literal converts to real32 directly, not through
# binary64; and literal terms are never combined across a variable, so
# the nonzero-u cancellation input agrees with the single-direction form.
_ABOVE_MIDPOINT = 2 ** 54 + 2 ** 30 + 1
_SLICE_DOUBLE_ROUNDING = """simulation_description("direct conversion");
lattices { lattice u(1, 9, real32, 4, false); }
initializer I { u.out[x | :] = 0.5; }
dynamic D {
    u.out[x | :] = u.in[x | :] * 18014399583223809;
    u.out[x | 0] = u.in[x | 0] * 18014399583223809;
}
gauge G -> (real expanded, real scalar) {
    expanded = u.in[x | 1];
    scalar = u.in[x | 0];
}
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""
_SLICE_CANCELLATION = _SLICE_LITERAL_CONVERSION.replace("u.out[x | :] = 0.0;", "u.out[x | :] = 0.5;")

# A collapsed axis substitutes the coordinate's value as an
# int64, and integer arithmetic on x takes the scalar path in Highway,
# where the SIMD body holds x as a double vector.
_SINGLETON_WIDTH = """simulation_description("singleton coordinate width");
lattices { lattice u(1, 1, real, 1, false); }
initializer I { u.out[x | 0] = 0.5; }
dynamic D { u.out[x | 0] = (x + 2147483647) + 1; }
gauge G -> (real v) { v = u.in[x | 0]; }
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""
_SIMD_CELLS = 67
_SIMD_DIVISION = f"""simulation_description("integer division on x");
lattices {{ lattice u(1, 1, real, {_SIMD_CELLS}, false); }}
initializer I {{ u.out[x | 0] = 0.5; }}
dynamic D {{ u.out[x | 0] = (x - 7) / 2; }}
gauge G -> (real v) {{ v = u.in[x | 0]; }}
node_classes {{ node_class B(I, D, G); }}
geometry {{ nodes[:] = B; }}
"""
_SIMD_CONTROL = _SIMD_DIVISION.replace("(x - 7) / 2", "x * 0.5")

# The scalar CSE shared `v*v` across `v = 2.0`, so b - a was 0: a shared
# subtree is shared only while every name it reads has one value.
_CSE_ACROSS_A_WRITE = """simulation_description("CSE around a write to an existing local");
lattices { lattice u(1, 9, real, 4, false); }
initializer I { u.out[x | :] = 1.0; }
dynamic D {
    real v = u.in[x | 0];
    u.out[x | :] = u.in[x | :];
    real a = v * v;
    v = 2.0;
    real b = v * v;
    u.out[x | 0] = b - a;
}
gauge G -> (real value) { value = u.in[x | 0]; }
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""

# The repeated real32 square is shared as a temporary, which
# must be real32: squared in real64 it lost the inner rounding.
_SLICE_REPEATED_NARROW = """simulation_description("repeated real32 subtree");
lattices { lattice u(1, 9, real32, 4, false); }
initializer I { u.out[x | :] = 1.1; }
dynamic D {
    u.out[x | :] = 3.0 * ((u.in[x | :] * u.in[x | :]) * (u.in[x | :] * u.in[x | :]));
    u.out[x | 0] = 3.0 * ((u.in[x | 0] * u.in[x | 0]) * (u.in[x | 0] * u.in[x | 0]));
}
gauge G -> (real expanded, real scalar) {
    expanded = u.in[x | 1];
    scalar = u.in[x | 0];
}
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""

# A real zero has a sign.  The expanded slice and the single
# direction must both give the native result; atan2 shows the sign.
_SIGNED_ZERO = """simulation_description("signed zero");
lattices {{ lattice u(1, 9, real, 4, false); }}
initializer I {{ u.out[x | :] = {initial}; }}
dynamic D {{
    u.out[x | :] = {slice};
    u.out[x | 0] = {single};
}}
gauge G -> (real expanded, real scalar, real angle) {{
    expanded = u.in[x | 1];
    scalar = u.in[x | 0];
    angle = atan2(u.in[x | 1], -1.0);
}}
node_classes {{ node_class B(I, D, G); }}
geometry {{ nodes[:] = B; }}
"""
_SIGNED_ZERO_CASES = [
    # (id, initial, expression of U, native result for that input)
    ("product", "-1.0", "U * 0.0", -0.0),
    ("sum", "-0.0", "U + 0.0", 0.0),
    ("difference", "0.0", "0.0 - U", 0.0),
]

# An index equal to x, through int64 arithmetic that overflows
# a default integer, on a collapsed Fortran axis.
_COLLAPSED_INDEX = """simulation_description("collapsed spatial index");
lattices { lattice u(1, 1, real, 1, false); }
initializer I { u.out[x | 0] = 7.0; }
dynamic D { u.out[x | 0] = u.in[((x + 2147483647) + 1) - 2147483647 - 1 | 0]; }
gauge G -> (real v) { v = u.in[x | 0]; }
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""

# A power is the backend's: the Fortran backend calls pow, which need not
# equal the repeated product, so the expansion must not unroll it.
_CUBE_INPUT = 1.112
_SLICE_CUBE = f"""simulation_description("slice power");
lattices {{ lattice u(1, 9, real, 4, false); }}
initializer I {{ u.out[x | :] = {_CUBE_INPUT!r}; }}
dynamic D {{
    u.out[x | :] = u.in[x | :]^3;
    u.out[x | 0] = u.in[x | 0]^3;
}}
gauge G -> (real expanded, real scalar) {{
    expanded = u.in[x | 1];
    scalar = u.in[x | 0];
}}
node_classes {{ node_class B(I, D, G); }}
geometry {{ nodes[:] = B; }}
"""


# Two whole-array assignments entered the scalar CSE, whose
# temporary is a scalar; and two random() draws were shared as one.
_WHOLE_ARRAY_CSE = """simulation_description("CSE on two whole-array assignments");
lattices { lattice u(1,9,real,4,false); }
initializer I { u.out[x | :] = {1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0}; }
dynamic D {
    array[real,9] a;
    array[real,9] b;
    a = u.in[x | :] * u.in[x | :];
    b = u.in[x | :] * u.in[x | :];
    u.out[x | :] = a + b;
}
gauge G -> (real first, real last) {
    first = u.in[x | 0]; last = u.in[x | 8];
}
node_classes { node_class B(I,D,G); }
geometry { nodes[:] = B; }
"""
_RANDOM_DRAWS = """simulation_description("Distinct random draws");
lattices { lattice u(1,2,real,4,false); }
initializer I { u.out[x | :] = 1.0; }
dynamic D {
    real a = 2.0 * random();
    real b = 2.0 * random();
    u.out[x | 0] = a - b;
    u.out[x | 1] = random() - 0.5 * (random() - u.in[x | 1]);
}
gauge G -> (real difference, real collinear) {
    difference = u.in[x | 0];
    collinear = u.in[x | 1];
}
node_classes { node_class B(I,D,G); }
geometry { nodes[:] = B; }
"""
_ALL_OFF = "--no-slice-simplify --no-scalar-cse --no-collinearity-rewrite"


def _run(tmp_path, source, backend, simplify=True, plain_flags="--no-slice-simplify",
         extra="", threads=None, run_args=(), strict_cuda=True, env_extra=None,
         check=True):
    """Compile and run ``source`` through ``gelb-run``; ``run_args`` are
    extra ``gelb-run`` options (``--strict-fp``, ``-v``).  ``strict_cuda``
    sets the battery's strict nvcc flags for CUDA; pass False to test
    what ``gelb-run`` itself does to the flags.  ``env_extra`` adds or
    overrides environment variables (a ``GELB_CXXFLAGS`` override, say).
    A failed build raises ``RuntimeError``, never ``AssertionError``, so
    an expected numerical failure can be told from a broken build; with
    ``check=False`` the ``CompletedProcess`` is returned instead."""
    work = tmp_path / f"{backend}_{'simplified' if simplify else 'plain'}"
    work.mkdir(parents=True)
    src = work / "prog.gelb"
    src.write_text(source)
    env = dict(os.environ, GELB_PYTHON=sys.executable)
    if backend == "gpu_cuda_cpp" and strict_cuda:
        env["GELB_NVCC_FLAGS"] = _STRICT_NVCC_FLAGS
    if threads is not None:
        env["OMP_NUM_THREADS"] = str(threads)
    env["GELBC_EXTRA"] = " ".join(f for f in (extra, "" if simplify else plain_flags) if f)
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        [str(_GELB_RUN), "--keep", *run_args, "-b", backend, "-n", "1", "-w", "1", str(src)],
        cwd=work, env=env, capture_output=True, text=True, timeout=600)
    (work / "gelb-run.log").write_text(result.stdout + result.stderr)
    if not check:
        return result
    if result.returncode != 0:
        raise RuntimeError(f"gelb-run failed ({result.returncode}):\n"
                           + result.stdout + result.stderr)
    return netCDF4.Dataset(next(work.glob("*.nc")))


def _log(tmp_path, backend, simplify=True):
    """``gelb-run``'s combined output for the last ``_run`` of ``backend``."""
    work = tmp_path / f"{backend}_{'simplified' if simplify else 'plain'}"
    return (work / "gelb-run.log").read_text()


def _generated(tmp_path, backend, simplify=True):
    """The generated source of the last ``_run`` for ``backend``."""
    work = tmp_path / f"{backend}_{'simplified' if simplify else 'plain'}"
    suffix = {"cpu_fortran_serial": ".f90", "gpu_cuda_cpp": ".cu"}.get(backend, ".cpp")
    return (work / "prog").with_suffix(suffix).read_text()


@pytest.mark.parametrize("backend", BACKENDS)
def test_real_is_double_precision_in_a_real32_program(tmp_path, backend):
    nc = _run(tmp_path, _REAL_IS_REAL64, backend)
    for step in (0, 1):
        for name in ("via_real", "literal_sum"):
            assert np.asarray(nc[name][step]).tolist() == [1.0] * 4, (name, step)


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_real32_expression_stays_single_precision(tmp_path, backend):
    u32, w32 = np.float32(_U), np.float32(_W)
    expected = float(np.float32(np.float32(u32 * w32) * w32))
    assert expected != float(np.float32((float(u32) * float(w32)) * float(w32)))
    nc = _run(tmp_path, _REAL32_CHAIN, backend)
    for step in (0, 1):
        assert np.asarray(nc["chain"][step]).tolist() == [expected] * 4, step


@pytest.mark.parametrize("simplify", [True, False], ids=["expanded", "no-slice-simplify"])
@pytest.mark.parametrize("backend", BACKENDS)
def test_slice_expansion_keeps_a_real_literal_double_precision(tmp_path, backend, simplify):
    u = np.float32(1.1)
    expected = float(np.float32(0.1 * float(u)))          # double product, rounded once
    assert expected != float(np.float32(np.float32(0.1) * u))  # the single-precision result
    nc = _run(tmp_path, _SLICE_LITERAL, backend, simplify)
    for name in ("expanded", "scalar"):
        assert np.asarray(nc[name][1]).tolist() == [expected] * 4, name


@pytest.mark.parametrize("simplify", [True, False], ids=["expanded", "no-slice-simplify"])
@pytest.mark.parametrize("backend", BACKENDS)
def test_slice_expansion_keeps_a_real32_product_single_precision(tmp_path, backend, simplify):
    u = np.float32(2.3)
    inner = np.float32(u * u)                               # the real32 product
    expected = float(np.float32(3.0 * float(inner)))       # widened, times 3.0, rounded at the store
    assert expected != float(np.float32(3.0 * float(u) * float(u)))  # an all-double evaluation
    nc = _run(tmp_path, _SLICE_COMPOSITE, backend, simplify)
    for name in ("expanded", "scalar"):
        assert np.asarray(nc[name][1]).tolist() == [expected] * 4, name


@pytest.mark.parametrize("simplify", [True, False], ids=["expanded", "no-slice-simplify"])
@pytest.mark.parametrize("backend", BACKENDS)
def test_slice_expansion_converts_an_integer_sum_after_adding(tmp_path, backend, simplify):
    expected = [float(np.float32(0.5) * np.float32(x + 16777217)) for x in range(4)]
    assert expected == [8388608.0, 8388609.0, 8388610.0, 8388610.0]
    rounded_first = [float(np.float32(0.5) * (np.float32(16777217) + np.float32(x))) for x in range(4)]
    assert rounded_first != expected
    nc = _run(tmp_path, _SLICE_INTEGER_SUM, backend, simplify)
    for name in ("expanded", "scalar"):
        assert np.asarray(nc[name][1]).tolist() == expected, name


@pytest.mark.parametrize("simplify", [True, False], ids=["expanded", "no-slice-simplify"])
@pytest.mark.parametrize("backend", BACKENDS)
def test_slice_expansion_keeps_an_integer_division(tmp_path, backend, simplify):
    def trunc_div(a, b):            # GeLB, Fortran and C++ truncate toward zero
        return int(abs(a) // abs(b)) * (1 if (a < 0) == (b < 0) else -1)
    expected = [0.5 * trunc_div(x - 7, 2) for x in range(4)]
    assert expected == [-1.5, -1.5, -1.0, -1.0]
    assert expected != [0.5 * (x - 7) / 2 for x in range(4)]
    nc = _run(tmp_path, _SLICE_INTEGER_QUOTIENT, backend, simplify)
    for name in ("expanded", "scalar"):
        assert np.asarray(nc[name][1]).tolist() == expected, name


@pytest.mark.parametrize("simplify", [True, False], ids=["expanded", "no-slice-simplify"])
@pytest.mark.parametrize("backend", BACKENDS)
def test_integer_literals_are_converted_before_the_algebra(tmp_path, backend, simplify):
    u = np.float32(0.0)
    expected = float((u + np.float32(16777217)) - np.float32(16777216))
    assert expected == 0.0 and float(u + np.float32(16777217 - 16777216)) == 1.0
    nc = _run(tmp_path, _SLICE_LITERAL_CONVERSION, backend, simplify)
    for name in ("expanded", "scalar"):
        assert np.asarray(nc[name][1]).tolist() == [expected] * 4, name


@pytest.mark.parametrize("simplify", [True, False], ids=["expanded", "no-slice-simplify"])
@pytest.mark.parametrize("backend", BACKENDS)
def test_an_integer_literal_converts_to_real32_directly(tmp_path, backend, simplify):
    direct = float(np.array([_ABOVE_MIDPOINT], dtype=np.int64).astype(np.float32)[0])
    expected = float(np.float32(0.5) * np.float32(direct))
    assert expected == 9007200328482816.0
    assert float(np.float32(0.5) * np.float32(float(_ABOVE_MIDPOINT))) == 9007199254740992.0
    nc = _run(tmp_path, _SLICE_DOUBLE_ROUNDING, backend, simplify)
    for name in ("expanded", "scalar"):
        assert np.asarray(nc[name][1]).tolist() == [expected] * 4, name


@pytest.mark.parametrize("simplify", [True, False], ids=["expanded", "no-slice-simplify"])
@pytest.mark.parametrize("backend", BACKENDS)
def test_literal_terms_are_not_combined_across_a_variable(tmp_path, backend, simplify):
    u = np.float32(0.5)
    expected = float((u + np.float32(16777217)) - np.float32(16777216))
    assert expected == 0.0 and float(u + np.float32(0)) == 0.5   # combined literals would give u back
    nc = _run(tmp_path, _SLICE_CANCELLATION, backend, simplify)
    for name in ("expanded", "scalar"):
        assert np.asarray(nc[name][1]).tolist() == [expected] * 4, name


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_collapsed_axis_keeps_the_coordinate_64_bit(tmp_path, backend):
    nc = _run(tmp_path, _SINGLETON_WIDTH, backend)
    assert np.asarray(nc["v"][1]).tolist() == [2147483648.0]
    code = _generated(tmp_path, backend)
    # The value above is the proof: a 32-bit coordinate would wrap to
    # -2147483648.  Each backend shows its 64-bit arithmetic differently.
    # Fortran keeps a kind-8 literal zero for the collapsed axis; Highway
    # folds that axis' arithmetic, and the fold lands on 2147483648 only
    # in 64 bits; CUDA never specializes a collapsed axis to a literal,
    # because every thread derives its own coordinate, so the width shows
    # in the coordinate's declared type instead.
    evidence = {"cpu_fortran_serial": "int(0, 8)",
                "cpu_highway": "2147483648LL",
                "gpu_cuda_cpp": "int64_t g_x"}[backend]
    assert evidence in code


@pytest.mark.parametrize("backend", BACKENDS)
def test_integer_division_on_x_is_exact_on_every_path(tmp_path, backend):
    def trunc_div(a, b):
        return int(abs(a) // abs(b)) * (1 if (a < 0) == (b < 0) else -1)
    expected = [float(trunc_div(x - 7, 2)) for x in range(_SIMD_CELLS)]
    assert expected[:4] == [-3.0, -3.0, -2.0, -2.0]
    nc = _run(tmp_path, _SIMD_DIVISION, backend)
    assert np.asarray(nc["v"][1]).tolist() == expected
    if backend == "cpu_highway":
        # The dynamic takes the scalar path (no vector x in a real division);
        # the control program, real arithmetic on x, does enter the SIMD body.
        code = _generated(tmp_path, backend)
        assert "hn::Set(d, 7)" not in code and "/ hn::Set(d, 2)" not in code
        control = _run(tmp_path / "control", _SIMD_CONTROL, backend)
        assert np.asarray(control["v"][1]).tolist() == [0.5 * x for x in range(_SIMD_CELLS)]
        assert "hn::Iota(d, static_cast<double>(g_x))" in _generated(tmp_path / "control", backend)


@pytest.mark.parametrize("backend", BACKENDS)
def test_the_minimum_int64_literal_keeps_its_value(tmp_path, backend):
    expected = 0.5 * float(-2 ** 63)
    assert expected == -4611686018427387904.0
    nc = _run(tmp_path, _MINIMUM_INT64, backend)
    assert np.asarray(nc["v"][1]).tolist() == [expected] * 4


@pytest.mark.parametrize("backend", BACKENDS)
def test_coordinates_and_implicit_integers_are_64_bit(tmp_path, backend):
    nc = _run(tmp_path, _COORDINATE_WIDTH, backend)
    assert np.asarray(nc["total"][1]).tolist() == [float(x + 2147483647) for x in range(4)]
    assert np.asarray(nc["product"][1]).tolist() == [float(x * 1073741824) for x in range(4)]
    assert np.asarray(nc["sized"][1]).tolist() == [float((4 + 1) * 1073741824)] * 4


@pytest.mark.parametrize("simplify", [True, False], ids=["scalar-cse", "no-scalar-cse"])
@pytest.mark.parametrize("backend", BACKENDS)
def test_scalar_cse_does_not_share_a_value_across_a_write(tmp_path, backend, simplify):
    a, b = 1.0 * 1.0, 2.0 * 2.0
    nc = _run(tmp_path, _CSE_ACROSS_A_WRITE, backend, simplify, "--no-scalar-cse")
    assert np.asarray(nc["value"][1]).tolist() == [b - a] * 4


@pytest.mark.parametrize("simplify", [True, False], ids=["expanded", "no-slice-simplify"])
@pytest.mark.parametrize("backend", BACKENDS)
def test_a_shared_real32_subtree_stays_real32(tmp_path, backend, simplify):
    u = np.float32(1.1)
    square = np.float32(u * u)
    expected = float(np.float32(3.0 * float(np.float32(square * square))))
    assert expected == 4.392300605773926
    assert float(np.float32(3.0 * (float(square) * float(square)))) == 4.392300128936768
    nc = _run(tmp_path, _SLICE_REPEATED_NARROW, backend, simplify)
    for name in ("expanded", "scalar"):
        assert np.asarray(nc[name][1]).tolist() == [expected] * 4, name
    if simplify:
        code = _generated(tmp_path, backend)
        declared = "real(4) :: gelb_b1_g___gelb__cse__" if backend == "cpu_fortran_serial" else "float g__gelb_cse_"
        assert declared in code
        assert ("double precision :: gelb_b1_g___gelb__cse__" not in code
                if backend == "cpu_fortran_serial" else "double g__gelb_cse_" not in code)


@pytest.mark.parametrize("case", _SIGNED_ZERO_CASES, ids=[c[0] for c in _SIGNED_ZERO_CASES])
@pytest.mark.parametrize("simplify", [True, False], ids=["expanded", "no-slice-simplify"])
@pytest.mark.parametrize("backend", BACKENDS)
def test_a_real_zero_keeps_its_sign(tmp_path, backend, simplify, case):
    _, initial, expression, expected = case
    source = _SIGNED_ZERO.format(initial=initial,
                                 slice=expression.replace("U", "u.in[x | :]"),
                                 single=expression.replace("U", "u.in[x | 0]"))
    nc = _run(tmp_path, source, backend, simplify)
    for name in ("expanded", "scalar"):
        values = np.asarray(nc[name][1])
        assert values.tolist() == [0.0] * 4, name
        assert np.signbit(values).tolist() == [np.signbit(expected)] * 4, name
    angle = np.pi if not np.signbit(expected) else -np.pi
    assert np.asarray(nc["angle"][1]).tolist() == [angle] * 4


@pytest.mark.parametrize("simplify", [True, False], ids=["expanded", "no-slice-simplify"])
@pytest.mark.parametrize("backend", BACKENDS)
def test_a_collapsed_coordinate_in_index_arithmetic_is_64_bit(tmp_path, backend, simplify):
    nc = _run(tmp_path, _COLLAPSED_INDEX, backend, simplify)
    assert np.asarray(nc["v"][1]).tolist() == [7.0]
    if backend == "cpu_fortran_serial":
        code = _generated(tmp_path, backend, simplify)
        assert "g_u(0, ((((int(0, 8) + 2147483647) + 1) - 2147483647) - 1), g_u_old)" in code
        assert "g_u(0, 0, g_u_new)" in code          # a coordinate alone stays bare


@pytest.mark.parametrize("backend", BACKENDS)
def test_the_expansion_leaves_a_power_to_the_backend(tmp_path, backend):
    from fractions import Fraction
    u = _CUBE_INPUT
    assert float(Fraction(u) ** 3) != (u * u) * u        # pow and the product differ here
    nc = _run(tmp_path, _SLICE_CUBE, backend)
    expanded, scalar = (np.asarray(nc[n][1]).tolist() for n in ("expanded", "scalar"))
    assert expanded == scalar
    assert expanded[0] in (float(Fraction(u) ** 3), (u * u) * u)


@pytest.mark.parametrize("simplify", [True, False], ids=["scalar-cse", "no-scalar-cse"])
@pytest.mark.parametrize("backend", BACKENDS)
def test_whole_array_assignments_stay_arrays(tmp_path, backend, simplify):
    u = np.arange(1.0, 10.0)
    expected = u * u + u * u
    assert (expected[0], expected[8]) == (2.0, 162.0)
    nc = _run(tmp_path, _WHOLE_ARRAY_CSE, backend, simplify, "--no-scalar-cse")
    assert np.asarray(nc["first"][1]).tolist() == [expected[0]] * 4
    assert np.asarray(nc["last"][1]).tolist() == [expected[8]] * 4


@pytest.mark.parametrize("backend", BACKENDS)
def test_distinct_random_draws_stay_distinct(tmp_path, backend):
    # The same seed on one thread draws the same stream: the optimizer
    # must not change how many numbers are drawn or in which order.
    optimized = _run(tmp_path, _RANDOM_DRAWS, backend, True, extra="--seed 1", threads=1)
    plain = _run(tmp_path, _RANDOM_DRAWS, backend, False, _ALL_OFF, extra="--seed 1", threads=1)
    for name in ("difference", "collinear"):
        got, reference = np.asarray(optimized[name][1]), np.asarray(plain[name][1])
        assert got.view(np.uint64).tolist() == reference.view(np.uint64).tolist(), name
    assert np.count_nonzero(np.asarray(optimized["difference"][1])) == 4   # one shared draw gave 0


# ---------------------------------------------------------------------------
# Build modes (user manual, Numerical semantics: Build modes).  A default
# build runs
# the native compilers with contraction off on the CPU backends and keeps
# nvcc's fusion on CUDA; a strict build (--strict-fp) fuses nothing
# anywhere: gelb-run adds -ffp-contract=off / -fmad=false, and the
# generated C++ defines GELB_STRICT_FP before the runtime header so the
# one fusion GeLB decides itself (the Highway SIMD reduction helper) is
# off too.  The fusion probe shows it: a dot product whose only
# non-trivial term, (1 + 2^-52) * (1 - 2^-52), rounds to 1 before the
# addition of -1 when unfused (giving +0) and keeps its 2^-104 when fused
# (giving -2^-104).

_FUSION_PROBE_COEFF_4 = 1.0000000000000002     # 1 + 2^-52
_FUSION_PROBE_INPUT_4 = 0.9999999999999998     # 1 - 2^-52
_FUSION_PROBE = f"""simulation_description("a reduction whose fusion shows");
global_constants {{
    const array[real, 9] C = {{1.0, 1.0, 1.0, 1.0, {_FUSION_PROBE_COEFF_4!r}, 1.0, 1.0, 1.0, 1.0}};
}}
lattices {{ lattice u(1, 9, real, {_SIMD_CELLS}, false); }}
initializer I {{
    u.out[x | :] = 0.0;
    u.out[x | 0] = -1.0;
    u.out[x | 4] = {_FUSION_PROBE_INPUT_4!r};
}}
dynamic D {{ u.out[x | :] = u.in[x | :]; }}
gauge G -> (real v) {{
    array[real, 9] a = u.in[x | :];
    v = dot_prod(C, a);
}}
node_classes {{ node_class B(I, D, G); }}
geometry {{ nodes[:] = B; }}
"""
_FUSION_PROBE_UNFUSED = 0.0
_FUSION_PROBE_FUSED = -(2.0 ** -104)


def _fusion_probe_arithmetic_is_as_described():
    from fractions import Fraction
    assert _FUSION_PROBE_COEFF_4 == 1 + 2 ** -52 and _FUSION_PROBE_INPUT_4 == 1 - 2 ** -52
    product = Fraction(_FUSION_PROBE_COEFF_4) * Fraction(_FUSION_PROBE_INPUT_4)
    assert product == 1 - Fraction(2) ** -104
    assert float(product) == 1.0                               # one rounding: the 2^-104 is gone
    assert float(Fraction(-1) + product) == _FUSION_PROBE_FUSED         # fused: it survives
    assert -1.0 + float(product) == _FUSION_PROBE_UNFUSED


def _strict_marker(backend):
    return ("! Strict floating point" if backend == "cpu_fortran_serial"
            else "#define GELB_STRICT_FP 1")


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_default_build_runs_the_native_compiler_without_contraction(tmp_path, backend):
    _run(tmp_path, _SINGLETON_WIDTH, backend, run_args=("-v",), strict_cuda=False)
    log = _log(tmp_path, backend)
    compile_line = next(l for l in log.splitlines() if "Compiling with" in l)
    if backend == "gpu_cuda_cpp":
        # A default CUDA build keeps nvcc's fusion.
        assert "-fmad=false" not in compile_line
    else:
        assert "-ffp-contract=off" in compile_line
    assert _strict_marker(backend) not in _generated(tmp_path, backend)


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_strict_build_reaches_the_native_compiler_and_the_generated_source(tmp_path, backend):
    _run(tmp_path, _SINGLETON_WIDTH, backend, run_args=("--strict-fp", "-v"), strict_cuda=False)
    log = _log(tmp_path, backend)
    compile_line = next(l for l in log.splitlines() if "Compiling with" in l)
    assert ("-fmad=false" if backend == "gpu_cuda_cpp" else "-ffp-contract=off") in compile_line
    code = _generated(tmp_path, backend)
    assert _strict_marker(backend) in code
    if backend != "cpu_fortran_serial":
        # The define must precede the include: the header chooses on it.
        assert code.index("#define GELB_STRICT_FP 1") < code.index("#include ")


def test_strict_fp_and_fast_math_exclude_each_other(tmp_path):
    src = tmp_path / "prog.gelb"
    src.write_text(_SINGLETON_WIDTH)
    result = subprocess.run(
        [str(_GELB_RUN), "--strict-fp", "-F", "-b", "cpu_highway", str(src)],
        cwd=tmp_path, env=dict(os.environ, GELB_PYTHON=sys.executable),
        capture_output=True, text=True, timeout=120)
    assert result.returncode != 0
    assert "--strict-fp" in result.stderr and "--fast-math" in result.stderr
    assert not list(tmp_path.glob("*.cpp")), "nothing may be generated after the conflict"


@pytest.mark.parametrize("backend", BACKENDS)
def test_fusion_probe_a_strict_build_fuses_nothing_on_any_path(tmp_path, backend):
    _fusion_probe_arithmetic_is_as_described()
    nc = _run(tmp_path, _FUSION_PROBE, backend, run_args=("--strict-fp",), strict_cuda=False)
    values = np.asarray(nc["v"][1]).tolist()
    assert values == [_FUSION_PROBE_UNFUSED] * _SIMD_CELLS
    # +0 is what the unfused order gives on every backend: -1 + 1 is +0
    # under round-to-nearest, and adding +0 terms keeps it.
    assert all(math.copysign(1.0, v) == 1.0 for v in values)
    if backend == "cpu_highway":
        # The program must actually take both paths the rule is about:
        # the SIMD body (the ``d``-taking helper) and the scalar tail.
        code = _generated(tmp_path, backend)
        assert "gelb::gelb_dot_prod_const(d, " in code
        assert "gelb::gelb_dot_prod_const(gelb_dp_coeff" in code


@pytest.mark.parametrize("backend", BACKENDS)
def test_fusion_probe_identical_cells_agree_in_a_default_build(tmp_path, backend):
    # Within one build, identical inputs give identical bits whatever
    # the cell's position (user manual, Numerical semantics:
    # Reproducibility).  Not a strict build, and the CUDA run keeps
    # nvcc's fusion on purpose: the claim is agreement, not a value.
    # The scalar reduction helper fuses exactly where the vector one
    # does (where the compiled Highway target has an FMA), so the SIMD
    # body, the peeled edges and the scalar tail round alike on every
    # target: GeLB decides the fusion, identically in every code path.
    nc = _run(tmp_path, _FUSION_PROBE, backend, strict_cuda=False)
    values = np.asarray(nc["v"][1]).tolist()
    assert set(values) <= {_FUSION_PROBE_UNFUSED, _FUSION_PROBE_FUSED}, sorted(set(values))
    assert len(set(values)) == 1, (values.count(_FUSION_PROBE_FUSED), values.count(_FUSION_PROBE_UNFUSED))
    if backend == "cpu_fortran_serial":
        assert values[0] == _FUSION_PROBE_UNFUSED      # a default Fortran build fuses nothing


# Every term of a reduction counts, zero coefficients included.  With
# EX's zero coefficient at direction 0, a NaN there (sqrt of a negative
# run-time value) must reach the result: 0 * NaN is NaN.  Highway used
# to skip zero-coefficient terms, which gave a finite value here.
_ZERO_TERM_NAN = f"""simulation_description("a NaN in a zero-coefficient direction");
global_constants {{ const array[real, 9] EX = {{0.0, 1.0, 0.0, -1.0, 0.0, 1.0, -1.0, -1.0, 1.0}}; }}
lattices {{ lattice u(1, 9, real, {_SIMD_CELLS}, false); }}
initializer I {{ u.out[x | :] = 0.25; u.out[x | 0] = sqrt(-1.0 - x); }}
dynamic D {{ u.out[x | :] = u.in[x | :]; }}
gauge G -> (real v, real w) {{
    array[real, 9] a = u.in[x | :];
    v = dot_prod(EX, a);
    w = dot_prod(a, EX);
}}
node_classes {{ node_class B(I, D, G); }}
geometry {{ nodes[:] = B; }}
"""


# ... and an Inf there is NaN too (0 * Inf), where a pruned term would
# have given a finite value (user manual, Numerical semantics: Special
# values).
_ZERO_TERM_INF = _ZERO_TERM_NAN.replace("u.out[x | 0] = sqrt(-1.0 - x);", "u.out[x | 0] = 1.0 / (0.0 * x);")


@pytest.mark.parametrize("program", [_ZERO_TERM_NAN, _ZERO_TERM_INF], ids=["NaN", "Inf"])
@pytest.mark.parametrize("backend", BACKENDS)
def test_a_nan_in_a_zero_coefficient_direction_propagates(tmp_path, backend, program):
    nc = _run(tmp_path, program, backend)
    for name in ("v", "w"):
        values = np.asarray(nc[name][1]).tolist()
        assert all(math.isnan(x) for x in values), (name, values[:4])


# A strict build passes no value-changing native flag, from -F or from the
# environment (user manual, Numerical semantics: Build modes).  Two
# probes that fast math breaks and strict mode must not: (a + b) - a
# with a = 2^53 and b = 1 is +0 as written (2^53 + 1
# rounds to 2^53) and 1 under re-association; the smallest normal real32,
# halved, is the subnormal 2^-127 as written and 0 under flush-to-zero.
_REAL32_MIN_NORMAL = 1.1754943508222875e-38      # 2^-126
_STRICT_PROBE = f"""simulation_description("strict mode against the environment");
global_constants {{ const real32 HALF = 0.5; }}
lattices {{
    lattice u(1, 2, real, 4, false);
    lattice w(1, 1, real32, 4, false);
}}
initializer I {{
    u.out[x | 0] = 9007199254740992.0;
    u.out[x | 1] = 1.0;
    w.out[x | 0] = {_REAL32_MIN_NORMAL!r};
}}
dynamic D {{ u.out[x | :] = u.in[x | :]; w.out[x | 0] = w.in[x | 0]; }}
gauge G -> (real v, real32 s) {{
    v = (u.in[x | 0] + u.in[x | 1]) - u.in[x | 0];
    s = w.in[x | 0] * HALF;
}}
node_classes {{ node_class B(I, D, G); }}
geometry {{ nodes[:] = B; }}
"""
_ORDINARY_OVERRIDE = {
    "cpu_fortran_serial": ("GELB_FFLAGS", "-O3 -march=native -ffree-line-length-none"),
    "cpu_highway": ("GELB_CXXFLAGS", "-std=c++17 -O3 -march=native -DNDEBUG"),
    "gpu_cuda_cpp": ("GELB_NVCC_FLAGS",
                     f"-O3 {_NVCC_ARCH} -std=c++17 --expt-relaxed-constexpr -DNDEBUG"),
}
_NVCC_BASE = f"-O2 {_NVCC_ARCH} -std=c++17 --expt-relaxed-constexpr"
_REJECTED_SPELLINGS = [
    pytest.param("cpu_fortran_serial", "GELB_FFLAGS", "-O2 -ffast-math -ffree-line-length-none",
                 "-ffast-math", marks=_requires_gfortran, id="gfortran -ffast-math"),
    pytest.param("cpu_fortran_serial", "GELB_FFLAGS", "-Ofast -ffree-line-length-none",
                 "-Ofast", marks=_requires_gfortran, id="gfortran -Ofast"),
    pytest.param("cpu_highway", "GELB_CXXFLAGS", "-std=c++17 -O2 -ffast-math",
                 "-ffast-math", marks=requires_cpp_highway_compiler, id="g++ -ffast-math"),
    pytest.param("cpu_highway", "GELB_CXXFLAGS", "-std=c++17 -O2 -ffp-contract=fast",
                 "-ffp-contract=fast", marks=requires_cpp_highway_compiler, id="g++ -ffp-contract=fast"),
    pytest.param("cpu_highway", "GELB_CXXFLAGS", "-std=c++17 -O2 -fassociative-math",
                 "-fassociative-math", marks=requires_cpp_highway_compiler, id="g++ -fassociative-math"),
] + [
    pytest.param("gpu_cuda_cpp", "GELB_NVCC_FLAGS", f"{_NVCC_BASE} {spelling}", spelling,
                 marks=[pytest.mark.gpu, requires_gpu_cuda_cpp_compiler], id=f"nvcc {spelling}")
    for spelling in ("--use_fast_math", "--ftz=true", "--ftz true", "-ftz true",
                     "--prec-div false", "--prec-sqrt=false", "--fmad true")
] + [
    # Host-compiler forwarding, joined and separated: the members get the
    # direct spelling's treatment, so a value-changing flag cannot pass
    # through the host compiler unseen.
    pytest.param("gpu_cuda_cpp", "GELB_NVCC_FLAGS", f"{_NVCC_BASE} {flags}", spelling,
                 marks=[pytest.mark.gpu, requires_gpu_cuda_cpp_compiler], id=f"nvcc {flags}")
    for flags, spelling in (("-Xcompiler=-ffast-math", "-Xcompiler=-ffast-math"),
                            ("-Xcompiler -O2,-ffast-math", "-O2,-ffast-math"),
                            ("--compiler-options=-O2,-Ofast", "--compiler-options=-O2,-Ofast"))
]


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_strict_build_wins_over_an_ordinary_flag_override(tmp_path, backend):
    assert float(np.float32(_REAL32_MIN_NORMAL)) == 2.0 ** -126
    var, flags = _ORDINARY_OVERRIDE[backend]
    nc = _run(tmp_path, _STRICT_PROBE, backend, run_args=("--strict-fp", "-v"),
              strict_cuda=False, env_extra={var: flags})
    assert np.asarray(nc["v"][1]).tolist() == [0.0] * 4
    assert np.asarray(nc["s"][1]).tolist() == [2.0 ** -127] * 4
    compile_line = next(l for l in _log(tmp_path, backend).splitlines() if "Compiling with" in l)
    assert ("-fmad=false" if backend == "gpu_cuda_cpp" else "-ffp-contract=off") in compile_line


@pytest.mark.parametrize("backend,var,flags,spelling", _REJECTED_SPELLINGS)
def test_a_strict_build_rejects_a_value_changing_flag_from_the_environment(
        tmp_path, backend, var, flags, spelling):
    # Aggregates, their members, and nvcc's booleans in both the
    # ``--opt=value`` and the ``--opt value`` spelling, one or two dashes.
    result = _run(tmp_path, _STRICT_PROBE, backend, run_args=("--strict-fp",),
                  strict_cuda=False, env_extra={var: flags}, check=False)
    assert result.returncode != 0
    assert "--strict-fp" in result.stderr and var in result.stderr
    assert f"'{spelling}'" in result.stderr, result.stderr
    work = tmp_path / f"{backend}_simplified"
    assert not list(work.glob("*.nc")), "nothing may run after the rejection"


@pytest.mark.gpu
@requires_gpu_cuda_cpp_compiler
def test_a_strict_build_accepts_safe_nvcc_option_values(tmp_path):
    # The same options with the values a strict build wants are not flags
    # to reject: ``--ftz false`` keeps the subnormal.
    nc = _run(tmp_path, _STRICT_PROBE, "gpu_cuda_cpp", run_args=("--strict-fp",),
              strict_cuda=False,
              env_extra={"GELB_NVCC_FLAGS": f"{_NVCC_BASE} --ftz false --prec-div true --fmad false"})
    assert np.asarray(nc["s"][1]).tolist() == [2.0 ** -127] * 4


# -- One promotion rule (user manual, Numerical semantics: Types and promotion)
# The width-changing rows of the intrinsic table (``min``, ``max``,
# ``mod``, ``abs`` and the library functions follow the promotion
# table), run on three backends and compared with the value the table
# gives.  Each program
# also discriminates: the value the old rule gave (``sqrt`` and ``min``
# typed ``real``, ``abs`` typed ``real``) is asserted to differ.

_SQRT32 = """simulation_description("sqrt of a real32 is real32");
global_constants { const real32 C = 0.3; }
lattices { lattice w(1, 1, real32, 4, false); }
initializer I { w.out[x | 0] = 3.0; }
dynamic D { w.out[x | 0] = w.in[x | 0]; }
gauge G -> (real v) { v = sqrt(w.in[x | 0]) * C; }
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""
# sqrt in binary32, then a binary32 product (each rounds to its type) ...
_SQRT32_EXPECTED = float(np.float32(np.sqrt(np.float32(3.0))) * np.float32(0.3))
# ... not a binary32 sqrt widened into a binary64 product (the old rule)
_SQRT32_OLD = float(np.float32(np.sqrt(np.float32(3.0)))) * float(np.float32(0.3))

_MIN32 = """simulation_description("min of a real32 and an integer is real32");
global_constants { const real32 C = 0.3; }
lattices { lattice w(1, 1, real32, 4, false); }
initializer I { w.out[x | 0] = 0.1; }
dynamic D { w.out[x | 0] = w.in[x | 0]; }
gauge G -> (real v) { v = min(w.in[x | 0], 1) * C; }
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""
_MIN32_EXPECTED = float(np.float32(0.1) * np.float32(0.3))
_MIN32_OLD = float(np.float32(0.1)) * float(np.float32(0.3))

_ABS_INT = """simulation_description("abs of an integer is an integer");
lattices { lattice f(1, 1, real, 7, false); }
initializer I { f.out[x | 0] = 0.0; }
dynamic D { f.out[x | 0] = f.in[x | 0]; }
gauge G -> (real v) { v = abs(x - 3) / 2; }
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""
# |x - 3| for x = 0..6 is 3 2 1 0 1 2 3; a truncating integer quotient ...
_ABS_INT_EXPECTED = [1.0, 1.0, 0.0, 0.0, 0.0, 1.0, 1.0]
# ... not a real one (the old rule typed abs(int) as real)
_ABS_INT_OLD = [1.5, 1.0, 0.5, 0.0, 0.5, 1.0, 1.5]


@pytest.mark.parametrize("backend", BACKENDS)
def test_sqrt_of_a_real32_stays_real32(tmp_path, backend):
    assert _SQRT32_EXPECTED != _SQRT32_OLD
    nc = _run(tmp_path, _SQRT32, backend)
    assert np.asarray(nc["v"][1]).tolist() == [_SQRT32_EXPECTED] * 4


@pytest.mark.parametrize("backend", BACKENDS)
def test_min_of_a_real32_and_an_integer_is_real32(tmp_path, backend):
    assert _MIN32_EXPECTED != _MIN32_OLD
    nc = _run(tmp_path, _MIN32, backend)
    assert np.asarray(nc["v"][1]).tolist() == [_MIN32_EXPECTED] * 4


@pytest.mark.parametrize("backend", BACKENDS)
def test_abs_of_an_integer_is_an_integer(tmp_path, backend):
    nc = _run(tmp_path, _ABS_INT, backend)
    assert np.asarray(nc["v"][1]).tolist() == _ABS_INT_EXPECTED


_REAL16 = _SQRT32.replace("real32", "real16")


def test_real16_is_not_in_this_version(tmp_path):
    # Rejected by gelbc before any backend runs (user manual, Numerical
    # semantics: Not in this version); the diagnostic says so and names
    # what to use instead.
    result = _run(tmp_path, _REAL16, "cpu_highway", check=False)
    assert result.returncode != 0
    assert "'real16' is not in this version" in result.stderr, result.stderr
    assert "real32" in result.stderr
    work = tmp_path / "cpu_highway_simplified"
    assert not list(work.glob("*.nc")) and not list(work.glob("*.cpp"))


# -- One compile-time evaluator (user manual, Numerical semantics: Constant folding)
# Constants fold at compile time with one evaluator, which gives the
# run-time values (the truncated integer remainder, exact integer
# powers, the host's library functions at the argument's width) and
# makes an integer overflow or an out-of-range conversion an error; the
# folded literal then has to survive each backend's emission.  Each
# program also pins what the old folder gave.

_FOLDED_INTEGERS = """simulation_description("folded mod and powers");
lattices { lattice f(1, 1, real, 4, false); }
initializer I { f.out[x | 0] = 0.0; }
dynamic D { f.out[x | 0] = f.in[x | 0]; }
gauge G -> (real m, real p, real q, real r) {
    m = mod(-7, 2);
    p = 2^(-1);
    q = (-2)^3;
    r = mod(-7.5, 2.0);
}
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""
# the truncated remainder, Fortran's negative-exponent rule, an exact
# integer power, fmod ... not Python's floor remainder (1, 0.5)
_FOLDED_INTEGERS_EXPECTED = {"m": -1.0, "p": 0.0, "q": -8.0, "r": -1.5}
_FOLDED_INTEGERS_OLD = {"m": 1.0, "p": 0.5, "r": 0.5}

_TAU = 0.6
_FOLDED_LIBRARY = f"""simulation_description("folded library calls");
global_constants {{
    const real32 W = 0.5;
    const real TAU = {_TAU!r};
}}
lattices {{ lattice f(1, 1, real, 4, false); }}
initializer I {{ f.out[x | 0] = 0.0; }}
dynamic D {{ f.out[x | 0] = f.in[x | 0]; }}
gauge G -> (real s, real e) {{
    s = sin(W);
    e = exp(-1.0 / TAU);
}}
node_classes {{ node_class B(I, D, G); }}
geometry {{ nodes[:] = B; }}
"""
# the host's binary64 sin of the real32 value, rounded once to real32
# (a binary32 fold is the binary64 fold rounded once), then widened;
# exp of the rounded quotient
_FOLDED_LIBRARY_EXPECTED = {"s": float(np.float32(math.sin(0.5))),
                            "e": math.exp(-1.0 / _TAU)}


@pytest.mark.parametrize("backend", BACKENDS)
def test_folded_integer_intrinsics_and_powers_follow_the_contract(tmp_path, backend):
    assert all(_FOLDED_INTEGERS_OLD[k] != _FOLDED_INTEGERS_EXPECTED[k] for k in _FOLDED_INTEGERS_OLD)
    nc = _run(tmp_path, _FOLDED_INTEGERS, backend)
    for name, expected in _FOLDED_INTEGERS_EXPECTED.items():
        assert np.asarray(nc[name][1]).tolist() == [expected] * 4, name


@pytest.mark.parametrize("backend", BACKENDS)
def test_folded_library_calls_use_the_host_library_at_the_argument_width(tmp_path, backend):
    assert _FOLDED_LIBRARY_EXPECTED["s"] != math.sin(0.5)
    nc = _run(tmp_path, _FOLDED_LIBRARY, backend)
    for name, expected in _FOLDED_LIBRARY_EXPECTED.items():
        assert np.asarray(nc[name][1]).tolist() == [expected] * 4, name


_REJECTED_CONSTANTS = [
    pytest.param("const int A = 9223372036854775807 + 1;", "overflow", id="int64 overflow"),
    pytest.param("const int A = 2^63;", "overflow", id="integer power overflow"),
    pytest.param("const int A = int(1.0e300);", "out of range", id="real to int out of range"),
    pytest.param("const int A = mod(7, 0);", "mod by zero", id="mod by zero"),
    pytest.param("const int A = 0^(-1);", "negative integer power", id="0 to a negative power"),
]


@pytest.mark.parametrize("decl,message", _REJECTED_CONSTANTS)
def test_a_constant_the_contract_makes_an_error_is_rejected_by_gelbc(tmp_path, decl, message):
    source = _FOLDED_INTEGERS.replace("initializer I {", "initializer I { " + decl)
    result = _run(tmp_path, source, "cpu_highway", check=False)
    assert result.returncode != 0
    assert message in result.stderr, result.stderr
    work = tmp_path / "cpu_highway_simplified"
    assert not list(work.glob("*.nc")) and not list(work.glob("*.cpp"))


# -- Intrinsic helpers in both emitter families --------------------------
# The generated code computes the promotion table's values (user manual,
# Numerical semantics: Types and promotion) on every path: one helper per
# intrinsic row (integer ``mod`` and powers, conversions, IEEE ``min``
# and ``max``), the same on Highway's SIMD body, its scalar tail, CUDA
# and Fortran.

_HELPERS_ON_X = f"""simulation_description("integer intrinsics on the coordinate");
lattices {{ lattice u(1, 1, real, {_SIMD_CELLS}, false); }}
initializer I {{ u.out[x | 0] = 0.5; }}
dynamic D {{ u.out[x | 0] = u.in[x | 0]; }}
gauge G -> (real m, real p, real q, real n, real c, real w) {{
    m = mod(x - 7, 2);
    p = (x - 7)^3;
    q = 2^(x - 7);
    n = min(x, 9) + max(x, 60);
    c = real32(x) * 0.5;
    w = int8(x + 120);
}}
node_classes {{ node_class B(I, D, G); }}
geometry {{ nodes[:] = B; }}
"""


def _helpers_on_x_expected(x):
    from gelb.midware import ast_eval as ev
    return {
        "m": float(ev.truncated_mod(x - 7, 2)),
        "p": float(ev.power(x - 7, 3)),
        "q": float(ev.power(2, x - 7)),
        "n": float(min(x, 9) + max(x, 60)),
        "c": float(np.float32(x)) * 0.5,
        "w": float(ev.convert(x + 120, "int8")),
    }


@pytest.mark.parametrize("backend", BACKENDS)
def test_integer_intrinsics_on_the_coordinate_follow_the_contract(tmp_path, backend):
    expected = {name: [_helpers_on_x_expected(x)[name] for x in range(_SIMD_CELLS)]
                for name in ("m", "p", "q", "n", "c", "w")}
    assert expected["m"][:3] == [-1.0, 0.0, -1.0]          # truncated, not floor
    assert expected["q"][:9] == [0.0] * 7 + [1.0, 2.0]      # 2^-7 .. 2^1 as integers
    assert expected["w"][7:9] == [127.0, -128.0]            # int8 wraps
    nc = _run(tmp_path, _HELPERS_ON_X, backend)
    for name, values in expected.items():
        assert np.asarray(nc[name][1]).tolist() == values, name


# Real min/max are IEEE 754-2019 minimum/maximum on every path: a NaN
# (sqrt of a negative run-time value; gfortran rejects a constant one)
# operand gives NaN (std::min(1.0, NaN) gives 1.0) and -0 is less than +0
# (std::min(0.0, -0.0) gives +0).  67 cells put most cells in Highway's
# SIMD body and the rest in its scalar tail.
_IEEE_MINMAX = f"""simulation_description("IEEE minimum and maximum");
lattices {{
    lattice u(1, 1, real, {_SIMD_CELLS}, false);
    lattice s(1, 1, real, {_SIMD_CELLS}, false);
}}
initializer I {{ u.out[x | 0] = sqrt(-1.0 - x); s.out[x | 0] = -0.0; }}
dynamic D {{ u.out[x | 0] = u.in[x | 0]; s.out[x | 0] = s.in[x | 0]; }}
gauge G -> (real a, real b, real c, real d) {{
    a = min(1.0, u.in[x | 0]);
    b = max(u.in[x | 0], 1.0);
    c = min(0.0, s.in[x | 0]);
    d = max(s.in[x | 0], 0.0);
}}
node_classes {{ node_class B(I, D, G); }}
geometry {{ nodes[:] = B; }}
"""


@pytest.mark.parametrize("backend", BACKENDS)
def test_real_min_and_max_are_ieee_minimum_and_maximum_on_every_path(tmp_path, backend):
    nc = _run(tmp_path, _IEEE_MINMAX, backend)
    a, b, c, d = (np.asarray(nc[n][1]).tolist() for n in ("a", "b", "c", "d"))
    assert all(math.isnan(v) for v in a) and all(math.isnan(v) for v in b)
    assert c == [0.0] * _SIMD_CELLS and all(math.copysign(1.0, v) < 0 for v in c)
    assert d == [0.0] * _SIMD_CELLS and all(math.copysign(1.0, v) > 0 for v in d)
    if backend == "cpu_highway":
        code = _generated(tmp_path, backend)
        assert "gelb::gelb_min(" in code and "gelb::gelb_min<double>(" in code   # body and tail
        assert "hn::Min(" not in code and "std::min(" not in code


# -- Consistent math-library dispatch (user manual, Numerical semantics: Library functions)
# One implementation of each library function per backend, in every code
# path: on cpu_highway, Highway's math in the SIMD body and, through a
# one-lane vector, in the scalar tail; the platform's function outside
# Highway's valid range, chosen per lane by the argument's value.

# The library-dispatch probe: a uniform argument across 67 cells (body
# and tail) gave one-ULP differences between cells for sin(10), cos(20),
# tanh(0.1), and a vectorized tan did not compile.
_UNIFORM_LIBRARY = f"""simulation_description("uniform library arguments");
lattices {{
    lattice u(1, 1, real, {_SIMD_CELLS}, false);
    lattice w(1, 1, real, {_SIMD_CELLS}, false);
}}
initializer I {{ u.out[x | 0] = 10.0; w.out[x | 0] = 0.1; }}
dynamic D {{ u.out[x | 0] = u.in[x | 0]; w.out[x | 0] = w.in[x | 0]; }}
gauge G -> (real s, real c, real tn, real h, real e, real l) {{
    s = sin(u.in[x | 0]);
    c = cos(2.0 * u.in[x | 0]);
    tn = tan(u.in[x | 0]);
    h = tanh(w.in[x | 0]);
    e = exp(w.in[x | 0]);
    l = log(u.in[x | 0]);
}}
node_classes {{ node_class B(I, D, G); }}
geometry {{ nodes[:] = B; }}
"""


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_library_function_gives_identical_bits_in_every_cell(tmp_path, backend):
    nc = _run(tmp_path, _UNIFORM_LIBRARY, backend)
    for name, reference in (("s", math.sin(10.0)), ("c", math.cos(20.0)), ("tn", math.tan(10.0)),
                            ("h", math.tanh(0.1)), ("e", math.exp(0.1)), ("l", math.log(10.0))):
        values = np.asarray(nc[name][1]).tolist()
        assert len(set(values)) == 1, (name, sorted(set(values)))
        # the implementation is the backend's own: within a few ULP of the platform's
        assert abs(values[0] - reference) <= 4 * math.ulp(reference), (name, values[0], reference)
    if backend == "cpu_highway":
        code = _generated(tmp_path, backend)
        assert "gelb::gelb_sin(" in code and "gelb::gelb_tan(" in code
        assert "hn::Sin(" not in code and "std::sin(" not in code and "std::tan(" not in code


# Outside Highway's valid range the platform's function serves the lane,
# chosen by the argument's value: exp above +706 and sin beyond 39000, with
# the argument varying across the vector so that both kinds of lane share
# one vector.
_RANGE_FALLBACK = f"""simulation_description("library arguments beyond the vector range");
lattices {{ lattice u(1, 1, real, {_SIMD_CELLS}, false); }}
initializer I {{ u.out[x | 0] = 0.5; }}
dynamic D {{ u.out[x | 0] = u.in[x | 0]; }}
gauge G -> (real e, real s, real l) {{
    e = exp(700.0 + 0.1 * x);
    s = sin(38998.0 + 0.1 * x);
    l = log(0.5 - u.in[x | 0] + 0.1 * (x - 2));
}}
node_classes {{ node_class B(I, D, G); }}
geometry {{ nodes[:] = B; }}
"""


@pytest.mark.parametrize("backend", BACKENDS)
def test_outside_highways_range_the_platform_function_serves_the_lane(tmp_path, backend):
    nc = _run(tmp_path, _RANGE_FALLBACK, backend)
    e, s, l = (np.asarray(nc[n][1]).tolist() for n in ("e", "s", "l"))
    for x in range(_SIMD_CELLS):
        ae, as_, al = 700.0 + 0.1 * x, 38998.0 + 0.1 * x, 0.1 * (x - 2)
        # within the backend's library bound of the platform's value ...
        assert abs(e[x] - math.exp(ae)) <= 2 * math.ulp(math.exp(ae)), (x, e[x])
        assert abs(s[x] - math.sin(as_)) <= 4 * math.ulp(math.sin(as_)), (x, s[x])
        if al > 0:
            assert abs(l[x] - math.log(al)) <= 4 * math.ulp(math.log(al)), (x, l[x])
        elif al == 0:
            assert l[x] == -math.inf, (x, l[x])
        else:
            assert math.isnan(l[x]), (x, l[x])
        # ... and, on cpu_highway, exactly the platform's value where Highway's
        # range ends, whatever the cell's position in the vector
        if backend == "cpu_highway" and ae > 706.0:
            assert e[x] == math.exp(ae), (x, e[x], math.exp(ae))
        if backend == "cpu_highway" and as_ > 39000.0:
            assert s[x] == math.sin(as_), (x, s[x], math.sin(as_))


# -- random() draw count and sequencing (user manual, Numerical semantics: Random numbers)
# In a slice or array expression random() draws once per element in
# index order (Fortran once broadcast one draw over a slice); several
# calls in one expression draw left to right; a default and a plain
# build of one program draw the same numbers.  The
# programs compare a build against an explicitly sequenced form of the
# same draws, with one seed on one thread, bit for bit.

_SLICE_DRAWS = """simulation_description("draws once per element");
global_constants { const array[real, 9] W = {4.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/36.0, 1.0/36.0, 1.0/36.0, 1.0/36.0}; }
lattices { lattice u(1, 9, real, 4, false); }
initializer I { u.out[x | :] = W * random(); }
dynamic D {
    array[real, 9] d = random();
    array[real, 9] e;
    e = 0.5 * random();
    u.out[x | :] = u.in[x | :] + 0.0 * d + 0.0 * e;
}
gauge G -> (real d0, real d1, real d2, real d3, real d4, real d5, real d6, real d7, real d8) {
    d0 = u.in[x | 0] / W[0]; d1 = u.in[x | 1] / W[1]; d2 = u.in[x | 2] / W[2];
    d3 = u.in[x | 3] / W[3]; d4 = u.in[x | 4] / W[4]; d5 = u.in[x | 5] / W[5];
    d6 = u.in[x | 6] / W[6]; d7 = u.in[x | 7] / W[7]; d8 = u.in[x | 8] / W[8];
}
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_slice_draws_once_per_element_in_every_build(tmp_path, backend):
    optimized = _run(tmp_path, _SLICE_DRAWS, backend, True, extra="--seed 1", threads=1)
    plain = _run(tmp_path, _SLICE_DRAWS, backend, False, _ALL_OFF, extra="--seed 1", threads=1)
    names = [f"d{i}" for i in range(9)]
    for cell in range(4):
        draws = [float(optimized[n][1][cell]) for n in names]
        assert len(set(draws)) == 9, (cell, draws)        # nine draws, not one broadcast
        assert all(0.0 <= d < 1.0 for d in draws), draws
        assert draws == [float(plain[n][1][cell]) for n in names], cell   # no pass changes a draw


_ORDERED_DRAWS = """simulation_description("draws left to right");
global_constants { const array[real, 3] W = {1.0, 2.0, 4.0}; }
lattices { lattice u(1, 3, real, 4, false); }
initializer I { u.out[x | :] = 0.25; }
dynamic D { u.out[x | :] = u.in[x | :]; }
gauge G -> (real a, real b, real c) {
    array[real, 3] arr = u.in[x | :];
    a = random() - 2.0 * random();
    b = random() + dot_prod(W, arr * random());
    c = dot_prod(W, arr + random()) - random();
}
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""
# the same draws, sequenced by hand in the order the Random numbers
# section prescribes: a call draws in source order; one in an array
# expression draws once per element, in index order, before the next call
_ORDERED_DRAWS_EXPLICIT = _ORDERED_DRAWS.replace("""    a = random() - 2.0 * random();
    b = random() + dot_prod(W, arr * random());
    c = dot_prod(W, arr + random()) - random();
""", """    real r0 = random(); real r1 = random();
    a = r0 - 2.0 * r1;
    real r2 = random(); array[real, 3] r3 = random();
    b = r2 + dot_prod(W, arr * r3);
    array[real, 3] r4 = random(); real r5 = random();
    c = dot_prod(W, arr + r4) - r5;
""")


@pytest.mark.parametrize("backend", BACKENDS)
def test_several_draws_in_one_expression_are_sequenced_left_to_right(tmp_path, backend):
    assert _ORDERED_DRAWS_EXPLICIT != _ORDERED_DRAWS
    implicit = _run(tmp_path, _ORDERED_DRAWS, backend, extra="--seed 7", threads=1)
    explicit = _run(tmp_path / "explicit", _ORDERED_DRAWS_EXPLICIT, backend, extra="--seed 7", threads=1)
    for name in ("a", "b", "c"):
        got, reference = np.asarray(implicit[name][1]), np.asarray(explicit[name][1])
        assert got.view(np.uint64).tolist() == reference.view(np.uint64).tolist(), name
    # a seed reproduces the stream
    again = _run(tmp_path / "again", _ORDERED_DRAWS, backend, extra="--seed 7", threads=1)
    for name in ("a", "b", "c"):
        assert np.asarray(again[name][1]).view(np.uint64).tolist() == \
            np.asarray(implicit[name][1]).view(np.uint64).tolist(), name


# A stateful call is never shared, dropped, duplicated or reordered,
# including where its numeric contribution simplifies away (``0.0 * r``,
# ``1.0 * r``): the draws still happen, in order, so the next draw is the
# third of the stream.
_VANISHING_DRAWS = """simulation_description("draws whose contribution simplifies away");
lattices { lattice u(1, 1, real, 4, false); }
initializer I { u.out[x | 0] = 0.25; }
dynamic D { u.out[x | 0] = u.in[x | 0]; }
gauge G -> (real a, real b) {
    a = 1.0 * random() + 0.0 * random();
    b = random();
}
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""
_VANISHING_DRAWS_EXPLICIT = _VANISHING_DRAWS.replace(
    "    a = 1.0 * random() + 0.0 * random();\n    b = random();\n",
    "    real r0 = random(); real r1 = random(); real r2 = random();\n    a = 1.0 * r0 + 0.0 * r1;\n    b = r2;\n")


@pytest.mark.parametrize("simplify", [True, False], ids=["optimized", "plain"])
@pytest.mark.parametrize("backend", BACKENDS)
def test_a_draw_whose_contribution_simplifies_away_still_happens(tmp_path, backend, simplify):
    assert _VANISHING_DRAWS_EXPLICIT != _VANISHING_DRAWS
    got = _run(tmp_path, _VANISHING_DRAWS, backend, simplify, _ALL_OFF, extra="--seed 3", threads=1)
    reference = _run(tmp_path / "explicit", _VANISHING_DRAWS_EXPLICIT, backend, simplify, _ALL_OFF,
                     extra="--seed 3", threads=1)
    for name in ("a", "b"):
        assert np.asarray(got[name][1]).view(np.uint64).tolist() == \
            np.asarray(reference[name][1]).view(np.uint64).tolist(), name


# --- Narrow widths, draw order and shape, folded reductions, run-time narrowing

# A narrow-width local, or an implicit conversion to a narrow width, in
# a block over binary64 lattices.  Highway's SIMD body holds every real
# local as a binary64 vector, so such a block takes the scalar path and
# every cell rounds to binary32 as the other backends do; the scalar
# tail did already, which is how the difference showed.  The narrow
# integer wraps on every cell.
_WIDE_CELLS = 200
_NARROW_LOCALS = f"""simulation_description("narrow locals in a binary64 block");
lattices {{ lattice u(1, 1, real, {_WIDE_CELLS}, false); }}
initializer I {{ u.out[x | 0] = 0.1; }}
dynamic D {{ u.out[x | 0] = u.in[x | 0]; }}
gauge G -> (real v, real w, real k) {{
    real32 a = 0.1;
    real32 b = a * a;
    v = b;
    real32 c = u.in[x | 0];
    w = c * c;
    int8 m = x;
    k = m;
}}
node_classes {{ node_class B(I, D, G); }}
geometry {{ nodes[:] = B; }}
"""
_NARROW_LOCALS_EXPECTED = float(np.float32(0.1) * np.float32(0.1))   # 0.010000000707805157
_NARROW_LOCALS_WIDE = float(np.float32(0.1)) * float(np.float32(0.1))   # 0.010000000298023226


@pytest.mark.parametrize("simplify", [True, False], ids=["default", "plain"])
@pytest.mark.parametrize("backend", BACKENDS)
def test_narrow_locals_round_to_their_width_in_every_cell(tmp_path, backend, simplify):
    assert _NARROW_LOCALS_WIDE != _NARROW_LOCALS_EXPECTED
    nc = _run(tmp_path, _NARROW_LOCALS, backend, simplify=simplify, plain_flags=_ALL_OFF)
    for name in ("v", "w"):
        assert np.asarray(nc[name][1]).tolist() == [_NARROW_LOCALS_EXPECTED] * _WIDE_CELLS, name
    assert np.asarray(nc["k"][1]).tolist() == \
        [float(((x + 128) % 256) - 128) for x in range(_WIDE_CELLS)]


# Draws inside and around user-function calls keep source order
# (sequenced before inlining): the arguments of a call draw before its
# body, a call whose body
# draws is one unit in the left-to-right order, and nested calls keep
# their order.  Compared with explicit scalar draws from the same seed,
# in both pass modes.
_FUNCTION_DRAWS = """simulation_description("draw order through function calls");
lattices { lattice u(1, 1, real, 4, false); }
function Identity(real p) -> (real q) { q = p; }
function Noisy(real p) -> (real q) { q = p + 0.5 * random(); }
function Twice(real p) -> (real q) { q = Noisy(p) + Noisy(p); }
initializer I { u.out[x | 0] = 0.0; }
dynamic D { u.out[x | 0] = u.in[x | 0]; }
gauge G -> (real a, real b, real c, real nxt) {
    a = random() - Identity(random());
    b = Noisy(1.0) + random();
    c = random() * Twice(Identity(random()));
    nxt = random();
}
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""
_FUNCTION_DRAWS_EXPLICIT = _FUNCTION_DRAWS.replace("""    a = random() - Identity(random());
    b = Noisy(1.0) + random();
    c = random() * Twice(Identity(random()));
""", """    real r0 = random(); real r1 = random();
    a = r0 - r1;
    real r2 = random(); real r3 = random();
    b = (1.0 + 0.5 * r2) + r3;
    real r4 = random(); real r5 = random(); real r6 = random(); real r7 = random();
    c = r4 * ((r5 + 0.5 * r6) + (r5 + 0.5 * r7));
""")


def _bits_of(nc, name):
    return np.asarray(nc[name][1]).view(np.uint64).tolist()


@pytest.mark.parametrize("simplify", [True, False], ids=["default", "plain"])
@pytest.mark.parametrize("backend", BACKENDS)
def test_draws_around_function_calls_are_sequenced_left_to_right(tmp_path, backend, simplify):
    assert _FUNCTION_DRAWS_EXPLICIT != _FUNCTION_DRAWS
    implicit = _run(tmp_path, _FUNCTION_DRAWS, backend, simplify=simplify,
                    plain_flags=_ALL_OFF, extra="--seed 7", threads=1)
    explicit = _run(tmp_path / "explicit", _FUNCTION_DRAWS_EXPLICIT, backend, simplify=simplify,
                    plain_flags=_ALL_OFF, extra="--seed 7", threads=1)
    for name in ("a", "b", "c", "nxt"):
        assert _bits_of(implicit, name) == _bits_of(explicit, name), name


# The shape of a draw.  An element of an array constructor
# is a scalar context: ``{random(), random(), random()}`` is three scalar
# draws.  A scalar expression broadcast over an array draws once per
# element, intrinsic calls included: ``sqrt(random())``, ``min(random(),
# 0.5) + random()``, in a declaration, a whole-array assignment and a
# slice store.  Compared with explicit draws, both pass modes, 67 cells
# so that Highway's SIMD body runs.
_ARRAY_DRAWS = f"""simulation_description("draw shapes: constructors and broadcasts");
lattices {{ lattice u(1, 3, real, {_SIMD_CELLS}, false); }}
initializer I {{ u.out[x | :] = 0.25 + sqrt(random()); }}
dynamic D {{ u.out[x | :] = u.in[x | :]; }}
gauge G -> (real a, real b, real c, real d, real e, real nxt) {{
    array[real, 3] r = {{random(), random(), random()}};
    a = r[0] + 2.0 * r[1] + 4.0 * r[2];
    array[real, 3] s = sqrt(random());
    b = s[0] + 2.0 * s[1] + 4.0 * s[2];
    array[real, 3] m = min(random(), 0.5) + random();
    c = m[0] + 2.0 * m[1] + 4.0 * m[2];
    array[real, 3] w = u.in[x | :];
    w = w * sqrt(random());
    d = w[0] + 2.0 * w[1] + 4.0 * w[2];
    array[real, 3] g = u.in[x | :];
    e = g[0] + 2.0 * g[1] + 4.0 * g[2];
    nxt = random();
}}
node_classes {{ node_class B(I, D, G); }}
geometry {{ nodes[:] = B; }}
"""
_ARRAY_DRAWS_EXPLICIT = _ARRAY_DRAWS.replace(
    "initializer I { u.out[x | :] = 0.25 + sqrt(random()); }",
    "initializer I { array[real, 3] d0 = random(); "
    "array[real, 3] s0 = {sqrt(d0[0]), sqrt(d0[1]), sqrt(d0[2])}; "
    "u.out[x | :] = 0.25 + s0; }",
).replace("""    array[real, 3] r = {random(), random(), random()};
    a = r[0] + 2.0 * r[1] + 4.0 * r[2];
    array[real, 3] s = sqrt(random());
    b = s[0] + 2.0 * s[1] + 4.0 * s[2];
    array[real, 3] m = min(random(), 0.5) + random();
    c = m[0] + 2.0 * m[1] + 4.0 * m[2];
    array[real, 3] w = u.in[x | :];
    w = w * sqrt(random());
""", """    real r0 = random(); real r1 = random(); real r2 = random();
    array[real, 3] r = {r0, r1, r2};
    a = r[0] + 2.0 * r[1] + 4.0 * r[2];
    array[real, 3] d1 = random();
    array[real, 3] s = {sqrt(d1[0]), sqrt(d1[1]), sqrt(d1[2])};
    b = s[0] + 2.0 * s[1] + 4.0 * s[2];
    array[real, 3] d2 = random();
    array[real, 3] d3 = random();
    array[real, 3] m = {min(d2[0], 0.5) + d3[0], min(d2[1], 0.5) + d3[1], min(d2[2], 0.5) + d3[2]};
    c = m[0] + 2.0 * m[1] + 4.0 * m[2];
    array[real, 3] w = u.in[x | :];
    array[real, 3] d4 = random();
    array[real, 3] s4 = {sqrt(d4[0]), sqrt(d4[1]), sqrt(d4[2])};
    w = w * s4;
""")


@pytest.mark.parametrize("simplify", [True, False], ids=["default", "plain"])
@pytest.mark.parametrize("backend", BACKENDS)
def test_draw_shapes_in_constructors_and_broadcasts(tmp_path, backend, simplify):
    assert _ARRAY_DRAWS_EXPLICIT != _ARRAY_DRAWS
    implicit = _run(tmp_path, _ARRAY_DRAWS, backend, simplify=simplify,
                    plain_flags=_ALL_OFF, extra="--seed 7", threads=1)
    explicit = _run(tmp_path / "explicit", _ARRAY_DRAWS_EXPLICIT, backend, simplify=simplify,
                    plain_flags=_ALL_OFF, extra="--seed 7", threads=1)
    for name in ("a", "b", "c", "d", "e", "nxt"):
        assert _bits_of(implicit, name) == _bits_of(explicit, name), name
    # three scalar draws are three distinct numbers, not one broadcast
    r = np.asarray(implicit["a"][1]).tolist()
    assert len(set(r)) == len(r)


# A reduction of constants folds in the expression's width: an integer
# sum is exact, a real32 dot product rounds each product and each sum
# to binary32, and a result that overflows folds to the infinity, which
# every backend emits as an explicit special value (user manual,
# Numerical semantics: Special values).
_FOLDED_REDUCTIONS = """simulation_description("folded reductions in their width");
global_constants {
    const array[int, 2] BIG = {9007199254740993, 0};
    const array[real32, 2] P = {1.3, 1.0};
    const array[real32, 2] Q = {0.3, -0.39000001549720764};
    const array[real, 2] HUGE = {1.0e308, 1.0e308};
    const array[real, 2] H0 = {1.0e308, 0.0};
    const array[real, 2] TEN = {10.0, 0.0};
}
lattices { lattice u(1, 1, real, 4, false); }
initializer I { u.out[x | 0] = 0.0; }
dynamic D { u.out[x | 0] = u.in[x | 0]; }
gauge G -> (real s, real d, real h, real k) {
    s = sum(BIG) - 9007199254740992;
    d = dot_prod(P, Q);
    h = sum(HUGE);
    k = dot_prod(H0, TEN);
}
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""
_F32 = np.float32
_FOLDED_REDUCTIONS_EXPECTED = {
    "s": 1.0,
    "d": float(_F32(_F32(_F32(1.3) * _F32(0.3)) + _F32(_F32(1.0) * _F32(-0.39000001549720764)))),
    "h": math.inf,
    "k": math.inf,
}
# what a binary64 fold of the same constants gives (the defect)
_FOLDED_REDUCTIONS_WIDE = {"s": 0.0, "d": float(_F32(1.3)) * float(_F32(0.3))
                           + float(_F32(1.0)) * float(_F32(-0.39000001549720764))}


@pytest.mark.parametrize("backend", BACKENDS)
def test_folded_reductions_compute_in_their_width(tmp_path, backend):
    assert all(_FOLDED_REDUCTIONS_WIDE[k] != _FOLDED_REDUCTIONS_EXPECTED[k] for k in _FOLDED_REDUCTIONS_WIDE)
    nc = _run(tmp_path, _FOLDED_REDUCTIONS, backend)
    for name, expected in _FOLDED_REDUCTIONS_EXPECTED.items():
        assert np.asarray(nc[name][1]).tolist() == [expected] * 4, name


# A real narrowed past its range is not a compile-time error: the
# conversion folds to the infinity the narrowing produces, as a library
# overflow does at run time.  A real converted to an integer out of
# range remains an error (_REJECTED_CONSTANTS).
_OVERFLOWING_CASTS = """simulation_description("real narrowing overflow at run time");
lattices { lattice u(1, 1, real, 4, false); }
initializer I { u.out[x | 0] = 0.0; }
dynamic D { u.out[x | 0] = u.in[x | 0]; }
gauge G -> (real v, real w, real k) {
    v = real32(1.0e300);
    real32 a = 1.0e300;
    w = a;
    real32 b = 1.0e200 * 1.0e200;
    k = b;
}
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_real_narrowed_past_its_range_overflows_at_run_time(tmp_path, backend):
    nc = _run(tmp_path, _OVERFLOWING_CASTS, backend)
    for name in ("v", "w", "k"):
        assert np.asarray(nc[name][1]).tolist() == [math.inf] * 4, name


# --- Constant arrays in their declared width ------------------------------------

# A constant array's elements are the values its declared width stores,
# on every backend and in every reading: an ``int8`` array of
# ``{300, 1}`` holds 44 and 1, an ``int16`` of 70000 holds 4464, a
# ``real32`` array holds the binary32 roundings.  An element a narrow
# real width cannot hold (``1.0e300``) is an infinity, and a reduction
# or ``matmul`` over such an array folds to its IEEE value and is
# emitted as an explicit special value, so neither the folder (an
# overflowing array operand) nor the native build (a literal the
# declared type cannot spell) fails.  Both
# slice modes, since the slice expansion collects constant arrays too.
_CONSTANT_ARRAY_WIDTHS = """simulation_description("constant arrays in their declared width");
global_constants {
    const array[real32, 2] A = {1.0e300, 1.0};
    const array[real32, 2] C = {1.0, 1.0};
    const array[real32, 2] P = {1.3, 1.0};
    const array[int8, 2] N8 = {300, 1};
    const array[int16, 2] N16 = {70000, 1};
    const array[real32, {2, 2}] M = {{1.0e300, 0.0}, {0.0, 1.0}};
    const array[real32, 2] V = {1.0, 2.0};
}
lattices { lattice u(1, 1, real, 4, false); }
initializer I { u.out[x | 0] = 0.0; }
dynamic D { u.out[x | 0] = u.in[x | 0]; }
gauge G -> (real a0, real sa, real da, real p0, real n0, real sn, real s0, real m0, real m1) {
    a0 = A[0];
    sa = sum(A);
    da = dot_prod(A, C);
    p0 = P[0];
    n0 = N8[0];
    sn = sum(N8);
    s0 = N16[0];
    array[real32, 2] r = matmul(M, V);
    m0 = r[0];
    m1 = r[1];
}
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""
_CONSTANT_ARRAY_WIDTHS_EXPECTED = {
    "a0": math.inf, "sa": math.inf, "da": math.inf,
    "p0": float(np.float32(1.3)),
    "n0": 44.0, "sn": 45.0, "s0": 4464.0,
    "m0": math.inf, "m1": 2.0,
}


@pytest.mark.parametrize("simplify", [True, False], ids=["expanded", "no-slice-simplify"])
@pytest.mark.parametrize("backend", BACKENDS)
def test_constant_arrays_hold_their_declared_width_on_every_backend(tmp_path, backend, simplify):
    assert _CONSTANT_ARRAY_WIDTHS_EXPECTED["p0"] != 1.3
    nc = _run(tmp_path, _CONSTANT_ARRAY_WIDTHS, backend, simplify=simplify, plain_flags=_ALL_OFF)
    for name, expected in _CONSTANT_ARRAY_WIDTHS_EXPECTED.items():
        assert np.asarray(nc[name][1]).tolist() == [expected] * 4, name


# --- An overflowing element written as an expression ----------------------------

# The same rule as ``_CONSTANT_ARRAY_WIDTHS`` when the element the width
# cannot hold is written as an explicit conversion or as an overflowing
# product, in a 1-D and a 2-D constant array: read, summed and multiplied
# it is an infinity, through the frontend (no binding for a shape),
# the slice expansion and each backend's declaration (a constant
# expression for the infinity on C++, the converted expression on
# Fortran).  Two independent programs, so a frontend failure in one
# cannot hide an emitter path in the other; both slice modes.
def _overflowing_element_program(element):
    return f"""simulation_description("an overflowing constant-array element");
global_constants {{
    const array[real32, 2] A = {{{element}, 1.0}};
    const array[real32, {{2, 2}}] M = {{{{{element}, 0.0}}, {{0.0, 1.0}}}};
    const array[real32, 2] V = {{1.0, 2.0}};
}}
lattices {{ lattice u(1, 1, real, 4, false); }}
initializer I {{ u.out[x | 0] = 0.0; }}
dynamic D {{ u.out[x | 0] = u.in[x | 0]; }}
gauge G -> (real a0, real sa, real m0, real m1) {{
    a0 = A[0];
    sa = sum(A);
    array[real32, 2] r = matmul(M, V);
    m0 = r[0];
    m1 = r[1];
}}
node_classes {{ node_class B(I, D, G); }}
geometry {{ nodes[:] = B; }}
"""


_OVERFLOWING_ELEMENTS = [
    ("cast", "real32(1.0e300)"),
    ("product", "1.0e300 * 1.0e300"),
]
_OVERFLOWING_ELEMENT_EXPECTED = {"a0": math.inf, "sa": math.inf, "m0": math.inf, "m1": 2.0}


@pytest.mark.parametrize("element", [e for _, e in _OVERFLOWING_ELEMENTS],
                         ids=[k for k, _ in _OVERFLOWING_ELEMENTS])
@pytest.mark.parametrize("simplify", [True, False], ids=["expanded", "no-slice-simplify"])
@pytest.mark.parametrize("backend", BACKENDS)
def test_an_overflowing_element_expression_is_an_infinity_on_every_backend(
        tmp_path, backend, simplify, element):
    nc = _run(tmp_path, _overflowing_element_program(element), backend,
              simplify=simplify, plain_flags=_ALL_OFF)
    for name, expected in _OVERFLOWING_ELEMENT_EXPECTED.items():
        assert np.asarray(nc[name][1]).tolist() == [expected] * 4, name
