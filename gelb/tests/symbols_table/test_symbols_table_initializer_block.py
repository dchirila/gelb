#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import get_ast, build_symbols_tables
from gelb.utils.exceptions import (
    GeLBExSymbolExists, GeLBExSymbolUnknown, GeLBExSymbolConstantRecursion
)
from gelb.frontend.SymbolsTable import SymbolsTable


def test_valid():
    # Arrange
    test_string = """
    initializer SetDFsToConstant { //
      const real64 PI = 3.141592653589793;
      f.out[x, y, z | :] = PI;
    }
    """
    # Act
    ast = get_ast("initializer_block", test_string)
    ast = build_symbols_tables(ast, symbol_to_ignore_for_testing="f")
    assert repr(ast.symbol_defs) == (
        "(PI"
        " \"constant definition\""
        " (ConstantDefinitionStmt"
        " (Identifier PI)"
        " (ScalarDataType real64)"
        " (RealLiteral 3.141592653589793)"
        ")"
        ")"
    )


def test_invalid1():
    """
    Invalid because we re-define PI.
    """
    # Arrange
    test_string = """
    initializer SetDFsToConstant { //
      const real64 PI = 3.141592653589793;
      const real32 PI = 3.14159265;
      const real16 PI = 3.141;
      f.out[x, y, z | :] = PI;
    }
    """
    # Act
    ast = get_ast("initializer_block", test_string)
    with pytest.raises(GeLBExSymbolExists):
        ast = build_symbols_tables(ast, "f")


def test_invalid2():
    """
    Invalid because we refer to unknown symbol PI.

    Should raise a GeLBExSymbolUnknown exception.
    """
    # Arrange
    test_string = """
    initializer SetDFsToConstant { //
      const int TWOPI = PI;
      f.out[x, y, z | :] = TWOPI;
    }
    """
    # Act
    ast = get_ast("initializer_block", test_string)
    with pytest.raises(GeLBExSymbolUnknown):
        ast = build_symbols_tables(ast, "f")


def test_invalid3():
    """
    Invalid because we refer to unknown symbol TWOPI.

    Should raise a GeLBExSymbolUnknown exception.
    """
    # Arrange
    test_string = """
    initializer SetDFsToConstant { //
      f.out[x, y, z | :] = TWOPI;
    }
    """
    # Act
    ast = get_ast("initializer_block", test_string)
    with pytest.raises(GeLBExSymbolUnknown):
        ast = build_symbols_tables(ast, "f")


def test_invalid4():
    """
    Invalid because we refer to unknown symbol PI.

    Should raise a GeLBExSymbolUnknown exception.
    """
    # Arrange
    test_string = """
    initializer SetDFsToConstant { //
      int tutu;
      tutu = PI;
      f.out[x, y, z | :] = tutu;
    }
    """
    # Act
    ast = get_ast("initializer_block", test_string)
    with pytest.raises(GeLBExSymbolUnknown):
        ast = build_symbols_tables(ast, "f")


def test_invalid5():
    """
    Invalid because symbol NY refers to itself (infinite recursion).

    Should raise a GeLBExSymbolRecursion exception.
    """
    # Arrange
    test_string = """
    initializer SetDFsToConstant { //
      const int NX = 123;
      const int NY = -2 * NY + NX;
      g.out[x, y, z | :] = NY;
    }
    """
    # Act
    ast = get_ast("initializer_block", test_string)
    with pytest.raises(GeLBExSymbolConstantRecursion):
        ast = build_symbols_tables(ast, "g")
