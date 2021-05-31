#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import ASTBuilderVisitor, get_ast


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

def test_simple_real_elems():
    # Arrange
    test_string = "{1.2, 3.4}"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(ArrayLiteral1D (RealLiteral 1.2) (RealLiteral 3.4))"



