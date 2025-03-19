#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import get_ast, build_symbols_tables
from gelb.utils.exceptions import (
    GeLBExSymbolExists,
    GeLBExSymbolUnknown,
    GeLBExSymbolConstantRecursion,
    GeLBExSymbolRefBeforeDef
)
from gelb.frontend.SymbolsTable import SymbolsTable


def test_valid():
    # Arrange
    test_string = """
    global_constants {
        const int CX = 0;//a nasty comment
        const real64 Z = /*why not another comment */123;
        }
    """
    # Act
    ast = get_ast("global_constants_block", test_string)
    ast = build_symbols_tables(ast)
    assert repr(ast.symbol_defs) == (
        "(CX"
        " \"constant definition\""
        " (ConstantDefinitionStmt"
        " (Identifier CX)"
        " (ScalarDataType int)"
        " (IntLiteral 0)"
        "))"
        " (Z"
        " \"constant definition\""
        " (ConstantDefinitionStmt"
        " (Identifier Z)"
        " (ScalarDataType real64)"
        " (IntLiteral 123)"
        "))"
    )

def test_invalid1():
    """
    Invalid because we re-define NX.

    Should raise a GeLBExSymbolExists exception.
    """
    # Arrange
    test_string = """
    global_constants {
      const array<int32, {23, 32}> NX = 32;
      const array<real64, {23, 32}> NX = 3.14;
    }
    """
    # Act
    ast = get_ast("global_constants_block", test_string)
    with pytest.raises(GeLBExSymbolExists):
        ast = build_symbols_tables(ast)

def test_invalid2():
    """
    Invalid because we refer to unknown symbol NX.

    Should raise a GeLBExSymbolUnknown exception.
    """
    # Arrange
    test_string = """
    global_constants {
      const int NY = -2 * NX + NZ;
    }
    """
    # Act
    ast = get_ast("global_constants_block", test_string)
    with pytest.raises(GeLBExSymbolUnknown):
        ast = build_symbols_tables(ast)

def test_invalid3():
    """
    Invalid because symbol NY refers to itself (infinite recursion).

    Should raise a GeLBExSymbolRecursion exception.
    """
    # Arrange
    test_string = """
    global_constants {
      const int NX = 123;
      const int NY = -2 * NY + NX;
    }
    """
    # Act
    ast = get_ast("global_constants_block", test_string)
    with pytest.raises(GeLBExSymbolConstantRecursion):
        ast = build_symbols_tables(ast)


def test_invalid4():
    """Invalid, because we refer to TWELVE before we define it. """
    # Arrange
    test_string = """
    global_constants {
      const int TWENTYFOUR = 2 * TWELVE + TWELVE;
      const int TWELVE = 12;
    }
    """
    # Act
    ast = get_ast("global_constants_block", test_string)
    with pytest.raises(GeLBExSymbolRefBeforeDef):
        ast = build_symbols_tables(ast)
