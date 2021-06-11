#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import ASTBuilderVisitor, get_ast


def test_int_array_plus_int():
    # Arrange
    test_string = "{1, 2} + 34"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == (
        "(Add"
        " (ArrayLiteral1D (IntLiteral 1) (IntLiteral 2))"
        " (IntLiteral 34)"
        ")"
    )

def test_array_of_identifiers_plus_real():
    # Arrange
    test_string = "{alpha, beta} + 34.99"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == (
        "(Add"
        " (ArrayLiteral1D (Identifier alpha) (Identifier beta))"
        " (RealLiteral 34.99)"
        ")"
    )

def test_int_array_plus_int_array():
    # Arrange
    test_string = "{1, 2} + {34, 56}"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == (
        "(Add"
        " (ArrayLiteral1D (IntLiteral 1) (IntLiteral 2))"
        " (ArrayLiteral1D (IntLiteral 34) (IntLiteral 56))"
        ")"
    )

def test_real_array_plus_int_array():
    # Arrange
    test_string = "{1.23, 2.56} + {34, 56}"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == (
        "(Add"
        " (ArrayLiteral1D (RealLiteral 1.23) (RealLiteral 2.56))"
        " (ArrayLiteral1D (IntLiteral 34) (IntLiteral 56))"
        ")"
    )
