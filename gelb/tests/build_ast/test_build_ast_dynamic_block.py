#!/usr/bin/env python3

import pytest
from frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_simple():
    # Arrange
    test_string = """
    dynamic SetDFsToOne {
      f.out[x | 0] = 1;
    }
    """
    # Act
    ast = get_ast("dynamic_block", test_string)
    # Assert
    assert str(ast) == (
        "(Dynamic"
        " (Identifier SetDFsToOne)"
        " (LatticeOutSelectionAssignmentStmt"
        " (RectSelOfLatticeOutDFs"
        " (Identifier f)"
        " (Range (Identifier x) (Identifier x))"
        " (Range (IntLiteral 0) (IntLiteral 0))"
        ")"
        " (IntLiteral 1)"
        ")"
        ")"
    )
