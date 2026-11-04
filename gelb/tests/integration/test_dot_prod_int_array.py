"""``dot_prod`` of real constant coefficients with an integer array is
real, on every backend.

The result has the real operand's width, and each integer element
converts to that width before it is multiplied (user manual, Numerical
semantics: Types and promotion), whatever the operand order and the
array's length, whether the integer array holds constants or values
computed per cell, and when both arrays are constants passed to a
function.  On ``cpu_highway`` and ``gpu_cuda_cpp`` the scalar code
path writes the products out and adds them in index order; a
``dot_prod`` whose array is real keeps its reduction helper.  Outside
the ``real32`` shapes the coefficients are dyadic, so every product and
sum is exact in binary64; the ``real32`` shapes round in binary32 after
every operation.  The backends must agree bit for bit.
"""

import os
import pathlib
import re
import subprocess
import sys

import numpy as np
import pytest
from click.testing import CliRunner

from gelb.backends.highway import common
from gelb.gelbc import cli
from gelb.tests.integration._toolchain import (
    requires_compiler, requires_cpp_highway_compiler,
    requires_gpu_cuda_cpp_compiler)

netCDF4 = pytest.importorskip("netCDF4")

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_GELB_RUN = _ROOT / "scripts" / "gelb-run"

# A 16 x 4 periodic lattice: DF 1 holds x + 0.5 and DF 0 the dot product.
PROGRAM = """
simulation_description("dot_prod of real coefficients with an int array");
global_constants {{
    const array[real, 3] W = {{0.5, 0.25, 0.125}};
    const array[real, 9] W9 = {{0.5, -0.25, 0.0, 1.5, 0.125, -2.0, 0.75, 0.0625, 3.0}};
    const array[real32, 2] W32 = {{0.1, 0.5}};
    const array[real, 3] PM = {{1.0, 1.0, -1.0}};
    const array[real32, 3] ONES32 = {{1.0, 1.0, 1.0}};
    const array[int, 3] KC = {{1, 2, 3}};
    const array[real, 3] ONES = {{1.0, 1.0, 1.0}};
    const array[real32, 2] W2 = {{1.0, -1.0}};
    const array[int, 2] K2 = {{9007199791611905, 9007199254740992}};
}}
{functions}
lattices {{ lattice f(2, 2, real, {{16, 4}}, {{true, true}}); }}
initializer Init {{ f.out[x, y | 0] = 0.0; f.out[x, y | 1] = real(x) + 0.5; }}
dynamic Step {{
{body}
    f.out[x, y | 1] = f.in[x, y | 1];
}}
gauge G -> (real s) {{ s = f.in[x, y | 0]; }}
node_classes {{ node_class BULK(Init, Step, G); }}
geometry {{ nodes[:, :] = BULK; }}
"""

_X = np.arange(16, dtype=np.float64)
_W9 = np.array([0.5, -0.25, 0.0, 1.5, 0.125, -2.0, 0.75, 0.0625, 3.0])

# name: (dynamic body, expected DF 0 along x)
SHAPES = {
    "local": ("    array[int, 3] k = {1, 2, 3};\n"
              "    f.out[x, y | 0] = dot_prod(W, k);",
              np.full(16, 1.375)),
    "per_cell": ("    array[int, 3] k = {x, 1, 2};\n"
                 "    f.out[x, y | 0] = dot_prod(W, k);",
                 0.5 * _X + 0.5),
    "reversed": ("    array[int, 3] k = {x, 1, 2};\n"
                 "    f.out[x, y | 0] = dot_prod(k, W);",
                 0.5 * _X + 0.5),
    # Longer than the helper's four accumulators, with zero and
    # negative coefficients.
    "nine_terms": ("    array[int, 9] k = {x, 1, 2, 3, 4, 5, 6, 7, 8};\n"
                   "    f.out[x, y | 0] = dot_prod(W9, k);",
                   _W9[0] * _X + _W9[1:] @ np.arange(1.0, 9.0)),
    # real32 coefficients: the products and the sum are binary32.
    "real32": ("    array[int, 2] k = {3, x};\n"
               "    f.out[x, y | 0] = dot_prod(W32, k);",
               (np.float32(0.1) * np.float32(3)
                + np.float32(0.5) * _X.astype(np.float32)).astype(np.float64)),
    # Coefficients of +/-1: the sum is real, so an int8 array does not
    # wrap, and a real32 sum rounds after every addition (2^24 + 1 is
    # 2^24 in binary32).
    "unit_int8": ("    array[int8, 3] k = {int8(100), int8(100), int8(x)};\n"
                  "    f.out[x, y | 0] = dot_prod(PM, k);",
                  200.0 - _X),
    "unit_real32": ("    array[int, 3] k = {16777216, 1, x};\n"
                    "    f.out[x, y | 0] = dot_prod(ONES32, k);",
                    ((np.float32(16777216) + np.float32(1))
                     + _X.astype(np.float32)).astype(np.float64)),
    # A quotient of two such sums is a real division.
    "unit_quotient": ("    array[int, 3] k = {x, 1, 2};\n"
                      "    array[int, 3] j = {1, 1, 0};\n"
                      "    f.out[x, y | 0] = dot_prod(ONES, k) / dot_prod(ONES, j);",
                      (_X + 3.0) / 2.0),
    # Both arrays constant, through an inlined function, in both orders.
    "function": ("    f.out[x, y | 0] = DotWK(W, KC);", np.full(16, 1.375)),
    "function_reversed": ("    f.out[x, y | 0] = DotKW(KC, W);",
                          np.full(16, 1.375)),
    # Each integer converts to binary32 directly, not through binary64:
    # 2^53 + 2^29 + 1 rounds up to 2^53 + 2^30.
    "function_reversed_real32": ("    f.out[x, y | 0] = DotKW32(K2, W2);",
                                 np.full(16, 2.0 ** 30)),
    # Integer coefficients with a real32 array computed per cell: K2[0]
    # converts to 2^53 + 2^30 directly; through binary64 it would become
    # 2^53.  The products and the sum round in binary32.
    "int_coefficients_real32": (
        "    array[real32, 2] r = {real32(f.in[x, y | 1]), -real32(f.in[x, y | 1])};\n"
        "    f.out[x, y | 0] = dot_prod(K2, r);",
        (np.float32(2.0 ** 53 + 2.0 ** 30) * (_X + 0.5).astype(np.float32)
         + np.float32(2.0 ** 53) * -(_X + 0.5).astype(np.float32)
         ).astype(np.float64)),
    # Controls, right before the change: integer coefficients with a
    # real array (the helper reads the real array), and two arrays that
    # are both computed per cell.
    "int_coefficients": ("    array[real, 3] r = {f.in[x, y | 1], 1.0, 2.0};\n"
                         "    f.out[x, y | 0] = dot_prod(KC, r);",
                         _X + 0.5 + 2.0 + 6.0),
    "both_per_cell": ("    array[real, 3] r = {f.in[x, y | 1], 1.0, 2.0};\n"
                      "    array[int, 3] k = {x, 1, 2};\n"
                      "    f.out[x, y | 0] = dot_prod(r, k);",
                      (_X + 0.5) * _X + 1.0 + 4.0),
}

# The dynamics read a per-cell or constant integer array, which the
# Highway SIMD body does not build yet, so Highway runs them on AoS,
# its scalar path.
CONFIGS = [
    pytest.param("cpu_fortran_serial", None, marks=requires_compiler,
                 id="fortran"),
    pytest.param("cpu_highway", "aos", marks=requires_cpp_highway_compiler,
                 id="highway-aos"),
    pytest.param("gpu_cuda_cpp", None, marks=requires_gpu_cuda_cpp_compiler,
                 id="cuda"),
]


FUNCTIONS = """
function DotWK(array[real, 3] w, array[int, 3] k) -> (real v) { v = dot_prod(w, k); }
function DotKW(array[int, 3] k, array[real, 3] w) -> (real v) { v = dot_prod(k, w); }
function DotKW32(array[int, 2] k, array[real32, 2] w) -> (real32 v) { v = dot_prod(k, w); }
"""


def _program(shape):
    body = SHAPES[shape][0]
    return PROGRAM.format(body=body,
                          functions=FUNCTIONS if "Dot" in body else "")


def _run(directory, backend, source, layout=None):
    directory.mkdir()
    path = directory / "probe.gelb"
    path.write_text(source)
    env = dict(os.environ, GELB_PYTHON=sys.executable)
    if layout is not None:
        env["GELBC_EXTRA"] = f"--storage-layout {layout}"
    flags = ["--strict-fp"] if backend == "gpu_cuda_cpp" else []
    result = subprocess.run(
        [str(_GELB_RUN), "-b", backend, *flags, "-n", "1", "-w", "1",
         str(path)],
        cwd=directory, env=env, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stdout + result.stderr
    with netCDF4.Dataset(next(directory.glob("*.nc"))) as nc:
        return {name: np.asarray(var[:]) for name, var in nc.variables.items()}


@pytest.mark.parametrize("backend, layout", CONFIGS)
@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_dot_prod_with_an_integer_array_is_real(tmp_path, shape, backend,
                                                layout):
    expected = SHAPES[shape][1]
    data = _run(tmp_path / "run", backend, _program(shape), layout)
    s = data["s"][-1]
    assert s.shape == (4, 16)
    np.testing.assert_array_equal(s, np.broadcast_to(expected, s.shape))


# A gauge with an integer output takes the scalar gauge path on every
# Highway layout, so the SoA and CBT layouts reach the dot product too.
INT_OUTPUT_GAUGE = """
simulation_description("dot_prod in a gauge with an int output");
global_constants { const array[real, 3] W = {0.5, 0.25, 0.125}; }
lattices { lattice f(2, 2, real, {64, 4}, {true, true}); }
initializer Init { f.out[x, y | :] = 0.0; }
dynamic Step { f.out[x, y | :] = f.in[x, y | :]; }
gauge G -> (int tt, real s) {
    array[int, 3] k = {x, 1, 2};
    tt = x;
    s = dot_prod(W, k);
}
node_classes { node_class BULK(Init, Step, G); }
geometry { nodes[:, :] = BULK; }
"""


@pytest.mark.parametrize("backend, layout", [
    pytest.param("cpu_fortran_serial", None, marks=requires_compiler,
                 id="fortran"),
    *(pytest.param("cpu_highway", layout,
                   marks=requires_cpp_highway_compiler,
                   id=f"highway-{layout}")
      for layout in ("soa", "aos", "cbt")),
    pytest.param("gpu_cuda_cpp", None, marks=requires_gpu_cuda_cpp_compiler,
                 id="cuda"),
])
def test_in_a_gauge_with_an_integer_output(tmp_path, backend, layout):
    if layout == "cbt" and not common._detect_avx512_available():
        pytest.skip("the cbt layout needs an AVX-512 host")
    data = _run(tmp_path / "run", backend, INT_OUTPUT_GAUGE, layout)
    x = np.arange(64, dtype=np.float64)
    np.testing.assert_array_equal(
        data["s"], np.broadcast_to(0.5 * x + 0.5, data["s"].shape))


def _aos_source(tmp_path, source):
    path = tmp_path / "prog.gelb"
    path.write_text(source)
    out = tmp_path / "prog.cpp"
    result = CliRunner().invoke(
        cli, [str(path), "-o", str(out), "--storage-layout", "aos"])
    assert result.exit_code == 0, result.output
    return out.read_text()


@pytest.mark.parametrize("shape, cpp_type", [
    ("per_cell", "double"), ("real32", "float"),
    ("function_reversed", "double"), ("function_reversed_real32", "float")])
def test_the_integer_elements_are_converted_in_line(tmp_path, shape, cpp_type):
    cpp = _aos_source(tmp_path, _program(shape))
    assert "gelb_dot_prod_const(" not in cpp
    assert re.search(rf"static_cast<{cpp_type}>\(\w+\[0\]\)", cpp)


def test_a_real_array_keeps_the_reduction_helper(tmp_path):
    body = ("    array[real, 3] r = {f.in[x, y | 1], 1.0, 2.0};\n"
            "    f.out[x, y | 0] = dot_prod(W, r);")
    cpp = _aos_source(tmp_path, PROGRAM.format(body=body, functions=""))
    assert "gelb::gelb_dot_prod_const(" in cpp
    assert "static_cast<double>(g_r[" not in cpp
