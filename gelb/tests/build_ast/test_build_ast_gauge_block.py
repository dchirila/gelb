#!/usr/bin/env python3

import pytest
from frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_simple():
    # Arrange
    test_string = """
    gauge CurrentState(out = {int state;}) { //
      state = g.in[x | 0];
    }
    """
    # Act
    ast = get_ast("gauge_block", test_string)
    # Assert
    assert str(ast) == (
        "(Gauge"
        " (Identifier CurrentState)"
        " (VariableDeclarationStmt"
            " (Identifier state)"
            " (ScalarDataType int)"
            ")"
        " (VariableAssignmentStmt"
            " (Identifier state)"
            " (RectSelOfLatticeInDFs"
                " (Identifier g)"
                " (Range (Identifier x) (Identifier x))"
                " (Range (IntLiteral 0) (IntLiteral 0))"
                ")"
            ")"
        ")"
    )
