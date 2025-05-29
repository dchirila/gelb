#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_scalar_int():
    # Arrange
    test_string = "const int LENGTH = 32;"
    # Act (trigger parsing & building of sub-AST)
    ast = get_ast("constant_definition_stmt", test_string)
    # Assert (test the (sub-)AST, based on string representation)
    assert str(ast) == (
            "(ConstantDefinitionStmt"
            " (Identifier LENGTH)"
            " (ScalarDataType int)"
            " (IntLiteral 32)"
            ")"
    )

def test_1d_array_real32_init_with_scalar():
    # Arrange
    test_string = "const array[real32, 9] DFS = 1;"
    # Act (trigger parsing)
    ast = get_ast("constant_definition_stmt", test_string)
    # Assert (test the AST)
    assert str(ast) == (
            "(ConstantDefinitionStmt"
            " (Identifier DFS)"
            " (ArrayDataType (ScalarDataType real32) (IntLiteral 9))"
            " (IntLiteral 1)"
            ")"
    )

def test_1d_array_real32_init_with_array_lit():
    # Arrange
    test_string = "const array[real32, 3] TMP = {1, 0, 29};"
    # Act (trigger parsing)
    ast = get_ast("constant_definition_stmt", test_string)
    # Assert (test the AST)
    assert str(ast) == (
        "(ConstantDefinitionStmt"
        " (Identifier TMP)"
        " (ArrayDataType (ScalarDataType real32) (IntLiteral 3))"
        " (ArrayLiteral1D (IntLiteral 1) (IntLiteral 0) (IntLiteral 29))"
        ")"
    )

def test_2d_array_real_init_with_2d_array_lit():
    # Arrange
    test_string = "const array[real, {2,2}] W = {{1,2}, {3,4}};"
    # Act (trigger parsing)
    ast = get_ast("constant_definition_stmt", test_string)
    # Assert (test the AST)
    assert str(ast) == (
        "(ConstantDefinitionStmt"
        " (Identifier W)"
        " (ArrayDataType"
            " (ScalarDataType real)"
            " (ArrayLiteral1D (IntLiteral 2) (IntLiteral 2))"
        ")"
        " (ArrayLiteral2D"
            " (ArrayLiteral1D (IntLiteral 1) (IntLiteral 2))"
            " (ArrayLiteral1D (IntLiteral 3) (IntLiteral 4))"
        ")"
        ")"
    )

def test_3d_array_real_init_with_3d_array_lit():
    # Arrange
    test_string = "const array[real, {2,2,2}] Q = {{{1,2}, {3,4}}, {{5,6}, {7,8}}};"
    # Act (trigger parsing)
    ast = get_ast("constant_definition_stmt", test_string)
    # Assert (test the AST)
    assert str(ast) == (
        "(ConstantDefinitionStmt"
        " (Identifier Q)"
        " (ArrayDataType"
        " (ScalarDataType real)"
        " (ArrayLiteral1D (IntLiteral 2) (IntLiteral 2) (IntLiteral 2))"
        ")"
        " (ArrayLiteral3D"
        " (ArrayLiteral2D"
        " (ArrayLiteral1D (IntLiteral 1) (IntLiteral 2))"
        " (ArrayLiteral1D (IntLiteral 3) (IntLiteral 4))"
        ")"
        " (ArrayLiteral2D"
        " (ArrayLiteral1D (IntLiteral 5) (IntLiteral 6))"
        " (ArrayLiteral1D (IntLiteral 7) (IntLiteral 8))"
        ")"
        ")"
        ")"
    )
