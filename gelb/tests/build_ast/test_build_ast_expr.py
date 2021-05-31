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
    # Assert (test the parse tree)
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
    # Assert (test the parse tree)
    assert str(ast) == "(UnaryMinusExpr (IntLiteral 981))"

def test_really_positive_int():
    # Arrange
    test_string = "+29"
    # Act
    ast = get_ast("expr", test_string)
    # Assert (test the parse tree)
    assert str(ast) == "(IntLiteral 29)"

# def test_int_plus_int():
#     # Arrange
#     test_string = "123 + 321"
#     # Act (trigger parsing)
#     result = get_cst_as_string("expr", test_string)
#     # Assert (test the parse tree)
#     assert result == "(expr 123)"
