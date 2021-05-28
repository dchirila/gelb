#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import ASTBuilderVisitor, get_ast


def test_simple():
    # Arrange
    test_string = """
    lattice_constants D2Q1 {
        const int D = 2;
        const int Q = 1;
        }
    """
    # Act
    ast = get_ast("lattice_constants_block", test_string)
    # Assert (test the parse tree)
    assert str(ast) == (
        "(LatticeConstantsBlock"
        " (Identifier D2Q1)"
            " (ConstantDefinitionStmt"
            " (Identifier D)"
            " (ScalarDataType int)"
            " (IntLiteral 2)"
            ")"
            " (ConstantDefinitionStmt"
            " (Identifier Q)"
            " (ScalarDataType int)"
            " (IntLiteral 1)"
            ")"
        ")"
    )
