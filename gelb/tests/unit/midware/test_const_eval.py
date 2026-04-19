#!/usr/bin/env python3
"""The one compile-time evaluator (user manual, Numerical semantics: Types
and promotion; Library functions; Constant folding).

The first half checks ``gelb.midware.ast_eval``'s value-level
operations, one test per rule; the second half checks that the constant
folder, the geometry's expression evaluator and the exact simplifier
give a program the same values through it, and that what the contract
makes a compile-time error is reported as one.
"""

import math

import numpy as np
import pytest

from gelb.frontend.stage1_frontend import get_ast
from gelb.gelb_ast.ASTNodes import (
    Array1DLiteral_N,
    IntLiteral_N, IntrinsicFunctionCall_N, Mul_N, RealLiteral_N,
    TypePromotionNode_N)
from gelb.midware import ast_eval as ev
from gelb.midware.ast_eval import (
    IntegerOverflow, InvalidConversion, eval_const_expr)
from gelb.midware.stage2_midware import validate_division_by_zero
from gelb.tests.test_utils import minimal_gelb_program_1d
from gelb.tests.unit.midware.midware_test_utils import get_midware_processed_ast
from gelb.utils.exceptions import GeLBExTypeError

f32 = np.float32
i8 = np.int8


def _same(a, b):
    """Equal values of the same width; zeros compare by sign too."""
    if type(a) is not type(b):
        return False
    if isinstance(a, (float, np.floating)):
        if math.isnan(float(a)) or math.isnan(float(b)):
            return math.isnan(float(a)) and math.isnan(float(b))
        return float(a) == float(b) and \
            math.copysign(1.0, float(a)) == math.copysign(1.0, float(b))
    return a == b


# --- mod, division, min, max, abs --------------------------------------

@pytest.mark.parametrize("a,b,expected", [
    (-7, 2, -1), (7, -2, 1), (-7, -2, -1), (7, 2, 1),
    (i8(-7), i8(2), i8(-1)),
    (-7.5, 2.0, -1.5), (7.5, -2.0, 1.5),
    (f32(-7.5), f32(2.0), f32(-1.5)),
])
def test_mod_is_the_truncated_remainder_with_the_dividends_sign(a, b, expected):
    assert _same(ev.truncated_mod(a, b), expected)


@pytest.mark.parametrize("a,b", [(7, 0), (7.0, 0.0), (f32(7), f32(0)), (i8(7), i8(0))])
def test_mod_by_zero_is_a_zero_divisor(a, b):
    with pytest.raises(ZeroDivisionError):
        ev.truncated_mod(a, b)


@pytest.mark.parametrize("a,b,expected", [
    (-7, 2, -3), (7, -2, -3), (-7, -2, 3), (7, 2, 3),
    (i8(-7), i8(2), i8(-3)),
])
def test_integer_division_truncates_toward_zero(a, b, expected):
    assert _same(ev.divide(a, b), expected)
    assert _same(ev.int_div(a, b), expected)


def test_a_real_division_by_zero_is_a_zero_divisor_too():
    with pytest.raises(ZeroDivisionError):
        ev.divide(1.0, 0.0)
    with pytest.raises(ZeroDivisionError):
        ev.divide(f32(1.0), f32(-0.0))


def test_the_minimum_divided_by_minus_one_overflows():
    with pytest.raises(IntegerOverflow):
        ev.divide(-2 ** 63, -1)
    with pytest.raises(IntegerOverflow):
        ev.divide(i8(-128), i8(-1))


def test_min_and_max_of_integers_are_integers():
    assert _same(ev.minimum(3, 5), 3) and _same(ev.maximum(3, 5), 5)
    assert _same(ev.minimum(i8(3), i8(5)), i8(3))


def test_min_and_max_of_reals_follow_ieee_minimum_and_maximum():
    # -0 is less than +0
    assert _same(ev.minimum(0.0, -0.0), -0.0)
    assert _same(ev.minimum(-0.0, 0.0), -0.0)
    assert _same(ev.maximum(-0.0, 0.0), 0.0)
    assert _same(ev.maximum(0.0, -0.0), 0.0)
    # a NaN operand gives NaN
    assert math.isnan(ev.minimum(math.nan, 1.0))
    assert math.isnan(ev.maximum(1.0, math.nan))
    assert _same(ev.minimum(f32(1.5), f32(-2.5)), f32(-2.5))


def test_abs_keeps_the_width_and_clears_the_sign_of_zero():
    assert _same(ev.absolute(-3), 3)
    assert _same(ev.absolute(i8(-3)), i8(3))
    assert _same(ev.absolute(-0.0), 0.0)
    assert _same(ev.absolute(f32(-1.5)), f32(1.5))


def test_abs_of_the_minimum_integer_overflows():
    with pytest.raises(IntegerOverflow):
        ev.absolute(-2 ** 63)
    with pytest.raises(IntegerOverflow):
        ev.absolute(i8(-128))


# --- integer overflow is an error ----------------------------------------

@pytest.mark.parametrize("operation", [
    lambda: ev.add(2 ** 63 - 1, 1),
    lambda: ev.sub(-2 ** 63, 1),
    lambda: ev.mul(2 ** 32, 2 ** 31),
    lambda: ev.negate(-2 ** 63),
    lambda: ev.add(i8(100), i8(100)),
    lambda: ev.sub(np.int16(-32768), np.int16(1)),
    lambda: ev.mul(np.int32(65536), np.int32(32768)),
    lambda: ev.negate(np.int32(-2 ** 31)),
])
def test_an_integer_result_outside_its_width_is_an_overflow(operation):
    with pytest.raises(IntegerOverflow):
        operation()


def test_integer_arithmetic_within_the_width_is_exact():
    assert _same(ev.add(2 ** 62, 2 ** 62 - 1), 2 ** 63 - 1)
    assert _same(ev.sub(-2 ** 63 + 1, 1), -2 ** 63)
    assert _same(ev.mul(i8(-8), i8(16)), i8(-128))
    assert _same(ev.negate(np.int32(2 ** 31 - 1)), np.int32(-2 ** 31 + 1))


# --- powers ----------------------------------------------------------------

@pytest.mark.parametrize("base,exponent,expected", [
    (2, 10, 1024), (-2, 3, -8), (7, 0, 1), (0, 0, 1),
    (2, -1, 0), (-3, -2, 0), (1, -5, 1), (-1, -3, -1), (-1, -2, 1),
    (i8(2), i8(6), i8(64)),
])
def test_an_integer_power_is_exact_with_fortrans_negative_exponent_rule(
        base, exponent, expected):
    assert _same(ev.power(base, exponent), expected)


def test_zero_to_a_negative_power_is_a_zero_divisor():
    with pytest.raises(ZeroDivisionError):
        ev.power(0, -1)


@pytest.mark.parametrize("base,exponent", [(2, 63), (2, 64), (10, 1000), (i8(2), i8(7))])
def test_an_integer_power_outside_its_width_is_an_overflow(base, exponent):
    with pytest.raises(IntegerOverflow):
        ev.power(base, exponent)


def test_a_real_base_uses_the_hosts_pow_rounded_once_to_its_width():
    assert _same(ev.power(2.0, 0.5), math.pow(2.0, 0.5))
    assert _same(ev.power(1.1, 3), math.pow(1.1, 3.0))
    assert _same(ev.power(f32(1.1), 3), f32(math.pow(float(f32(1.1)), 3.0)))
    assert _same(ev.power(f32(1.1), f32(0.5)), f32(math.pow(float(f32(1.1)), 0.5)))
    with pytest.raises(ValueError):          # a domain error, not a complex number
        ev.power(-8.0, 1.0 / 3.0)
    with pytest.raises(OverflowError):
        ev.power(10.0, 400.0)


# --- conversions -------------------------------------------------------------

@pytest.mark.parametrize("value,dtype,expected", [
    (3.9, 'int', 3), (-3.9, 'int', -3), (f32(3.9), 'int32', np.int32(3)),
    (300, 'int8', i8(44)), (2 ** 31, 'int32', np.int32(-2 ** 31)),
    (-129, 'int8', i8(127)),
    (16777217, 'real32', f32(16777216.0)),
    (2 ** 54 + 2 ** 30 + 1, 'real32', f32(18014399583223812.0)),   # direct, not through binary64
    (True, 'real', 1.0), (False, 'int', 0), (True, 'int8', i8(1)),
    (0.1, 'real32', f32(0.1)), (f32(0.1), 'real', float(f32(0.1))),
])
def test_conversions(value, dtype, expected):
    assert _same(ev.convert(value, dtype), expected)


@pytest.mark.parametrize("value,dtype", [
    (math.nan, 'int'), (math.inf, 'int'), (-math.inf, 'int32'),
    (1e300, 'int'), (300.0, 'int8'), (-129.0, 'int8'), (2 ** 63 + 0.0, 'int'),
    (f32(3e9), 'int32'),
])
def test_a_nan_infinite_or_out_of_range_real_to_integer_is_an_error(value, dtype):
    with pytest.raises(InvalidConversion):
        ev.convert(value, dtype)


# --- the library --------------------------------------------------------------

@pytest.mark.parametrize("name", ["sqrt", "exp", "log", "sin", "cos", "tan", "tanh"])
def test_a_library_function_uses_the_hosts_binary64_library_rounded_once(name):
    fn = getattr(math, name)
    assert _same(ev.library(name, 0.5), fn(0.5))
    # a real32 argument: the binary64 result of the argument's value,
    # rounded once to real32 (not a binary32 library)
    assert _same(ev.library(name, f32(0.5)), f32(fn(float(f32(0.5)))))
    assert _same(ev.intrinsic(name, [f32(0.5)]), f32(fn(float(f32(0.5)))))


def test_a_library_domain_error_or_overflow_raises_outside_the_ieee_mode():
    # the geometry evaluator and the simplifier see the exception and
    # leave the expression; the folder runs in the IEEE mode (below)
    with pytest.raises(OverflowError):          # a pole: -infinity
        ev.library('log', 0.0)
    with pytest.raises(ValueError):             # a domain error: NaN
        ev.library('sqrt', -1.0)
    with pytest.raises(ValueError):
        ev.library('log', -1.0)
    with pytest.raises(OverflowError):
        ev.library('exp', 1000.0)


def test_a_library_domain_error_or_overflow_is_the_ieee_value_in_the_ieee_mode():
    with ev.ieee_special_values():
        assert ev.library('log', 0.0) == -math.inf
        assert math.isnan(ev.library('sqrt', -1.0))
        assert math.isnan(ev.library('log', -1.0))
        assert ev.library('exp', 1000.0) == math.inf
        assert ev.library('exp', f32(100.0)) == f32(math.inf)   # in its width
        assert math.isnan(ev.power(-8.0, 1.0 / 3.0))
        assert ev.power(10.0, 400.0) == math.inf
        assert ev.power(-10.0, 401.0) == -math.inf
        assert ev.power(0.0, -1.0) == math.inf


def test_atan2_takes_the_common_real_width():
    assert _same(ev.atan2(1.0, 1.0), math.atan2(1.0, 1.0))
    assert _same(ev.atan2(f32(1.0), f32(1.0)), f32(math.atan2(1.0, 1.0)))
    assert _same(ev.atan2(1, 2), math.atan2(1.0, 2.0))


# --- widths --------------------------------------------------------------------

def test_a_result_takes_the_table_width_and_rounds_once():
    assert _same(ev.add(i8(1), 1), 2)                       # int8 with int is int
    assert _same(ev.add(f32(1.0), 1), f32(2.0))             # real32 with int is real32
    assert _same(ev.mul(f32(0.1), 0.1), float(f32(0.1)) * 0.1)   # real32 with real is real
    assert _same(ev.add(f32(16777216.0), f32(1.0)), f32(16777216.0))   # one binary32 rounding
    assert _same(ev.add(True, True), 2)                      # bool with bool is int
    assert ev.width_of(ev.mul(i8(2), i8(3))) == 'int8'


# --- the passes agree ------------------------------------------------------------

def _folded_constant(decl, name="R"):
    code = minimal_gelb_program_1d(initializer_content=f"{decl}\nf.out[x | 0] = 0;")
    ast = get_midware_processed_ast(code)
    for stmt in ast.initializers[0].stmts:
        if getattr(getattr(stmt, "name", None), "name", None) == name:
            node = stmt.value
            while isinstance(node, TypePromotionNode_N):
                node = node.expr
            return node
    raise AssertionError(f"no constant {name}")


@pytest.mark.parametrize("decl,kind,expected", [
    ("const int R = mod(-7, 2);", IntLiteral_N, -1),
    ("const int R = mod(7, -2);", IntLiteral_N, 1),
    ("const real R = mod(-7.5, 2.0);", RealLiteral_N, -1.5),
    ("const int R = 2^(-1);", IntLiteral_N, 0),
    ("const int R = (-2)^3;", IntLiteral_N, -8),
    ("const int R = 1^(-5);", IntLiteral_N, 1),
    ("const int R = (-1)^(-3);", IntLiteral_N, -1),
    ("const int R = int(-3.9);", IntLiteral_N, -3),
    ("const int8 R = int8(300);", IntLiteral_N, 44),
    ("const int R = min(3, 5);", IntLiteral_N, 3),
    ("const int R = abs(-9223372036854775807);", IntLiteral_N, 9223372036854775807),
    ("const int R = -9223372036854775807 - 1;", IntLiteral_N, -9223372036854775808),
])
def test_the_folder_folds_through_the_evaluator(decl, kind, expected):
    node = _folded_constant(decl)
    assert isinstance(node, kind)
    assert node.value == expected


def test_the_folder_rounds_a_real32_library_result_once():
    node = _folded_constant("const real32 W = 0.5; const real32 R = sin(W);")
    assert isinstance(node, RealLiteral_N)
    assert node.value == float(f32(math.sin(0.5)))
    assert node.inferred_type.element_dtype == "real32"


def test_the_folder_folds_a_transcendental_on_the_rounded_argument():
    # the division rounds first, in its width, then the host's exp
    node = _folded_constant("const real TAU = 0.6; const real R = exp(-1.0 / TAU);")
    assert isinstance(node, RealLiteral_N)
    assert node.value == math.exp(-1.0 / 0.6)


def test_the_folder_folds_a_real_overflow_and_a_domain_error_to_the_ieee_value():
    # the value the run time would give, which the backends write as an
    # explicit special value (user manual, Numerical semantics: Special
    # values)
    assert _folded_constant("const real R = exp(1000.0);").value == math.inf
    assert _folded_constant("const real R = log(0.0);").value == -math.inf
    assert math.isnan(_folded_constant("const real R = sqrt(-1.0);").value)
    assert _folded_constant("const real R = 1e308 * 10.0;").value == math.inf
    assert _folded_constant("const real R = -(1e308 * 10.0);").value == -math.inf


@pytest.mark.parametrize("decl,match", [
    ("const int R = 9223372036854775807 + 1;", "overflow"),
    ("const int R = -(-9223372036854775807 - 1);", "overflow"),
    ("const int8 R = int8(100) + int8(100);", "overflow"),
    ("const int R = 2^63;", "overflow"),
    ("const int R = abs(-9223372036854775807 - 1);", "overflow"),
    ("const int R = int(1e300);", "out of range"),
    ("const int8 R = int8(300.0);", "out of range"),
    ("const int R = mod(7, 0);", "mod by zero"),
    ("const real R = mod(7.0, 0.0);", "mod by zero"),
    ("const int R = 0^(-2);", "negative integer power"),
])
def test_what_the_contract_makes_an_error_is_reported(decl, match):
    # the folder reports an overflow or an invalid conversion itself; a
    # visible zero divisor is left for the validator that follows it
    code = minimal_gelb_program_1d(initializer_content=f"{decl}\nf.out[x | 0] = 0;")
    with pytest.raises(GeLBExTypeError, match=match):
        validate_division_by_zero(get_midware_processed_ast(code))


def test_a_constant_stored_at_a_width_it_does_not_fit_is_an_error():
    code = minimal_gelb_program_1d(
        initializer_content="const int8 A = 300.0;\nconst int B = A;\nf.out[x | 0] = 0;")
    with pytest.raises(GeLBExTypeError, match="out of range"):
        get_midware_processed_ast(code)


def test_the_geometry_evaluator_agrees():
    # the same functions evaluate a where-predicate's expression
    assert eval_const_expr(get_ast("expr", "mod(x - 7, 2)"), {"x": 0}) == -1
    assert eval_const_expr(get_ast("expr", "mod(x - 7, 2)"), {"x": 1}) == 0
    assert eval_const_expr(get_ast("expr", "2^(-1)")) == 0
    assert eval_const_expr(get_ast("expr", "(-2)^3")) == -8
    assert eval_const_expr(get_ast("expr", "int(-3.9)")) == -3
    with pytest.raises(IntegerOverflow):
        eval_const_expr(get_ast("expr", "x + 1"), {"x": 2 ** 63 - 1})


# --- a real overflow raises outside the IEEE mode, is the infinity inside ---

def test_a_real_overflow_or_invalid_operation_raises_outside_the_ieee_mode():
    with pytest.raises(OverflowError):
        ev.mul(1.0e308, 10.0)
    with pytest.raises(OverflowError):
        ev.add(1.7e308, 1.7e308)
    with pytest.raises(OverflowError):
        ev.convert(1.0e300, 'real32')
    with pytest.raises(OverflowError):
        ev.mul(f32(1.0e38), f32(10.0))
    # an operand that is already non-finite propagates
    assert math.isnan(ev.sub(math.inf, math.inf))
    assert ev.add(math.inf, 1.0) == math.inf


def test_the_simplifier_leaves_an_overflowing_product_and_the_folder_writes_the_infinity():
    # the slice simplifier folds literal-only subtrees with the same
    # evaluator, outside the IEEE mode: 1.0e308 * 10.0 stays a product
    # there; the folder, which runs first, writes the infinity, and the
    # backends emit it as an explicit special value, never as an "inf"
    # token
    from gelb.midware.ast_simplify import simplify_exact
    tree = get_ast("expr", "1.0e308 * 10.0")
    assert isinstance(simplify_exact(tree), Mul_N)
    folded = _folded_constant("const real R = 1.0e308 * 10.0;")
    assert isinstance(folded, RealLiteral_N) and folded.value == math.inf


# --- reductions of constants fold in the element width; a real narrowed
# --- past its range is the infinity ----------------------------------------

@pytest.mark.parametrize("decl,kind,expected", [
    # an integer sum is exact: the low bit survives
    ("const int R = sum({9007199254740993, 0});", IntLiteral_N, 9007199254740993),
    ("const int R = sum({9007199254740993, 0}) - 9007199254740992;", IntLiteral_N, 1),
    # a real32 dot product rounds each product and each sum to binary32
    ("const real32 R = dot_prod({real32(1.3), real32(1.0)},"
     " {real32(0.3), real32(-0.39000001549720764)});", RealLiteral_N, 0.0),
    # named constants, in a block, fold the same way
    ("const array[int, 2] BIG = {9007199254740993, 0}; const int R = sum(BIG);",
     IntLiteral_N, 9007199254740993),
    ("const array[real32, 2] P = {1.3, 1.0};"
     " const array[real32, 2] Q = {0.3, -0.39000001549720764};"
     " const real32 R = dot_prod(P, Q);", RealLiteral_N, 0.0),
    ("const array[real, 3] W = {0.5, 0.25, 0.125}; const real R = sum(W);",
     RealLiteral_N, 0.875),
])
def test_a_reduction_of_constants_folds_in_its_width(decl, kind, expected):
    assert float(f32(1.3)) * float(f32(0.3)) + float(f32(-0.39000001549720764)) != 0.0
    node = _folded_constant(decl)
    assert isinstance(node, kind)
    assert node.value == expected


def test_a_reduction_that_overflows_folds_to_the_infinity():
    assert _folded_constant("const real R = sum({1.0e308, 1.0e308});").value == math.inf
    assert _folded_constant("const real R = dot_prod({1.0e308, 0.0}, {10.0, 0.0});").value == math.inf


def test_an_integer_sum_outside_its_width_is_an_error():
    with pytest.raises(GeLBExTypeError, match="overflow"):
        _folded_constant("const int R = sum({9223372036854775807, 1});")


def test_matmul_of_constants_folds_in_the_element_width():
    node = _folded_constant(
        "const array[real32, {2, 2}] M = {{1.3, 0.0}, {0.0, 1.0}};"
        " const array[real32, 2] V = {0.3, 2.0};"
        " const array[real32, 2] R = matmul(M, V);")
    assert isinstance(node, Array1DLiteral_N)
    values = [e.value for e in node.value.elements]
    # row 0: f32(1.3) * f32(0.3) rounded to binary32, plus 0 * 2
    assert values[0] == float(f32(f32(1.3) * f32(0.3)))
    assert values[0] != float(f32(1.3)) * float(f32(0.3))
    assert values[1] == 2.0
    assert node.inferred_type.element_dtype == "real32"


def test_an_integer_matmul_stays_integer():
    node = _folded_constant(
        "const array[int, {2, 2}] M = {{2, 0}, {0, 3}};"
        " const array[int, 2] V = {4, 5};"
        " const array[int, 2] R = matmul(M, V);")
    assert isinstance(node, Array1DLiteral_N)
    assert all(isinstance(e, IntLiteral_N) for e in node.value.elements)
    assert [e.value for e in node.value.elements] == [8, 15]


def test_a_real_narrowed_past_its_range_is_the_real32_infinity():
    # the cast folds to the infinity in its width, as in a block-local
    # const; a named real32 constant too large for its width is that infinity
    # wherever it is used; an integer conversion out of range, or of an
    # infinity, is still an error
    node = _folded_constant("const real R = real32(1.0e300);")
    assert isinstance(node, RealLiteral_N) and node.value == math.inf
    node = _folded_constant("const real32 W = 1.0e300; const real R = W * 2.0;")
    assert isinstance(node, RealLiteral_N) and node.value == math.inf
    with pytest.raises(GeLBExTypeError, match="out of range"):
        _folded_constant("const int R = int(1.0e300);")
    with pytest.raises(GeLBExTypeError, match="cannot convert inf"):
        _folded_constant("const int R = int(1.0e300 * 1.0e300);")


# --- an array operand converted past its width is the infinity, and the
# --- reduction folds with it ------------------------------------------------

@pytest.mark.parametrize("decl", [
    "const array[real32, 2] A = {1.0e300, 1.0}; const real R = sum(A);",
    "const array[real32, 2] A = {1.0e300, 1.0}; const array[real32, 2] C = {1.0, 1.0};"
    " const real R = dot_prod(A, C);",
])
def test_a_reduction_whose_operand_overflows_its_width_folds_to_the_infinity(decl):
    node = _folded_constant(decl)
    assert isinstance(node, RealLiteral_N) and node.value == math.inf


def test_a_matmul_whose_operand_overflows_its_width_folds_with_the_infinity():
    node = _folded_constant(
        "const array[real32, {2, 2}] M = {{1.0e300, 0.0}, {0.0, 1.0}};"
        " const array[real32, 2] V = {1.0, 2.0}; const array[real32, 2] R = matmul(M, V);")
    assert isinstance(node, Array1DLiteral_N)
    first, second = node.value.elements
    assert first.value == math.inf and second.value == 2.0


def test_a_matrix_intrinsic_on_an_element_past_its_width_is_an_error():
    code = minimal_gelb_program_1d(
        global_constants_content="const array[real32, {2, 2}] M = {{1.0e300, 0.0}, {0.0, 1.0}};"
                                 " const array[real32, {2, 2}] R = inverse(M);",
        initializer_content="f.out[x | 0] = 0;")
    with pytest.raises(GeLBExTypeError, match="constant matrix"):
        get_midware_processed_ast(code)


# --- an overflowing constant-array element expression passes the frontend --

@pytest.mark.parametrize("element", ["real32(1.0e300)", "1.0e300 * 1.0e300"])
def test_an_overflowing_constant_array_element_passes_the_frontend(element):
    code = minimal_gelb_program_1d(
        global_constants_content=f"const array[real32, 2] A = {{{element}, 1.0}};",
        initializer_content="f.out[x | 0] = 0;")
    ast = get_midware_processed_ast(code)      # no OverflowError
    assert ast is not None


def test_an_overflowing_constant_needed_for_a_shape_is_a_diagnostic():
    from gelb.utils.exceptions import GeLBException
    code = minimal_gelb_program_1d(
        global_constants_content="const real BIG = 1.0e300 * 1.0e300;",
        initializer_content="array[real, int(BIG)] a; f.out[x | 0] = 0;")
    with pytest.raises(GeLBException):
        get_midware_processed_ast(code)


def test_the_evaluators_ieee_mode_gives_the_special_values():
    with ev.ieee_special_values():
        assert math.isinf(ev.convert(1.0e300, "real32"))
        assert math.isinf(ev.mul(1.0e300, 1.0e300))
    with pytest.raises(OverflowError):
        ev.convert(1.0e300, "real32")
