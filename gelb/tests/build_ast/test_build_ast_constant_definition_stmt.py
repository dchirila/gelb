#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import ASTBuilderVisitor, get_ast


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
    test_string = "const array<real32, 9> DFS = 1;"
    # Act (trigger parsing)
    ast = get_ast("constant_definition_stmt", test_string)
    # Assert (test the parse tree)
    assert str(ast) == (
            "(ConstantDefinitionStmt"
            " (Identifier DFS)"
            " (ArrayDataType (ScalarDataType real32) (IntLiteral 9))"
            " (IntLiteral 1)"
            ")"
    )

# def test_1d_array_real32_init_with_array_lit():
#     # Arrange
#     test_string = "const array<real32, 3> TMP = {1, 0, 29};"
#     # Act (trigger parsing)
#     ast = get_ast("constant_definition_stmt", test_string)
#     # Assert (test the parse tree)
#     assert str(ast) == (
#         "(ConstantDefinitionStmt"
#         " (Identifier TMP)"
#         " (ArrayDataType (ScalarDataType real32) (IntLiteral 9))"
#         " (IntLiteral 1)"
#         ")"
#     )
