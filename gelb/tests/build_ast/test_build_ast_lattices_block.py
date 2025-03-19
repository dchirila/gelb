#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_one_lattice_instance_no_arg_keywords():
    # Arrange
    test_string = """lattices {
        lattice f(2, 9, bool);
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
        ")"
        ")"
    )

def test_two_lattice_instances_no_arg_keywords():
    # Arrange
    test_string = """lattices {
        lattice f(3, 19, real64);
        lattice g(3, 5, real64);
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
        ")"
        " (LatticeInstaStmt"
            " (Identifier g)"
            " (IntLiteral 3)"
            " (IntLiteral 5)"
            " (ScalarDataType real64)"
        ")"
        ")"
    )
