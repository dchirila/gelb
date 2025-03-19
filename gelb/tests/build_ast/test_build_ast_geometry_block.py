#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_valid1():
    # Arrange
    test_string = """
    geometry { //
      set_grid_size(32);
      set_grid_periodicity(false);
      nodes[:] = BULK;
    }
    """
    # Act
    ast = get_ast("geometry_block", test_string)
    # Assert
    assert str(ast) == (
        "(GeometryBlock"
            " (GridSize (IntLiteral 32))"
            " (GridPeriodicity (BoolLiteral false))"
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
      set_grid_size({32, 32});
      set_grid_periodicity({true, false});
      nodes[:] = BULK;
    }
    """
    # Act
    ast = get_ast("geometry_block", test_string)
    # Assert
    assert str(ast) == (
        "(GeometryBlock"
        " (GridSize (ArrayLiteral1D (IntLiteral 32) (IntLiteral 32)))"
        " (GridPeriodicity"
            " (ArrayLiteral1D (BoolLiteral true) (BoolLiteral false))"
        ")"
        " (PaintNodesStmt"
        " (List (Range (RangePlaceholder Min) (RangePlaceholder Max)))"
        " (Identifier BULK)"
        ")"
        ")"
    )
