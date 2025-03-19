#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_simple_identifier():
    # Arrange
    test_string = "alpha"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(Identifier alpha)"

def test_identifier_plus_int():
    # Arrange
    test_string = "beta + 97"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == (
        "(Add"
        " (Identifier beta)"
        " (IntLiteral 97)"
        ")"
    )

def test_real_times_identifier():
    # Arrange
    test_string = "3.14 * gamma"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == (
        "(Mul"
        " (RealLiteral 3.14)"
        " (Identifier gamma)"
        ")"
    )
