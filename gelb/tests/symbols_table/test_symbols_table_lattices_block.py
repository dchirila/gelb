#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import get_ast, build_symbols_tables
from gelb.utils.exceptions import GeLBExSymbolExists
from gelb.SymbolsTable import SymbolsTable


def test_valid():
    # Arrange
    test_string = """
    lattices {
      lattice f(2,          // d
                9,          // q
                real64,     // df_type
                {256, 256}  // size
      );
      lattice g(2,          // d
                5,          // q
                real64,     // df_type
                {256, 256}  // size
      );
    }
    """
    # Act
    ast = get_ast("lattices_block", test_string)
    ast = build_symbols_tables(ast)
    assert repr(ast.symbols) == (
        "(f"
        " \"lattice instance\""
        " (LatticeInstaStmt"
        " (Identifier f)"
        " (IntLiteral 2)"
        " (IntLiteral 9)"
        " (ScalarDataType real64)"
        " (ArrayLiteral1D (IntLiteral 256) (IntLiteral 256))"
        ")"
        ")"
        " (g"
        " \"lattice instance\""
        " (LatticeInstaStmt"
        " (Identifier g)"
        " (IntLiteral 2)"
        " (IntLiteral 5)"
        " (ScalarDataType real64)"
        " (ArrayLiteral1D (IntLiteral 256) (IntLiteral 256))"
        ")"
        ")"
    )


def test_invalid():
    # Arrange
    test_string = """
    lattices {
      lattice f(3,               // d
                19,              // q
                real64,          // df_type
                {256, 256, 256}  // size
      );
      lattice g(3,               // d
                5,               // q
                real64,          // df_type
                {256, 256, 256}  // size
      );
      lattice f(3,               // d
                19,              // q
                real64,          // df_type
                {256, 256, 256}  // size
      );
    }
    """
    # Act
    ast = get_ast("lattices_block", test_string)
    with pytest.raises(GeLBExSymbolExists):
        ast = build_symbols_tables(ast)
