"""A call to a user function means what its body says, with the
caller's values, on every backend.

Every call is inlined by the compiler (user manual, GeLB in 10 minutes:
User-defined functions).  Every statement of the body, whatever its
kind, is copied with the caller's names: a destructuring call or an
element store inside a function, and a call inside an element store,
build and give the value the body computes.  A call stores each
argument in its parameter and each output in its target, converted and
checked as a declaration's initializer is.  A call whose arguments are
constants is a constant expression, like an intrinsic of constants
(user manual, Numerical semantics: Constant folding): what the
contract makes a compile-time error is one, named with the call, and
what folds to a special value is written as one.

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


def _run(directory, backend, source, layout=None, seed=None):
    directory.mkdir()
    path = directory / "probe.gelb"
    path.write_text(source)
    env = dict(os.environ, GELB_PYTHON=sys.executable)
    if layout is not None:
        env["GELBC_EXTRA"] = f"--storage-layout {layout}"
    seeded = ["-s", str(seed)] if seed is not None else []
    result = subprocess.run(
        [str(_GELB_RUN), "-b", backend, "-n", "1", "-w", "1", *seeded, str(path)],
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


# ---------------------------------------------------------------------------
# a call stores each argument in its parameter and each output in its
# target, converting and checking them as a store does
# ---------------------------------------------------------------------------

_X = np.arange(NX)
SQ = "function Sq(int a) -> (int b) { b = a * a; }"
R_ID = "function I(real a) -> (real b) { b = a; }"
R_Q = "function Q(real a) -> (real b, real c) { b = a; c = 7.0 / b; }"

# Each case runs across x = 0..66, where the store's conversion matters
# for some cells and not others (an int32 square past 2^31 from x = 41).
CONVERSIONS = [
    pytest.param(
        program("int32 h = int32(x) + int32(46300); f.out[x, y | 1] = real(Sq(h));",
                functions=SQ),
        ((46300 + _X) ** 2).astype(np.float64), id="int32 argument, int parameter"),
    pytest.param(
        program("int h = x + 46300; f.out[x, y | 1] = real(Sq(h));", functions=SQ),
        ((46300 + _X) ** 2).astype(np.float64), id="control: int argument"),
    pytest.param(
        program("int16 a = int16(x) + int16(30000); int16 b = int16(30000);"
                " f.out[x, y | 1] = real(P3(a, b, b));",
                functions="function P3(int a, int b, int c) -> (int d) { d = a * b * c; }"),
        ((30000 + _X) * 30000 * 30000).astype(np.float64),
        id="int16 arguments, int parameters"),
    pytest.param(
        program("int h = x + 4294967297; f.out[x, y | 1] = real(N32(h));",
                functions="function N32(int32 a) -> (int b) { b = a; }"),
        (1 + _X).astype(np.float64), id="int argument, int32 parameter"),
    pytest.param(
        program("int32 h = int32(x + 4294967297); f.out[x, y | 1] = real(N32(h));",
                functions="function N32(int32 a) -> (int b) { b = a; }"),
        (1 + _X).astype(np.float64), id="control: int32 argument"),
    pytest.param(
        program("real32 w = real32(v * 0.1); f.out[x, y | 1] = Sqr(w);",
                functions="function Sqr(real a) -> (real b) { b = a * a; }"),
        (V * 0.1).astype(np.float32).astype(np.float64) ** 2,
        id="real32 argument, real parameter"),
    pytest.param(
        program("real w = real(real32(v * 0.1)); f.out[x, y | 1] = Sqr(w);",
                functions="function Sqr(real a) -> (real b) { b = a * a; }"),
        (V * 0.1).astype(np.float32).astype(np.float64) ** 2,
        id="control: real argument"),
    pytest.param(
        program("int32 p; int32 u; {p, u} = F2(x + 65536); f.out[x, y | 1] = real(p);",
                functions="function F2(int a) -> (int b, int c)"
                          " { b = a; b = b * b / 65536; c = 0; }"),
        ((65536 + _X) ** 2 // 65536).astype(np.float64),
        id="int output, int32 target"),
    pytest.param(
        program("int p; int u; {p, u} = F2(x + 65536); f.out[x, y | 1] = real(p);",
                functions="function F2(int a) -> (int b, int c)"
                          " { b = a; b = b * b / 65536; c = 0; }"),
        ((65536 + _X) ** 2 // 65536).astype(np.float64),
        id="control: int target"),
    pytest.param(
        program("f.out[x, y | 1] = Second(v);",
                functions="function Second(array[real, 2] a) -> (real b) { b = a[1]; }"),
        V, id="scalar argument, array parameter"),
    pytest.param(
        program("f.out[x, y | 1] = real(I(v > 0.0));",
                functions="function I(int a) -> (int b) { b = a * 3; }"),
        3.0 * (V > 0.0), id="bool argument, int parameter"),
]


@pytest.mark.parametrize("source, expected", CONVERSIONS)
@pytest.mark.parametrize("backend, layout", CONFIGS)
def test_a_call_converts_its_arguments_and_outputs_as_a_store_does(
        tmp_path, backend, layout, source, expected):
    _check(tmp_path, backend, layout, source, expected)


@pytest.mark.parametrize("functions, call, message", [
    ("function F(int a) -> (int b) { b = a; }",
     "f.out[x, y | 1] = real(F(2.5));",
     "Argument 'a' of 'F' is declared as 'int' but given 'real'"),
    ("function F(bool a) -> (int b) { b = int(a); }",
     "f.out[x, y | 1] = real(F(1));",
     "Argument 'a' of 'F' is declared as 'bool' but given 'int'"),
    ("function F(real a) -> (real b) { b = a; }",
     "f.out[x, y | 1] = F({1.0, 2.0});",
     r"Argument 'a' of 'F' is declared with shape scalar but given shape \[2\]"),
    ("function F(array[real, 3] a) -> (real b) { b = a[1]; }",
     "f.out[x, y | 1] = F({1.0, 2.0});",
     r"Argument 'a' of 'F' is declared with shape \[3\] but given shape \[2\]"),
    ("function F(real a) -> (real b, real c) { b = a; c = a; }",
     "int p; int u; {p, u} = F(2.5); f.out[x, y | 1] = real(p);",
     "Output 'b' of 'F' is 'real' but its target 'p' is 'int'"),
    ("function T(real a) -> (array[real, 3] p, real q) { p = {a, a, a}; q = a; }",
     "array[real32, 2] w; real zz; {w, zz} = T(v); f.out[x, y | 1] = real(w[0]);",
     r"Output 'p' of 'T' has shape \[3\] but its target 'w' has shape \[2\]"),
    ("function S(array[int, 2] a) -> (int b) { b = a[0]; }",
     "f.out[x, y | 1] = real(S(v));",
     "Argument 'a' of 'S' is declared as an array of 'int' but given 'real'"),
    ("function T(real a) -> (real p, real q) { p = a; q = a; }",
     "array[int, 2] w; real zz; {w, zz} = T(v); f.out[x, y | 1] = real(w[0]);",
     "Output 'p' of 'T' is 'real' but its target 'w' is an array of 'int'"),
])
def test_a_call_is_checked_as_a_store_is(functions, call, message):
    """What a declaration's initializer may not hold, an argument may not
    either, and an output stored in a target is checked as an assignment."""
    from gelb.compiler_pipeline import (
        PipelineOptions, PipelineProfile, compile_source)
    from gelb.utils.exceptions import GeLBExTypeError
    with pytest.raises(GeLBExTypeError, match=message):
        compile_source(program(call, functions=functions),
                       PipelineProfile.CODEGEN, PipelineOptions())


# ---------------------------------------------------------------------------
# a call whose arguments are constants is a constant expression
# ---------------------------------------------------------------------------

def _compile(source):
    from gelb.compiler_pipeline import (
        PipelineOptions, PipelineProfile, compile_source)
    return compile_source(source, PipelineProfile.CODEGEN, PipelineOptions())


@pytest.mark.parametrize("functions, dynamic, message", [
    pytest.param(SQ, "f.out[x, y | 1] = real(Sq(3037000500));",
                 r"integer overflow: \d+ does not fit int in a constant expression,"
                 r" in the call Sq\(3037000500\) on line 12",
                 id="overflow in the body"),
    pytest.param(SQ, "f.out[x, y | 1] = real(1 / Sq(0));",
                 r"Division by zero: divisor is integer literal 0,"
                 r" the value of the call Sq\(0\) on line 12",
                 id="zero divisor from the call's value"),
    pytest.param(SQ, "f.out[x, y | 1] = real(Sq(Sq(100000)));",
                 r"integer overflow: 100000000000000000000 does not fit int"
                 r".* in the call Sq\(Sq\(100000\)\) on line 12",
                 id="overflow of a call of a call"),
    pytest.param(SQ, "int q = Sq(3037000000) + Sq(3037000000); f.out[x, y | 1] = real(q);",
                 r"integer overflow: \d+ does not fit int in a constant expression,"
                 r" the value of the call Sq\(3037000000\)",
                 id="overflow of two calls' values"),
    pytest.param("function Q(int a) -> (int b) { b = 7 / a; }",
                 "f.out[x, y | 1] = real(Q(0));",
                 r"Division by zero: divisor is integer literal 0, in the call Q\(0\) on line 12",
                 id="zero divisor in the body"),
    pytest.param("function R(real a) -> (real b) { b = sqrt(a); }",
                 "f.out[x, y | 1] = real(int(R(-1.0)));",
                 r"cannot convert nan to int in a constant expression,"
                 r" the value of the call R\(-1\.0\) on line 12",
                 id="NaN to int of the call's value"),
    pytest.param("function D(int a) -> (int b, int c) { b = a * a; c = 7 / a; }",
                 "int p; int u; {p, u} = D(0); f.out[x, y | 1] = real(p + u);",
                 r"Division by zero: divisor is integer literal 0, in the call D\(0\) on line 12",
                 id="destructuring call"),
    pytest.param("""function Inner(int a) -> (int b) { b = 7 / a; }
function Outer(int p) -> (int r) { r = Inner(p) + 1; }""",
                 "f.out[x, y | 1] = real(Outer(0));",
                 r"Division by zero: divisor is integer literal 0,"
                 r" in the call Inner\(p\) on line 4, in the call Outer\(0\) on line 13",
                 id="nested calls"),
])
def test_a_call_of_constants_is_checked_as_a_constant_expression(
        functions, dynamic, message):
    """The errors of chapter 19 for a constant expression, found after
    inlining, and named with the calls they come from (their lines
    count from the program's first line)."""
    from gelb.utils.exceptions import GeLBExTypeError
    with pytest.raises(GeLBExTypeError, match=message):
        _compile(program(dynamic, functions=functions))


SPECIAL = [
    pytest.param("function R(real a) -> (real b) { b = sqrt(a); }",
                 "f.out[x, y | 1] = R(-1.0);", np.full(NX, np.nan),
                 id="sqrt(-1.0) in the body"),
    pytest.param("function L(real a) -> (real b) { b = log(a); }",
                 "f.out[x, y | 1] = L(0.0);", np.full(NX, -np.inf),
                 id="log(0.0) in the body"),
    pytest.param("function P(real w, real c) -> (real b) { b = w * sqrt(c); }",
                 "f.out[x, y | 1] = P(v, -1.0);", np.full(NX, np.nan),
                 id="a constant argument and a variable one"),
    pytest.param("function Inv(real a) -> (real b) { b = 2.0 * a; }",
                 "f.out[x, y | 1] = Inv(1.0e308);", np.full(NX, np.inf),
                 id="a real overflow in the body"),
]


@pytest.mark.parametrize("functions, dynamic, expected", SPECIAL)
@pytest.mark.parametrize("backend, layout", CONFIGS)
def test_a_call_of_constants_folds_to_its_special_value(
        tmp_path, backend, layout, functions, dynamic, expected):
    """No native compiler sees ``sqrt(-1.0)`` or ``log(0.0)`` as a
    constant argument after inlining (gfortran rejects them): the value
    is folded and written as a special value."""
    _check(tmp_path, backend, layout, program(dynamic, functions=functions),
           expected)


@pytest.mark.parametrize("backend, layout", CONFIGS)
def test_a_calls_value_stored_in_a_variable_is_a_variable(tmp_path, backend, layout):
    """Only a call's own names carry its constant value: ``int a =
    Sq(0);`` is a variable holding 0, and dividing by it is a run-time
    division (here real: ``inf``, and ``nan`` at x = 0), as dividing
    by any variable is."""
    source = program("int a = Sq(0); f.out[x, y | 1] = real(x) / real(a);",
                     functions=SQ)
    with np.errstate(divide="ignore", invalid="ignore"):
        expected = _X.astype(np.float64) / 0.0
    _check(tmp_path, backend, layout, source, expected)


@pytest.mark.parametrize("backend, layout", CONFIGS)
def test_a_call_of_constants_builds_and_gives_its_value(tmp_path, backend, layout):
    source = program(
        "f.out[x, y | 1] = real(Sq(46341)) + v * real(Sq(2) - 4) + Third(3.0);",
        functions=SQ + "\nfunction Third(real a) -> (real b) { real t = a / 9.0; b = t; }")
    _check(tmp_path, backend, layout, source,
           2147488281.0 + V * 0.0 + 3.0 / 9.0)


RANDOM_IN_A_BODY = [
    program("f.out[x, y | 1] = N(2.0) + N(v);", functions=(
        "function N(real a) -> (real b) { real r = random(); b = a * 0.0 + r; }")),
    program("real r1 = random(); real r2 = random();"
            " f.out[x, y | 1] = (2.0 * 0.0 + r1) + (v * 0.0 + r2);"),
]


@pytest.mark.parametrize("backend, layout", CONFIGS)
def test_a_draw_in_a_body_called_with_constants_is_kept_in_order(
        tmp_path, backend, layout):
    """Folding a call of constants never drops, duplicates or reorders a
    ``random()`` draw of its body (user manual, Numerical semantics:
    Random numbers): with one seed, the calls draw what the same
    statements written in the block draw."""
    _skip_cbt_without_avx512(layout)
    called, written = (
        _run(tmp_path / name, backend, source, layout, seed=42)
        for name, source in zip(("called", "written"), RANDOM_IN_A_BODY))
    np.testing.assert_array_equal(called, written)


@pytest.mark.parametrize("functions, dynamic, message", [
    pytest.param("function Q(int a) -> (int b, int c) { b = a; c = 7 / b; }",
                 "int p; int q; {p, q} = Q(0); f.out[x, y | 1] = real(p + q);",
                 r"Division by zero: divisor is integer literal 0, the value of the call"
                 r" Q\(0\)|Division by zero: divisor is integer literal 0, in the call Q\(0\)",
                 id="an output the body reads, its target of its type"),
    pytest.param(SQ, "const int a = Sq(0); f.out[x, y | 1] = real(7 / a);",
                 r"Division by zero: divisor is integer literal 0",
                 id="a block constant holding a call of constants"),
    pytest.param(R_ID + "\n" + R_Q,
                 "const real kk = I(0.0); real p; real q; {p, q} = Q(kk);"
                 " f.out[x, y | 1] = p + q;",
                 r"Division by zero: divisor is real literal 0\.0, in the call Q\(kk\)",
                 id="that constant passed to a call whose body reads its output"),
    pytest.param(R_ID + "\n" + R_Q + "\nfunction E(real a, real w) -> (real e) {"
                 " real r; real s; {r, s} = Q(a); e = r + s + w; }",
                 "const real kk = I(0.0); f.out[x, y | 1] = E(kk, v);",
                 r"Division by zero: divisor is real literal 0\.0,"
                 r" in the call Q\(a\) on line \d+, in the call E\(kk, v\)",
                 id="and passed on, in a call with a variable argument"),
    pytest.param("function Sz(array[real, 2] a) -> (real b) { real zero = 0.0; b = 7.0 / zero; }\n"
                 "function Q(real a) -> (array[real, 2] m, real c) { m = {a, 1.0}; c = Sz(m); }",
                 "array[real, 2] mm; real cc; {mm, cc} = Q(0.0); f.out[x, y | 1] = cc + mm[1];",
                 r"Division by zero: divisor is real literal 0\.0,"
                 r" in the call Sz\(m\) on line \d+, in the call Q\(0\.0\)",
                 id="an array output the body passes on"),
])
def test_a_call_of_constants_is_checked_through_its_targets_and_constants(
        functions, dynamic, message):
    """Whatever names a call's arguments and outputs are written in,
    only the folder decides whether it is a call of constants: an
    output the body reads is the call's own name, which it carries."""
    from gelb.utils.exceptions import GeLBExTypeError
    with pytest.raises(GeLBExTypeError, match=message):
        _compile(program(dynamic, functions=functions))


ZERO_DIVISOR = "{ real zero = 0.0; b = 7.0 / zero; }"
S_ARRAY = "function S(array[real, 2] a) -> (real b) " + ZERO_DIVISOR
A_GLOBAL = "global_constants { const array[real, 2] A = {0.0, 1.0}; }"


@pytest.mark.parametrize("globals, functions, dynamic, call", [
    pytest.param("", "function F(array[int, 2] a) -> (real b) " + ZERO_DIVISOR,
                 "f.out[x, y | 1] = F({1, 2});", r"F\(\{1, 2\}\)",
                 id="an array literal"),
    pytest.param(A_GLOBAL, S_ARRAY, "f.out[x, y | 1] = S(A);", r"S\(A\)",
                 id="a global constant array"),
    pytest.param("", S_ARRAY,
                 "const array[real, 2] B = {0.0, 1.0}; f.out[x, y | 1] = S(B);",
                 r"S\(B\)", id="a block-local constant array"),
    pytest.param("", "function T(array[real, 2] a) -> (real b) "
                 "{ a[0] = 1.0; real zero = 0.0; b = 7.0 / zero; }",
                 "f.out[x, y | 1] = T({0.0, 1.0});", r"T\(\{0\.0, 1\.0\}\)",
                 id="an array literal the body stores into"),
    pytest.param(A_GLOBAL.replace("}; }", "}; const array[real, 2] NA = -A; }"), S_ARRAY,
                 "f.out[x, y | 1] = S(NA);", r"S\(NA\)",
                 id="a global constant array, whatever its form"),
    pytest.param("", "function SB(array[bool, 2] a) -> (real b) " + ZERO_DIVISOR,
                 "f.out[x, y | 1] = SB({true, false});", r"SB\(\{true, false\}\)",
                 id="an array literal of bools"),
    pytest.param("", "function Q(array[real, 2] a) -> (real b) { b = 7.0 / (sum(a) - 1.0); }",
                 "f.out[x, y | 1] = Q({0.0, 1.0});", r"Q\(\{0\.0, 1\.0\}\)",
                 id="an array literal the body reduces"),
    pytest.param("", S_ARRAY + "\nfunction F(real p) -> (real r) {"
                 " array[real, 2] a = {p, 1.0}; a = -a; r = S(a); }",
                 "f.out[x, y | 1] = F(2.0);", r"S\(a\)",
                 id="an array updated from itself"),
    pytest.param("", "function F(real p) -> (real r) {"
                 " array[real, 2] a = {p, 1.0}; a = a; r = 7.0 / (sum(a) - 3.0); }",
                 "f.out[x, y | 1] = F(2.0);", r"F\(2\.0\)",
                 id="an array stored onto itself, then reduced"),
])
def test_a_constant_array_is_a_constant_argument(globals, functions, dynamic, call):
    """A constant array is a constant: a call whose arguments are such
    arrays and other constants is a call of constants, its locals
    carried, though the arrays' elements are not."""
    from gelb.utils.exceptions import GeLBExTypeError
    with pytest.raises(GeLBExTypeError,
                       match=r"Division by zero: divisor is real literal 0\.0, in the call " + call):
        _compile(program(dynamic, functions=functions, globals=globals))


def test_only_a_calls_output_is_named_as_its_value():
    """A zero that is a local of the call is reported in the call, not as
    the call's value; the same call named twice is named once."""
    from gelb.utils.exceptions import GeLBExTypeError
    with pytest.raises(GeLBExTypeError) as local:
        _compile(program("f.out[x, y | 1] = real(Q(3));", functions=(
            "function Q(int a) -> (int b) { int c = a - a; b = 7 / c; }")))
    assert "in the call Q(3) on line 12" in str(local.value)
    assert "the value of" not in str(local.value)
    with pytest.raises(GeLBExTypeError) as nested:
        _compile(program("f.out[x, y | 1] = real(Sq(Sq(100000)));", functions=SQ))
    assert str(nested.value).count("the value of the call Sq(100000)") == 1


with np.errstate(divide="ignore"):
    V_OVER_ZERO = V / 0.0

CARRIED_ONLY_IN_CALLS_OF_CONSTANTS = [
    pytest.param("function F(real a) -> (real b) { real zero = 0.0; b = a / zero; }",
                 "f.out[x, y | 1] = F(v);", V_OVER_ZERO,
                 id="a local of a call with a variable argument stays a variable"),
    pytest.param("function F(real a) -> (real b) { real zero = 0.0; b = a / zero; }",
                 "real zero = 0.0; f.out[x, y | 1] = v / zero;", V_OVER_ZERO,
                 id="control: the same in the block"),
]


@pytest.mark.parametrize("functions, dynamic, expected", CARRIED_ONLY_IN_CALLS_OF_CONSTANTS)
@pytest.mark.parametrize("backend, layout", CONFIGS)
def test_a_call_with_a_variable_argument_is_not_a_constant_expression(
        tmp_path, backend, layout, functions, dynamic, expected):
    """Its locals are variables, as the same statements in the block
    are: no compile-time error, the division happens at run time."""
    _check(tmp_path, backend, layout, program(dynamic, functions=functions),
           expected)


@pytest.mark.parametrize("backend, layout", [FORTRAN])
def test_a_constant_overwritten_by_a_destructuring_is_not_carried(
        tmp_path, backend, layout):
    """A local holding a constant, then overwritten by a destructuring
    from an array (cpu_highway does not implement those), holds the
    destructured value."""
    source = program("array[real, 2] w = {v, 3.0 * v}; f.out[x, y | 1] = F(w);",
                     functions="""function F(array[real, 2] q) -> (real r) {
    real p = 1.0; real s = 2.0; {p, s} = q; r = p * 10.0 + s;
}""")
    _check(tmp_path, backend, layout, source, 13.0 * V)


@pytest.mark.parametrize("backend, layout", CONFIGS)
def test_a_user_variable_named_like_an_inlined_name_is_a_variable(
        tmp_path, backend, layout):
    """The initializer inlines Sq(3.0) (its output a name of the
    inliner); the dynamic block's own variable of that name is a user
    variable, never carried."""
    source = program("real __Sq_0_b = v; f.out[x, y | 1] = 2.0 * __Sq_0_b;",
                     functions="function Sq(real a) -> (real b) { b = a * a; }")
    source = source.replace("f.out[x, y | 1] = 0.0;", "f.out[x, y | 1] = Sq(3.0) * 0.0;")
    _check(tmp_path, backend, layout, source, 2.0 * V)


H_ZERO = "function H(real c) -> (real e) { real k = 0.0; e = c / k; }"

NOT_CALLS_OF_CONSTANTS = [
    pytest.param("function F(real a) -> (real b) { a = 0.0; b = 1.0 / a; }",
                 "f.out[x, y | 1] = F(v) + v * 0.0;",
                 id="a parameter the body stores a constant into"),
    pytest.param(H_ZERO + "\nfunction F(real a, real p) -> (real b) { p = p * a; b = H(p); }",
                 "f.out[x, y | 1] = F(v, 2.0) + v * 0.0;",
                 id="a copy of a constant argument overwritten, then passed on"),
    pytest.param(H_ZERO + "\nfunction R(real a) -> (real b) { real d = random() + 1.0; b = a * H(d); }",
                 "f.out[x, y | 1] = R(2.0) + v * 0.0;",
                 id="a draw passed on by a call of constants"),
    pytest.param(S_ARRAY, "array[real, 2] w = {0.0, 1.0}; f.out[x, y | 1] = S(w) + v * 0.0;",
                 id="an array variable holding constants"),
    pytest.param(A_GLOBAL + "\n" + S_ARRAY,
                 "array[real, 2] A = {v, 1.0}; f.out[x, y | 1] = S(A);",
                 id="a local array named like a global constant one"),
    pytest.param(S_ARRAY, "const array[real, 2] C = {v, 1.0}; f.out[x, y | 1] = S(C);",
                 id="a block constant array holding a variable"),
    pytest.param(S_ARRAY + "\nfunction F(real p) -> (real r) {"
                 " array[real, 2] a = {p, 1.0}; a = {random(), 1.0}; r = S(a); }",
                 "f.out[x, y | 1] = F(2.0) + v * 0.0;",
                 id="a constant array overwritten with a draw"),
    pytest.param("function Q(real a) -> (real b, real c) { c = 0.0; b = a; }\n"
                 "function E(real a) -> (real o) {"
                 " real w = random() + a; real r; real s; {r, s} = Q(w); o = 7.0 / s; }",
                 "f.out[x, y | 1] = v + E(0.0);",
                 id="a constant a call of variables stores in a call of constants"),
    pytest.param("function Q(real a) -> (array[real, 2] m, real c) { m = {0.0, 1.0}; c = a; }\n"
                 "function D(array[real, 2] a) -> (real b) { real z = 0.0; b = 7.0 / z; }\n"
                 "function E(real a) -> (real o) {"
                 " real w = random() + a; array[real, 2] m; real c; {m, c} = Q(w); o = D(m) + c; }",
                 "f.out[x, y | 1] = v + E(0.0);",
                 id="an array a call of variables stores in a call of constants"),
]


@pytest.mark.parametrize("functions, dynamic", NOT_CALLS_OF_CONSTANTS)
def test_a_value_computed_at_run_time_makes_no_call_of_constants(functions, dynamic):
    """Whether a call is a call of constants is decided from the values
    its arguments hold where it is called: a variable stored into a
    parameter's copy, or a draw, makes the calls it reaches calls of
    variables, whose locals are variables (no compile-time error)."""
    _compile(program(dynamic, functions=functions))


def test_a_constant_holding_a_call_of_constants_is_a_constant_argument():
    from gelb.utils.exceptions import GeLBExTypeError
    functions = SQ + "\nfunction F(int p) -> (int b) { int l = p * 4611686018427387904; b = l * 2; }"
    with pytest.raises(GeLBExTypeError, match=r"integer overflow.* in the call F\(a\) on line 13"):
        _compile(program("const int a = Sq(1); f.out[x, y | 1] = real(F(a));",
                         functions=functions))


def test_an_output_read_in_its_own_body_is_the_calls_own_name():
    from gelb.utils.exceptions import GeLBExTypeError
    with pytest.raises(GeLBExTypeError) as error:
        _compile(program("f.out[x, y | 1] = real(T1(3037000500));", functions=(
            "function T1(int a) -> (int p) { p = a; p = p * 3037000500; }")))
    assert "in the call T1(3037000500) on line 12" in str(error.value)
    assert "the value of" not in str(error.value)
