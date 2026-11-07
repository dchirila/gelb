"""Local arrays of the same name in different blocks keep their own
length and type on every backend.

A local belongs to the block that declares it (user manual, GeLB in
10 minutes: Types).  Two blocks may give a local the same name with a
different length or a different type, and each block computes with its
own declaration: a ``dot_prod`` or a whole-array assignment unrolls
over the length declared in that block, ``matmul`` checks the vector
against that length, and an array ``tmp`` in one dynamic does not turn
a scalar ``tmp`` of another dynamic into an array.  Each case runs two
node classes, one per block, from a position-dependent state, and
expects the closed-form value of each block's own arithmetic on every
backend and Highway layout; the control gives the two blocks' locals
different names and expects the same values, so a backend that confuses
the names fails the case and passes the control.  The order of the
declarations in the file is part of the matrix: on an emitter that
takes another block's length, the long-first order reads past the end
of the shorter array.
"""

import os
import pathlib
import subprocess
import sys

import numpy as np
import pytest

from gelb.backends.highway import common
from gelb.tests.integration._toolchain import (
    requires_compiler, requires_cpp_highway_compiler,
    requires_gpu_cuda_cpp_compiler)

netCDF4 = pytest.importorskip("netCDF4")

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_GELB_RUN = _ROOT / "scripts" / "gelb-run"

NX = 67   # a vector body of eight lanes and a remainder
NY = 8    # rows 0..3 run block A, rows 4..7 block B
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
        return np.asarray(nc.variables["val"][:])   # (time, y, x): t = 0, 1


def _skip_cbt_without_avx512(layout):
    if layout == "cbt" and not common._detect_avx512_available():
        pytest.skip("the cbt layout needs an AVX-512 host")


def _assert_rows(val, expected_a, expected_b):
    """``val`` is (NY, NX); rows 0..3 hold block A's value along x and
    rows 4..7 block B's."""
    assert val.shape == (NY, NX)
    np.testing.assert_array_equal(val[:4], np.broadcast_to(expected_a, (4, NX)))
    np.testing.assert_array_equal(val[4:], np.broadcast_to(expected_b, (4, NX)))


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

_FRAME = """\
simulation_description("{title}");
{constants}
lattices {{
    lattice f(2, 2, real, {{{nx}, {ny}}}, {{false, false}});
}}
initializer Init {{
    f.out[x, y | :] = real(x);
}}
{first}
{second}
gauge Out -> (real val) {{
    val = f.in[x, y | 0];
}}
node_classes {{
    node_class A(Init, DynA, Out);
    node_class B(Init, DynB, Out);
}}
geometry {{
    nodes[:, 0:3] = A;
    nodes[:, 4:7] = B;
}}
"""


def _program(title, block_a, block_b, *, long_first=False, constants=""):
    first, second = (block_b, block_a) if long_first else (block_a, block_b)
    return _FRAME.format(title=title, constants=constants, nx=NX, ny=NY,
                         first=first, second=second)


def _names(shared):
    """The local names of the two blocks: the same, or distinct."""
    return ("v", "w", "v", "w") if shared else ("v2", "w2", "v4", "w4")


# Block A: two-element arrays over x; block B: four-element arrays.
# From f.in = x in every direction, A's dot product is x*x + 1 and B's
# x*x + 3; A's doubled sum 2x + 2 and B's 2x + 6; A's first matmul row
# x + 1 and B's x + 3.
DOT_A = _X * _X + 1.0
DOT_B = _X * _X + 3.0
SUM_A = 2.0 * _X + 2.0
SUM_B = 2.0 * _X + 6.0
ROW_A = _X + 1.0
ROW_B = _X + 3.0


def _dot_blocks(shared):
    va, wa, vb, wb = _names(shared)
    block_a = f"""\
dynamic DynA {{
    array[real, 2] {va} = {{f.in[x, y | 0], 1.0}};
    array[real, 2] {wa} = {{f.in[x, y | 1], 1.0}};
    f.out[x, y | 0] = dot_prod({va}, {wa});
    f.out[x, y | 1] = 0.0;
}}"""
    block_b = f"""\
dynamic DynB {{
    array[real, 4] {vb} = {{f.in[x, y | 0], 1.0, 1.0, 1.0}};
    array[real, 4] {wb} = {{f.in[x, y | 1], 1.0, 1.0, 1.0}};
    f.out[x, y | 0] = dot_prod({vb}, {wb});
    f.out[x, y | 1] = 0.0;
}}"""
    return block_a, block_b


@pytest.mark.parametrize("backend, layout", CONFIGS)
@pytest.mark.parametrize("long_first", [False, True],
                         ids=["short_first", "long_first"])
@pytest.mark.parametrize("shared", [True, False], ids=["same_name", "control"])
def test_dot_prod_uses_the_length_declared_in_its_block(
        tmp_path, backend, layout, long_first, shared):
    """``dot_prod`` of two local arrays unrolls over the length the
    block declares: two terms in DynA, four in DynB, whichever block
    comes first in the file."""
    _skip_cbt_without_avx512(layout)
    block_a, block_b = _dot_blocks(shared)
    source = _program("dot_prod over same-name locals of two lengths",
                      block_a, block_b, long_first=long_first)
    val = _run(tmp_path / "run", backend, source, layout)
    _assert_rows(val[-1], DOT_A, DOT_B)


def _whole_array_blocks(shared):
    va, wa, vb, wb = _names(shared)
    block_a = f"""\
dynamic DynA {{
    array[real, 2] {va} = {{f.in[x, y | 0], 1.0}};
    {va} = {va} * 2.0;
    f.out[x, y | 0] = sum({va});
    f.out[x, y | 1] = 0.0;
}}"""
    block_b = f"""\
dynamic DynB {{
    array[real, 4] {vb} = {{f.in[x, y | 0], 1.0, 1.0, 1.0}};
    {vb} = {vb} * 2.0;
    f.out[x, y | 0] = sum({vb});
    f.out[x, y | 1] = 0.0;
}}"""
    return block_a, block_b


@pytest.mark.parametrize("backend, layout", CONFIGS)
@pytest.mark.parametrize("long_first", [False, True],
                         ids=["short_first", "long_first"])
@pytest.mark.parametrize("shared", [True, False], ids=["same_name", "control"])
def test_whole_array_assignment_covers_the_length_declared_in_its_block(
        tmp_path, backend, layout, long_first, shared):
    """``v = v * 2.0`` doubles every element of the block's own array:
    the sum is 2x + 2 in DynA and 2x + 6 in DynB."""
    _skip_cbt_without_avx512(layout)
    block_a, block_b = _whole_array_blocks(shared)
    source = _program("whole-array assignment to same-name locals",
                      block_a, block_b, long_first=long_first)
    val = _run(tmp_path / "run", backend, source, layout)
    _assert_rows(val[-1], SUM_A, SUM_B)


_MATRICES = """\
global_constants {
    const array[real, {2, 2}] MA = {
        {1.0, 1.0},
        {1.0, 0.0}
    };
    const array[real, {2, 4}] MB = {
        {1.0, 1.0, 1.0, 1.0},
        {1.0, 0.0, 0.0, 0.0}
    };
}"""


def _matmul_blocks(shared):
    va, _, vb, _ = _names(shared)
    block_a = f"""\
dynamic DynA {{
    array[real, 2] {va} = {{f.in[x, y | 0], 1.0}};
    f.out[x, y | :] = matmul(MA, {va});
}}"""
    block_b = f"""\
dynamic DynB {{
    array[real, 4] {vb} = {{f.in[x, y | 0], 1.0, 1.0, 1.0}};
    f.out[x, y | :] = matmul(MB, {vb});
}}"""
    return block_a, block_b


@pytest.mark.parametrize("backend, layout", CONFIGS)
@pytest.mark.parametrize("long_first", [False, True],
                         ids=["short_first", "long_first"])
@pytest.mark.parametrize("shared", [True, False], ids=["same_name", "control"])
def test_matmul_checks_the_vector_against_its_own_block(
        tmp_path, backend, layout, long_first, shared):
    """``matmul(M, v)`` takes the length of the ``v`` declared in the
    block: a 2 x 2 matrix in DynA and a 2 x 4 matrix in DynB both
    compile, and each block's first row is its own dot product."""
    _skip_cbt_without_avx512(layout)
    block_a, block_b = _matmul_blocks(shared)
    source = _program("matmul over same-name locals of two lengths",
                      block_a, block_b, long_first=long_first,
                      constants=_MATRICES)
    val = _run(tmp_path / "run", backend, source, layout)
    _assert_rows(val[-1], ROW_A, ROW_B)


def _matmul_into_array_blocks(shared):
    va, _, vb, _ = _names(shared)
    block_a = f"""\
dynamic DynA {{
    array[real, 2] {va} = {{f.in[x, y | 0], 1.0}};
    array[real, 2] res = matmul(MA, {va});
    f.out[x, y | 0] = res[0];
    f.out[x, y | 1] = res[1];
}}"""
    block_b = f"""\
dynamic DynB {{
    array[real, 4] {vb} = {{f.in[x, y | 0], 1.0, 1.0, 1.0}};
    array[real, 2] res = matmul(MB, {vb});
    f.out[x, y | 0] = res[0];
    f.out[x, y | 1] = res[1];
}}"""
    return block_a, block_b


@pytest.mark.parametrize("backend, layout", CONFIGS)
@pytest.mark.parametrize("long_first", [False, True],
                         ids=["short_first", "long_first"])
@pytest.mark.parametrize("shared", [True, False], ids=["same_name", "control"])
def test_matmul_into_a_declared_array_checks_the_vector_against_its_own_block(
        tmp_path, backend, layout, long_first, shared):
    """``array[real, 2] res = matmul(M, v)``, the declared-array form of
    ``matmul`` (a second emitter path next to the slice store), takes
    the length of the ``v`` declared in the block: the first row is
    x + 1 in DynA and x + 3 in DynB."""
    _skip_cbt_without_avx512(layout)
    block_a, block_b = _matmul_into_array_blocks(shared)
    source = _program("matmul into a declared array over same-name locals",
                      block_a, block_b, long_first=long_first,
                      constants=_MATRICES)
    val = _run(tmp_path / "run", backend, source, layout)
    _assert_rows(val[-1], ROW_A, ROW_B)


_THREE_BLOCKS = """\
simulation_description("the same local names in an initializer, a dynamic and a gauge");
lattices {{
    lattice f(2, 2, real, {{{nx}, {ny}}}, {{false, false}});
}}
initializer Init {{
    array[real, 3] {v3} = {{real(x), 1.0, 1.0}};
    array[real, 3] {w3} = {{1.0, 1.0, 1.0}};
    f.out[x, y | 0] = dot_prod({v3}, {w3});
    f.out[x, y | 1] = 0.0;
}}
dynamic Dyn {{
    array[real, 4] {v4} = {{f.in[x, y | 0], 1.0, 1.0, 1.0}};
    array[real, 4] {w4} = {{1.0, 1.0, 1.0, 1.0}};
    f.out[x, y | 0] = dot_prod({v4}, {w4});
    f.out[x, y | 1] = 0.0;
}}
gauge Out -> (real val) {{
    array[real, 2] {v2} = {{f.in[x, y | 0], 1.0}};
    array[real, 2] {w2} = {{1.0, 1.0}};
    val = dot_prod({v2}, {w2});
}}
node_classes {{
    node_class A(Init, Dyn, Out);
}}
geometry {{
    nodes[:, :] = A;
}}
"""


@pytest.mark.parametrize("backend, layout", CONFIGS)
@pytest.mark.parametrize("shared", [True, False], ids=["same_name", "control"])
def test_every_block_kind_uses_its_own_declaration(
        tmp_path, backend, layout, shared):
    """An initializer, a dynamic and a gauge each declare ``v`` and
    ``w`` with their own lengths (3, 4 and 2) and each takes its own:
    the initializer writes x + 2, the dynamic adds 3, and the gauge
    reads that value plus 1: ``val`` is x + 3 at t = 0 (the gauge's
    first pass, over the initializer's state) and x + 6 after one step,
    on every backend."""
    _skip_cbt_without_avx512(layout)
    names = (dict(v3="v", w3="w", v4="v", w4="w", v2="v", w2="w") if shared
             else dict(v3="v3", w3="w3", v4="v4", w4="w4", v2="v2", w2="w2"))
    source = _THREE_BLOCKS.format(nx=NX, ny=NY, **names)
    val = _run(tmp_path / "run", backend, source, layout)
    assert val.shape[0] == 2
    _assert_rows(val[0], _X + 3.0, _X + 3.0)
    _assert_rows(val[-1], _X + 6.0, _X + 6.0)


def _array_then_scalar_blocks(shared):
    name_a = "tmp"
    name_b = "tmp" if shared else "tmp_s"
    block_a = f"""\
dynamic DynA {{
    array[real, 2] {name_a} = {{f.in[x, y | 0], f.in[x, y | 1]}};
    f.out[x, y | :] = {name_a};
}}"""
    block_b = f"""\
dynamic DynB {{
    real {name_b} = 2.0;
    f.out[x, y | :] = f.in[x, y | :] * {name_b};
}}"""
    return block_a, block_b


@pytest.mark.parametrize("backend, layout", CONFIGS)
@pytest.mark.parametrize("long_first", [False, True],
                         ids=["array_first", "scalar_first"])
@pytest.mark.parametrize("shared", [True, False], ids=["same_name", "control"])
def test_an_array_in_one_block_leaves_a_scalar_of_that_name_alone(
        tmp_path, backend, layout, long_first, shared):
    """A name that is an array in DynA and a scalar in DynB is a scalar
    in DynB: the block builds and multiplies by it, giving 2x, while
    DynA copies its array, giving x."""
    _skip_cbt_without_avx512(layout)
    block_a, block_b = _array_then_scalar_blocks(shared)
    source = _program("an array and a scalar of the same name",
                      block_a, block_b, long_first=long_first)
    val = _run(tmp_path / "run", backend, source, layout)
    _assert_rows(val[-1], _X, 2.0 * _X)
