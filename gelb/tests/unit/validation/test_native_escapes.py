#!/usr/bin/env python3
"""Programs that reached the native compiler and failed there.

The programs here once passed ``gelbc`` with empty diagnostics and then
failed in gfortran, g++ or nvcc.  Each family below is an input the
language does not support, so each is now a source-located ``gelbc``
error.  Each family has two checks:

* the diagnostic, through ``gelbc --diagnostics-json`` as the editor
  calls it: an error at the construct's line, with the message the
  manual's wording;
* the runner, through ``scripts/gelb-run``, the path the user takes:
  the run must stop at the ``gelbc`` step with the ``[Problem]`` block,
  before any native compiler is invoked.  An emitted-text assertion
  or an empty ``--diagnostics-json`` passed on every one of these
  programs before the fix.
"""

import json
import os
import pathlib
import subprocess
import sys

import pytest

from gelb.tests.integration._toolchain import requires_compiler

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_GELB_RUN = _REPO_ROOT / "scripts" / "gelb-run"


def _program(gauge_body, *, global_constants="", functions="",
             gauge_outputs="real v", description="native diagnostic check"):
    """A one-cell program, with the construct under test."""
    return (
        f'simulation_description("{description}");\n'
        f'{global_constants}\n'
        'lattices { lattice u(1,1,real,4,false); }\n'
        f'{functions}\n'
        'initializer I { u.out[x | 0] = 1.0; }\n'
        'dynamic D { u.out[x | 0] = u.in[x | 0]; }\n'
        f'gauge G -> ({gauge_outputs}) {{ {gauge_body} }}\n'
        'node_classes { node_class BULK(I,D,G); }\n'
        'geometry { nodes[:] = BULK; }\n'
    )


def _write(tmp_path, source, name="case.gelb"):
    path = tmp_path / name
    path.write_text(source)
    return path


def _line_of(source, text):
    """1-based number of the first line of ``source`` containing ``text``."""
    return next(i for i, line in enumerate(source.splitlines(), 1)
                if text in line)


def _clean_env():
    env = dict(os.environ)
    env.pop("PYTEST_CURRENT_TEST", None)
    for name in ("GELB_FFLAGS", "GELB_CXXFLAGS", "GELB_NVCC_FLAGS",
                 "GELBC_EXTRA"):
        env.pop(name, None)
    return env


def diagnostics(tmp_path, source):
    """``gelbc --diagnostics-json`` on ``source``: (exit code, the one
    error), asserting there is exactly one error."""
    path = _write(tmp_path, source)
    result = subprocess.run(
        [sys.executable, "-m", "gelb.gelbc", str(path), "--diagnostics-json"],
        env=_clean_env(), text=True, capture_output=True, cwd=tmp_path)
    payload = json.loads(result.stdout)
    errors = [d for d in payload["diagnostics"] if d["severity"] == "error"]
    assert result.returncode == 1, result.stdout + result.stderr
    assert len(errors) == 1, payload
    return errors[0]


def assert_error_at(error, source, text, message):
    """The error names ``message`` and sits on the line of ``text``."""
    assert message in error["message"], error
    assert error["range"]["startLine"] == _line_of(source, text) - 1, error
    assert error["source"] == "gelbc"
    assert "internal" not in error["message"], error


def stops_before_the_native_compiler(tmp_path, source, message,
                                     backend="cpu_fortran_serial"):
    """``gelb-run`` on ``source`` fails at the ``gelbc`` step: the
    ``[Problem]`` block names ``message`` and no compiler was invoked."""
    path = _write(tmp_path, source)
    env = _clean_env()
    env["GELB_PYTHON"] = sys.executable
    env["OMP_NUM_THREADS"] = "1"
    result = subprocess.run(
        [str(_GELB_RUN), "-v", "-b", backend, "-n", "1", str(path)],
        env=env, text=True, capture_output=True, cwd=tmp_path)
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "[Problem]" in output, output
    assert message in output, output
    # gelb-run announces every native compilation with this line.
    assert "Compiling with" not in output, output
    assert not list(tmp_path.glob("*.f90")), "generated source was written"
    assert not list(tmp_path.glob("*.cpp")), "generated source was written"
    assert not list(tmp_path.glob("*.cu")), "generated source was written"


# ---------------------------------------------------------------------------
# An array extent that is not positive
# ---------------------------------------------------------------------------

_NEGATIVE_ARRAY = _program("array[real,-2] a; v = sum(a);")
_ZERO_ARRAY = _program("array[real,0] a; v = sum(a);")
_ZERO_MATRIX = _program("array[real,{2,0}] a; v = sum(a);")
_ZERO_GLOBAL = _program(
    "v = sum(A);", global_constants="global_constants { const int N = 0; }"
).replace("v = sum(A);", "array[real,N] A; v = sum(A);")


@pytest.mark.parametrize("source, extent, text", [
    (_NEGATIVE_ARRAY, -2, "array[real,-2]"),
    (_ZERO_ARRAY, 0, "array[real,0]"),
    (_ZERO_MATRIX, 0, "array[real,{2,0}]"),
    (_ZERO_GLOBAL, 0, "array[real,N]"),
], ids=["negative", "zero", "zero matrix axis", "zero from a constant"])
def test_a_nonpositive_array_extent_is_an_error(tmp_path, source, extent, text):
    error = diagnostics(tmp_path, source)
    assert_error_at(error, source, text,
                    f"Array extent must be at least 1, got {extent}")


def test_a_positive_extent_from_a_constant_still_compiles(tmp_path):
    source = _program(
        "array[real,N] a = {1.0, 2.0}; v = sum(a);",
        global_constants="global_constants { const int N = 2; }")
    path = _write(tmp_path, source)
    result = subprocess.run(
        [sys.executable, "-m", "gelb.gelbc", str(path), "--diagnostics-json"],
        env=_clean_env(), text=True, capture_output=True, cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["diagnostics"] == []


@requires_compiler
def test_a_nonpositive_extent_stops_the_runner_before_the_native_compiler(tmp_path):
    stops_before_the_native_compiler(
        tmp_path, _NEGATIVE_ARRAY, "Array extent must be at least 1, got -2")



# ---------------------------------------------------------------------------
# dot_prod of matrices
# ---------------------------------------------------------------------------

_DOT_MATRIX = _program(
    "array[real,{2,2}] a = {{x * 1.0,2.0},{3.0,4.0}}; v = dot_prod(a,a);")
_DOT_MATRIX_SECOND = _program(
    "array[real,2] b = {1.0, 2.0}; array[real,{2,2}] a = {{1.0,2.0},{3.0,4.0}};"
    " v = dot_prod(b, a);")
_DOT_VECTOR = _program(
    "array[real,2] a = {x * 1.0, 2.0}; v = dot_prod(a, a);")


def test_dot_prod_of_matrices_is_an_error(tmp_path):
    error = diagnostics(tmp_path, _DOT_MATRIX)
    assert_error_at(error, _DOT_MATRIX, "dot_prod(a,a)",
                    "Function 'dot_prod' takes vectors; argument 1 is a "
                    "2-dimensional array")


def test_dot_prod_matrix_may_be_the_second_argument(tmp_path):
    error = diagnostics(tmp_path, _DOT_MATRIX_SECOND)
    assert "argument 2 is a 2-dimensional array" in error["message"], error


def test_dot_prod_of_vectors_still_compiles(tmp_path):
    path = _write(tmp_path, _DOT_VECTOR)
    result = subprocess.run(
        [sys.executable, "-m", "gelb.gelbc", str(path), "--diagnostics-json"],
        env=_clean_env(), text=True, capture_output=True, cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["diagnostics"] == []


@requires_compiler
def test_dot_prod_of_matrices_stops_the_runner_before_the_native_compiler(tmp_path):
    stops_before_the_native_compiler(
        tmp_path, _DOT_MATRIX, "Function 'dot_prod' takes vectors")


# ---------------------------------------------------------------------------
# A real literal outside binary64
# ---------------------------------------------------------------------------

_NONFINITE_LITERAL = _program("v = 1.0e400;")
_NONFINITE_GLOBAL = _program(
    "v = a;", global_constants="global_constants {const real a = 1e400;}")
_LARGEST_LITERAL = _program("v = 1.7e308;")
_OVERRIDDEN = _program(
    "v = A;", global_constants="global_constants { const real A = 1.0; }")


def test_a_real_literal_outside_the_range_is_an_error(tmp_path):
    error = diagnostics(tmp_path, _NONFINITE_LITERAL)
    assert_error_at(error, _NONFINITE_LITERAL, "1.0e400",
                    "Real literal 1.0e400 is outside the range of real")


def test_a_real_literal_outside_the_range_in_a_global_constant_too(tmp_path):
    error = diagnostics(tmp_path, _NONFINITE_GLOBAL)
    assert_error_at(error, _NONFINITE_GLOBAL, "1e400",
                    "Real literal 1e400 is outside the range of real")


def test_the_largest_finite_literal_compiles(tmp_path):
    path = _write(tmp_path, _LARGEST_LITERAL)
    result = subprocess.run(
        [sys.executable, "-m", "gelb.gelbc", str(path), "--diagnostics-json"],
        env=_clean_env(), text=True, capture_output=True, cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["diagnostics"] == []


@pytest.mark.parametrize("value", ["1e400", "inf", "nan", "-inf"])
def test_a_define_override_outside_the_range_is_an_error(tmp_path, value):
    """The same rule for a value given on the command line, which no
    literal rule sees."""
    path = _write(tmp_path, _OVERRIDDEN)
    result = subprocess.run(
        [sys.executable, "-m", "gelb.gelbc", str(path), "--diagnostics-json",
         "-D", f"A={value}"],
        env=_clean_env(), text=True, capture_output=True, cwd=tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    [error] = json.loads(result.stdout)["diagnostics"]
    assert f"Value '{value}' for constant 'A' is outside the range of real" \
        in error["message"], error


@requires_compiler
def test_an_out_of_range_literal_stops_the_runner_before_the_native_compiler(tmp_path):
    stops_before_the_native_compiler(
        tmp_path, _NONFINITE_LITERAL,
        "Real literal 1.0e400 is outside the range of real")


# ---------------------------------------------------------------------------
# random() in a global constant
# ---------------------------------------------------------------------------

_GLOBAL_RANDOM = _program(
    "v = a;", global_constants="global_constants {const real a = random();}")
_GLOBAL_RANDOM_NESTED = _program(
    "v = a;",
    global_constants="global_constants {const real a = 2.0 * (1.0 + random());}")
_GLOBAL_RANDOM_IN_ARRAY = _program(
    "v = a[0];",
    global_constants="global_constants {const array[real, 2] a = {random(), 1.0};}")
_LOCAL_RANDOM = _program("v = random();")


@pytest.mark.parametrize("source", [
    _GLOBAL_RANDOM, _GLOBAL_RANDOM_NESTED, _GLOBAL_RANDOM_IN_ARRAY,
], ids=["alone", "in an expression", "in an array constructor"])
def test_random_in_a_global_constant_is_an_error(tmp_path, source):
    error = diagnostics(tmp_path, source)
    assert_error_at(error, source, "random()",
                    "random() in the global constant 'a'")
    assert error["range"]["startCol"] == source.splitlines()[1].index("random()")


def test_random_in_a_gauge_still_compiles(tmp_path):
    path = _write(tmp_path, _LOCAL_RANDOM)
    result = subprocess.run(
        [sys.executable, "-m", "gelb.gelbc", str(path), "--diagnostics-json"],
        env=_clean_env(), text=True, capture_output=True, cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["diagnostics"] == []


@requires_compiler
def test_random_in_a_global_constant_stops_the_runner_before_the_native_compiler(tmp_path):
    stops_before_the_native_compiler(
        tmp_path, _GLOBAL_RANDOM, "random() in the global constant 'a'")


# ---------------------------------------------------------------------------
# A user function called in a global constant
# ---------------------------------------------------------------------------

_F_REAL = "function F(real z) -> (real y) {y = z*2.0;}"
_GLOBAL_USER_FUNCTION = _program(
    "v = a;", global_constants="global_constants {const real a = F(2.0);}",
    functions=_F_REAL)
_GLOBAL_USER_FUNCTION_INTEGER = _program(
    "v = real(n);",
    global_constants="global_constants {const int n = 1 + Twice(2);}",
    functions="function Twice(int k) -> (int m) {m = 2*k;}")
_USER_FUNCTION_IN_GAUGE = _program("v = F(u.in[x | 0]);", functions=_F_REAL)


def test_a_user_function_in_a_global_constant_is_an_error(tmp_path):
    error = diagnostics(tmp_path, _GLOBAL_USER_FUNCTION)
    assert_error_at(error, _GLOBAL_USER_FUNCTION, "F(2.0)",
                    "Function 'F' called in the global constant 'a'")
    assert "not in this version" in error["hint"]


def test_an_integer_user_function_nested_in_an_expression(tmp_path):
    error = diagnostics(tmp_path, _GLOBAL_USER_FUNCTION_INTEGER)
    assert_error_at(error, _GLOBAL_USER_FUNCTION_INTEGER, "Twice(2)",
                    "Function 'Twice' called in the global constant 'n'")


def test_a_user_function_in_a_gauge_still_compiles(tmp_path):
    path = _write(tmp_path, _USER_FUNCTION_IN_GAUGE)
    result = subprocess.run(
        [sys.executable, "-m", "gelb.gelbc", str(path), "--diagnostics-json"],
        env=_clean_env(), text=True, capture_output=True, cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["diagnostics"] == []


@requires_compiler
def test_a_user_function_in_a_global_constant_stops_the_runner_before_the_native_compiler(tmp_path):
    stops_before_the_native_compiler(
        tmp_path, _GLOBAL_USER_FUNCTION,
        "Function 'F' called in the global constant 'a'")


# ---------------------------------------------------------------------------
# An array-valued gauge output
# ---------------------------------------------------------------------------

_ARRAY_GAUGE = _program("v = {real(x),1.0};", gauge_outputs="array[real,2] v")
_MATRIX_GAUGE = _program(
    "w = 1.0; m = {{1.0, 2.0}, {3.0, 4.0}};",
    gauge_outputs="real w, array[real,{2,2}] m")
_LOCAL_ARRAY_IN_GAUGE = _program(
    "array[real,2] a = {real(x),1.0}; v = a[0]; w = a[1];",
    gauge_outputs="real v, real w")


def test_an_array_valued_gauge_output_is_an_error(tmp_path):
    error = diagnostics(tmp_path, _ARRAY_GAUGE)
    assert_error_at(error, _ARRAY_GAUGE, "array[real,2] v",
                    "Gauge 'G' output 'v' is an array")
    assert "not in this version" in error["hint"]


def test_a_matrix_gauge_output_after_a_scalar_one(tmp_path):
    error = diagnostics(tmp_path, _MATRIX_GAUGE)
    assert_error_at(error, _MATRIX_GAUGE, "array[real,{2,2}] m",
                    "Gauge 'G' output 'm' is an array")


def test_a_local_array_split_into_scalar_outputs_compiles(tmp_path):
    path = _write(tmp_path, _LOCAL_ARRAY_IN_GAUGE)
    result = subprocess.run(
        [sys.executable, "-m", "gelb.gelbc", str(path), "--diagnostics-json"],
        env=_clean_env(), text=True, capture_output=True, cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["diagnostics"] == []


@requires_compiler
def test_an_array_valued_gauge_output_stops_the_runner_before_the_native_compiler(tmp_path):
    stops_before_the_native_compiler(
        tmp_path, _ARRAY_GAUGE, "Gauge 'G' output 'v' is an array")


# ---------------------------------------------------------------------------
# Boolean ordering has no meaning
# ---------------------------------------------------------------------------

_BOOL_LT = _program("bool a = x > 0; bool b = x > 1; v = int(a < b);")
_BOOL_GE_ARRAYS = _program(
    "array[bool,2] a = {x > 0, x > 1}; array[bool,2] c = a >= a; v = int(c[0]);")
_BOOL_EQ = _program("bool a = x > 0; bool b = x > 1; v = int(a == b) + int(a != b);")
_BOOL_INT_ORDER = _program("bool a = x > 0; bool b = x > 1; v = int(int(a) < int(b));")


@pytest.mark.parametrize("source, text, symbol", [
    (_BOOL_LT, "a < b", "<"),
    (_BOOL_GE_ARRAYS, "a >= a", ">="),
], ids=["scalars", "arrays"])
def test_an_ordering_comparison_of_bools_is_an_error(tmp_path, source, text, symbol):
    error = diagnostics(tmp_path, source)
    assert_error_at(error, source, text,
                    f"Boolean values have no order: '{symbol}' on bool operands")


@pytest.mark.parametrize("source", [_BOOL_EQ, _BOOL_INT_ORDER],
                         ids=["== and !=", "ordered as integers"])
def test_bool_equality_and_integer_ordering_still_compile(tmp_path, source):
    path = _write(tmp_path, source)
    result = subprocess.run(
        [sys.executable, "-m", "gelb.gelbc", str(path), "--diagnostics-json"],
        env=_clean_env(), text=True, capture_output=True, cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["diagnostics"] == []


@requires_compiler
def test_bool_ordering_stops_the_runner_before_the_native_compiler(tmp_path):
    stops_before_the_native_compiler(
        tmp_path, _BOOL_LT, "Boolean values have no order")
