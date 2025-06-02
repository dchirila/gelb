#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_simple():
    # Arrange
    test_string = """
    initializer ToZero {
      h.out[x | :] = 0;
    }
    """
    # Act
    ast = get_ast("initializer_block", test_string)
    # Assert
    assert str(ast) == (
        "(Initializer"
        " (Identifier ToZero)"
        " (LatticeOutSelectionAssignmentStmt"
            " (RectSelOfLatticeOutDFs"
                " (Identifier h)"
                " (Range (Identifier x) (Identifier x))"
                " (Range (RangePlaceholder Min) (RangePlaceholder Max))"
            ")"
            " (IntLiteral 0)"
        ")"
        ")"
    )
