#!/usr/bin/env python3

import pytest
from frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_true():
    # Arrange
    test_string = "true"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(BoolLiteral true)"

def test_false():
    # Arrange
    test_string = "false"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == "(BoolLiteral false)"

