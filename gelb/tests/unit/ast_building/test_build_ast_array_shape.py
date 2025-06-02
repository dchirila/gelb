#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_expr_shape():
    # Arrange
    test_string = "5"
    # Act
    ast = get_ast("array_shape", test_string)
    # Assert
    assert str(ast) == "(IntLiteral 5)"

def test_expr_identifier_shape():
    # Arrange
    test_string = "N"
    # Act
    ast = get_ast("array_shape", test_string)
    # Assert
    assert str(ast) == "(Identifier N)"

def test_array_literal_1d_shape():
    # Arrange
    test_string = "{2, 3}"
    # Act
    ast = get_ast("array_shape", test_string)
    # Assert
    expected = "(ArrayLiteral1D (IntLiteral 2) (IntLiteral 3))"
    assert str(ast) == expected

def test_array_literal_1d_complex_shape():
    # Arrange
    test_string = "{3, 4, 5}"
    # Act
    ast = get_ast("array_shape", test_string)
    # Assert
    expected = "(ArrayLiteral1D (IntLiteral 3) (IntLiteral 4) (IntLiteral 5))"
    assert str(ast) == expected

def test_expr_arithmetic_shape():
    # Arrange
    test_string = "N + 1"
    # Act
    ast = get_ast("array_shape", test_string)
    # Assert
    expected = "(Add (Identifier N) (IntLiteral 1))"
    assert str(ast) == expected