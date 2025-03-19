#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_01():
    # Arrange
    test_string = "f.out[x | 0]"
    # Act
    ast = get_ast("rect_sel_of_lattice_out_dfs", test_string)
    # Assert
    assert str(ast) == (
        "(RectSelOfLatticeOutDFs"
        " (Identifier f)"
        " (Range (Identifier x) (Identifier x))"
        " (Range (IntLiteral 0) (IntLiteral 0))"
        ")"
    )

def test_02():
    # Arrange
    test_string = "g.out[x+1, y-1 | :]"
    # Act
    ast = get_ast("rect_sel_of_lattice_out_dfs", test_string)
    # Assert
    assert str(ast) == (
        "(RectSelOfLatticeOutDFs"
        " (Identifier g)"
        " (Range"
        " (Add"
        " (Identifier x)"
        " (IntLiteral 1)"
        ")"
        " (Add"
        " (Identifier x)"
        " (IntLiteral 1)"
        ")"
        ")"
        " (Range"
        " (Sub"
        " (Identifier y)"
        " (IntLiteral 1)"
        ")"
        " (Sub"
        " (Identifier y)"
        " (IntLiteral 1)"
        ")"
        ")"
        " (Range (RangePlaceholder Min) (RangePlaceholder Max))"
        ")"
    )

def test_03():
    # Arrange
    test_string = "ff.out[-1+x, 3-y, z-x | 3:Q]"
    # Act
    ast = get_ast("rect_sel_of_lattice_out_dfs", test_string)
    # Assert
    assert str(ast) == (
        "(RectSelOfLatticeOutDFs"
        " (Identifier ff)"
        " (Range"
        " (Add (UnaryMinusExpr (IntLiteral 1)) (Identifier x))"
        " (Add (UnaryMinusExpr (IntLiteral 1)) (Identifier x))"
        ")"
        " (Range"
        " (Sub (IntLiteral 3) (Identifier y))"
        " (Sub (IntLiteral 3) (Identifier y))"
        ")"
        " (Range"
        " (Sub (Identifier z) (Identifier x))"
        " (Sub (Identifier z) (Identifier x))"
        ")"
        " (Range (IntLiteral 3) (Identifier Q))"
        ")"
    )
