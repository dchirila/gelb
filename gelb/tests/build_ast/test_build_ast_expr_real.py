#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import ASTBuilderVisitor, get_ast


def test_positive_real1():
    # Arrange
    test_string = "0."
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(RealLiteral 0.0)"

def test_positive_real2():
    # Arrange
    test_string = "0.1"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(RealLiteral 0.1)"

def test_positive_real3():
    # Arrange
    test_string = "0.e9"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(RealLiteral 0.0)"

def test_positive_real4():
    # Arrange
    test_string = "1.2e+9"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(RealLiteral 1200000000.0)"

def test_positive_real5():
    # Arrange
    test_string = "8.e-19"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(RealLiteral 8e-19)"

def test_positive_real6():
    # Arrange
    test_string = ".0"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(RealLiteral 0.0)"

def test_positive_real7():
    # Arrange
    test_string = ".1"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(RealLiteral 0.1)"

def test_positive_real8():
    # Arrange
    test_string = ".1e7"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(RealLiteral 1000000.0)"

def test_positive_real9():
    # Arrange
    test_string = ".1e-7"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(RealLiteral 1e-08)"
