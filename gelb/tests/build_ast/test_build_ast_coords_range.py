#!/usr/bin/env python3

import pytest
from frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_01():
    # Arrange
    test_string = "1"
    # Act
    ast = get_ast("coords_range", test_string)
    # Assert
    assert str(ast) == "(Range (IntLiteral 1) (IntLiteral 1))"

def test_02():
    # Arrange
    test_string = "23:"
    # Act
    ast = get_ast("coords_range", test_string)
    # Assert
    assert str(ast) == "(Range (IntLiteral 23) (RangePlaceholder Max))"

def test_03():
    # Arrange
    test_string = ":45"
    # Act
    ast = get_ast("coords_range", test_string)
    # Assert
    assert str(ast) == "(Range (RangePlaceholder Min) (IntLiteral 45))"

def test_04():
    # Arrange
    test_string = "x"
    # Act
    ast = get_ast("coords_range", test_string)
    # Assert
    assert str(ast) == "(Range (Identifier x) (Identifier x))"

def test_05():
    # Arrange
    test_string = "x- 1"
    # Act
    ast = get_ast("coords_range", test_string)
    # Assert
    assert str(ast) == (
        "(Range"
        " (Sub (Identifier x) (IntLiteral 1))"
        " (Sub (Identifier x) (IntLiteral 1))"
        ")"
    )

def test_06():
    # Arrange
    test_string = "x- 1:"
    # Act
    ast = get_ast("coords_range", test_string)
    # Assert
    assert str(ast) == (
        "(Range"
        " (Sub (Identifier x) (IntLiteral 1))"
        " (RangePlaceholder Max)"
        ")"
    )

def test_07():
    # Arrange
    test_string = "x:- 1"
    # Act
    ast = get_ast("coords_range", test_string)
    # Assert
    assert str(ast) == (
        "(Range"
        " (Identifier x)"
        " (UnaryMinusExpr (IntLiteral 1))"
        ")"
    )

def test_08():
    # Arrange
    test_string = "x:x+1"
    # Act
    ast = get_ast("coords_range", test_string)
    # Assert
    assert str(ast) == (
        "(Range"
        " (Identifier x)"
        " (Add (Identifier x) (IntLiteral 1))"
        ")"
    )

def test_09():
    # Arrange
    test_string = ":"
    # Act
    ast = get_ast("coords_range", test_string)
    # Assert
    assert str(ast) == (
        "(Range"
        " (RangePlaceholder Min)"
        " (RangePlaceholder Max)"
        ")"
    )
