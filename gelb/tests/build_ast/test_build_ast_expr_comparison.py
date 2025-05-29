#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_less_than():
    # Arrange
    test_string = "x < y"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(Less (Identifier x) (Identifier y))"

def test_greater_than():
    # Arrange
    test_string = "x > y"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(Greater (Identifier x) (Identifier y))"

def test_less_equal():
    # Arrange
    test_string = "x <= y"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(LessEqual (Identifier x) (Identifier y))"

def test_greater_equal():
    # Arrange
    test_string = "x >= y"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(GreaterEqual (Identifier x) (Identifier y))"

def test_equal():
    # Arrange
    test_string = "x == y"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(Equal (Identifier x) (Identifier y))"

def test_not_equal():
    # Arrange
    test_string = "x != y"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(NotEqual (Identifier x) (Identifier y))"

def test_comparison_with_literals():
    # Arrange
    test_string = "5 < 10"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(Less (IntLiteral 5) (IntLiteral 10))"

def test_comparison_with_arithmetic():
    # Arrange
    test_string = "x + 1 > y * 2"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(Greater (Add (Identifier x) (IntLiteral 1)) (Mul (Identifier y) (IntLiteral 2)))"

def test_chained_comparisons():
    # Arrange - note: this will parse as (x < y) < z due to left-associativity
    test_string = "x < y < z"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    # This might not be semantically meaningful but it's what the grammar produces
    assert str(ast) == "(Less (Less (Identifier x) (Identifier y)) (Identifier z))"