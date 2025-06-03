#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_valid1():
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
            " (List (Range (RangePlaceholder Min) (RangePlaceholder Max)))"
            " (Identifier BULK)"
            ")"
        ")"
    )


def test_valid2():
    # Arrange
    test_string = """
    geometry { //
      nodes[:, :] = BULK;
    }
    """
    # Act
    ast = get_ast("geometry_block", test_string)
    # Assert
    assert str(ast) == (
        "(GeometryBlock"
        " (PaintNodesStmt"
        " (List"
            " (Range (RangePlaceholder Min) (RangePlaceholder Max))"
            " (Range (RangePlaceholder Min) (RangePlaceholder Max))"
        ")"
        " (Identifier BULK)"
        ")"
        ")"
    )
