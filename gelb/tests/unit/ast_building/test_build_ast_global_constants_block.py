#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import ASTBuilderVisitor, get_ast


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
    # Assert (test the AST)
    assert str(ast) == (
        "(GlobalConstantsBlock"
        " (ConstantDefinitionStmt"
            " (Identifier CX)"
            " (ArrayDataType int (List ))"
            " (IntLiteral 0)"
            ")"
        " (ConstantDefinitionStmt"
            " (Identifier Z)"
            " (ArrayDataType int (List ))"
            " (IntLiteral 123)"
            ")"
        ")"
    )

