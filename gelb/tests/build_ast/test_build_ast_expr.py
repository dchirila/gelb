#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import ASTBuilderVisitor, get_ast


def test_zero():
    # Arrange
    test_string = "0"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(IntLiteral 0)"

def test_zero_inside_parens():
    # Arrange
    test_string = "(0)"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(IntLiteral 0)"

def test_positive_int():
    # Arrange
    test_string = "123"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(IntLiteral 123)"

def test_positive_int_inside_parens():
    # Arrange
    test_string = "(921)"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(IntLiteral 921)"

def test_negative_int():
    # Arrange
    test_string = "-981"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(UnaryMinusExpr (IntLiteral 981))"

def test_really_positive_int():
    # Arrange
    test_string = "+29"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(IntLiteral 29)"

def test_int_plus_int():
    # Arrange
    test_string = "123 + 321"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(Add (IntLiteral 123) (IntLiteral 321))"

def test_int_minus_int():
    # Arrange
    test_string = "123 - 321"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(Sub (IntLiteral 123) (IntLiteral 321))"

def test_int_times_int():
    # Arrange
    test_string = "12 * 10"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(Mul (IntLiteral 12) (IntLiteral 10))"

def test_int_divided_by_int():
    # Arrange
    test_string = "120 / 12"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(Div (IntLiteral 120) (IntLiteral 12))"
