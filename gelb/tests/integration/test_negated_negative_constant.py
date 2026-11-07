"""Negating a negative constant gives its exact negation on every backend.

A negative constant reaches the generated code as a bare literal: a
negative ``-D`` value, or an element of a constant array such as
``EX``.  A program may negate it, multiply it by -1 or subtract it from
zero; each is the IEEE negation (user manual, Numerical semantics: the
IEEE basic operations), so a zero keeps its sign (Special values), a
``real32`` constant keeps its precision, and the backends agree bit
for bit.  The C++ and CUDA builds must read such
a minus as one negation, never as a decrement.  The constants reach the
blocks through an inlined function, as a moving wall's velocity does: a
constant used directly in a block is folded by the midware before any
backend sees it.
"""

import os
import pathlib
import subprocess
import sys

import numpy as np
import pytest

from gelb.backends.highway import common
from gelb.tests.integration._toolchain import (
    requires_compiler,
    requires_cpp_highway_compiler,
    requires_gpu_cuda_cpp_compiler,
)

netCDF4 = pytest.importorskip("netCDF4")

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_GELB_RUN = _ROOT / "scripts" / "gelb-run"
_EXAMPLES = _ROOT / "examples"

# 1 + EX * U, with EX's -1 negating U.
DOUBLE_MINUS = (_ROOT / "gelb/tests/fixtures/regressions/double_minus.gelb").read_text()

# An integer: EI's -1 negates K.
INTEGER = """
simulation_description("a negated negative integer constant");
global_constants {
    const int K = -2;
    const array[int, 3] EI = {0, 1, -1};
}
lattices { lattice f(2, 3, real, {64, 8}, {true, true}); }
function Scale(int k) -> (array[real, 3] g) { g = real(EI * k); }
initializer Init { f.out[x, y | :] = Scale(K); }
dynamic Step { f.out[x, y | :] = f.in[x, y | :]; }
gauge G -> (real a, real b, real c) {
    a = f.in[x, y | 0];
    b = f.in[x, y | 1];
    c = f.in[x, y | 2];
}
node_classes { node_class BULK(Init, Step, G); }
geometry { nodes[:, :] = BULK; }
"""

# A signed zero: the sign of EX * Z shows as the sign of 1 / (EX * Z).
SIGNED_ZERO = """
simulation_description("a negated negative zero keeps the IEEE sign");
global_constants {
    const real Z = -0.0;
    const array[real, 3] EX = {0.0, 1.0, -1.0};
}
lattices { lattice f(2, 3, real, {64, 8}, {true, true}); }
function Recip(real u) -> (array[real, 3] g) { g = 1.0 / (EX * u); }
initializer Init { f.out[x, y | :] = Recip(Z); }
dynamic Step { f.out[x, y | :] = f.in[x, y | :]; }
gauge G -> (real a, real b, real c) {
    a = f.in[x, y | 0];
    b = f.in[x, y | 1];
    c = f.in[x, y | 2];
}
node_classes { node_class BULK(Init, Step, G); }
geometry { nodes[:, :] = BULK; }
"""

# A unary minus: -(EX * U).
UNARY = DOUBLE_MINUS.replace(
    "a negated negative constant: 1 + EX * U with U < 0",
    "a unary minus of a negative constant: -(EX * U) with U < 0").replace(
    "g = 1.0 + EX * u;", "g = -(EX * u);")

# A real32 constant: its literal carries a suffix (-0.05f), which the
# negation keeps.
REAL32 = """
simulation_description("a negated negative real32 constant");
global_constants {
    const real U = -0.05;
    const array[real32, 3] A = {real32(U), real32(2.0 * U), real32(0.0 * U)};
}
lattices { lattice f(2, 3, real32, {64, 8}, {true, true}); }
function Neg(array[real32, 3] v) -> (array[real32, 3] g) { g = -v; }
initializer Init { f.out[x, y | :] = Neg(A); }
dynamic Step { f.out[x, y | :] = f.in[x, y | :]; }
gauge G -> (real32 a, real32 b, real32 c) {
    a = f.in[x, y | 0];
    b = f.in[x, y | 1];
    c = f.in[x, y | 2];
}
node_classes { node_class BULK(Init, Step, G); }
geometry { nodes[:, :] = BULK; }
"""

# A difference from a negative zero: only Z's -0.0 entry folds to a
# negation of U; 0.0 - U keeps the sign IEEE gives it when U is a zero.
SUBTRACT = """
simulation_description("a negative constant subtracted from a negative zero");
global_constants {
    const real U = -0.25;
    const array[real, 3] Z = {-0.0, 0.0, 2.0};
}
lattices { lattice f(2, 3, real, {64, 8}, {true, true}); }
function Sub(real u) -> (array[real, 3] g) { g = Z - u; }
initializer Init { f.out[x, y | :] = Sub(U); }
dynamic Step { f.out[x, y | :] = f.in[x, y | :]; }
gauge G -> (real a, real b, real c) {
    a = f.in[x, y | 0];
    b = f.in[x, y | 1];
    c = f.in[x, y | 2];
}
node_classes { node_class BULK(Init, Step, G); }
geometry { nodes[:, :] = BULK; }
"""

_EX = np.array([0.0, 1.0, -1.0])
_Z = np.array([-0.0, 0.0, 2.0])

# name: (source, constant, its negative value, the value of the
# positive control, the three DF values for a constant value v).  Each
# source's own value is negative.
CASES = {
    "real": (DOUBLE_MINUS, "U", -0.05, 0.05, lambda v: 1.0 + _EX * v),
    "int": (INTEGER, "K", -2, 2, lambda v: np.array([0, 1, -1]) * v * 1.0),
    "signed_zero": (SIGNED_ZERO, "Z", -0.0, 0.0, lambda v: 1.0 / (_EX * v)),
    "unary": (UNARY, "U", -0.05, 0.05, lambda v: -(_EX * v)),
    "real32": (REAL32, "U", -0.05, 0.05,
               lambda v: -np.array([v, 2.0 * v, 0.0 * v], dtype=np.float32)),
    "subtract": (SUBTRACT, "U", -0.25, 0.25, lambda v: _Z - v),
    "subtract_zero": (SUBTRACT, "U", -0.0, 0.0, lambda v: _Z - v),
}

CONFIGS = [
    pytest.param("cpu_fortran_serial", None, marks=requires_compiler,
                 id="fortran"),
    *(pytest.param("cpu_highway", layout,
                   marks=requires_cpp_highway_compiler,
                   id=f"highway-{layout}")
      for layout in ("soa", "aos", "cbt")),
    pytest.param("gpu_cuda_cpp", None, marks=requires_gpu_cuda_cpp_compiler,
                 id="cuda"),
]


def _run(directory, backend, program, layout=None, steps=2, defines=()):
    """Run ``program`` (a path, or source text) and return its variables."""
    directory.mkdir()
    if isinstance(program, str):
        path = directory / "probe.gelb"
        path.write_text(program)
    else:
        path = program
    env = dict(os.environ, GELB_PYTHON=sys.executable)
    if layout is not None:
        env["GELBC_EXTRA"] = f"--storage-layout {layout}"
    result = subprocess.run(
        [str(_GELB_RUN), "-b", backend, "-n", str(steps), "-w", "1",
         *(arg for d in defines for arg in ("-D", d)), str(path)],
        cwd=directory, env=env, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stdout + result.stderr
    with netCDF4.Dataset(next(directory.glob("*.nc"))) as nc:
        nc.set_auto_mask(False)
        return {name: np.asarray(var[:]) for name, var in nc.variables.items()
                if name not in ("x", "y", "z", "time")}


@pytest.mark.parametrize("sign", ["negative", "positive"])
@pytest.mark.parametrize("case", sorted(CASES))
@pytest.mark.parametrize("backend, layout", CONFIGS)
def test_negated_constant(tmp_path, backend, layout, case, sign):
    if layout == "cbt" and not common._detect_avx512_available():
        pytest.skip("the cbt layout needs an AVX-512 host")
    source, name, negative, positive, values = CASES[case]
    # Both signs set the constant with -D, as a reversed wall does; the
    # positive control takes the same path with no double minus.
    value = negative if sign == "negative" else positive
    data = _run(tmp_path / "run", backend, source, layout,
                defines=(f"{name}={value}",))
    with np.errstate(divide="ignore"):
        expected = values(value)
    for output, v in zip(("a", "b", "c"), expected):
        np.testing.assert_array_equal(
            data[output], np.full(data[output].shape, v), err_msg=output)
        # A zero keeps its sign: -(0.0 * -0.05) is +0.0.
        assert (np.signbit(data[output]) == np.signbit(v)).all(), output


# Moving walls reversed with -D: the lid-driven cavities (the paper's
# among them) and a bounce-back Couette flow.
WALLS = [
    ("lbm/2d/lid_driven_cavity_2d_bgk.gelb", "U_LID=-0.1"),
    ("lbm/3d/lid_driven_cavity_3d_bgk.gelb", "U_LID=-0.05"),
    ("softwarex-2026-paper/lid_driven_cavity_2d_bgk.gelb", "U_LID=-0.1"),
    ("lbm/2d/couette_flow_2d_bgk.gelb", "U_WALL=-0.01"),
]


@pytest.fixture(scope="module")
def fortran_run(tmp_path_factory):
    """One Fortran run per example, the reference for the C++ builds."""
    runs = {}

    def get(example, define):
        if example not in runs:
            runs[example] = _run(tmp_path_factory.mktemp("fortran") / "run",
                                 "cpu_fortran_serial", _EXAMPLES / example,
                                 steps=1, defines=(define,))
        return runs[example]
    return get


@requires_compiler
@pytest.mark.parametrize("backend", [
    pytest.param("cpu_highway", marks=requires_cpp_highway_compiler),
    pytest.param("gpu_cuda_cpp", marks=requires_gpu_cuda_cpp_compiler),
])
@pytest.mark.parametrize("example, define", WALLS,
                         ids=[e.removesuffix(".gelb").replace("/", "-")
                              for e, _ in WALLS])
def test_reversed_wall_builds(tmp_path, fortran_run, backend, example, define):
    data = _run(tmp_path / "run", backend, _EXAMPLES / example,
                steps=1, defines=(define,))
    reference = fortran_run(example, define)
    assert data.keys() == reference.keys()
    for output, values in data.items():
        # The same flow as Fortran's; the backends may differ in rounding
        # (CUDA keeps nvcc's multiply-adds).
        np.testing.assert_allclose(values, reference[output],
                                   rtol=1e-12, atol=1e-15, err_msg=output)
