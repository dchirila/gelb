#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import (
    ASTBuilderVisitor,
    get_ast,
    build_symbols_tables,
    resolve_all_constants
)
from gelb.utils.exceptions import (
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
            " (ArrayDataType int (List ))"
            " (IntLiteral 12))"
        " (ConstantDefinitionStmt"
            " (Identifier TWENTYFOUR)"
            " (ArrayDataType int (List ))"
            " (Add (Mul (IntLiteral 2) (IntLiteral 12)) (IntLiteral 12))))"
    )


def test_valid2():
    """Resolve a real64 constant, which depends on another real64 constant.

    A reference to a constant is substituted at the constant's declared
    type: the copy of PI's value arrives wrapped in a conversion to
    real64, so a `const real P = 7` is the real 7.0 wherever it is used
    (the declared width was once lost between declaration and use).
    Integer constants are substituted as written (test_valid1).
    """
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
            " (ArrayDataType real64 (List ))"
            " (RealLiteral 3.141592653589793))"
        " (ConstantDefinitionStmt"
            " (Identifier TENPI)"
            " (ArrayDataType real64 (List ))"
            " (Mul (IntrinsicCall real64((RealLiteral 3.141592653589793)))"
            " (RealLiteral 10.0))))"
    )


def test_valid3():
    """Resolve an array constant with a narrow element type.

    The substituted copy is promoted to the declared array type, so
    arithmetic on the array uses the values the array stores, however
    the array was initialized (an integer 16777217 in a real32 array is
    16777216.0); an int array is substituted as written.
    """
    test_string = """
    global_constants {
      const array[real32, 2] A = {1.5, -2.0};
      const array[real32, 2] B = A * 2.0;
      const array[int, 2] N = {1, 2};
      const array[int, 2] M = N * 2;
    }
    """
    ast = get_ast("global_constants_block", test_string)
    ast = build_symbols_tables(ast)
    ast = resolve_all_constants(ast)
    assert str(ast) == (
        "(GlobalConstantsBlock"
        " (ConstantDefinitionStmt"
            " (Identifier A)"
            " (ArrayDataType real32 (IntLiteral 2))"
            " (ArrayLiteral1D (RealLiteral 1.5) (UnaryMinusExpr (RealLiteral 2.0))))"
        " (ConstantDefinitionStmt"
            " (Identifier B)"
            " (ArrayDataType real32 (IntLiteral 2))"
            " (Mul (TypePromotion (ArrayLiteral1D (RealLiteral 1.5)"
            " (UnaryMinusExpr (RealLiteral 2.0))) -> (ArrayDataType real32 (IntLiteral 2)))"
            " (RealLiteral 2.0)))"
        " (ConstantDefinitionStmt"
            " (Identifier N)"
            " (ArrayDataType int (IntLiteral 2))"
            " (ArrayLiteral1D (IntLiteral 1) (IntLiteral 2)))"
        " (ConstantDefinitionStmt"
            " (Identifier M)"
            " (ArrayDataType int (IntLiteral 2))"
            " (Mul (ArrayLiteral1D (IntLiteral 1) (IntLiteral 2)) (IntLiteral 2))))"
    )

