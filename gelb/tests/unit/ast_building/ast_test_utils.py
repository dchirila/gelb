#!/usr/bin/env python3
"""
AST test utilities for Abstract Syntax Tree testing.

This module provides utilities specific to AST building and validation tests.
"""

def assert_ast_equals(test_string, expected, rule):
    """
    Helper to test AST (Abstract Syntax Tree) building.
    
    Args:
        test_string (str): Input string to parse and build AST from
        expected (str): Expected AST string representation
        rule (str): ANTLR rule name to start parsing from
    """
    from gelb.tests.test_utils import get_ast
    ast = get_ast(rule, test_string)
    result = str(ast)
    assert result == expected


def get_expression_ast_test_data():
    """Return test data for expression AST building tests across all expression types."""
    return [
        # Boolean literals
        ("bool", "true_literal", "true", "(BoolLiteral true)"),
        ("bool", "false_literal", "false", "(BoolLiteral false)"),
        
        # Integer literals and arithmetic
        ("int", "zero", "0", "(IntLiteral 0)"),
        ("int", "zero_in_parens", "(0)", "(IntLiteral 0)"),
        ("int", "positive_int", "123", "(IntLiteral 123)"),
        ("int", "positive_int_in_parens", "(921)", "(IntLiteral 921)"),
        ("int", "negative_int", "-981", "(UnaryMinusExpr (IntLiteral 981))"),
        ("int", "explicitly_positive_int", "+29", "(IntLiteral 29)"),
        ("int", "addition", "123 + 321", "(Add (IntLiteral 123) (IntLiteral 321))"),
        ("int", "subtraction", "123 - 321", "(Sub (IntLiteral 123) (IntLiteral 321))"),
        ("int", "multiplication", "12 * 10", "(Mul (IntLiteral 12) (IntLiteral 10))"),
        ("int", "division", "120 / 12", "(Div (IntLiteral 120) (IntLiteral 12))"),
        ("int", "exponentiation", "2 ^ 3", "(Pow (IntLiteral 2) (IntLiteral 3))"),
        
        # Real literals and arithmetic
        ("real", "zero_dot_zero", "0.0", "(RealLiteral 0.0)"),
        ("real", "zero_dot_zero_in_parens", "(0.0)", "(RealLiteral 0.0)"),
        ("real", "simple_real", "123.456", "(RealLiteral 123.456)"),
        ("real", "real_in_parens", "(123.456)", "(RealLiteral 123.456)"),
        ("real", "negative_real", "-123.456", "(UnaryMinusExpr (RealLiteral 123.456))"),
        ("real", "explicitly_positive_real", "+123.456", "(RealLiteral 123.456)"),
        ("real", "real_addition", "123.0 + 321.0", "(Add (RealLiteral 123.0) (RealLiteral 321.0))"),
        ("real", "real_subtraction", "123.0 - 321.0", "(Sub (RealLiteral 123.0) (RealLiteral 321.0))"),
        ("real", "real_multiplication", "12.5 * 10.2", "(Mul (RealLiteral 12.5) (RealLiteral 10.2))"),
        ("real", "real_division", "120.0 / 12.0", "(Div (RealLiteral 120.0) (RealLiteral 12.0))"),
        ("real", "real_exponentiation", "2.0 ^ 3.0", "(Pow (RealLiteral 2.0) (RealLiteral 3.0))"),
        ("real", "mixed_int_real", "5 + 3.14", "(Add (IntLiteral 5) (RealLiteral 3.14))"),
        ("real", "scientific_notation_positive", "1.23e10", "(RealLiteral 12300000000.0)"),
        ("real", "scientific_notation_negative", "1.23e-10", "(RealLiteral 1.23e-10)"),
        ("real", "scientific_notation_uppercase", "1.23E10", "(RealLiteral 12300000000.0)"),
        ("real", "large_scientific", "6.022e23", "(RealLiteral 6.022e+23)"),
        ("real", "small_scientific", "1.602e-19", "(RealLiteral 1.602e-19)"),
        
        # Comparison operations
        ("comparison", "less_than", "x < y", "(Less (Identifier x) (Identifier y))"),
        ("comparison", "greater_than", "x > y", "(Greater (Identifier x) (Identifier y))"),
        ("comparison", "less_equal", "x <= y", "(LessEqual (Identifier x) (Identifier y))"),
        ("comparison", "greater_equal", "x >= y", "(GreaterEqual (Identifier x) (Identifier y))"),
        ("comparison", "equal", "x == y", "(Equal (Identifier x) (Identifier y))"),
        ("comparison", "not_equal", "x != y", "(NotEqual (Identifier x) (Identifier y))"),
        ("comparison", "literal_comparison", "5 < 10", "(Less (IntLiteral 5) (IntLiteral 10))"),
        ("comparison", "arithmetic_comparison", "x + 1 > y * 2", "(Greater (Add (Identifier x) (IntLiteral 1)) (Mul (Identifier y) (IntLiteral 2)))"),
        ("comparison", "chained_comparison", "x < y < z", "(Less (Less (Identifier x) (Identifier y)) (Identifier z))"),
        
        # Logical operations
        ("logical", "and_operation", "x && y", "(And (Identifier x) (Identifier y))"),
        ("logical", "or_operation", "x || y", "(Or (Identifier x) (Identifier y))"),
        ("logical", "not_operation", "!x", "(NotExpr (Identifier x))"),
        ("logical", "bool_and", "true && false", "(And (BoolLiteral true) (BoolLiteral false))"),
        ("logical", "bool_or", "true || false", "(Or (BoolLiteral true) (BoolLiteral false))"),
        ("logical", "bool_not", "!true", "(NotExpr (BoolLiteral true))"),
        ("logical", "complex_logical", "x && y || z", "(Or (And (Identifier x) (Identifier y)) (Identifier z))"),
        ("logical", "logical_with_comparison", "x < y && z > w", "(And (Less (Identifier x) (Identifier y)) (Greater (Identifier z) (Identifier w)))"),
        ("logical", "nested_logical_parens", "(x && y) || (z && w)", "(Or (And (Identifier x) (Identifier y)) (And (Identifier z) (Identifier w)))"),
        
        # Parentheses and precedence
        ("parens", "simple_parens", "(x)", "(Identifier x)"),
        ("parens", "nested_parens", "((x))", "(Identifier x)"),
        ("parens", "triple_nested_parens", "(((x)))", "(Identifier x)"),
        ("parens", "complex_parens", "(x + y) * z", "(Mul (Add (Identifier x) (Identifier y)) (Identifier z))"),
        ("parens", "precedence_override", "x + (y * z)", "(Add (Identifier x) (Mul (Identifier y) (Identifier z)))"),
        ("parens", "multiple_parens", "(x + y) * (z - w)", "(Mul (Add (Identifier x) (Identifier y)) (Sub (Identifier z) (Identifier w)))"),
        ("parens", "logical_parens", "(x && y) || z", "(Or (And (Identifier x) (Identifier y)) (Identifier z))"),
        ("parens", "comparison_parens", "(x < y) && (z > w)", "(And (Less (Identifier x) (Identifier y)) (Greater (Identifier z) (Identifier w)))"),
        
        # Identifiers
        ("identifier", "simple_identifier", "x", "(Identifier x)"),
        ("identifier", "identifier_in_parens", "(myVariable)", "(Identifier myVariable)"),
        ("identifier", "identifier_arithmetic", "x + y", "(Add (Identifier x) (Identifier y))"),
        ("identifier", "complex_identifier", "myLongVariableName", "(Identifier myLongVariableName)"),
        
        # Array expressions (basic cases) - these use RectSelOfArrayElems in GeLB
        ("array", "simple_array_access", "arr[i]", "(RectSelOfArrayElems (Identifier arr) (Range (Identifier i) (Identifier i)))"),
        ("array", "multi_dim_array", "matrix[i, j]", "(RectSelOfArrayElems (Identifier matrix) (Range (Identifier i) (Identifier i)) (Range (Identifier j) (Identifier j)))"),
        ("array", "array_with_arithmetic", "arr[i + 1]", "(RectSelOfArrayElems (Identifier arr) (Range (Add (Identifier i) (IntLiteral 1)) (Add (Identifier i) (IntLiteral 1))))"),
    ]