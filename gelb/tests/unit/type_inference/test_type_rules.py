#!/usr/bin/env python3
"""The one promotion rule (user manual, Numerical semantics: Types and
promotion), one test per row.

The first half checks the table in ``gelb.frontend.type_rules``
directly; the second half checks that the three passes that used to
carry their own copy -- type inference, type promotion and the
intrinsic table -- give a program the same types, with the argument
conversions the rule implies inserted.  ``real16`` is not in this
version: every spelling is rejected where the parser builds it.
"""

import pytest

from gelb.frontend.stage1_frontend import promote_types
from gelb.frontend.type_rules import (
    arithmetic_result_type, common_type, intrinsic_argument_types,
    intrinsic_result_type)
from gelb.gelb_ast.ASTNodes import (
    IntrinsicFunctionCall_N, TypePromotionNode_N)
from gelb.tests.test_utils import get_typed_ast, minimal_gelb_program_1d
from gelb.utils.exceptions import GeLBExTypeError


# --- The table ----------------------------------------------------------

# (left, right, result): the table's rows for the arithmetic operators.
_ARITHMETIC_ROWS = [
    ("int", "real", "real"),
    ("int", "real32", "real32"),        # the integer converts to real32
    ("real32", "real", "real"),         # widest real operand
    ("real32", "real32", "real32"),
    ("real", "real64", "real64"),       # alias; the explicit spelling wins
    ("int8", "int8", "int8"),           # narrow integers are not widened
    ("int8", "int", "int"),             # ... unless the other operand is
    ("int8", "int16", "int16"),
    ("int16", "int32", "int32"),
    ("int32", "int64", "int64"),
    ("int", "int64", "int64"),
    ("bool", "bool", "int"),            # bool with bool gives int
    ("bool", "int8", "int8"),           # bool with a numeric type takes it
    ("bool", "int", "int"),
    ("bool", "real32", "real32"),
    ("bool", "real", "real"),
]


@pytest.mark.parametrize("left,right,result", _ARITHMETIC_ROWS,
                         ids=[f"{l}+{r}" for l, r, _ in _ARITHMETIC_ROWS])
def test_the_arithmetic_table(left, right, result):
    assert arithmetic_result_type(left, right) == result
    assert arithmetic_result_type(right, left) == result


def test_bool_with_bool_is_bool_for_a_comparison_and_int_in_arithmetic():
    assert common_type("bool", "bool") == "bool"
    assert arithmetic_result_type("bool", "bool") == "int"


def test_a_type_outside_arithmetic_has_no_common_type():
    assert common_type("string", "int") is None
    assert common_type("int", None) is None
    assert arithmetic_result_type("string", "real") is None


# (name, argument types, result): the table's intrinsic result types.
_INTRINSIC_ROWS = [
    ("sqrt", ("real32",), "real32"),    # the library keeps the real width
    ("sqrt", ("real",), "real"),
    ("sqrt", ("int",), "real"),         # an integer argument gives real
    ("exp", ("int8",), "real"),
    ("sin", ("real32",), "real32"),
    ("tanh", ("real64",), "real64"),
    ("abs", ("int",), "int"),           # abs keeps its argument's type
    ("abs", ("int8",), "int8"),
    ("abs", ("real32",), "real32"),
    ("abs", ("real",), "real"),
    ("min", ("real32", "int"), "real32"),   # the table, not real
    ("max", ("int", "real32"), "real32"),
    ("min", ("real32", "real"), "real"),
    ("max", ("int8", "int8"), "int8"),
    ("mod", ("int8", "int"), "int"),
    ("mod", ("int", "int"), "int"),
    ("mod", ("real32", "real32"), "real32"),
    ("atan2", ("real32", "real32"), "real32"),  # the common real type
    ("atan2", ("real32", "int"), "real32"),
    ("atan2", ("int", "int"), "real"),          # never an integer result
    ("atan2", ("real32", "real"), "real"),
]


@pytest.mark.parametrize("name,args,result", _INTRINSIC_ROWS,
                         ids=[f"{n}({','.join(a)})" for n, a, _ in _INTRINSIC_ROWS])
def test_the_intrinsic_result_types(name, args, result):
    assert intrinsic_result_type(name, list(args)) == result


# (name, argument types, the types the arguments are converted to)
_CONVERSION_ROWS = [
    ("sqrt", ("int",), ("real",)),
    ("sqrt", ("real32",), ("real32",)),
    ("abs", ("int",), (None,)),         # nothing to convert
    ("min", ("real32", "int"), ("real32", "real32")),
    ("mod", ("int8", "int"), ("int", "int")),
    ("atan2", ("int", "int"), ("real", "real")),
    ("atan2", ("real32", "real32"), ("real32", "real32")),
    ("dot_prod", ("real", "real"), (None, None)),   # array intrinsics: none
]


@pytest.mark.parametrize("name,args,targets", _CONVERSION_ROWS,
                         ids=[f"{n}({','.join(a)})" for n, a, _ in _CONVERSION_ROWS])
def test_the_argument_conversions(name, args, targets):
    assert intrinsic_argument_types(name, list(args)) == targets


# --- The passes agree with the table -----------------------------------

def _typed_rhs(initializer_content, global_constants_content=""):
    # Inference, then promotion: the types the backends see.
    ast = promote_types(get_typed_ast(minimal_gelb_program_1d(
        global_constants_content=global_constants_content,
        initializer_content=initializer_content)))
    return ast.initializers[0].stmts.elements[-1].rhs


def _element_type(node):
    return node.inferred_type.element_dtype


def test_inference_and_promotion_give_an_int8_sum_int8():
    rhs = _typed_rhs("int8 a; int8 b; int8 c; a = 1; b = 2; c = a + b;")
    assert _element_type(rhs) == "int8"
    assert not isinstance(rhs.left, TypePromotionNode_N)
    assert not isinstance(rhs.right, TypePromotionNode_N)


def test_an_int8_with_an_int_literal_is_int():
    rhs = _typed_rhs("int8 a; int c; a = 1; c = a + 1;")
    assert _element_type(rhs) == "int"
    assert isinstance(rhs.left, TypePromotionNode_N)
    assert rhs.left.target_type.element_dtype == "int"


def test_an_integer_with_a_real32_is_real32():
    rhs = _typed_rhs("real32 w; real32 v; w = 0.5; v = w * x;")
    assert _element_type(rhs) == "real32"
    assert isinstance(rhs.right, TypePromotionNode_N)
    assert rhs.right.target_type.element_dtype == "real32"


def test_a_real32_with_a_real_literal_is_real():
    rhs = _typed_rhs("real32 w; real v; w = 0.5; v = w * 1.0;")
    assert _element_type(rhs) == "real"
    assert isinstance(rhs.left, TypePromotionNode_N)
    assert rhs.left.target_type.element_dtype == "real"


def test_a_nested_narrow_sum_is_typed_before_the_intrinsic_sees_it():
    # The intrinsic table reads the argument's inferred type; it must
    # be the table's int8, not an int that promotion later corrects.
    rhs = _typed_rhs("int8 a; int8 b; int8 c; a = 1; b = 2; c = max(a + b, b);")
    assert isinstance(rhs, IntrinsicFunctionCall_N)
    assert _element_type(rhs) == "int8"


def test_sqrt_of_a_real32_is_real32_and_of_an_integer_real():
    rhs = _typed_rhs("real32 w; real32 s; w = 2.0; s = sqrt(w);")
    assert _element_type(rhs) == "real32"
    assert not isinstance(rhs.arguments.elements[0], TypePromotionNode_N)
    rhs = _typed_rhs("real s; s = sqrt(x);")
    assert _element_type(rhs) == "real"
    arg = rhs.arguments.elements[0]
    assert isinstance(arg, TypePromotionNode_N)
    assert arg.target_type.element_dtype == "real"


def test_abs_keeps_its_argument_type():
    rhs = _typed_rhs("int k; k = abs(x - 3);")
    assert _element_type(rhs) == "int"
    assert not isinstance(rhs.arguments.elements[0], TypePromotionNode_N)
    rhs = _typed_rhs("real32 w; real32 v; w = -0.5; v = abs(w);")
    assert _element_type(rhs) == "real32"


def test_min_of_a_real32_and_an_integer_converts_the_integer_to_real32():
    rhs = _typed_rhs("real32 w; real32 v; w = 0.5; v = min(w, 1);")
    assert _element_type(rhs) == "real32"
    first, second = rhs.arguments.elements
    assert not isinstance(first, TypePromotionNode_N)
    assert isinstance(second, TypePromotionNode_N)
    assert second.target_type.element_dtype == "real32"


def test_mod_of_two_integers_stays_integer_and_widens_the_narrow_one():
    rhs = _typed_rhs("int8 a; int r; a = 7; r = mod(a, x);")
    assert _element_type(rhs) == "int"
    first, second = rhs.arguments.elements
    assert isinstance(first, TypePromotionNode_N)
    assert first.target_type.element_dtype == "int"
    assert not isinstance(second, TypePromotionNode_N)


def test_atan2_converts_both_arguments_to_the_common_real_type():
    rhs = _typed_rhs("real a; a = atan2(x, 2);")
    assert _element_type(rhs) == "real"
    for arg in rhs.arguments.elements:
        assert isinstance(arg, TypePromotionNode_N)
        assert arg.target_type.element_dtype == "real"
    rhs = _typed_rhs("real32 w; real32 a; w = 0.5; a = atan2(w, 1);")
    assert _element_type(rhs) == "real32"
    assert rhs.arguments.elements[1].target_type.element_dtype == "real32"


# --- real16 is not in this version -------------------------------------

_REAL16_SPELLINGS = [
    pytest.param("real16 h; h = 0.0;", id="declaration"),
    pytest.param("array[real16, 3] h; h = 0.0;", id="array declaration"),
    pytest.param("real h; h = real16(x);", id="cast"),
]


@pytest.mark.parametrize("initializer_content", _REAL16_SPELLINGS)
def test_real16_is_rejected_as_not_in_this_version(initializer_content):
    with pytest.raises(GeLBExTypeError, match="not in this version") as info:
        get_typed_ast(minimal_gelb_program_1d(initializer_content=initializer_content))
    assert "real32" in str(info.value)       # the hint names the alternatives


def test_a_real16_constant_is_rejected():
    with pytest.raises(GeLBExTypeError, match="not in this version"):
        get_typed_ast(minimal_gelb_program_1d(
            global_constants_content="const real16 H = 0.5;",
            initializer_content="f.out[x | 0] = 0.0;"))


def test_a_real16_lattice_is_rejected():
    source = minimal_gelb_program_1d(initializer_content="f.out[x | 0] = 0.0;")
    assert source.count("lattice f(1, 1, int,") == 1
    source = source.replace("lattice f(1, 1, int,", "lattice f(1, 1, real16,")
    with pytest.raises(GeLBExTypeError, match="not in this version"):
        get_typed_ast(source)
