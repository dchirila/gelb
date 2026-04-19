#!/usr/bin/env python3
"""
Tests for math intrinsic functions (sin, cos, sqrt) type inference.
"""

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.tests.test_utils import get_typed_ast, minimal_gelb_program_1d
from gelb.utils.exceptions import GeLBExTypeError


class TestSinTypeInference:
    """Tests for sin() intrinsic function."""

    def test_sin_real_literal(self):
        """sin(3.14) -> scalar real"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content="f.out[x | 0] = sin(3.14);"
        )
        ast = get_typed_ast(gelb_code)
        rhs = ast.initializers[0].stmts[0].rhs
        assert isinstance(rhs, IntrinsicFunctionCall_N)
        assert rhs.inferred_type.element_dtype == "real"
        assert isinstance(rhs.inferred_type.shape, List_N)
        assert len(rhs.inferred_type.shape.elements) == 0

    def test_sin_int_argument(self):
        """sin(x) with int argument -> scalar real (int promoted)"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content="f.out[x | 0] = sin(x);"
        )
        ast = get_typed_ast(gelb_code)
        rhs = ast.initializers[0].stmts[0].rhs
        assert rhs.inferred_type.element_dtype == "real"

    def test_sin_no_arguments_error(self):
        """sin() with no arguments -> error"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content="f.out[x | 0] = sin();"
        )
        with pytest.raises(GeLBExTypeError):
            get_typed_ast(gelb_code)

    def test_sin_too_many_arguments_error(self):
        """sin(1, 2) -> error"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content="f.out[x | 0] = sin(1, 2);"
        )
        with pytest.raises(GeLBExTypeError):
            get_typed_ast(gelb_code)

    def test_sin_array_argument_error(self):
        """sin({1.0, 2.0, 3.0}) -> error (array argument rejected)"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content="f.out[x | 0] = sin({1.0, 2.0, 3.0});"
        )
        with pytest.raises(GeLBExTypeError):
            get_typed_ast(gelb_code)


class TestCosTypeInference:
    """Tests for cos() intrinsic function."""

    def test_cos_real_literal(self):
        """cos(1.57) -> scalar real"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content="f.out[x | 0] = cos(1.57);"
        )
        ast = get_typed_ast(gelb_code)
        rhs = ast.initializers[0].stmts[0].rhs
        assert isinstance(rhs, IntrinsicFunctionCall_N)
        assert rhs.inferred_type.element_dtype == "real"

    def test_cos_int_argument(self):
        """cos(0) with int argument -> scalar real"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content="f.out[x | 0] = cos(0);"
        )
        ast = get_typed_ast(gelb_code)
        rhs = ast.initializers[0].stmts[0].rhs
        assert rhs.inferred_type.element_dtype == "real"


class TestSqrtTypeInference:
    """Tests for sqrt() intrinsic function."""

    def test_sqrt_real_literal(self):
        """sqrt(2.0) -> scalar real"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content="f.out[x | 0] = sqrt(2.0);"
        )
        ast = get_typed_ast(gelb_code)
        rhs = ast.initializers[0].stmts[0].rhs
        assert isinstance(rhs, IntrinsicFunctionCall_N)
        assert rhs.inferred_type.element_dtype == "real"

    def test_sqrt_int_argument(self):
        """sqrt(4) with int argument -> scalar real"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content="f.out[x | 0] = sqrt(4);"
        )
        ast = get_typed_ast(gelb_code)
        rhs = ast.initializers[0].stmts[0].rhs
        assert rhs.inferred_type.element_dtype == "real"

    def test_sqrt_expression(self):
        """sqrt(x * x + 1) -> scalar real"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content="f.out[x | 0] = sqrt(x * x + 1);"
        )
        ast = get_typed_ast(gelb_code)
        rhs = ast.initializers[0].stmts[0].rhs
        assert rhs.inferred_type.element_dtype == "real"


class TestNewScalarMathIntrinsics:
    """Tests for exp, abs, log, tan, tanh intrinsic functions.

    All follow the same pattern as sin/cos/sqrt: single scalar numeric
    argument -> scalar real return type.
    """

    @pytest.mark.parametrize("func_name", ["exp", "abs", "log", "tan", "tanh"])
    def test_real_literal(self, func_name):
        """func(1.0) -> scalar real"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content=f"f.out[x | 0] = {func_name}(1.0);"
        )
        ast = get_typed_ast(gelb_code)
        rhs = ast.initializers[0].stmts[0].rhs
        assert isinstance(rhs, IntrinsicFunctionCall_N)
        assert rhs.inferred_type.element_dtype == "real"
        assert isinstance(rhs.inferred_type.shape, List_N)
        assert len(rhs.inferred_type.shape.elements) == 0

    @pytest.mark.parametrize("func_name", ["exp", "log", "tan", "tanh"])
    def test_int_argument(self, func_name):
        """func(x) with int argument -> scalar real (int promoted)"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content=f"f.out[x | 0] = {func_name}(x);"
        )
        ast = get_typed_ast(gelb_code)
        rhs = ast.initializers[0].stmts[0].rhs
        assert rhs.inferred_type.element_dtype == "real"

    def test_abs_keeps_an_int_argument_int(self):
        """abs(x) with int argument -> scalar int: abs keeps its argument's type"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content="f.out[x | 0] = abs(x);"
        )
        ast = get_typed_ast(gelb_code)
        rhs = ast.initializers[0].stmts[0].rhs
        assert rhs.inferred_type.element_dtype == "int"

    @pytest.mark.parametrize("func_name", ["exp", "abs", "log", "tan", "tanh", "sqrt", "sin", "cos"])
    def test_real32_argument_keeps_the_width(self, func_name):
        """func(w) with a real32 argument -> scalar real32: the width is kept"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content=f"real32 w; w = 0.5; f.out[x | 0] = {func_name}(w);"
        )
        ast = get_typed_ast(gelb_code)
        rhs = ast.initializers[0].stmts[-1].rhs
        assert rhs.inferred_type.element_dtype == "real32"

    @pytest.mark.parametrize("func_name", ["exp", "abs", "log", "tan", "tanh"])
    def test_no_arguments_error(self, func_name):
        """func() with no arguments -> error"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content=f"f.out[x | 0] = {func_name}();"
        )
        with pytest.raises(GeLBExTypeError):
            get_typed_ast(gelb_code)

    @pytest.mark.parametrize("func_name", ["exp", "abs", "log", "tan", "tanh"])
    def test_too_many_arguments_error(self, func_name):
        """func(1, 2) -> error"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content=f"f.out[x | 0] = {func_name}(1, 2);"
        )
        with pytest.raises(GeLBExTypeError):
            get_typed_ast(gelb_code)

    @pytest.mark.parametrize("func_name", ["exp", "abs", "log", "tan", "tanh"])
    def test_array_argument_error(self, func_name):
        """func({1.0, 2.0, 3.0}) -> error (array argument rejected)"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content=f"f.out[x | 0] = {func_name}({{1.0, 2.0, 3.0}});"
        )
        with pytest.raises(GeLBExTypeError):
            get_typed_ast(gelb_code)


class TestTwoArgIntrinsics:
    """Tests for min, max, mod, atan2 intrinsic functions."""

    @pytest.mark.parametrize("func_name", ["min", "max", "mod"])
    def test_two_reals(self, func_name):
        """func(1.0, 2.0) -> scalar real"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content=f"f.out[x | 0] = {func_name}(1.0, 2.0);"
        )
        ast = get_typed_ast(gelb_code)
        rhs = ast.initializers[0].stmts[0].rhs
        assert isinstance(rhs, IntrinsicFunctionCall_N)
        assert rhs.inferred_type.element_dtype == "real"

    @pytest.mark.parametrize("func_name", ["min", "max", "mod"])
    def test_two_ints(self, func_name):
        """func(x, x) with int args -> scalar int (preserved)"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content=f"f.out[x | 0] = {func_name}(x, x);"
        )
        ast = get_typed_ast(gelb_code)
        rhs = ast.initializers[0].stmts[0].rhs
        base = rhs.inferred_type.element_dtype
        assert 'int' in base

    @pytest.mark.parametrize("func_name", ["min", "max", "mod"])
    def test_mixed_int_real(self, func_name):
        """func(x, 1.0) -> scalar real (int promoted to real)"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content=f"f.out[x | 0] = {func_name}(x, 1.0);"
        )
        ast = get_typed_ast(gelb_code)
        rhs = ast.initializers[0].stmts[0].rhs
        assert rhs.inferred_type.element_dtype == "real"

    @pytest.mark.parametrize("func_name", ["min", "max", "mod"])
    def test_real32_with_int_is_real32(self, func_name):
        """func(w, 1) with w real32 -> scalar real32: the promotion table, not real"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content=f"real32 w; w = 0.5; f.out[x | 0] = {func_name}(w, 1);"
        )
        ast = get_typed_ast(gelb_code)
        rhs = ast.initializers[0].stmts[-1].rhs
        assert rhs.inferred_type.element_dtype == "real32"

    def test_atan2_of_two_ints_returns_real(self):
        """atan2(x, 2) -> scalar real: never an integer result"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content="f.out[x | 0] = atan2(x, 2);"
        )
        ast = get_typed_ast(gelb_code)
        rhs = ast.initializers[0].stmts[0].rhs
        assert rhs.inferred_type.element_dtype == "real"

    def test_atan2_returns_real(self):
        """atan2(1.0, 2.0) -> scalar real"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content="f.out[x | 0] = atan2(1.0, 2.0);"
        )
        ast = get_typed_ast(gelb_code)
        rhs = ast.initializers[0].stmts[0].rhs
        assert rhs.inferred_type.element_dtype == "real"

    @pytest.mark.parametrize("func_name", ["min", "max", "mod", "atan2"])
    def test_wrong_arg_count_one(self, func_name):
        """func(1.0) with one argument -> error"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content=f"f.out[x | 0] = {func_name}(1.0);"
        )
        with pytest.raises(GeLBExTypeError):
            get_typed_ast(gelb_code)

    @pytest.mark.parametrize("func_name", ["min", "max", "mod", "atan2"])
    def test_wrong_arg_count_three(self, func_name):
        """func(1, 2, 3) with three arguments -> error"""
        gelb_code = minimal_gelb_program_1d(
            initializer_content=f"f.out[x | 0] = {func_name}(1, 2, 3);"
        )
        with pytest.raises(GeLBExTypeError):
            get_typed_ast(gelb_code)
