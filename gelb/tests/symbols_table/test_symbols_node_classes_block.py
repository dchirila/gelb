#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import get_ast, build_symbols_tables
from gelb.utils.exceptions import GeLBExSymbolExists
from gelb.SymbolsTable import SymbolsTable


def test_valid():
    # Arrange
    test_string = """
    node_classes { //
      node_class TOP(SetDFsToZero, SetDFsToOne, CurrentState);
      node_class BULK(SetDFsToZero, SetDFsToOne, CurrentState);
    }
    """
    # Act
    ast = get_ast("node_classes_block", test_string)
    ast = build_symbols_tables(ast)
    assert repr(ast.symbol_defs) == (
        "(TOP"
        " \"node class\""
        " (NodeClassInstaStmt"
        " (Identifier TOP)"
        " (Identifier SetDFsToZero)"
        " (Identifier SetDFsToOne)"
        " (Identifier CurrentState)"
        ")"
        ")"
        " (BULK"
        " \"node class\""
        " (NodeClassInstaStmt"
        " (Identifier BULK)"
        " (Identifier SetDFsToZero)"
        " (Identifier SetDFsToOne)"
        " (Identifier CurrentState)"
        ")"
        ")"
    )


def test_invalid():
    """
    Invalid because we re-define f.

    Should raise a GeLBExSymbolExists exception.
    """
    # Arrange
    test_string = """
    node_classes { //
      node_class BULK(SetDFsToZero, SetDFsToOne, CurrentState);
      node_class BULK(SetDFsToZero, SetDFsToOne, CurrentState);
    }
    """
    # Act
    ast = get_ast("node_classes_block", test_string)
    with pytest.raises(GeLBExSymbolExists):
        ast = build_symbols_tables(ast)
