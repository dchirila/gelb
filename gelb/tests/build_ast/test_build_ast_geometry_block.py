#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import ASTBuilderVisitor, get_ast


def test_simple():
    # Arrange
    test_string = """
    geometry { //
      nodes[:] = BULK;
    }
    """
    # Act
    ast = get_ast("geometry_block", test_string)
    # Assert
    assert str(ast) == (
        "(GeometryBlock"
            " (PaintNodesStmt"
            " (Identifier BULK)"
            " (Range (RangePlaceholder Min) (RangePlaceholder Max))"
            ")"
        ")"
    )
