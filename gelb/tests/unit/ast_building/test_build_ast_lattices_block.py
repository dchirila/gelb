#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_one_lattice_instance():
    # Arrange
    test_string = """lattices {
        lattice f(2, 9, bool, 32, false);
    }"""
    # Act
    ast = get_ast("lattices_block", test_string)
    # Assert (test the AST)
    assert str(ast) == (
        "(LatticesBlock"
        " (LatticeInstaStmt"
        " (Identifier f)"
        " (IntLiteral 2)"
        " (IntLiteral 9)"
        " (ScalarDataType bool)"
        " (IntLiteral 32)"
        " (BoolLiteral false)"
        ")"
        ")"
    )

def test_two_lattice_instances():
    # Arrange
    test_string = """lattices {
        lattice f(3, 19, real64, {64, 64, 64}, {true, true, true});
        lattice g(3, 5, real64, {32, 32, 32}, {false, false, false});
    }"""
    # Act
    ast = get_ast("lattices_block", test_string)
    # Assert (test the AST)
    assert str(ast) == (
        "(LatticesBlock"
        " (LatticeInstaStmt"
            " (Identifier f)"
            " (IntLiteral 3)"
            " (IntLiteral 19)"
            " (ScalarDataType real64)"
            " (ArrayLiteral1D (IntLiteral 64) (IntLiteral 64) (IntLiteral 64))"
            " (ArrayLiteral1D (BoolLiteral true) (BoolLiteral true) (BoolLiteral true))"
        ")"
        " (LatticeInstaStmt"
            " (Identifier g)"
            " (IntLiteral 3)"
            " (IntLiteral 5)"
            " (ScalarDataType real64)"
            " (ArrayLiteral1D (IntLiteral 32) (IntLiteral 32) (IntLiteral 32))"
            " (ArrayLiteral1D (BoolLiteral false) (BoolLiteral false) (BoolLiteral false))"
        ")"
        ")"
    )
