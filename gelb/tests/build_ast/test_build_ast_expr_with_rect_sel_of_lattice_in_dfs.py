#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import ASTBuilderVisitor, get_ast


def test_rect_sel_lattice_in_plus_int():
    # Arrange
    test_string = "f.in[x:x+1, y-1:y+1 | 2:] + 12"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == (
        "(Add"
        " (RectSelOfLatticeInDFs"
        " (Identifier f)"
        " (Range"
        " (Identifier x)"
        " (Add (Identifier x) (IntLiteral 1))"
        ")"
        " (Range"
        " (Sub (Identifier y) (IntLiteral 1))"
        " (Add (Identifier y) (IntLiteral 1))"
        ")"
        " (Range (IntLiteral 2) (RangePlaceholder Max))"
        ")"
        " (IntLiteral 12)"
        ")"
    )

def test_rect_sel_lattice_in_plus_real_array_literal():
    # Arrange
    test_string = "f.in[x:x+1, y-1:y+1 | 2:9] + {1.23, 4.56}"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == (
        "(Add"
        " (RectSelOfLatticeInDFs"
        " (Identifier f)"
        " (Range"
        " (Identifier x)"
        " (Add (Identifier x) (IntLiteral 1))"
        ")"
        " (Range"
        " (Sub (Identifier y) (IntLiteral 1))"
        " (Add (Identifier y) (IntLiteral 1))"
        ")"
        " (Range (IntLiteral 2) (IntLiteral 9))"
        ")"
        " (ArrayLiteral1D (RealLiteral 1.23) (RealLiteral 4.56))"
        ")"
    )
