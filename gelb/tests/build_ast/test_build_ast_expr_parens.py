#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_simple_int():
    # Arrange
    test_string = "((3))"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(IntLiteral 3)"

def test_simple_explicitly_positive_int():
    # Arrange
    test_string = """(
    (+3))
    """
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(IntLiteral 3)"

def test_simple_negative_int():
    # Arrange
    test_string = """(((-123)))"""
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(UnaryMinusExpr (IntLiteral 123))"

def test_simple_bool_true():
    # Arrange
    test_string = "((true))"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(BoolLiteral true)"

def test_simple_bool_false():
    # Arrange
    test_string = "((((false))))"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(BoolLiteral false)"

def test_simple_real():
    # Arrange
    test_string = """(
    (3.1415926539))
    """
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(RealLiteral 3.1415926539)"

def test_simple_explicitly_positive_real():
    # Arrange
    test_string = """(
    (+3.1415926539))
    """
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(RealLiteral 3.1415926539)"

def test_simple_negative_real():
    # Arrange
    test_string = """(
    (-3.1415926539))
    """
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(UnaryMinusExpr (RealLiteral 3.1415926539))"

def test_int_plus_int():
    # Arrange
    test_string = "((3)) + 1"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(Add (IntLiteral 3) (IntLiteral 1))"

def test_real_divided_by_int():
    # Arrange
    test_string = "12.34e19 / (((321)))"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(Div (RealLiteral 1.234e+20) (IntLiteral 321))"

def test_mix_01():
    # Arrange
    test_string = "1 * 2 + 3 / 4"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == (
        "(Add"
        " (Mul (IntLiteral 1) (IntLiteral 2))"
        " (Div (IntLiteral 3) (IntLiteral 4))"
        ")"
    )

def test_mix_02():
    # Arrange
    test_string = "(1* 2)+(3 /4)"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == (
        "(Add"
        " (Mul (IntLiteral 1) (IntLiteral 2))"
        " (Div (IntLiteral 3) (IntLiteral 4))"
        ")"
    )

def test_mix_03():
    # Arrange
    test_string = "1.23 / 2 - 3 * 4.56e2"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == (
        "(Sub"
        " (Div (RealLiteral 1.23) (IntLiteral 2))"
        " (Mul (IntLiteral 3) (RealLiteral 456.0))"
        ")"
    )
