#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import ASTBuilderVisitor, get_ast


def test_simple():
    # Arrange
    test_string = """
    initializer ToZero {
      f.out[x | :] = 0;
    }
    """
    # Act
    ast = get_ast("initializer_block", test_string)
    # Assert
    assert str(ast) == (
        "(Initializer"
        " (Identifier ToZero)"
        " (LatticeAssignmentStmt"
            " (RectSelOfLatticeOutDFs"
                " (Range (Identifier x) (Identifier x))"
                " (Range (RangePlaceholder Min) (RangePlaceholder Max))"
            ")"
            " (IntLiteral 0)"
        ")"
        ")"
    )
