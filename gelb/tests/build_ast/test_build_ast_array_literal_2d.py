#!/usr/bin/env python3

import pytest
from frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_simple():
    # Arrange
    test_string = "{{1, 2}, {3, 4} }"
    # Act (trigger parsing & building of sub-AST)
    ast = get_ast("array_literal_2d", test_string)
    # Assert (test the (sub-)AST, based on string representation)
    assert str(ast) == (
        "(ArrayLiteral2D"
        " (ArrayLiteral1D (IntLiteral 1) (IntLiteral 2))"
        " (ArrayLiteral1D (IntLiteral 3) (IntLiteral 4))"
        ")"
    )