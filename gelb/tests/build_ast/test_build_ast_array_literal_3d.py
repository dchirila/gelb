#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import ASTBuilderVisitor, get_ast


def test_simple():
    # Arrange
    test_string = "{ {{1 ,2}, {  3,4  }}, {{5  ,  6}, {7,8    }} }"
    # Act (trigger parsing & building of sub-AST)
    ast = get_ast("array_literal_3d", test_string)
    # Assert (test the (sub-)AST, based on string representation)
    assert str(ast) == (
        "(ArrayLiteral3D {"
        "(ArrayLiteral2D {"
        "(ArrayLiteral1D {(IntLiteral 1), (IntLiteral 2)}), "
        "(ArrayLiteral1D {(IntLiteral 3), (IntLiteral 4)})"
        "}), "
        "(ArrayLiteral2D {"
        "(ArrayLiteral1D {(IntLiteral 5), (IntLiteral 6)}), "
        "(ArrayLiteral1D {(IntLiteral 7), (IntLiteral 8)})"
        "})"
        "})"
    )