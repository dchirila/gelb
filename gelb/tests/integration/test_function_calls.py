"""A call to a user function means what its body says, with the
caller's values, on every backend.

Every call is inlined by the compiler (user manual, GeLB in 10 minutes:
User-defined functions).  Every statement of the body, whatever its
kind, is copied with the caller's names: a destructuring call or an
element store inside a function, and a call inside an element store,
build and give the value the body computes.

Each case runs a 67 x 4 grid (a vector body of eight lanes and a
remainder) from a position-dependent state ``v = x / 2 - 7.75`` and
expects the closed-form value along x on every backend and Highway
layout that supports the construct; each control writes the same
arithmetic without the construct under test.
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

NX, NY = 67, 4
V = np.arange(NX, dtype=np.float64) * 0.5 - 7.75


def program(dynamic, *, functions="", globals="", output="real val"):
    """A program whose dynamic block computes ``val`` from ``v``."""
    return f'''simulation_description("function calls");
{globals}
{functions}
lattices {{ lattice f(2, 2, real, {{{NX}, {NY}}}, {{false, false}}); }}
initializer Init {{
    f.out[x, y | 0] = real(x) * 0.5 - 7.75;
    f.out[x, y | 1] = 0.0;
}}
dynamic Step {{
    f.out[x, y | 0] = f.in[x, y | 0];
    real v = f.in[x, y | 0];
    {dynamic}
}}
gauge G -> ({output}) {{ val = f.in[x, y | 1]; }}
node_classes {{ node_class BULK(Init, Step, G); }}
geometry {{ nodes[:, :] = BULK; }}
'''


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
        return np.asarray(nc.variables["val"][:])[-1]   # t = 1, (y, x)


def _skip_cbt_without_avx512(layout):
    if layout == "cbt" and not common._detect_avx512_available():
        pytest.skip("the cbt layout needs an AVX-512 host")


FORTRAN = pytest.param("cpu_fortran_serial", None, marks=requires_compiler,
                       id="fortran")
CONFIGS = [
    FORTRAN,
    *(pytest.param("cpu_highway", layout, marks=requires_cpp_highway_compiler,
                   id=f"highway-{layout}")
      for layout in ("soa", "aos", "cbt")),
    pytest.param("gpu_cuda_cpp", None,
                 marks=[pytest.mark.gpu, requires_gpu_cuda_cpp_compiler],
                 id="cuda"),
]


def _check(tmp_path, backend, layout, source, expected):
    _skip_cbt_without_avx512(layout)
    val = _run(tmp_path / "run", backend, source, layout)
    np.testing.assert_array_equal(val, np.broadcast_to(expected, (NY, NX)))


# ---------------------------------------------------------------------------
# every statement of a body is inlined with the caller's names
# ---------------------------------------------------------------------------

TWO = "function Two(real a) -> (real b, real c) { b = a; c = 2.0 * a; }"

DESTRUCTURING_IN_A_BODY = [
    pytest.param(
        program("f.out[x, y | 1] = Outer(v);", functions=TWO + """
function Outer(real p) -> (real r) {
    real u; real w; {u, w} = Two(p); r = u + w;
}"""),
        id="destructuring in a function"),
    pytest.param(
        program("real u; real w; {u, w} = Two(v); f.out[x, y | 1] = u + w;",
                functions=TWO),
        id="control: destructuring in the block"),
]


@pytest.mark.parametrize("source", DESTRUCTURING_IN_A_BODY)
@pytest.mark.parametrize("backend, layout", CONFIGS)
def test_a_destructuring_call_inside_a_function_is_inlined(
        tmp_path, backend, layout, source):
    _check(tmp_path, backend, layout, source, 3.0 * V)


# cpu_highway and gpu_cuda_cpp do not implement element stores
# (``a[0] = ...``; they stop with a NotImplementedError), so these run on
# Fortran.
ELEMENT_STORES = [
    pytest.param(
        program("f.out[x, y | 1] = Pair(v);", functions="""
function Pair(real a) -> (real b) {
    array[real, 2] tt; tt[0] = a; tt[1] = 2.0 * a; b = tt[0] + tt[1];
}"""),
        id="element store in a function"),
    pytest.param(
        program("array[real, 2] tt; tt[0] = v; tt[1] = Dbl(v);"
                " f.out[x, y | 1] = tt[0] + tt[1];",
                functions="function Dbl(real a) -> (real b) { b = 2.0 * a; }"),
        id="call in an element store"),
    pytest.param(
        program("array[real, 2] tt; tt[0] = v; tt[1] = 2.0 * v;"
                " f.out[x, y | 1] = tt[0] + tt[1];"),
        id="control: element stores without a call"),
]


@pytest.mark.parametrize("source", ELEMENT_STORES)
@pytest.mark.parametrize("backend, layout", [FORTRAN])
def test_an_element_store_inside_or_around_a_call_is_inlined(
        tmp_path, backend, layout, source):
    _check(tmp_path, backend, layout, source, 3.0 * V)


# A call stores each argument in its parameter: the body works on its
# own copy, and no store in the body reaches the caller's variable; each
# output is stored in its target after the body.
VALUES = [
    pytest.param(
        program("real u = v; real w = F(u); f.out[x, y | 1] = u + 100.0 * w;",
                functions="function F(real a) -> (real b) { a = a * 2.0; b = a; }"),
        201.0 * V, id="the body assigns its parameter"),
    pytest.param(
        program("f.out[x, y | 1] = v + F(3.0);",
                functions="function F(real a) -> (real b) { a = a * 2.0; b = a; }"),
        V + 6.0, id="the body assigns a parameter given a literal"),
    pytest.param(
        program("real w = v; real q; {w, q} = Two(w); f.out[x, y | 1] = 10.0 * w + q;",
                functions="function Two(real a) -> (real b, real c) { b = 2.0 * a; c = a + 1.0; }"),
        21.0 * V + 1.0, id="a target is also the argument"),
    pytest.param(
        program("real w = v; real p; real q; {p, q} = Two(w); f.out[x, y | 1] = 10.0 * p + q;",
                functions="function Two(real a) -> (real b, real c) { b = 2.0 * a; c = a + 1.0; }"),
        21.0 * V + 1.0, id="control: distinct targets"),
]


VALUES += [
    pytest.param(
        program("real w; {w, w} = Two(v); f.out[x, y | 1] = w;",
                functions="function Two(real a) -> (real b, real c) { c = a + 1.0; b = 2.0 * a; }"),
        V + 1.0, id="two outputs into one target, stored in the targets' order"),
    pytest.param(
        program("real __F_0_a = 100.0; real w = v; f.out[x, y | 1] = F(w) + __F_0_a;",
                functions="function F(real a) -> (real b) { a = a * 2.0; b = a; }"),
        2.0 * V + 100.0, id="a user variable named like an inlined copy"),
    pytest.param(
        program("array[real, 3] w = {v, 2.0 * v, 3.0 * v}; f.out[x, y | 1] = w[I(1)] + w[0];",
                functions="function I(int a) -> (int b) { b = a + 1; }"),
        4.0 * V, id="a call of constants as an array index"),
]


@pytest.mark.parametrize("source, expected", VALUES)
@pytest.mark.parametrize("backend, layout", CONFIGS)
def test_a_call_works_on_copies_of_its_arguments(
        tmp_path, backend, layout, source, expected):
    _check(tmp_path, backend, layout, source, expected)


@pytest.mark.parametrize("backend, layout", [FORTRAN])
def test_an_element_store_into_an_array_parameter_stays_in_the_function(
        tmp_path, backend, layout):
    source = program(
        "array[real, 3] w = {v, 2.0 * v, 3.0 * v}; f.out[x, y | 1] = S(w) + w[1];",
        functions="function S(array[real, 3] a) -> (real b)"
                  " { a[1] = 0.0; b = a[0] + a[1] + a[2]; }")
    _check(tmp_path, backend, layout, source, 6.0 * V)


CHAIN = [("A", "B"), ("B", "C"), ("C", "D")]


@pytest.mark.parametrize("order", ["callers first", "callees first"])
@pytest.mark.parametrize("backend, layout", CONFIGS)
def test_calls_are_inlined_whatever_the_order_of_the_definitions(
        tmp_path, backend, layout, order):
    """A chain of functions whose bodies are single calls: every call is
    inlined, whichever function is defined first."""
    defs = [f"function {f}(real a) -> (real b) {{ b = {g}(a); }}" for f, g in CHAIN]
    defs.append("function D(real a) -> (real b) { b = 2.0 * a; }")
    if order == "callees first":
        defs.reverse()
    source = program("f.out[x, y | 1] = A(v);", functions="\n".join(defs))
    _check(tmp_path, backend, layout, source, 2.0 * V)


@pytest.mark.parametrize("order", ["callers first", "callees first"])
@pytest.mark.parametrize("backend, layout", [FORTRAN])
def test_destructuring_bodies_are_inlined_whatever_the_order(
        tmp_path, backend, layout, order):
    defs = [f"function {f}(real a) -> (real b, real c) {{ {{b, c}} = {g}(a); }}"
            for f, g in CHAIN]
    # every body one statement long, also once inlined
    defs.append("function D(real a) -> (real b, real c) { {b, c} = {a, 2.0 * a}; }")
    if order == "callees first":
        defs.reverse()
    source = program("real r; real q; {r, q} = A(v); f.out[x, y | 1] = r + q;",
                     functions="\n".join(defs))
    _check(tmp_path, backend, layout, source, 3.0 * V)


IDENTITY = "function I(int a) -> (int b) { b = a; }"


@pytest.mark.parametrize("store, message", [
    pytest.param("f.out[x, y | I(k)] = v + 1.0;",
                 "with DF index 'I(k)', which is not a compile-time integer",
                 id="its DF selector"),
    pytest.param("f.out[x + I(k), y | 1] = v;",
                 "along x with 'x + I(k)', which is not x plus or minus a compile-time integer",
                 id="its spatial index"),
])
def test_a_call_in_the_index_of_a_lattice_store_is_reported(tmp_path, store, message):
    """A lattice store names its cells and DFs with compile-time
    integers: a call of a variable there is reported as the variable
    itself is, and inlining ends (gelbc runs in a process of its own,
    so that a pass that never ends fails this test instead of hanging
    it)."""
    source = tmp_path / "selector.gelb"
    source.write_text(program("int k = 1; " + store, functions=IDENTITY))
    result = subprocess.run(
        [sys.executable, "-m", "gelb.gelbc", str(source), "--diagnostics-json"],
        cwd=_ROOT, capture_output=True, text=True, timeout=120)
    assert result.returncode == 1
    assert message in result.stdout


@pytest.mark.parametrize("backend, layout", CONFIGS)
def test_a_call_of_a_constant_in_the_df_selector_of_a_store_builds(
        tmp_path, backend, layout):
    source = program("f.out[x, y | I(1)] = v + 1.0;", functions=IDENTITY)
    _check(tmp_path, backend, layout, source, V + 1.0)
