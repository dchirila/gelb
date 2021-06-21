#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import get_ast, build_symbols_tables
from gelb.utils.exceptions import GeLBExSymbolExists
from gelb.SymbolsTable import SymbolsTable


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
    assert repr(ast.symbols) == (
        "(CX"
        " \"(ScalarDataType int)\""
        " (ConstantDefinitionStmt"
        " (Identifier CX)"
        " (ScalarDataType int)"
        " (IntLiteral 0)"
        "))"
        " (Z"
        " \"(ScalarDataType real64)\""
        " (ConstantDefinitionStmt"
        " (Identifier Z)"
        " (ScalarDataType real64)"
        " (IntLiteral 123)"
        "))"
    )

def test_invalid():
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
