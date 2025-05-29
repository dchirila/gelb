#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_logical_and():
    # Arrange
    test_string = "x && y"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(And (Identifier x) (Identifier y))"

def test_logical_or():
    # Arrange
    test_string = "x || y"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(Or (Identifier x) (Identifier y))"

def test_logical_and_with_bools():
    # Arrange
    test_string = "true && false"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(And (BoolLiteral true) (BoolLiteral false))"

def test_logical_or_with_bools():
    # Arrange
    test_string = "true || false"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(Or (BoolLiteral true) (BoolLiteral false))"

def test_complex_logical_expression():
    # Arrange - test precedence: && has higher precedence than ||
    test_string = "x && y || z"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(Or (And (Identifier x) (Identifier y)) (Identifier z))"

def test_logical_with_comparisons():
    # Arrange
    test_string = "x > 0 && y < 10"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(And (Greater (Identifier x) (IntLiteral 0)) (Less (Identifier y) (IntLiteral 10)))"

def test_logical_with_equality():
    # Arrange
    test_string = "x == 5 || y != 3"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(Or (Equal (Identifier x) (IntLiteral 5)) (NotEqual (Identifier y) (IntLiteral 3)))"

def test_nested_logical_with_parens():
    # Arrange
    test_string = "(a && b) || (c && d)"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(Or (And (Identifier a) (Identifier b)) (And (Identifier c) (Identifier d)))"

def test_logical_not():
    # Arrange
    test_string = "!x"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(NotExpr (Identifier x))"

def test_logical_not_with_comparison():
    # Arrange
    test_string = "!(x > 5)"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(NotExpr (Greater (Identifier x) (IntLiteral 5)))"