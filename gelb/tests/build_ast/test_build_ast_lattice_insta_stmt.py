#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import get_ast


def test_1d_no_arg_keywords():
    # Arrange
    test_string = "lattice f(2, 9, bool);"
    # Act
    ast = get_ast("lattice_insta_stmt", test_string)
    # Assert (test the AST)
    assert str(ast) == (
        "(LatticeInstaStmt"
        " (Identifier f)"
        " (IntLiteral 2)"
        " (IntLiteral 9)"
        " (ScalarDataType bool)"
        ")"
    )


def test_2d_no_arg_keywords():
    # Arrange
    test_string = "lattice g(2, 9, real32);"
    # Act
    ast = get_ast("lattice_insta_stmt", test_string)
    # Assert (test the AST)
    assert str(ast) == (
        "(LatticeInstaStmt"
        " (Identifier g)"
        " (IntLiteral 2)"
        " (IntLiteral 9)"
        " (ScalarDataType real32)"
        ")"
    )
