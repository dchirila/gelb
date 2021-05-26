#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import ASTBuilderVisitor, get_ast


def test_simple():
    # Arrange
    test_string = """
    global_constants {
        const int CX = 0;//a nasty comment
        const int Z = /*why not another comment */123;
        }
    """
    # Act (trigger parsing)
    ast = get_ast("global_constants_block", test_string)
    # Assert (test the parse tree)
    assert str(ast) == (
        "(GlobalConstantsBlock"
        " (ConstantDefinitionStmt CX (ScalarDataType int) (IntLiteral 0))"
        " (ConstantDefinitionStmt Z (ScalarDataType int) (IntLiteral 123))"
        ")"
    )

