"""Integer values in the Highway vector body: per-cell integer casts,
arithmetic and stores, reductions of integer arrays, ``^0`` and
``real()`` of a vector.

An integer operation is exact in its type on every backend and every
code path, and a real converts to an integer by truncation (user
manual, Numerical semantics: Types and promotion; What must agree).
The ``cpu_highway`` vector body holds every per-cell value as a
binary64 vector, so a block whose integer value varies from cell to
cell (an ``int`` cast of a lattice value or of ``x``, an int local
assigned such a value, an inlined function returning one, integer
arithmetic on the ``int`` of a comparison, a per-cell int array) or
that reduces an integer array (``sum``, ``dot_prod``, ``matmul``) is
emitted once as scalar code, where every operation has its type; the
two shapes the body holds exactly, an int local copied from ``x`` and
the ``int`` of a comparison, stay vectorized, unless a later statement
stores into such a local.  ``v^0`` is a scalar one in the power's own
type that the consuming operation broadcasts, and ``real()`` of a
binary64 vector is the vector.  Every backend and layout is checked
against the closed form of the program, exactly, zero signs included;
the checks on the generated code
pin which path a dynamic takes, an implementation choice the manual
does not define.
"""

import os
import pathlib
import re
import subprocess
import sys

import numpy as np
import pytest

from gelb.backends.highway import common
from gelb.tests.integration._toolchain import (
    requires_compiler, requires_cpp_highway_compiler,
    requires_gpu_cuda_cpp_compiler)
from gelb.gelbc import cli
from click.testing import CliRunner

netCDF4 = pytest.importorskip("netCDF4")

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_GELB_RUN = _ROOT / "scripts" / "gelb-run"

NX = 67   # a vector body of eight lanes and a remainder
NY = 4
_X = np.arange(NX, dtype=np.float64)
_F = _X * 0.5 - 7.75          # the lattice value: exact, negative for x < 16
_POS = (_F > 0.0).astype(np.float64)
# int(F) through an integer: truncation toward zero, +0 at x = 15
_TRUNC = np.trunc(_F).astype(np.int64).astype(np.float64)


def _run(directory, backend, source, layout=None, steps=1):
    directory.mkdir()
    path = directory / "probe.gelb"
    path.write_text(source)
    env = dict(os.environ, GELB_PYTHON=sys.executable)
    if layout is not None:
        env["GELBC_EXTRA"] = f"--storage-layout {layout}"
    result = subprocess.run(
        [str(_GELB_RUN), "-b", backend, "-n", str(steps), "-w", "1",
         str(path)],
        cwd=directory, env=env, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stdout + result.stderr
    with netCDF4.Dataset(next(directory.glob("*.nc"))) as nc:
        return {name: np.asarray(var[:]) for name, var in nc.variables.items()
                if name not in ("x", "y", "z", "time")}


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


def _assert_field(data, name, expected, record=-1):
    """The field ``name`` at ``record`` (the last by default) equals
    ``expected`` bit for bit, the sign of a zero included: a row along
    x, broadcast to every row, or a full ``(NY, NX)`` plane."""
    field = data[name][record]
    field = field.reshape(-1, NX)
    expected = np.broadcast_to(np.asarray(expected, dtype=np.float64),
                               field.shape)
    np.testing.assert_array_equal(field, expected)
    np.testing.assert_array_equal(np.signbit(field), np.signbit(expected))


CONFIGS = [
    pytest.param("cpu_fortran_serial", None, marks=requires_compiler,
                 id="fortran"),
    *(pytest.param("cpu_highway", layout, marks=requires_cpp_highway_compiler,
                   id=f"highway-{layout}")
      for layout in ("soa", "cbt")),
    pytest.param("gpu_cuda_cpp", None,
                 marks=[pytest.mark.gpu, requires_gpu_cuda_cpp_compiler],
                 id="cuda"),
]
CONFIGS_WITH_AOS = CONFIGS[:1] + [
    pytest.param("cpu_highway", "aos", marks=requires_cpp_highway_compiler,
                 id="highway-aos")] + CONFIGS[1:]

_FUNCS = {
    "Trunc": "function Trunc(real a) -> (int b) { b = int(a); }",
    "Ident": "function Ident(int a) -> (int b) { b = a; }",
    "Two": "function Two(int a) -> (int b, real c) { b = a; c = real(a); }",
}

# Each shape: the statements, the value stored as the result, the
# closed form along x at the last record (F = x / 2 - 7.75 is the
# lattice value, exact), and whether the dynamic stays vectorized.
# ``{F}`` is the per-cell real value of the block, ``{S}`` the full
# DF slice of the cell (DF 1 is 0 at the first step).
_SHAPES = {
    # (a) an integer cast of a per-cell value
    "cast_int":        ("int k = int({F});", "real(k)", _TRUNC, False),
    "cast_real_local": ("real q = {F}; int k = int(q);", "real(k)",
                        _TRUNC, False),
    "int_of_x":        ("int k = int(x);", "real(k)", _X, False),
    "cast_in_function": ("int k = Trunc({F});", "real(k)", _TRUNC,
                         False),
    # (b) a per-cell value stored into an int local
    "assign_x":        ("int k; k = x;", "real(k)", _X, False),
    "literal_then_x":  ("int k = 3; k = x;", "real(k)", _X, False),
    "copy_of_x_local": ("int k = x; int m = k;", "real(m)", _X, False),
    "int_function":    ("int k = Ident(x);", "real(k)", _X, False),
    "destructuring":   ("int k; real h; {k, h} = Two(x);", "real(k) + h",
                        2.0 * _X, False),
    "int_array_of_x":  ("array[int, 2] a = {x, 1};", "real(sum(a))",
                        _X + 1.0, False),
    # (c) integer arithmetic on the int of a comparison, silent before
    "mask_arithmetic": ("", "real(int({F} > 0.0) * 3 / 2)", _POS, False),
    "mask_local_arithmetic": ("int k = int({F} > 0.0) * 3;", "real(k / 2)",
                              _POS, False),
    "mask_big_constant": ("", "real(int({F} > 0.0) * 9007199254740993"
                              " - 9007199254740992)",
                          np.where(_POS > 0, 1.0, -9007199254740992.0), False),
    # a later store into an admitted int local (a double vector would
    # round 2^53 + 1 to 2^53)
    # (compared, not subtracted: integer arithmetic on the local would
    # send the block scalar by itself)
    "reassign_x_local": ("int k = x; k = 9007199254740993;",
                         "real(k == 9007199254740992)", np.zeros(NX), False),
    "reassign_mask_local": ("int k = int({F} > 0.0); k = 9007199254740993;",
                            "real(k == 9007199254740992)", np.zeros(NX),
                            False),
    # an int intrinsic over x gives up the vector body
    "max_of_x":        ("int k = max(x, 3);", "real(k)", np.maximum(_X, 3.0),
                        False),
    # controls: the two shapes the vector body holds exactly
    "x_local":         ("int k = x;", "real(k) * 0.25 + {F}",
                        _X * 0.25 + _F, True),
    "int_of_bool":     ("bool b = {F} > 0.0; int k = int(b);", "real(k)",
                        _POS, True),
    "x_compared":      ("int k = x;", "real(k > 3)", (_X > 3).astype(float),
                        True),
    # a uniform int local is a scalar in the body
    "uniform_int":     ("int k = t;", "real(k) + {F}", 1.0 + _F, True),
}

# C17b: reductions of integer arrays, ``^0`` and ``real()`` of a vector.
_GLOBALS = """\
global_constants {
    const array[real, 3] W = {0.5, 0.25, 0.125};
    const array[int, 3] C = {1, 2, 3};
    const array[real, {2, 3}] M = {{0.5, 0.25, 0.125}, {1.0, -1.0, 0.5}};
    const array[int, {2, 3}] MI = {{1, 2, 3}, {2, -1, 1}};
}
"""
_SHAPES_B = {
    "pow_zero":        ("", "{F}^0 + 1.0", np.full(NX, 2.0), True),
    "pow_zero_division": ("", "({F}^0 + {F}^0) / ({F}^0 + {F}^0 + {F}^0)",
                          np.full(NX, 2.0 / 3.0), True),
    "pow_zero_over_int": ("", "{F}^0 / 2", np.full(NX, 0.5), True),
    # the int of a comparison on a uniform reduction (here of ``t``, 1
    # at every step of the run) is a vector too: a later store or integer
    # arithmetic sends the block scalar
    "reassign_reduction_mask": ("array[real, 3] u = {real(min(t, 1)), 0.25, 0.125};"
                                " int m = int(dot_prod(W, u) > 0.25);"
                                " m = 9007199254740993;",
                                "real(m == 9007199254740992)", np.zeros(NX),
                                False),
    "reduction_mask_arithmetic": ("array[real, 3] u = {real(min(t, 1)), 0.25, 0.125};"
                                  " int m = int(dot_prod(W, u) > 0.25);",
                                  "real(m * 3 / 2)", np.ones(NX), False),
    "reduction_mask": ("array[real, 3] u = {real(min(t, 1)), 0.25, 0.125};"
                       " int m = int(dot_prod(W, u) > 0.25);",
                       "{F} * 0.0 + real(m)", np.ones(NX), True),
    # an int sum of a uniform int array
    "int_sum_of_uniform": ("array[int, 3] c = {min(t, 1), 2, 3}; int m = sum(c);",
                           "{F} * 0.0 + real(m)", np.full(NX, 6.0), False),
    # the same of constants folds to a constant, which the vector body
    # holds (user manual, Numerical semantics: Constant folding)
    "constant_reduction_mask": ("int m = int(dot_prod(W, W) > 0.25);",
                                "real(m * 3 / 2)", np.ones(NX), True),
    "int_sum_of_constant": ("int m = sum(C);", "{F} * 0.0 + real(m)",
                            np.full(NX, 6.0), True),
    # (the type of a zero power: test_literal_types.py)
    "real_of_array_element": ("array[real, 2] fi = {S};"
                              " real c = real(fi[0]) + real(fi[1]) * 0.5;",
                              "c", _F, True),
    "real_of_real_sum": ("array[real, 3] kr = {1.0, 2.0, 3.0};",
                         "{F} * real(sum(kr))", 6.0 * _F, True),
    "sum_of_int_array": ("array[int, 3] k = {1, 2, 3};",
                         "{F} * real(sum(k))", 6.0 * _F, False),
    "matmul_int_array": ("array[int, 3] k = {1, 2, 3};"
                         " array[real, 2] r = matmul(M, k);",
                         "{F} * r[0]", 1.375 * _F, False),
    "dot_prod_int_array": ("array[int, 3] k = {1, 2, 3};",
                           "{F} * dot_prod(W, k)", 1.375 * _F, False),
    # a global constant int array keeps the vector body (exact helpers)
    "dot_prod_int_coefficients": ("array[real, 3] fi = {{F}, 2.0 * {F},"
                                  " 3.0 * {F}};", "dot_prod(C, fi)",
                                  14.0 * _F, True),
    "matmul_int_matrix": ("array[real, 3] fi = {{F}, 2.0 * {F}, 3.0 * {F}};"
                          " array[real, 2] r = matmul(MI, fi);",
                          "r[0] + r[1]", 17.0 * _F, True),
    # control: a real reduction stays vectorized
    "sum_of_real_array": ("array[real, 3] kr = {1.0, 2.0, 3.0};",
                          "{F} * sum(kr)", 6.0 * _F, True),
}

_DIMS = {
    1: ("lattice f(1, 2, real, {nx}, false);", "x", "nodes[:] = BULK;"),
    2: ("lattice f(2, 2, real, {{{nx}, {ny}}}, {{false, false}});", "x, y",
        "nodes[:, :] = BULK;"),
    3: ("lattice f(3, 2, real, {{{nx}, {ny}, 2}}, {{false, false, false}});",
        "x, y, z", "nodes[:, :, :] = BULK;"),
}


def _program(shape, block="dynamic", dim=2, with_globals=False):
    """The probe program: DF 0 holds F, DF 1 the shape's result,
    computed in ``block``; the gauge output ``s`` reports DF 1 (or the
    shape's result when the gauge computes it)."""
    stmts, result, _, _ = {**_SHAPES, **_SHAPES_B}[shape]
    lat, c, geo = _DIMS[dim]
    lat = lat.format(nx=NX, ny=NY)
    funcs = "\n".join(f for n, f in _FUNCS.items() if n + "(" in stmts)
    init_f = "(real(x) * 0.5 - 7.75)"
    lat_f = f"f.in[{c} | 0]"

    def body(value):
        slice_ = f"f.in[{c} | :]"
        return (stmts.replace("{F}", value).replace("{S}", slice_),
                result.replace("{F}", value))

    init = f"f.out[{c} | 1] = 0.0;"
    dyn = f"f.out[{c} | 1] = f.in[{c} | 1];"
    gauge = f"s = f.in[{c} | 1];"
    if block == "initializer":
        st, r = body(init_f)
        init = f"{st}\n    f.out[{c} | 1] = {r};"
    elif block == "dynamic":
        st, r = body(lat_f)
        dyn = f"{st}\n    f.out[{c} | 1] = {r};"
    else:
        st, r = body(lat_f)
        gauge = f"{st}\n    s = {r};"
    return f"""\
simulation_description("{shape} in a {block}, {dim}-D");
{funcs}
{_GLOBALS if with_globals else ""}lattices {{ {lat} }}
initializer Init {{
    f.out[{c} | 0] = real(x) * 0.5 - 7.75;
    {init}
}}
dynamic Step {{
    f.out[{c} | 0] = f.in[{c} | 0];
    {dyn}
}}
gauge G -> (real s) {{
    {gauge}
}}
node_classes {{ node_class BULK(Init, Step, G); }}
geometry {{ {geo} }}
"""


_DYNAMIC_PATH = re.compile(r"^\s*// Dynamic: Step \(BULK\)( -- SIMD)?$", re.M)


def _dynamic_is_vectorized(cpp):
    """Whether the dynamic ``Step`` of a one-class program takes the
    vector path (the emitter labels each block's path once)."""
    labels = _DYNAMIC_PATH.findall(cpp)
    assert len(labels) == 1, labels
    return labels[0] == " -- SIMD"


@pytest.mark.parametrize("backend, layout", CONFIGS)
@pytest.mark.parametrize("shape", sorted(_SHAPES))
def test_per_cell_integer_values(tmp_path, backend, layout, shape):
    """Each shape, computed in a dynamic, gives the closed form on every
    backend and layout: integer casts truncate, integer arithmetic is
    exact and an int local holds its per-cell value."""
    _skip_cbt_without_avx512(layout)
    data = _run(tmp_path / "run", backend, _program(shape), layout)
    _assert_field(data, "s", _SHAPES[shape][2])


@pytest.mark.parametrize("backend, layout", CONFIGS)
@pytest.mark.parametrize("shape", sorted(_SHAPES_B))
def test_reductions_power_zero_and_real_of_vector(tmp_path, backend, layout,
                                                  shape):
    """A reduction of an integer array, ``v^0`` and ``real()`` of a
    vector value give the closed form on every backend and layout."""
    _skip_cbt_without_avx512(layout)
    data = _run(tmp_path / "run", backend,
                _program(shape, with_globals=True), layout)
    _assert_field(data, "s", _SHAPES_B[shape][2])


@pytest.mark.parametrize("backend, layout", CONFIGS_WITH_AOS)
@pytest.mark.parametrize("block", ["initializer", "gauge"])
@pytest.mark.parametrize("shape", ["cast_int", "assign_x", "mask_arithmetic",
                                   "int_of_bool"])
def test_in_initializer_and_gauge(tmp_path, backend, layout, block, shape):
    """The same shapes computed in an initializer and in a gauge, on
    every layout (AoS included, the layout that was right before), at
    the initial gauge pass and after the step."""
    _skip_cbt_without_avx512(layout)
    data = _run(tmp_path / "run", backend, _program(shape, block), layout)
    for record in (0, -1):
        _assert_field(data, "s", _SHAPES[shape][2], record)


@pytest.mark.parametrize("backend, layout", CONFIGS)
@pytest.mark.parametrize("dim", [1, 3])
@pytest.mark.parametrize("shape", ["cast_int", "mask_arithmetic",
                                   "sum_of_int_array"])
def test_in_one_and_three_dimensions(tmp_path, backend, layout, dim, shape):
    """The shapes on a 1-D and a 3-D grid."""
    _skip_cbt_without_avx512(layout)
    data = _run(tmp_path / "run", backend,
                _program(shape, dim=dim, with_globals=True), layout)
    _assert_field(data, "s", {**_SHAPES, **_SHAPES_B}[shape][2])


@requires_cpp_highway_compiler
def test_gauge_output_assigned_an_int_cast(tmp_path):
    """A real gauge output assigned ``int(f.in[..])`` directly builds
    and truncates (the shape the shared-output hint leads to)."""
    program = _program("cast_int", "gauge").replace(
        "int k = int(f.in[x, y | 0]);\n    s = real(k);",
        "s = int(f.in[x, y | 0]);")
    assert "s = int(f.in[x, y | 0]);" in program
    data = _run(tmp_path / "run", "cpu_highway", program, "soa")
    _assert_field(data, "s", _TRUNC)


@pytest.mark.parametrize("shape", sorted({**_SHAPES, **_SHAPES_B}))
def test_dynamic_path(tmp_path, shape):
    """A dynamic with a per-cell integer value or an integer-array
    reduction takes the scalar path; the controls, ``^0`` and
    ``real()`` of a vector keep the vector body."""
    stmts, result, _, vectorized = {**_SHAPES, **_SHAPES_B}[shape]
    cpp = _source(tmp_path, _program(shape, with_globals=True))
    assert _dynamic_is_vectorized(cpp) == vectorized
    if vectorized:
        body = (cpp.split("// Dynamic: Step")[1].split("// SIMD body")[1]
                .split("// scalar remainder")[0])
        if shape == "pow_zero":
            # ``1.0 + 1.0`` is a scalar, broadcast at the store
            assert "hn::Set(d, 2.0)" in body
        if shape in ("real_of_array_element", "real_of_real_sum"):
            # no cast of a vector (the loop's ``hn::Iota`` casts its
            # scalar counter)
            assert not [line for line in body.splitlines()
                        if "static_cast<double>(" in line
                        and "hn::Iota" not in line], body
