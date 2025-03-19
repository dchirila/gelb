#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_simple():
    # Arrange
    test_string = "{1, 2, 3}"
    # Act (trigger parsing & building of sub-AST)
    ast = get_ast("array_literal_1d", test_string)
    # Assert (test the (sub-)AST, based on string representation)
    assert str(ast) == (
        "(ArrayLiteral1D"
        " (IntLiteral 1)"
        " (IntLiteral 2)"
        " (IntLiteral 3)"
        ")"
    )

def test_with_comments_and_whitespace():
    # Arrange
    test_string = "/* comment 1*/{\n123// comment 2\n, 456//\n}"
    # Act (trigger parsing & building of sub-AST)
    ast = get_ast("array_literal_1d", test_string)
    # Assert (test the (sub-)AST, based on string representation)
    assert str(ast) == (
        "(ArrayLiteral1D"
        " (IntLiteral 123)"
        " (IntLiteral 456)"
        ")"
    )
