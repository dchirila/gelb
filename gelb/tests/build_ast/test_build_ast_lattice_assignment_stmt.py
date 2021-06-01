#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import ASTBuilderVisitor, get_ast


def test_simple():
    # Arrange
    test_string = "f.out[x, y|:] = 3;"
    # Act
    ast = get_ast("lattice_assignment_stmt", test_string)
    # Assert
    assert str(ast) == (
        "(LatticeAssignmentStmt"
        " (RectSelOfLatticeOutDFs"
        " (Range (Identifier x) (Identifier x))"
        " (Range (Identifier y) (Identifier y))"
        " (Range (RangePlaceholder Min) (RangePlaceholder Max))"
        ")"
        " (IntLiteral 3)"
        ")"
    )
