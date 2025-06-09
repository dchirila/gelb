#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import get_ast


def test_1d_lattice_instantiation():
    # Arrange
    test_string = "lattice f(1, 3, bool, 32, true);"
    # Act
    ast = get_ast("lattice_insta_stmt", test_string)
    # Assert (test the AST)
    assert str(ast) == (
        "(LatticeInstaStmt"
        " (Identifier f)"
        " (IntLiteral 1)"
        " (IntLiteral 3)"
        " (ArrayDataType bool (List ))"
        " (IntLiteral 32)"
        " (BoolLiteral true)"
        ")"
    )


def test_2d_lattice_instantiation():
    # Arrange
    test_string = "lattice g(2, 9, real32, {64, 64}, {false, true});"
    # Act
    ast = get_ast("lattice_insta_stmt", test_string)
    # Assert (test the AST)
    assert str(ast) == (
        "(LatticeInstaStmt"
        " (Identifier g)"
        " (IntLiteral 2)"
        " (IntLiteral 9)"
        " (ArrayDataType real32 (List ))"
        " (ArrayLiteral1D (IntLiteral 64) (IntLiteral 64))"
        " (ArrayLiteral1D (BoolLiteral false) (BoolLiteral true))"
        ")"
    )
