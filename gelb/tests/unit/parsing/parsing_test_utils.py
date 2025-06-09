#!/usr/bin/env python3
"""
Parsing test utilities for CST (Concrete Syntax Tree) testing.

This module provides utilities specific to parsing tests.
"""

def assert_cst_equals(test_string, expected, rule):
    """
    Helper to test CST (Concrete Syntax Tree) parsing.
    
    Args:
        test_string (str): Input string to parse
        expected (str): Expected CST string representation
        rule (str): ANTLR rule name to start parsing from
    """
    from gelb.frontend.stage1_frontend import get_cst_as_string
    result = get_cst_as_string(rule, test_string)
    assert result == expected



def get_expression_parse_test_data():
    """Return test data for expression parsing tests (CST) across all expression types."""
    return [
        # Comparison operations
        ("comparison", "less_than", "x < y", "(expr (expr (identifier x)) < (expr (identifier y)))"),
        ("comparison", "greater_than", "x > y", "(expr (expr (identifier x)) > (expr (identifier y)))"),
        ("comparison", "less_equal", "x <= y", "(expr (expr (identifier x)) <= (expr (identifier y)))"),
        ("comparison", "greater_equal", "x >= y", "(expr (expr (identifier x)) >= (expr (identifier y)))"),
        ("comparison", "equal", "x == y", "(expr (expr (identifier x)) == (expr (identifier y)))"),
        ("comparison", "not_equal", "x != y", "(expr (expr (identifier x)) != (expr (identifier y)))"),
        ("comparison", "numbers", "5 < 10", "(expr (expr 5) < (expr 10))"),
        ("comparison", "arithmetic_comparison", "x + 1 < y * 2", "(expr (expr (expr (identifier x)) + (expr 1)) < (expr (expr (identifier y)) * (expr 2)))"),
        ("comparison", "chained_with_logical", "x > 0 && y < 10", "(expr (expr (expr (identifier x)) > (expr 0)) && (expr (expr (identifier y)) < (expr 10)))"),
        ("comparison", "equality_with_logical", "x == 5 || y != 3", "(expr (expr (expr (identifier x)) == (expr 5)) || (expr (expr (identifier y)) != (expr 3)))"),
        
        # Logical operations
        ("logical", "and_operation", "true && false", "(expr (expr true) && (expr false))"),
        ("logical", "or_operation", "true || false", "(expr (expr true) || (expr false))"),
        ("logical", "precedence_and_or", "x && y || z", "(expr (expr (expr (identifier x)) && (expr (identifier y))) || (expr (identifier z)))"),
        ("logical", "nested_with_parens", "(a && b) || (c && d)", "(expr (expr ( (expr (expr (identifier a)) && (expr (identifier b))) )) || (expr ( (expr (expr (identifier c)) && (expr (identifier d))) )))"),
        
        # Basic expression patterns
        ("basic", "simple_addition", "x + y", "(expr (expr (identifier x)) + (expr (identifier y)))"),
        ("basic", "simple_multiplication", "a * b", "(expr (expr (identifier a)) * (expr (identifier b)))"),
        ("basic", "complex_arithmetic", "a + b * c", "(expr (expr (identifier a)) + (expr (expr (identifier b)) * (expr (identifier c))))"),
        ("basic", "parentheses", "(x + y) * z", "(expr (expr ( (expr (expr (identifier x)) + (expr (identifier y))) )) * (expr (identifier z)))"),
        ("basic", "literals", "123 + 456", "(expr (expr 123) + (expr 456))"),
        ("basic", "real_literals", "3.14 * 2.0", "(expr (expr 3.14) * (expr 2.0))"),
    ]


def get_array_literal_parse_test_data():
    """Return test data for array literal parsing tests (CST)."""
    return [
        # 1D array literals
        ("1d", "simple", "{1, 2, 3}", 
         "(array_literal_1d { (expr 1) , (expr 2) , (expr 3) })"),
        ("1d", "with_comments", "/* comment 1*/{\n123// comment 2\n, 456//\n}",
         "(array_literal_1d { (expr 123) , (expr 456) })"),
        
        # 2D array literals  
        ("2d", "simple", "{{1, 2}, {3, 4} }",
         "(array_literal_2d { (array_literal_1d { (expr 1) , (expr 2) }) , (array_literal_1d { (expr 3) , (expr 4) }) })"),
        ("2d", "with_whitespace", "{\n{1, 2},\n{3, 4}\n}",
         "(array_literal_2d { (array_literal_1d { (expr 1) , (expr 2) }) , (array_literal_1d { (expr 3) , (expr 4) }) })"),
        
        # 3D array literals
        ("3d", "simple", "{{{1, 2}, {3, 4}}, {{5, 6}, {7, 8}}}",
         "(array_literal_3d { (array_literal_2d { (array_literal_1d { (expr 1) , (expr 2) }) , (array_literal_1d { (expr 3) , (expr 4) }) }) , (array_literal_2d { (array_literal_1d { (expr 5) , (expr 6) }) , (array_literal_1d { (expr 7) , (expr 8) }) }) })"),
        
        # 4D array literals  
        ("4d", "simple", "{{{{1,2},{3,4}},{{5,6},{7,8}}},{{{9,10},{11,12}},{{13,14},{15,16}}}}",
         "(array_literal_4d { (array_literal_3d { (array_literal_2d { (array_literal_1d { (expr 1) , (expr 2) }) , (array_literal_1d { (expr 3) , (expr 4) }) }) , (array_literal_2d { (array_literal_1d { (expr 5) , (expr 6) }) , (array_literal_1d { (expr 7) , (expr 8) }) }) }) , (array_literal_3d { (array_literal_2d { (array_literal_1d { (expr 9) , (expr 10) }) , (array_literal_1d { (expr 11) , (expr 12) }) }) , (array_literal_2d { (array_literal_1d { (expr 13) , (expr 14) }) , (array_literal_1d { (expr 15) , (expr 16) }) }) }) })"),
    ]


def get_array_selection_assignment_parse_test_data():
    """Return test data for array selection assignment statement parsing tests (CST)."""
    return [
        # Single element assignments
        ("element", "simple_int", "arr[0] = 42;",
         "(array_selection_assignment_stmt (rect_sel_of_array_elems (identifier arr) [ (coords_range (expr 0)) ]) = (expr 42) ;)"),
        ("element", "variable_index", "arr[i] = value;",
         "(array_selection_assignment_stmt (rect_sel_of_array_elems (identifier arr) [ (coords_range (expr (identifier i))) ]) = (expr (identifier value)) ;)"),
        
        # Multi-dimensional assignments
        ("multi_dim", "2d_simple", "matrix[x, y] = value;",
         "(array_selection_assignment_stmt (rect_sel_of_array_elems (identifier matrix) [ (coords_range (expr (identifier x))) , (coords_range (expr (identifier y))) ]) = (expr (identifier value)) ;)"),
        
        # Slice assignments
        ("slice", "simple_range", "arr[1:3] = expr;",
         "(array_selection_assignment_stmt (rect_sel_of_array_elems (identifier arr) [ (coords_range (expr 1) : (expr 3)) ]) = (expr (identifier expr)) ;)"),
        
        # Complex expressions
        ("complex", "arithmetic_rhs", "arr[0] = a + b;",
         "(array_selection_assignment_stmt (rect_sel_of_array_elems (identifier arr) [ (coords_range (expr 0)) ]) = (expr (expr (identifier a)) + (expr (identifier b))) ;)"),
        ("complex", "array_literal_rhs", "arr[0] = {1, 2};",
         "(array_selection_assignment_stmt (rect_sel_of_array_elems (identifier arr) [ (coords_range (expr 0)) ]) = (expr (array_literal_1d { (expr 1) , (expr 2) })) ;)"),
    ]