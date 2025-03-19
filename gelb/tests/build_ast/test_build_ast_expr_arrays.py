#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_simple_bool_elems():
    # Arrange
    test_string = "{true, false}"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(ArrayLiteral1D (BoolLiteral true) (BoolLiteral false))"

def test_simple_int_elems():
    # Arrange
    test_string = "{1, 2}"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(ArrayLiteral1D (IntLiteral 1) (IntLiteral 2))"

def test_int_array1d_plus_int():
    # Arrange
    test_string = "{1, 2} + 1"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == (
        "(Add"
        " (ArrayLiteral1D (IntLiteral 1) (IntLiteral 2))"
        " (IntLiteral 1)"
        ")"
    )

def test_simple_real_elems():
    # Arrange
    test_string = "{1.2, 3.4}"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(ArrayLiteral1D (RealLiteral 1.2) (RealLiteral 3.4))"

def test_real_array1d_minus_real():
    # Arrange
    test_string = "{1.2, 3.4} - 5.6"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == (
        "(Sub"
        " (ArrayLiteral1D (RealLiteral 1.2) (RealLiteral 3.4))"
        " (RealLiteral 5.6)"
        ")"
    )



