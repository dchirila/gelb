"""A ``where`` predicate, the constant folder and the same expression at
run time agree on numeric widths and conversions, so a constant's
declared width is never lost between declaration and use: the class map
a constant selects at compile time is the one a gauge computing the same
comparison sees, and a folded constant is the value the run-time
expression gives.  The programs reproduce width losses the compiler once
had; every expectation is independent of the compiler
(binary32 has 24 significand bits, so 16777217 rounds to 16777216; 7 / 2
between reals is 3.5 and between integers, whatever their width, 3).

Fortran only: the cpu_highway backend does not implement the ``real32``
intrinsic (a pre-existing limit, not part of this check).
"""

import os
import pathlib
import shutil
import subprocess
import sys

import numpy as np
import pytest

from gelb.tests.integration._toolchain import HAS_NETCDF_C

netCDF4 = pytest.importorskip("netCDF4")

_REPO = pathlib.Path(__file__).resolve().parents[3]
_GELB_RUN = _REPO / "scripts" / "gelb-run"

_requires_gfortran = pytest.mark.skipif(
    not (shutil.which("gfortran") and HAS_NETCDF_C),
    reason="gfortran or NetCDF-C not found")

_BLOCKS = """
lattices { lattice u(1, 1, real, 4, false); }
initializer I { u.out[x | 0] = 0.0; }
initializer IW { u.out[x | 0] = 1.0; }
dynamic D { u.out[x | 0] = u.in[x | 0]; }
"""
_CLASSES = """
node_classes { node_class B(I, D, G); node_class W(IW, D, G); }
"""

# A real32 constant array element against a real32 conversion.
_TYPED_ARRAY = """simulation_description("predicate precision");
global_constants {
    const array[real32, 2] A = {real32(16777217.0), real32(0.0)};
}
""" + _BLOCKS + """
gauge G -> (real painted, real runtime) {
    painted = u.in[x | 0];
    runtime = real(real(A[0]) == real(real32(x + 16777216)));
}
""" + _CLASSES + """
geometry {
    nodes[:] = B;
    nodes[where real(A[0]) == real(real32(x + 16777216))] = W;
}
"""

# An integer promoted to real32 before a comparison.
_PROMOTED_OPERAND = """simulation_description("folded promotion precision");
""" + _BLOCKS + """
function Same(int a, real32 b) -> (bool hit) { hit = a == b; }
gauge G -> (real painted, real folded, real runtime) {
    painted = u.in[x | 0];
    folded = real(16777217 == real32(16777216));
    runtime = real(Same(16777217, real32(16777216)));
}
""" + _CLASSES + """
geometry { nodes[:] = B; nodes[where 16777217 == real32(16777216)] = W; }
"""

# Integer elements of a real32 array, and a real constant
# written as an integer.
_ARRAY_ELEMENTS = """simulation_description("array element conversion");
global_constants {
    const array[real32, 2] ARR = {16777217, -16777216};
    const real C = sum(ARR);
    const real P = 7;
    const real Q = 2;
    const real F = P / Q;
}
""" + _BLOCKS + """
gauge G -> (real painted, real folded, real runtime, real ratio) {
    painted = u.in[x | 0];
    folded = real(C == 0.0);
    runtime = real(real(ARR[0]) + real(ARR[1]) == 0.0);
    ratio = F;
}
""" + _CLASSES + """
geometry { nodes[:] = B; nodes[where C == 0.0 && F == 3.5] = W; }
"""

# An array constant consumed through arithmetic before a
# reduction keeps its element width.
_ARRAY_ARITHMETIC = """simulation_description("array substitution precision");
global_constants {
    const array[real32, 2] ARR = {16777217.0, 0.0};
    const array[real, 2] WIDE = ARR + {0.0, 0.0};
    const real C = sum(WIDE);
}
""" + _BLOCKS + """
gauge G -> (real painted, real folded, real runtime) {
    painted = u.in[x | 0];
    folded = real(C == 16777216.0);
    runtime = real(real(ARR[0]) + real(ARR[1]) == 16777216.0);
}
""" + _CLASSES + """
geometry { nodes[:] = B; nodes[where C == 16777216.0] = W; }
"""

# Integer division after an integer-width promotion.
_MIXED_INT_DIVISION = """simulation_description("mixed-width integer division");
global_constants {
    const int VALUE = (int8(7) / int16(2)) * int16(2);
}
""" + _BLOCKS + """
function TwiceQuotient(int8 a, int16 b) -> (int v) {
    v = (a / b) * b;
}
gauge G -> (real painted, real folded, real runtime) {
    painted = u.in[x | 0];
    folded = real(VALUE == 6);
    runtime = real(TwiceQuotient(int8(7), int16(2)) == 6);
}
""" + _CLASSES + """
geometry { nodes[:] = B; nodes[where VALUE == 6] = W; }
"""

# An array initialized by an expression is stored at its width,
# and so is one that aliases a wider array.
_DERIVED_ARRAY = """simulation_description("array expression precision");
global_constants {
    const array[real32, 2] ARR = {16777216.0, 0.0} + {1.0, 0.0};
    const array[real, 2] WIDE = ARR + {0.0, 0.0};
    const real C = sum(WIDE);
}
""" + _BLOCKS + """
gauge G -> (real painted, real folded, real runtime) {
    painted = u.in[x | 0];
    folded = real(C == 16777216.0);
    runtime = real(real(ARR[0]) + real(ARR[1]) == 16777216.0);
}
""" + _CLASSES + """
geometry { nodes[:] = B; nodes[where C == 16777216.0] = W; }
"""

_ARRAY_ALIAS = """simulation_description("array alias precision");
global_constants {
    const array[real, 2] BIG = {16777216.0, 0.0} + {1.0, 0.0};
    const array[real32, 2] ARR = BIG;
    const array[real, 2] WIDE = ARR + {0.0, 0.0};
    const real C = sum(WIDE);
}
""" + _BLOCKS + """
gauge G -> (real painted, real folded, real runtime) {
    painted = u.in[x | 0];
    folded = real(C == 16777216.0);
    runtime = real(real(ARR[0]) + real(ARR[1]) == 16777216.0);
}
""" + _CLASSES + """
geometry { nodes[:] = B; nodes[where C == 16777216.0] = W; }
"""

# The slice expansion folds a constant array's elements as the
# array stores them (an integer element of a real32 array).
_SLICE_INTEGER = """simulation_description("slice expansion element width");
global_constants {
    const array[real32, 9] W = {16777217, -16777216, 0, 0, 0, 0, 0, 0, 0};
}
lattices { lattice u(1, 9, real, 4, false); }
initializer I { u.out[x | :] = W * (x + 1.0); }
dynamic D { u.out[x | :] = u.in[x | :]; }
gauge G -> (real expanded, real runtime) {
    expanded = u.in[x | 0];
    runtime = real(W[0]) * (x + 1.0);
}
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""


def _run(tmp_path, source):
    src = tmp_path / "precision.gelb"
    src.write_text(source)
    env = dict(os.environ, GELB_PYTHON=sys.executable)
    result = subprocess.run(
        [str(_GELB_RUN), "-b", "cpu_fortran_serial", "-n", "1", "-w", "1", str(src)],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stdout + result.stderr
    return netCDF4.Dataset(next(tmp_path.glob("*.nc")))


def _values(nc, name, step):
    return np.asarray(nc[name][step]).tolist()


@_requires_gfortran
def test_real32_constant_selects_the_same_cells_at_compile_time_and_at_run_time(tmp_path):
    nc = _run(tmp_path, _TYPED_ARRAY)
    for step in (0, 1):
        assert _values(nc, "painted", step) == [1.0, 1.0, 0.0, 0.0], step
        assert _values(nc, "runtime", step) == [1.0, 1.0, 0.0, 0.0], step


@_requires_gfortran
def test_a_promoted_operand_is_converted_before_the_folded_comparison(tmp_path):
    nc = _run(tmp_path, _PROMOTED_OPERAND)
    for step in (0, 1):
        for name in ("painted", "folded", "runtime"):
            assert _values(nc, name, step) == [1.0] * 4, (name, step)


@_requires_gfortran
def test_array_elements_and_real_constants_take_their_declared_type(tmp_path):
    nc = _run(tmp_path, _ARRAY_ELEMENTS)
    for step in (0, 1):
        for name in ("painted", "folded", "runtime"):
            assert _values(nc, name, step) == [1.0] * 4, (name, step)
        assert _values(nc, "ratio", step) == [3.5] * 4, step


@_requires_gfortran
def test_an_array_constant_keeps_its_element_width_through_arithmetic(tmp_path):
    nc = _run(tmp_path, _ARRAY_ARITHMETIC)
    for step in (0, 1):
        for name in ("painted", "folded", "runtime"):
            assert _values(nc, name, step) == [1.0] * 4, (name, step)


@_requires_gfortran
def test_integer_division_survives_an_integer_width_promotion(tmp_path):
    nc = _run(tmp_path, _MIXED_INT_DIVISION)
    for step in (0, 1):
        for name in ("painted", "folded", "runtime"):
            assert _values(nc, name, step) == [1.0] * 4, (name, step)


@_requires_gfortran
@pytest.mark.parametrize("source", [_DERIVED_ARRAY, _ARRAY_ALIAS],
                         ids=["expression", "alias"])
def test_an_array_initialized_by_an_expression_is_stored_at_its_width(tmp_path, source):
    nc = _run(tmp_path, source)
    for step in (0, 1):
        for name in ("painted", "folded", "runtime"):
            assert _values(nc, name, step) == [1.0] * 4, (name, step)


@_requires_gfortran
def test_slice_expansion_folds_array_elements_as_stored(tmp_path):
    nc = _run(tmp_path, _SLICE_INTEGER)
    expected = [16777216.0 * (x + 1) for x in range(4)]
    for step in (0, 1):
        assert _values(nc, "expanded", step) == expected, step
        assert _values(nc, "runtime", step) == expected, step
