#!/usr/bin/env python3

import pytest
from frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_01():
    # Arrange
    test_string = "| :"
    # Act
    ast = get_ast("lattice_dfs_range", test_string)
    # Assert
    assert str(ast) == "(Range (RangePlaceholder Min) (RangePlaceholder Max))"

def test_02():
    # Arrange
    test_string = "|: Q"
    # Act
    ast = get_ast("lattice_dfs_range", test_string)
    # Assert
    assert str(ast) == "(Range (RangePlaceholder Min) (Identifier Q))"

def test_03():
    # Arrange
    test_string = "|2 :"
    # Act
    ast = get_ast("lattice_dfs_range", test_string)
    # Assert
    assert str(ast) == "(Range (IntLiteral 2) (RangePlaceholder Max))"

def test_04():
    # Arrange
    test_string = "|3 "
    # Act
    ast = get_ast("lattice_dfs_range", test_string)
    # Assert
    assert str(ast) == "(Range (IntLiteral 3) (IntLiteral 3))"

def test_05():
    # Arrange
    test_string = "|/* why not a comment here? :) */4 :Q"
    # Act
    ast = get_ast("lattice_dfs_range", test_string)
    # Assert
    assert str(ast) == "(Range (IntLiteral 4) (Identifier Q))"
