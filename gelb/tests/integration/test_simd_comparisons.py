"""Comparisons in the Highway vector body: ``!=`` with a NaN, and
``==`` / ``!=`` between per-cell bools.

A comparison is one of the IEEE basic operations, defined exactly on
every backend (user manual, Numerical semantics: What must agree), so
``v != v`` is true and ``v == v`` false exactly where ``v`` is a NaN,
on the scalar paths and in the vector body alike.  Two ``bool`` values
compare with ``==`` and ``!=`` only (Types and promotion), and a
per-cell ``bool`` in the vector body, a mask, compares like one on the
scalar paths, also against a uniform ``bool`` (a local, or ``t > 0``
written inline) and under ``!`` and ``&&``.  Every backend and layout,
Fortran among them, is checked against the closed form of the
program, exactly.  The checks on the generated code pin the emitter's
spelling, an implementation choice the manual does not define: the
unordered ``hn::Not(hn::Eq(..))`` for ``!=`` on vectors (Highway's
``hn::Ne`` is the ordered comparison with AVX2 or AVX-512, false for a
NaN lane), ``hn::Xor`` for ``!=`` on masks, with an inline uniform
operand broadcast inside the comparison.
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

NX = 67   # a vector body of eight lanes and a remainder
NY = 4
_X = np.arange(NX, dtype=np.float64)


def _run(directory, backend, source, layout=None):
    directory.mkdir()
    path = directory / "probe.gelb"
    path.write_text(source)
    env = dict(os.environ, GELB_PYTHON=sys.executable)
    if layout is not None:
        env["GELBC_EXTRA"] = f"--storage-layout {layout}"
    result = subprocess.run(
        [str(_GELB_RUN), "-b", backend, "-n", "1", "-w", "1", str(path)],
        cwd=directory, env=env, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stdout + result.stderr
    with netCDF4.Dataset(next(directory.glob("*.nc"))) as nc:
        return {name: np.asarray(var[:]) for name, var in nc.variables.items()
                if name not in ("x", "y", "time")}


def _source(tmp_path, source, layout="soa"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "prog.gelb"
    path.write_text(source)
    out = tmp_path / "prog.cpp"
    result = CliRunner().invoke(
        cli, [str(path), "-o", str(out), "-b", "cpu_highway",
              "--storage-layout", layout])
    assert result.exit_code == 0, result.output
    return out.read_text()


def _skip_cbt_without_avx512(layout):
    if layout == "cbt" and not common._detect_avx512_available():
        pytest.skip("the cbt layout needs an AVX-512 host")


def _assert_field(data, name, expected):
    """The field ``name`` at the last step equals ``expected`` along x
    in every row."""
    field = data[name][-1]
    assert field.shape == (NY, NX)
    np.testing.assert_array_equal(
        field, np.broadcast_to(np.asarray(expected, dtype=np.float64),
                               field.shape))


CONFIGS = [
    pytest.param("cpu_fortran_serial", None, marks=requires_compiler,
                 id="fortran"),
    *(pytest.param("cpu_highway", layout, marks=requires_cpp_highway_compiler,
                   id=f"highway-{layout}")
      for layout in ("soa", "aos", "cbt")),
    pytest.param("gpu_cuda_cpp", None,
                 marks=[pytest.mark.gpu, requires_gpu_cuda_cpp_compiler],
                 id="cuda"),
]

# ``sqrt(real(x) - 31.5)`` is a NaN for x < 32 and a positive real from
# x = 32 on; the control subtracts without the square root.
_NAN_PROGRAMS = {
    "initializer": """\
simulation_description("!= and == with a run-time NaN, in an initializer");
lattices {{ lattice f(2, 2, real, {{{nx}, {ny}}}, {{false, false}}); }}
initializer Init {{
    real v = {value};
    f.out[x, y | 0] = real(v != v);
    f.out[x, y | 1] = real(v == v);
}}
dynamic Dyn {{ f.out[x, y | :] = f.in[x, y | :]; }}
gauge G -> (real ne, real eq) {{ ne = f.in[x, y | 0]; eq = f.in[x, y | 1]; }}
node_classes {{ node_class A(Init, Dyn, G); }}
geometry {{ nodes[:, :] = A; }}
""",
    "dynamic": """\
simulation_description("!= and == with a run-time NaN, in a dynamic");
lattices {{ lattice f(2, 2, real, {{{nx}, {ny}}}, {{false, false}}); }}
initializer Init {{ f.out[x, y | :] = {value}; }}
dynamic Dyn {{
    real v = f.in[x, y | 0];
    f.out[x, y | 0] = real(v != v);
    f.out[x, y | 1] = real(v == v);
}}
gauge G -> (real ne, real eq) {{ ne = f.in[x, y | 0]; eq = f.in[x, y | 1]; }}
node_classes {{ node_class A(Init, Dyn, G); }}
geometry {{ nodes[:, :] = A; }}
""",
    "gauge": """\
simulation_description("!= and == with a run-time NaN, in a gauge");
lattices {{ lattice f(2, 2, real, {{{nx}, {ny}}}, {{false, false}}); }}
initializer Init {{ f.out[x, y | :] = {value}; }}
dynamic Dyn {{ f.out[x, y | :] = f.in[x, y | :]; }}
gauge G -> (real ne, real eq) {{
    real v = f.in[x, y | 0];
    ne = real(v != v);
    eq = real(v == v);
}}
node_classes {{ node_class A(Init, Dyn, G); }}
geometry {{ nodes[:, :] = A; }}
""",
}

_NAN_VALUE = "sqrt(real(x) - 31.5)"
_FINITE_VALUE = "real(x) - 31.5"
IS_NAN = (_X < 32).astype(np.float64)


def _nan_program(block, with_nan):
    return _NAN_PROGRAMS[block].format(
        nx=NX, ny=NY, value=_NAN_VALUE if with_nan else _FINITE_VALUE)


@pytest.mark.parametrize("backend, layout", CONFIGS)
@pytest.mark.parametrize("block", ["initializer", "dynamic", "gauge"])
@pytest.mark.parametrize("with_nan", [True, False], ids=["nan", "control"])
def test_not_equal_is_true_for_a_nan(tmp_path, backend, layout, block,
                                     with_nan):
    """``v != v`` is 1 and ``v == v`` is 0 exactly in the cells where
    ``v`` is a NaN, whichever block computes it; the control without a
    NaN gives 0 and 1 everywhere."""
    _skip_cbt_without_avx512(layout)
    data = _run(tmp_path / "run", backend, _nan_program(block, with_nan),
                layout)
    expected = IS_NAN if with_nan else np.zeros(NX)
    _assert_field(data, "ne", expected)
    _assert_field(data, "eq", 1.0 - expected)


def test_not_equal_on_vectors_is_spelled_unordered(tmp_path):
    """The vector body spells ``!=`` as ``hn::Not(hn::Eq(..))`` and
    never ``hn::Ne``, the ordered comparison with AVX2 or AVX-512."""
    cpp = _source(tmp_path, _nan_program("dynamic", True))
    assert "hn::Not(hn::Eq(" in cpp
    assert "hn::Ne(" not in cpp


# Per-cell bools from f = x - 31.5: a is true from x = 32, b from x = 33,
# so a != b only at x = 32; c = (t > 0) is a uniform bool, true after
# the first step.
_BOOL_PROGRAM = """\
simulation_description("== and != between per-cell bools in the vector body");
lattices {{ lattice f(2, 2, real, {{{nx}, {ny}}}, {{false, false}}); }}
initializer Init {{ f.out[x, y | :] = real(x) - 31.5; }}
dynamic Dyn {{ f.out[x, y | :] = f.in[x, y | :]; }}
gauge G -> (real ne, real eq, real mixed, real notted, real anded,
            real inline_left, real inline_right) {{
    bool a = f.in[x, y | 0] > 0.0;
    bool b = f.in[x, y | 0] > 1.0;
    bool c = t > 0;
    ne = real(a != b);
    eq = real(a == b);
    mixed = real(c != b);
    notted = real(!(a == b));
    anded = real((a != b) && c);
    inline_left = real((t > 0) != b);     // a uniform bool operand, not a local
    inline_right = real(b == (t > 0));
}}
node_classes {{ node_class A(Init, Dyn, G); }}
geometry {{ nodes[:, :] = A; }}
"""

A = (_X > 31.5).astype(np.float64)
B = (_X > 32.5).astype(np.float64)


@pytest.mark.parametrize("backend, layout", CONFIGS)
def test_bool_locals_compare_with_equal_and_not_equal(tmp_path, backend,
                                                      layout):
    """``a != b`` and ``a == b`` between two per-cell bools build and
    give the scalar paths' values in the vector body, also against a
    uniform bool (a local, and ``t > 0`` written inline on either
    side), under ``!`` and inside ``&&``."""
    _skip_cbt_without_avx512(layout)
    data = _run(tmp_path / "run", backend, _BOOL_PROGRAM.format(nx=NX, ny=NY),
                layout)
    ne = np.abs(A - B)
    _assert_field(data, "ne", ne)
    _assert_field(data, "eq", 1.0 - ne)
    _assert_field(data, "mixed", 1.0 - B)        # c is true after step 1
    _assert_field(data, "notted", ne)
    _assert_field(data, "anded", ne)
    _assert_field(data, "inline_left", 1.0 - B)   # true != b
    _assert_field(data, "inline_right", B)        # b == true


def test_bool_comparisons_are_spelled_with_xor(tmp_path):
    """The vector body spells ``!=`` on masks as ``hn::Xor`` and ``==``
    as ``hn::Not(hn::Xor(..))``; an inline uniform bool operand is
    broadcast with ``hn::FirstN`` inside the comparison, on either
    side."""
    cpp = _source(tmp_path, _BOOL_PROGRAM.format(nx=NX, ny=NY))
    assert "hn::Not(hn::Xor(" in cpp
    assert "hn::Xor(" in cpp
    assert "hn::Xor(hn::FirstN(d, (" in cpp                    # (t > 0) != b
    assert re.search(r"hn::Not\(hn::Xor\(\w+, hn::FirstN\(d, \(", cpp)   # b == (t > 0)
