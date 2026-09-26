#!/usr/bin/env python3
"""Tests for parsing function blocks, user function calls, and destructuring."""

import pytest
from gelb.tests.unit.parsing.parsing_test_utils import assert_cst_equals


# Helpers to build CST fragments for canonical signature parameters.
def _scalar_param(type_category, type_name, var_name):
    """Build a CST string for a scalar parameter like ``int a``."""
    return (
        f"(param_decl "
        f"(data_type (scalar_data_type (scalar_{type_category}_data_type {type_name}))) "
        f"(identifier {var_name}))"
    )


def _array_param(elem_type_category, elem_type, shape, var_name):
    """Build a CST string for an array parameter."""
    return (
        f"(param_decl "
        f"(data_type (array_data_type array [ "
        f"(scalar_data_type (scalar_{elem_type_category}_data_type {elem_type})) , "
        f"(array_shape (expr {shape})) ])) "
        f"(identifier {var_name}))"
    )


class TestParseFunctionBlock:
    """Test parsing of function block definitions."""

    def test_minimal_function_block(self):
        """Parse a function with one input, one output, one statement."""
        src = (
            'function Foo(int a) -> (real b) '
            '{ b = 1.0; }'
        )
        int_a = _scalar_param("int", "int", "a")
        real_b = _scalar_param("real", "real", "b")
        assert_cst_equals(
            src,
            f"(function_block function (identifier Foo) ( {int_a} ) -> ( {real_b} ) "
            f"{{ (block_stmt (variable_assignment_stmt (identifier b) = (expr 1.0) ;)) }})",
            "function_block"
        )

    def test_function_block_multiple_inputs(self):
        """Parse a function with multiple inputs."""
        src = (
            'function Bar(int x, real y) -> (real z) '
            '{ z = y; }'
        )
        int_x = _scalar_param("int", "int", "x")
        real_y = _scalar_param("real", "real", "y")
        real_z = _scalar_param("real", "real", "z")
        assert_cst_equals(
            src,
            f"(function_block function (identifier Bar) ( {int_x} , {real_y} ) -> ( {real_z} ) "
            f"{{ (block_stmt (variable_assignment_stmt (identifier z) = (expr (identifier y)) ;)) }})",
            "function_block"
        )

    def test_function_block_multiple_outputs(self):
        """Parse a function with multiple outputs."""
        src = (
            'function Baz(int x) -> (real a, real b) '
            '{ a = 1.0; b = 2.0; }'
        )
        int_x = _scalar_param("int", "int", "x")
        real_a = _scalar_param("real", "real", "a")
        real_b = _scalar_param("real", "real", "b")
        assert_cst_equals(
            src,
            f"(function_block function (identifier Baz) ( {int_x} ) -> ( {real_a} , {real_b} ) "
            f"{{ (block_stmt (variable_assignment_stmt (identifier a) = (expr 1.0) ;)) "
            f"(block_stmt (variable_assignment_stmt (identifier b) = (expr 2.0) ;)) }})",
            "function_block"
        )

    def test_function_block_array_params(self):
        """Parse a function with array parameters."""
        src = (
            'function F(array[real, 9] fIn) -> (real rho) '
            '{ rho = sum(fIn); }'
        )
        arr_fIn = _array_param("real", "real", "9", "fIn")
        real_rho = _scalar_param("real", "real", "rho")
        assert_cst_equals(
            src,
            f"(function_block function (identifier F) ( {arr_fIn} ) -> ( {real_rho} ) "
            f"{{ (block_stmt (variable_assignment_stmt (identifier rho) = "
            f"(expr (intrinsic_function_call (intrinsic_function_name sum) ( (expr (identifier fIn)) ))) ;)) }})",
            "function_block"
        )


class TestParseUserFunctionCall:
    """Test parsing of user-defined function calls in expressions."""

    def test_simple_call(self):
        """Parse Foo(x)."""
        assert_cst_equals(
            "Foo(x)",
            "(expr (user_function_call (identifier Foo) ( (expr (identifier x)) )))",
            "expr"
        )

    def test_call_no_args(self):
        """Parse Foo()."""
        assert_cst_equals(
            "Foo()",
            "(expr (user_function_call (identifier Foo) ( )))",
            "expr"
        )

    def test_call_multiple_args(self):
        """Parse Foo(a, b, c)."""
        assert_cst_equals(
            "Foo(a, b, c)",
            "(expr (user_function_call (identifier Foo) ( "
            "(expr (identifier a)) , (expr (identifier b)) , (expr (identifier c)) )))",
            "expr"
        )

    def test_call_in_arithmetic(self):
        """Parse Foo(x) + 1."""
        assert_cst_equals(
            "Foo(x) + 1",
            "(expr (expr (user_function_call (identifier Foo) ( (expr (identifier x)) ))) + (expr 1))",
            "expr"
        )

    def test_nested_calls(self):
        """Parse Outer(Inner(x))."""
        assert_cst_equals(
            "Outer(Inner(x))",
            "(expr (user_function_call (identifier Outer) ( "
            "(expr (user_function_call (identifier Inner) ( (expr (identifier x)) ))) )))",
            "expr"
        )

    def test_call_with_literal_args(self):
        """Parse Foo(1, 2.0)."""
        assert_cst_equals(
            "Foo(1, 2.0)",
            "(expr (user_function_call (identifier Foo) ( (expr 1) , (expr 2.0) )))",
            "expr"
        )


class TestParseDestructuringAssignment:
    """Test parsing of destructuring assignment statements."""

    def test_simple_destructuring(self):
        """Parse {a, b} = Foo(x);"""
        assert_cst_equals(
            "{a, b} = Foo(x);",
            "(block_stmt (destructuring_assignment_stmt { (identifier a) , (identifier b) } = "
            "(expr (user_function_call (identifier Foo) ( (expr (identifier x)) ))) ;))",
            "block_stmt"
        )

    def test_three_targets(self):
        """Parse {rho, U, V} = Func(fIn);"""
        assert_cst_equals(
            "{rho, U, V} = Func(fIn);",
            "(block_stmt (destructuring_assignment_stmt { (identifier rho) , (identifier U) , (identifier V) } = "
            "(expr (user_function_call (identifier Func) ( (expr (identifier fIn)) ))) ;))",
            "block_stmt"
        )
