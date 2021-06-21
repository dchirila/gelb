#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import get_ast, build_symbols_tables
from gelb.utils.exceptions import GeLBExSymbolExists
from gelb.SymbolsTable import SymbolsTable


def test_valid():
    # Arrange
    test_string = """
    gauge PiTimesCurrentState(out = {int state;}) { //
      const real64 PI = 3.141592653589793;
      state = f.in[x | 0];
    }
    """
    # Act
    ast = get_ast("gauge_block", test_string)
    ast = build_symbols_tables(ast)
    assert repr(ast.symbols) == (
        "(PI"
        " \"constant definition\""
        " (ConstantDefinitionStmt"
        " (Identifier PI)"
        " (ScalarDataType real64)"
        " (RealLiteral 3.141592653589793)"
        ")"
        ")"
    )


def test_invalid():
    """
    Invalid because we re-define PI.

    Should raise a GeLBExSymbolExists exception.
    """
    # Arrange
    test_string = """
    gauge PiTimesCurrentState(out = {int state;}) { //
      const real64 PI = 3.141592653589793;
      const real32 PI = 3.14159265;
      const real16 PI = 3.141;
      state = PI*f.in[x | 0];
    }
    """
    # Act
    ast = get_ast("gauge_block", test_string)
    with pytest.raises(GeLBExSymbolExists):
        ast = build_symbols_tables(ast)
