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
            "(ConstantDefinitionStmt " +
            "LENGTH " +
            "(ScalarDataType int) " +
            "(IntLiteral 32)" +
            ")"
    )

def test_1d_array_real32():
    # Arrange
    test_string = "const array<real32, 9> DFS = 1;"
    # Act (trigger parsing)
    ast = get_ast("constant_definition_stmt", test_string)
    # Assert (test the parse tree)
    assert str(ast) == (
            "(ConstantDefinitionStmt " +
            "DFS " +
            "(ArrayDataType (ScalarDataType real32) (IntLiteral 9)) " +
            "(IntLiteral 1)" +
            ")"
    )
