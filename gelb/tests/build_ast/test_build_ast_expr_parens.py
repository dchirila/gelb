#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import ASTBuilderVisitor, get_ast


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
