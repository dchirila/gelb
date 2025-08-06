#!/usr/bin/env python3

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.tests.unit.parsing.parsing_test_utils import assert_cst_equals


class TestParseIntrinsicFunctions:
    """Test parsing of intrinsic function calls using CST (Concrete Syntax Tree) comparison."""
    
    def test_parse_sum_function_no_args(self):
        """Test parsing sum() with no arguments."""
        assert_cst_equals(
            "sum()",
            "(expr (intrinsic_function_call (intrinsic_function_name sum) ( )))",
            "expr"
        )
    
    def test_parse_sum_function_one_arg(self):
        """Test parsing sum() with one argument."""
        assert_cst_equals(
            "sum(x)",
            "(expr (intrinsic_function_call (intrinsic_function_name sum) ( (expr (identifier x)) )))",
            "expr"
        )
    
    def test_parse_sum_function_multiple_args(self):
        """Test parsing sum() with multiple arguments (for error testing later)."""
        assert_cst_equals(
            "sum(x, y)",
            "(expr (intrinsic_function_call (intrinsic_function_name sum) ( (expr (identifier x)) , (expr (identifier y)) )))",
            "expr"
        )
    
    def test_parse_sum_function_array_literal(self):
        """Test parsing sum() with array literal argument."""
        assert_cst_equals(
            "sum({1, 2, 3})",
            "(expr (intrinsic_function_call (intrinsic_function_name sum) ( (expr (array_literal_1d { (expr 1) , (expr 2) , (expr 3) })) )))",
            "expr"
        )
    
    def test_parse_dot_prod_function(self):
        """Test parsing dot_prod() with two arguments."""
        assert_cst_equals(
            "dot_prod(a, b)",
            "(expr (intrinsic_function_call (intrinsic_function_name dot_prod) ( (expr (identifier a)) , (expr (identifier b)) )))",
            "expr"
        )
    
    def test_parse_intrinsic_in_binary_expression(self):
        """Test parsing intrinsic functions in binary expressions."""
        assert_cst_equals(
            "sum(a) + dot_prod(b, c)",
            "(expr (expr (intrinsic_function_call (intrinsic_function_name sum) ( (expr (identifier a)) ))) + (expr (intrinsic_function_call (intrinsic_function_name dot_prod) ( (expr (identifier b)) , (expr (identifier c)) ))))",
            "expr"
        )
    
    def test_parse_intrinsic_with_lattice_selection(self):
        """Test parsing intrinsic functions with lattice selections."""
        assert_cst_equals(
            "sum(f.in[x,y|:])",
            "(expr (intrinsic_function_call (intrinsic_function_name sum) ( (expr (rect_sel_of_lattice_in_dfs (identifier f) . in [ (coords_range (expr (identifier x))) , (coords_range (expr (identifier y))) (lattice_dfs_range | (coords_range :)) ])) )))",
            "expr"
        )
    
    def test_parse_intrinsic_with_arithmetic_expressions(self):
        """Test parsing intrinsic functions with arithmetic expressions as arguments."""
        assert_cst_equals(
            "dot_prod(a + b, c * d)",
            "(expr (intrinsic_function_call (intrinsic_function_name dot_prod) ( (expr (expr (identifier a)) + (expr (identifier b))) , (expr (expr (identifier c)) * (expr (identifier d))) )))",
            "expr"
        )
    
    def test_parse_intrinsic_function_precedence(self):
        """Test that intrinsic function calls have correct precedence."""
        # sum(x) * 2 should parse as (sum(x)) * 2, not sum(x * 2)
        assert_cst_equals(
            "sum(x) * 2",
            "(expr (expr (intrinsic_function_call (intrinsic_function_name sum) ( (expr (identifier x)) ))) * (expr 2))",
            "expr"
        )
    
    def test_parse_nested_intrinsic_calls(self):
        """Test parsing nested intrinsic function calls."""
        assert_cst_equals(
            "sum({dot_prod(a, b), dot_prod(c, d)})",
            "(expr (intrinsic_function_call (intrinsic_function_name sum) ( (expr (array_literal_1d { (expr (intrinsic_function_call (intrinsic_function_name dot_prod) ( (expr (identifier a)) , (expr (identifier b)) ))) , (expr (intrinsic_function_call (intrinsic_function_name dot_prod) ( (expr (identifier c)) , (expr (identifier d)) ))) })) )))",
            "expr"
        )
    
    def test_parse_intrinsic_function_name_rule(self):
        """Test parsing just the intrinsic function name rule."""
        assert_cst_equals(
            "sum",
            "(intrinsic_function_name sum)",
            "intrinsic_function_name"
        )
        
        assert_cst_equals(
            "dot_prod",
            "(intrinsic_function_name dot_prod)",
            "intrinsic_function_name"
        )
    
    def test_parse_intrinsic_function_call_rule(self):
        """Test parsing just the intrinsic function call rule."""
        assert_cst_equals(
            "sum(x)",
            "(intrinsic_function_call (intrinsic_function_name sum) ( (expr (identifier x)) ))",
            "intrinsic_function_call"
        )