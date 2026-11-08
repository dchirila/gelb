"""Constant arrays and constant-coefficient ``dot_prod`` on every
backend: exact values, the result's type, one negation.

A constant array's elements are the values its declared width stores,
in every reading (user manual, Numerical semantics: Constant
folding): an ``int`` array holds an integer above 2^53 exactly,
whether it is stored directly or passed through a function, and an
element written into an expression carries its 64-bit width.  A
``dot_prod`` with an integer result is computed in that result's type:
each element and each coefficient converts to it first, and the
products and sums are exact integer operations, never a fused
multiply-add (Build modes), so an int8 array under int64
coefficients does not wrap, int64 coefficients above 2^53 keep their
low bits, and a reduction of five or more terms is exact in a default
build as in a strict one.  A ``dot_prod`` whose coefficients are all -1
builds in the Highway vector body, and negates there as the scalar
paths do, keeping the sign of a zero (Special values).  Fortran is the
reference, bit for bit, except for the sign of a zero that a reduction
produces: Fortran's ``dot_product`` starts from +0, so it gives +0
where the C++ and CUDA paths, which negate the first term, give -0;
chapter 19 promises no bound across backends for a reduction, and the
test pins that those paths agree with each other today.  The checks
on the generated code pin the emitter's spelling, an implementation
choice the manual does not define.
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
_X = np.arange(NX, dtype=np.int64)
TWO53 = 2 ** 53


def _run(directory, backend, source, layout=None, defines=(), strict=False):
    directory.mkdir()
    path = directory / "probe.gelb"
    path.write_text(source)
    env = dict(os.environ, GELB_PYTHON=sys.executable)
    if layout is not None:
        env["GELBC_EXTRA"] = f"--storage-layout {layout}"
    flags = ["--strict-fp"] if strict else []
    for define in defines:
        flags += ["-D", define]
    result = subprocess.run(
        [str(_GELB_RUN), "-b", backend, *flags, "-n", "1", "-w", "1",
         str(path)],
        cwd=directory, env=env, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stdout + result.stderr
    with netCDF4.Dataset(next(directory.glob("*.nc"))) as nc:
        return {name: np.asarray(var[:]) for name, var in nc.variables.items()}


def _source(tmp_path, source, backend, layout=None, defines=()):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "prog.gelb"
    path.write_text(source)
    out = tmp_path / ("prog.cu" if backend == "gpu_cuda_cpp" else "prog.cpp")
    args = [str(path), "-o", str(out), "-b", backend]
    if layout is not None:
        args += ["--storage-layout", layout]
    for define in defines:
        args += ["-D", define]
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    return out.read_text()


def _skip_cbt_without_avx512(layout):
    if layout == "cbt" and not common._detect_avx512_available():
        pytest.skip("the cbt layout needs an AVX-512 host")


def _assert_last_step(data, name, expected):
    """The gauge field ``name`` at the last step is ``expected`` along x
    in every row (a scalar or an array of NX values)."""
    field = data[name][-1]
    assert field.shape[-1] == NX
    np.testing.assert_array_equal(
        field, np.broadcast_to(np.asarray(expected), field.shape))


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

# The C++ and CUDA paths: the Highway vector body (soa, cbt), its
# scalar path (aos) and the CUDA kernels.
CPP_CONFIGS = [c for c in CONFIGS if c.id != "fortran"]


# ----------------------------------------------------------------------
# All -1 coefficients with a per-cell real array (the vector body)
# ----------------------------------------------------------------------

# ``S`` is set with -D: -1 gives coefficients that are all -1, +1 the
# control.  The dot product is taken where ``where`` says; the other
# blocks pass the values on.
NEG_UNIT = """
simulation_description("dot_prod with coefficients that are all S");
global_constants {{
    const real S = 1.0;
    const array[real, 3] C = S * {{1.0, 1.0, 1.0}};
    const array[real, 3] V0 = {{-0.25, -0.5, -0.75}};
}}
lattices {{ lattice f({d}, 3, real, {grid}, {periodic}); }}
initializer Init {{
    array[real, 3] v = V0;
    {init}
}}
dynamic Step {{
    array[real, 3] v = f.in[{coords} | :];
    {step}
}}
gauge G -> (real a) {{
    array[real, 3] v = f.in[{coords} | :];
    {gauge}
}}
node_classes {{ node_class BULK(Init, Step, G); }}
geometry {{ nodes[{all}] = BULK; }}
"""

_PASS_ON = "f.out[{coords} | :] = v;"
_TAKE = ("f.out[{coords} | 0] = dot_prod(C, v); "
         "f.out[{coords} | 1] = v[1]; f.out[{coords} | 2] = v[2];")
_WHERE = {
    "initializer": (_TAKE, _PASS_ON, "a = v[0];"),
    "dynamic": (_PASS_ON, _TAKE, "a = v[0];"),
    "gauge": (_PASS_ON, _PASS_ON, "a = dot_prod(C, v);"),
}
_DIMS = {
    2: dict(d=2, grid=f"{{{NX}, 4}}", periodic="{true, true}",
            coords="x, y", all=":, :"),
    3: dict(d=3, grid=f"{{{NX}, 4, 3}}", periodic="{true, true, true}",
            coords="x, y, z", all=":, :, :"),
}


def _neg_unit_program(where, dims):
    init, step, gauge = _WHERE[where]
    fields = dict(_DIMS[dims])
    coords = fields["coords"]
    return NEG_UNIT.format(init=init.format(coords=coords),
                           step=step.format(coords=coords),
                           gauge=gauge.format(coords=coords), **fields)


@pytest.mark.parametrize("backend, layout", CONFIGS)
@pytest.mark.parametrize("dims", [2, 3])
@pytest.mark.parametrize("where", sorted(_WHERE))
@pytest.mark.parametrize("sign, expected", [("-1.0", 1.5), ("1.0", -1.5)],
                         ids=["all_minus_one", "all_plus_one"])
def test_unit_coefficients_of_one_sign(tmp_path, backend, layout, dims,
                                       where, sign, expected):
    """A ``dot_prod`` whose constant coefficients are all -1 builds in
    the Highway vector body and gives the negated sum there as on every
    other path (user manual, Numerical semantics: Build modes); all +1
    is the control."""
    _skip_cbt_without_avx512(layout)
    data = _run(tmp_path / "run", backend, _neg_unit_program(where, dims),
                layout, defines=(f"S={sign}",))
    _assert_last_step(data, "a", expected)


@pytest.mark.parametrize("backend, layout", CPP_CONFIGS)
@pytest.mark.parametrize("where", sorted(_WHERE))
def test_negating_a_zero_keeps_its_sign_on_every_cpp_path(tmp_path, backend,
                                                          layout, where):
    """The C++ and CUDA paths negate the first term: for an array of
    +0 and coefficients of -1 they give -0, the vector body as the
    scalar paths (Fortran's ``dot_product`` gives +0, see the module
    docstring)."""
    _skip_cbt_without_avx512(layout)
    source = _neg_unit_program(where, 2).replace(
        "{-0.25, -0.5, -0.75}", "{0.0, 0.0, 0.0}")
    data = _run(tmp_path / "run", backend, source, layout,
                defines=("S=-1.0",))
    a = data["a"][-1]
    assert np.all(a == 0.0) and np.all(np.signbit(a))


# ----------------------------------------------------------------------
# Integer constant arrays through a function
# ----------------------------------------------------------------------

INT64_MAX = 2 ** 63 - 1
INT64_MIN = -2 ** 63

# A through an identity function and B negated by one, both returning
# arrays stored to a whole slice (the reading that loses the low bit);
# as controls, A stored directly, B's second element read by a constant
# index inside a function, and A as the coefficients of a dot product
# (its minimum is then spelled inside a constexpr array, which nvcc
# checks for narrowing).
INT_ARRAY = f"""
simulation_description("int64 constant arrays above 2^53 through functions");
global_constants {{
    const int K = {TWO53 + 1};
    const array[int, 4] A = {{2, K, {INT64_MAX}, {INT64_MIN + 1} - 1}};
    const array[int, 2] B = {{2, K}};
}}
lattices {{
    lattice f(2, 4, int, {{{NX}, 4}}, {{true, true}});
    lattice g(2, 2, int, {{{NX}, 4}}, {{true, true}});
    lattice h(2, 4, int, {{{NX}, 4}}, {{true, true}});
}}
function Id(array[int, 4] a) -> (array[int, 4] b) {{ b = a; }}
function Neg(array[int, 2] a) -> (array[int, 2] b) {{ b = -a; }}
function Second(array[int, 2] a) -> (int s) {{ s = a[1]; }}
initializer Init {{
    f.out[x, y | :] = Id(A);
    g.out[x, y | :] = Neg(B);
    h.out[x, y | :] = A;
}}
dynamic Step {{
    f.out[x, y | :] = f.in[x, y | :];
    g.out[x, y | :] = g.in[x, y | :];
    h.out[x, y | :] = h.in[x, y | :];
}}
gauge G -> (int id1, int id2, int id3, int neg1, int direct1, int second, int dp) {{
    id1 = f.in[x, y | 1] - {TWO53};
    id2 = f.in[x, y | 2];
    id3 = f.in[x, y | 3];
    neg1 = g.in[x, y | 1] + {TWO53};
    direct1 = h.in[x, y | 1] - {TWO53};
    second = Second(B) - {TWO53};
    array[int, 4] k = {{x, 0, 0, 0}};
    dp = dot_prod(A, k);
}}
node_classes {{ node_class BULK(Init, Step, G); }}
geometry {{ nodes[:, :] = BULK; }}
"""


@pytest.mark.parametrize("backend, layout", CONFIGS)
def test_an_int64_constant_array_keeps_its_values(tmp_path, backend, layout):
    """An ``int`` constant array's elements above 2^53 are exact whether
    the array is stored directly or passed through a function (user
    manual, Numerical semantics: Constant folding)."""
    _skip_cbt_without_avx512(layout)
    data = _run(tmp_path / "run", backend, INT_ARRAY, layout)
    for name, expected in [("id1", 1), ("id2", INT64_MAX), ("id3", INT64_MIN),
                           ("neg1", -1), ("direct1", 1), ("second", 1)]:
        _assert_last_step(data, name, np.int64(expected))
    _assert_last_step(data, "dp", 2 * _X)


# Narrow integer arrays at their extremes, each through an identity
# function; the lattices hold the width.
NARROW_ARRAY = f"""
simulation_description("narrow integer constant arrays through functions");
global_constants {{
    const array[int32, 2] A32 = {{2147483647, -2147483647 - 1}};
    const array[int16, 2] A16 = {{32767, -32768}};
    const array[int8, 2] A8 = {{127, -128}};
}}
lattices {{
    lattice f(2, 2, int32, {{{NX}, 4}}, {{true, true}});
    lattice g(2, 2, int16, {{{NX}, 4}}, {{true, true}});
    lattice h(2, 2, int8, {{{NX}, 4}}, {{true, true}});
}}
function Id32(array[int32, 2] a) -> (array[int32, 2] b) {{ b = a; }}
function Id16(array[int16, 2] a) -> (array[int16, 2] b) {{ b = a; }}
function Id8(array[int8, 2] a) -> (array[int8, 2] b) {{ b = a; }}
initializer Init {{
    f.out[x, y | :] = Id32(A32);
    g.out[x, y | :] = Id16(A16);
    h.out[x, y | :] = Id8(A8);
}}
dynamic Step {{
    f.out[x, y | :] = f.in[x, y | :];
    g.out[x, y | :] = g.in[x, y | :];
    h.out[x, y | :] = h.in[x, y | :];
}}
gauge G -> (int hi32, int lo32, int hi16, int lo16, int hi8, int lo8) {{
    hi32 = int(f.in[x, y | 0]); lo32 = int(f.in[x, y | 1]);
    hi16 = int(g.in[x, y | 0]); lo16 = int(g.in[x, y | 1]);
    hi8 = int(h.in[x, y | 0]); lo8 = int(h.in[x, y | 1]);
}}
node_classes {{ node_class BULK(Init, Step, G); }}
geometry {{ nodes[:, :] = BULK; }}
"""


@pytest.mark.parametrize("backend, layout", CONFIGS)
def test_a_narrow_integer_constant_array_keeps_its_values(tmp_path, backend,
                                                          layout):
    """A control: a narrow array's extremes are exact in binary64, so
    they were right before as well."""
    _skip_cbt_without_avx512(layout)
    data = _run(tmp_path / "run", backend, NARROW_ARRAY, layout)
    for name, expected in [("hi32", 2 ** 31 - 1), ("lo32", -2 ** 31),
                           ("hi16", 2 ** 15 - 1), ("lo16", -2 ** 15),
                           ("hi8", 127), ("lo8", -128)]:
        _assert_last_step(data, name, np.int64(expected))


# ----------------------------------------------------------------------
# Integer dot products, computed in the result's type
# ----------------------------------------------------------------------

# ``K0`` is 2^53 + 1, or 2^53 for the control (set with -D).  ``r`` is
# the dot product with a per-cell array, ``rf`` the one of two constant
# arrays through a function.
INT64_COEFF = f"""
simulation_description("int64 coefficients above 2^53 with an integer result");
global_constants {{
    const int K0 = {TWO53 + 1};
    const array[int, 2] KB = {{K0, 3}};
    const array[int, 2] ONE0 = {{1, 0}};
}}
lattices {{ lattice f(2, 2, int, {{{NX}, 4}}, {{true, true}}); }}
function Dot(array[int, 2] c, array[int, 2] v) -> (int r) {{ r = dot_prod(c, v); }}
initializer Init {{ f.out[x, y | :] = {{1, x}}; }}
dynamic Step {{ f.out[x, y | :] = f.in[x, y | :]; }}
gauge G -> (int r, int rf) {{
    array[int, 2] k = f.in[x, y | :];
    r = dot_prod(KB, k) - {TWO53};
    rf = Dot(KB, ONE0) - {TWO53};
}}
node_classes {{ node_class BULK(Init, Step, G); }}
geometry {{ nodes[:, :] = BULK; }}
"""


@pytest.mark.parametrize("backend, layout", CONFIGS)
@pytest.mark.parametrize("k0, low_bit", [(TWO53 + 1, 1), (TWO53, 0)],
                         ids=["above_2_53", "control_2_53"])
def test_int64_coefficients_keep_their_low_bit(tmp_path, backend, layout,
                                               k0, low_bit):
    """``int`` coefficients above 2^53 keep their low bit in a
    ``dot_prod`` with an integer result (user manual, Numerical
    semantics: Types and promotion); ``K0`` = 2^53 is the control."""
    _skip_cbt_without_avx512(layout)
    data = _run(tmp_path / "run", backend, INT64_COEFF, layout,
                defines=(f"K0={k0}",))
    _assert_last_step(data, "r", low_bit + 3 * _X)
    _assert_last_step(data, "rf", np.int64(low_bit))


# int64 coefficients with narrow arrays (``k8`` through the general
# helper, ``pm`` through the signed sum, ``u32`` with coefficients that
# are all +1, ``mixed`` with one per-cell int64 array), and two per-cell
# narrow arrays, whose product has their own type: ``both`` of two
# int32 arrays, ``n8`` of two int8 arrays, and ``w8`` the same int8
# product read as a real.  The control declares every array as ``int``.
NARROW_DOT = """
simulation_description("int64 coefficients with narrow integer arrays");
global_constants {{
    const array[int, 3] K = {{100, 100, 1}};
    const array[int, 3] PM = {{1, 1, -1}};
    const array[int, 2] ONES = {{1, 1}};
}}
lattices {{ lattice f(2, 1, int, {{{nx}, 4}}, {{true, true}}); }}
initializer Init {{ f.out[x, y | 0] = x; }}
dynamic Step {{ f.out[x, y | 0] = f.in[x, y | 0]; }}
gauge G -> (int k8, int pm, int u32, int mixed, int both, int n8, real w8) {{
    array[{t8}, 3] a8 = {{{t8}(100), {t8}(100), {t8}(f.in[x, y | 0])}};
    k8 = dot_prod(K, a8);
    pm = dot_prod(PM, a8);
    array[{t32}, 2] a32 = {{{t32}(2147483647), {t32}(1)}};
    u32 = dot_prod(ONES, a32);
    array[int, 2] b64 = {{2, f.in[x, y | 0]}};
    mixed = dot_prod(a32, b64);
    array[{t32}, 2] b32 = {{{t32}(2), {t32}(1)}};
    both = dot_prod(a32, b32);
    array[{t8}, 3] c8 = {{{t8}(100), {t8}(1), {t8}(1)}};
    n8 = dot_prod(a8, c8);
    w8 = real(dot_prod(a8, c8));
}}
node_classes {{ node_class BULK(Init, Step, G); }}
geometry {{ nodes[:, :] = BULK; }}
"""


def _wrap_int8(values):
    """The values an int8 holds, as int64."""
    return ((np.asarray(values, dtype=np.int64) + 128) % 256 - 128)


@pytest.mark.parametrize("backend, layout", CONFIGS)
@pytest.mark.parametrize("t8, t32", [("int8", "int32"), ("int", "int")],
                         ids=["narrow", "control_int64"])
def test_narrow_arrays_under_int64_coefficients(tmp_path, backend, layout,
                                                t8, t32):
    """A dot product's result has the common type of its arrays (user
    manual, Numerical semantics: Types and promotion): ``K . a8`` is
    int64, so the products of 100 do not wrap at 127.  ``both``, ``n8``
    and ``w8`` run past their own width, int32 and int8, which the
    manual leaves undefined (an integer overflow at run time); they pin
    the agreement of the C++ and CUDA paths with the Fortran reference,
    which wraps with the gfortran build ``gelb-run`` makes (the standard
    leaves the overflow undefined): an integer path narrows its sum to the
    result's type, and never widens it into a real, or leaves it in
    C++'s ``int``, on the way."""
    _skip_cbt_without_avx512(layout)
    narrow = t8 == "int8"
    source = NARROW_DOT.format(nx=NX, t8=t8, t32=t32)
    data = _run(tmp_path / "run", backend, source, layout)
    _assert_last_step(data, "k8", 20000 + _X)
    _assert_last_step(data, "pm", 200 - _X)
    _assert_last_step(data, "u32", np.int64(2 ** 31))
    _assert_last_step(data, "mixed", 2 * 2147483647 + _X)
    _assert_last_step(data, "both", np.int64(-1 if narrow else 2 ** 32 - 1))
    n8 = _wrap_int8(10100 + _X) if narrow else 10100 + _X
    _assert_last_step(data, "n8", n8)
    _assert_last_step(data, "w8", n8.astype(np.float64))


# Five terms: from the fifth, the helper accumulates with its
# multiply-add.  ``BIG`` makes the product exceed 2^53 (3 for the
# control).
INT_FMA = f"""
simulation_description("an integer dot_prod of five terms with a product above 2^53");
global_constants {{
    const int BIG = 3002399751580331;
    const array[int, 5] K = {{1, 1, 1, 1, 3}};
}}
lattices {{ lattice f(2, 5, int, {{{NX}, 4}}, {{true, true}}); }}
initializer Init {{ f.out[x, y | :] = {{0, 0, 0, 0, BIG}}; }}
dynamic Step {{ f.out[x, y | :] = f.in[x, y | :]; }}
gauge G -> (int r) {{ array[int, 5] k = f.in[x, y | :]; r = dot_prod(K, k) - {TWO53}; }}
node_classes {{ node_class BULK(Init, Step, G); }}
geometry {{ nodes[:, :] = BULK; }}
"""


@pytest.mark.parametrize("backend, layout", CONFIGS)
@pytest.mark.parametrize("strict", [False, True], ids=["default", "strict"])
@pytest.mark.parametrize("big, expected", [(3002399751580331, 1),
                                           (3, 9 - TWO53)],
                         ids=["above_2_53", "control"])
def test_five_terms_are_exact_in_a_default_build(tmp_path, backend, layout,
                                                 strict, big, expected):
    """An integer ``dot_prod`` is exact in a default build as in a strict
    one: no fused multiply-add enters it (user manual, Numerical
    semantics: Build modes)."""
    _skip_cbt_without_avx512(layout)
    data = _run(tmp_path / "run", backend, INT_FMA, layout,
                defines=(f"BIG={big}",), strict=strict)
    _assert_last_step(data, "r", np.int64(expected))


# ----------------------------------------------------------------------
# A constant element in arithmetic: the width it carries
# ----------------------------------------------------------------------

# ``A`` is doubled inside a function, element by element, and ``M``
# multiplies an int32 vector: both unroll to the folded elements, which
# enter the arithmetic as int64 values.  ``K`` is set with -D:
# 2147483647 doubles to a value that fits an int64 and not a C++
# ``int``, 100 is the control.
WIDTH_SCALE = f"""
simulation_description("a constant int array doubled in a function");
global_constants {{ const int K = 2147483647; const array[int, 2] A = {{K, 3}}; }}
lattices {{ lattice f(2, 2, int, {{{NX}, 4}}, {{true, true}}); }}
function Scale(array[int, 2] a) -> (array[int, 2] b) {{ b = a * 2; }}
initializer Init {{ f.out[x, y | :] = Scale(A); }}
dynamic Step {{ f.out[x, y | :] = f.in[x, y | :]; }}
gauge G -> (int a, int b) {{ a = f.in[x, y | 0]; b = f.in[x, y | 1]; }}
node_classes {{ node_class BULK(Init, Step, G); }}
geometry {{ nodes[:, :] = BULK; }}
"""

WIDTH_MATMUL = f"""
simulation_description("a constant int matrix times an int32 vector");
global_constants {{
    const int K = 2147483647;
    const array[int, {{2, 2}}] M = {{{{K, 0}}, {{0, 1}}}};
}}
lattices {{ lattice f(2, 2, int, {{{NX}, 4}}, {{true, true}}); }}
initializer Init {{
    array[int32, 2] v = {{int32(2), int32(x)}};
    array[int, 2] w = matmul(M, v);
    f.out[x, y | :] = w;
}}
dynamic Step {{ f.out[x, y | :] = f.in[x, y | :]; }}
gauge G -> (int a, int b) {{ a = f.in[x, y | 0]; b = f.in[x, y | 1]; }}
node_classes {{ node_class BULK(Init, Step, G); }}
geometry {{ nodes[:, :] = BULK; }}
"""


@pytest.mark.parametrize("backend, layout", CONFIGS)
@pytest.mark.parametrize("program, second",
                         [(WIDTH_SCALE, 6), (WIDTH_MATMUL, _X)],
                         ids=["scale", "matmul"])
@pytest.mark.parametrize("k", [2147483647, 100], ids=["int32_max", "control"])
def test_a_constant_element_keeps_its_width_in_arithmetic(
        tmp_path, backend, layout, program, second, k):
    """An ``int`` is 64 bits wide (user manual, Numerical semantics:
    Types and promotion), so a constant element that a backend writes
    into an expression carries that width: ``2147483647 * 2`` is
    4294967294 on every backend, in a function and in ``matmul``."""
    _skip_cbt_without_avx512(layout)
    data = _run(tmp_path / "run", backend, program, layout,
                defines=(f"K={k}",))
    _assert_last_step(data, "a", np.int64(2 * k))
    _assert_last_step(data, "b", second)


# ----------------------------------------------------------------------
# The folding peepholes on the suffixed literals
# ----------------------------------------------------------------------

# ``U * A`` is unrolled element by element on the suffixed literals,
# where the x1, x-1 and x0 peepholes fire; ``E * vv`` applies them to a
# per-cell array.
PEEP = f"""
simulation_description("the peepholes on suffixed integer literals");
global_constants {{
    const array[int, 4] U = {{1, -1, 0, 2}};
    const array[int, 4] A = {{7, -3, 9, 5}};
    const array[int, 3] E = {{0, 1, -1}};
}}
lattices {{ lattice f(2, 3, int, {{{NX}, 4}}, {{true, true}}); }}
initializer Init {{ f.out[x, y | :] = {{x, x, x}}; }}
dynamic Step {{ f.out[x, y | :] = f.in[x, y | :]; }}
gauge G -> (int w0, int w1, int w2, int w3, int m0, int m1, int m2) {{
    array[int, 4] w = U * A;
    array[int, 3] vv = f.in[x, y | :];
    array[int, 3] m = E * vv;
    w0 = w[0]; w1 = w[1]; w2 = w[2]; w3 = w[3];
    m0 = m[0]; m1 = m[1]; m2 = m[2];
}}
node_classes {{ node_class BULK(Init, Step, G); }}
geometry {{ nodes[:, :] = BULK; }}
"""


@pytest.mark.parametrize("backend, layout", CONFIGS)
def test_the_peepholes_give_the_unfolded_values(tmp_path, backend, layout):
    """Multiplying by a constant 1, -1 or 0 gives the product (user
    manual, Numerical semantics: Constant folding), whether the emitter
    folds it away or writes it out."""
    _skip_cbt_without_avx512(layout)
    data = _run(tmp_path / "run", backend, PEEP, layout)
    for name, expected in (("w0", 7), ("w1", 3), ("w2", 0), ("w3", 10),
                           ("m0", 0), ("m1", _X), ("m2", -_X)):
        _assert_last_step(data, name, expected)


def test_the_peepholes_fire_on_the_suffixed_literals(tmp_path):
    """A spelling check: the x1, x-1 and x0 folds recognise a literal
    with its ``LL`` suffix, and a negative one in its parentheses; the
    zero of x0 keeps the int64 width."""
    cpp = _source(tmp_path, PEEP, "cpu_highway", "aos")
    assert re.search(r"\w+\[0\] = 7LL;", cpp)
    assert re.search(r"\w+\[1\] = \(-\(-3LL\)\);", cpp)
    assert re.search(r"\w+\[2\] = 0LL;", cpp)
    assert re.search(r"\w+\[3\] = \(2LL \* 5LL\);", cpp)
    assert re.search(r"\w+\[1\] = \w+\[1\];", cpp)
    assert re.search(r"\w+\[2\] = \(-\w+\[2\]\);", cpp)


# A class painted on one row makes the Highway loop collapse that axis
# and fold the integer text it emits: the parentheses around a negative
# element must survive that fold, or ``-E`` is written as ``--1``.
EDGE = f"""
simulation_description("a constant int array negated in a one-row class");
global_constants {{ const array[int, 3] E = {{0, 1, -1}}; }}
lattices {{ lattice f(2, 3, int, {{{NX}, 8}}, {{true, false}}); }}
initializer Init {{ f.out[x, y | :] = {{x, x, x}}; }}
dynamic Bulk {{ f.out[x, y | :] = f.in[x, y | :]; }}
dynamic Edge {{
    array[int, 3] vv = f.in[x, y | :];
    array[int, 3] s = vv - E;
    array[int, 3] m = E * E;
    array[int, 3] n = -E;
    f.out[x, y | :] = s * 100 + m * 10 + n;
}}
gauge G -> (int a, int b, int c) {{
    a = f.in[x, y | 0]; b = f.in[x, y | 1]; c = f.in[x, y | 2];
}}
node_classes {{ node_class BULK(Init, Bulk, G); node_class EDGE(Init, Edge, G); }}
geometry {{ nodes[:, :] = BULK; nodes[:, 0] = EDGE; nodes[:, 7] = EDGE; }}
"""


@pytest.mark.parametrize("backend, layout", CONFIGS)
def test_a_negative_element_survives_the_one_row_fold(tmp_path, backend,
                                                     layout):
    """A constant array's negative element keeps its value under a
    minus, a product and a difference in a class that covers one row
    (user manual, Numerical semantics: Constant folding)."""
    _skip_cbt_without_avx512(layout)
    data = _run(tmp_path / "run", backend, EDGE, layout)
    for name, edge in (("a", 100 * _X), ("b", 100 * (_X - 1) + 9),
                       ("c", 100 * (_X + 1) + 11)):
        field = data[name][-1]
        np.testing.assert_array_equal(field[0], edge)
        np.testing.assert_array_equal(field[7], edge)
        np.testing.assert_array_equal(
            field[1:7], np.broadcast_to(_X, field[1:7].shape))


# ----------------------------------------------------------------------
# The generated code
# ----------------------------------------------------------------------

@requires_cpp_highway_compiler
def test_the_vector_body_negates_with_neg(tmp_path):
    """A spelling check: the vector body negates its first term with
    ``hn::Neg``."""
    cpp = _source(tmp_path, _neg_unit_program("gauge", 2), "cpu_highway",
                  "soa", defines=("S=-1.0",))
    assert re.search(r"hn::Neg\(\w+\[0\]\) - \w+\[1\] - \w+\[2\]", cpp)


def test_an_integer_array_is_spelled_exactly(tmp_path):
    """A spelling check: an integer element is written exactly, with
    its ``LL`` width, and the minimum as the negative maximum minus
    one."""
    for backend in ("cpu_highway", "gpu_cuda_cpp"):
        cpp = _source(tmp_path / backend, INT_ARRAY, backend)
        assert f"{TWO53 + 1}LL" in cpp
        assert f"{TWO53}.0" not in cpp
        assert "(-9223372036854775807LL - 1LL)" in cpp


def test_a_constant_element_is_spelled_with_its_width(tmp_path):
    """A spelling check: a bare ``2147483647`` is a C++ ``int``, and
    ``(2147483647 * 2)`` overflows it before the value reaches an int64
    variable; both literals carry the int64 width."""
    for backend in ("cpu_highway", "gpu_cuda_cpp"):
        cpp = _source(tmp_path / backend, WIDTH_SCALE, backend)
        assert "(2147483647LL * 2LL)" in cpp
        assert "(2147483647 * 2)" not in cpp


def test_an_integer_dot_prod_names_its_type(tmp_path):
    """A spelling check: an integer ``dot_prod`` calls the helper
    overloads that take its result's type, with ``int64_t`` coefficients
    and int64 products."""
    cpp = _source(tmp_path, NARROW_DOT.format(nx=NX, t8="int8", t32="int32"),
                  "cpu_highway", "aos")
    assert "gelb::gelb_dot_prod_const_as<int64_t>(" in cpp
    assert "gelb::gelb_signed_sum_as<int64_t>(" in cpp
    # Two per-cell arrays: int64 products, one conversion of the sum.
    assert re.search(r"static_cast<int8_t>\(static_cast<int64_t>\(\w+\[0\]\)"
                     r" \* static_cast<int64_t>\(\w+\[0\]\)", cpp)
    assert "static constexpr int64_t gelb_dp_coeff" in cpp
    assert "gelb::gelb_dot_prod_const(" not in cpp


def test_a_real_dot_prod_keeps_the_deducing_helpers(tmp_path):
    """A spelling check: integer coefficients with a real array, and
    real coefficients with a real array, are real results, and keep the
    helpers that deduce their type from the array, as before."""
    source = f"""
simulation_description("real dot products");
global_constants {{
    const array[int, 3] KC = {{1, 2, 3}};
    const array[real, 3] W = {{0.5, 0.25, 0.125}};
    const array[real, 3] PM = {{1.0, 1.0, -1.0}};
}}
lattices {{ lattice f(2, 3, real, {{{NX}, 4}}, {{true, true}}); }}
initializer Init {{ f.out[x, y | :] = {{1.0, 2.0, 3.0}}; }}
dynamic Step {{ f.out[x, y | :] = f.in[x, y | :]; }}
gauge G -> (real a, real b, real c) {{
    array[real, 3] v = f.in[x, y | :];
    a = dot_prod(KC, v);
    b = dot_prod(W, v);
    c = dot_prod(PM, v);
}}
node_classes {{ node_class BULK(Init, Step, G); }}
geometry {{ nodes[:, :] = BULK; }}
"""
    for layout in ("soa", "aos"):
        cpp = _source(tmp_path / layout, source, "cpu_highway", layout)
        assert "gelb::gelb_dot_prod_const(" in cpp
        assert "gelb::gelb_signed_sum(" in cpp
        assert "_as<" not in cpp
        # The integer coefficients are the helper's binary64 array.
        assert re.search(r"static constexpr double gelb_dp_coeff_\d+\[\] = "
                         r"\{ 1\.0, 2\.0, 3\.0 \};", cpp)
