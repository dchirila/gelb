#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_scalar():
    # Arrange
    test_string = "int x;"
    # Act
    ast = get_ast("variable_declaration_stmt", test_string)
    # Assert
    assert str(ast) == (
        "(VariableDeclarationStmt"
        " (Identifier x)"
        " (ScalarDataType int)"
        ")"
    )

def test_1d_array():
    # Arrange
    test_string = "array<real, 2> x;"
    # Act
    ast = get_ast("variable_declaration_stmt", test_string)
    # Assert
    assert str(ast) == (
        "(VariableDeclarationStmt"
        " (Identifier x)"
        " (ArrayDataType"
            " (ScalarDataType real)"
            " (IntLiteral 2)"
        ")"
        ")"
    )

def test_2d_array():
    # Arrange
    test_string = "array<real, {2, 3}> y;"
    # Act
    ast = get_ast("variable_declaration_stmt", test_string)
    # Assert
    assert str(ast) == (
        "(VariableDeclarationStmt"
        " (Identifier y)"
        " (ArrayDataType"
            " (ScalarDataType real)"
            " (ArrayLiteral1D (IntLiteral 2) (IntLiteral 3))"
        ")"
        ")"
    )
