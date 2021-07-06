#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import get_ast, build_symbols_tables
from gelb.utils.exceptions import (
    GeLBExSymbolExists, GeLBExSymbolUnknown, GeLBExSymbolConstantRecursion
)
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
    assert repr(ast.symbol_defs) == (
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


def test_invalid1():
    """
    Invalid because we re-define f.

    Should raise a GeLBExSymbolExists exception.
    """
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


def test_invalid2():
    """
    Invalid because f depends on unknown symbol TWO.

    Should raise a GeLBExSymbolUnknown exception.
    """
    # Arrange
    test_string = """
    lattices {
      lattice f(1 + TWO,         // d
                19,              // q
                real64,          // df_type
                {256, 256, 256}  // size
      );
    }
    """
    # Act
    ast = get_ast("lattices_block", test_string)
    with pytest.raises(GeLBExSymbolUnknown):
        ast = build_symbols_tables(ast)


def test_invalid3():
    """
    Invalid because f depends on unknown symbol TWO.

    Should raise a GeLBExSymbolUnknown exception.
    """
    # Arrange
    test_string = """
    lattices {
      lattice f(3,               // d
                TWO +17,         // q
                real64,          // df_type
                {256, 256, 256}  // size
      );
    }
    """
    # Act
    ast = get_ast("lattices_block", test_string)
    with pytest.raises(GeLBExSymbolUnknown):
        ast = build_symbols_tables(ast)


def test_invalid4():
    """
    Invalid because f depends on unknown symbol TWO.

    Should raise a GeLBExSymbolUnknown exception.
    """
    # Arrange
    test_string = """
    lattices {
      lattice f(3,                   // d
                19,                  // q
                real64,              // df_type
                {256, 254+TWO, 256}  // size
      );
    }
    """
    # Act
    ast = get_ast("lattices_block", test_string)
    with pytest.raises(GeLBExSymbolUnknown):
        ast = build_symbols_tables(ast)
