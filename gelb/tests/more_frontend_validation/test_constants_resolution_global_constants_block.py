#!/usr/bin/env python3

import pytest
from frontend.stage1_frontend import (
    ASTBuilderVisitor,
    get_ast,
    build_symbols_tables,
    resolve_all_constants
)
from utils.exceptions import (
    GeLBExSymbolRefBeforeDef
)


def test_valid1():
    """Resolve an int constant, which depends on another int constant."""
    # Arrange
    test_string = """
    global_constants {
      const int TWELVE = 12;
      const int TWENTYFOUR = 2 * TWELVE + TWELVE;
    }
    """
    # Act
    ast = get_ast("global_constants_block", test_string)
    ast = build_symbols_tables(ast)
    ast = resolve_all_constants(ast)
    # Assert (test the AST)
    assert str(ast) == (
        "(GlobalConstantsBlock"
        " (ConstantDefinitionStmt"
            " (Identifier TWELVE)"
            " (ScalarDataType int)"
            " (IntLiteral 12))"
        " (ConstantDefinitionStmt"
            " (Identifier TWENTYFOUR)"
            " (ScalarDataType int)"
            " (Add (Mul (IntLiteral 2) (IntLiteral 12)) (IntLiteral 12))))"
    )


def test_valid2():
    """Resolve a real64 constant, which depends on another real64 constant."""
    # Arrange
    test_string = """
    global_constants {
      const real64 PI = 3.141592653589793;
      const real64 TENPI = PI * 10.0;
    }
    """
    # Act
    ast = get_ast("global_constants_block", test_string)
    ast = build_symbols_tables(ast)
    ast = resolve_all_constants(ast)
    # Assert (test the AST)
    assert str(ast) == (
        "(GlobalConstantsBlock"
        " (ConstantDefinitionStmt"
            " (Identifier PI)"
            " (ScalarDataType real64)"
            " (RealLiteral 3.141592653589793))"
        " (ConstantDefinitionStmt"
            " (Identifier TENPI)"
            " (ScalarDataType real64)"
            " (Mul (RealLiteral 3.141592653589793) (RealLiteral 10.0))))"
    )


