#!/usr/bin/env python3

import pytest
from frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_simple():
    # Arrange
    test_string = "nodes[:] = BULK;"
    # Act
    ast = get_ast("paint_nodes_stmt", test_string)
    # Assert
    assert str(ast) == (
        "(PaintNodesStmt"
        " (List (Range (RangePlaceholder Min) (RangePlaceholder Max)))"
        " (Identifier BULK)"
        ")"
    )
