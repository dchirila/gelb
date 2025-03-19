#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_1d_array_type():
    # Arrange
    test_string = "array<int64, 3>"
    # Act
    ast = get_ast("array_data_type", test_string)
    # Assert
    assert str(ast) == (
        "(ArrayDataType"
        " (ScalarDataType int64)"
        " (IntLiteral 3)"
        ")"
    )

def test_2d_array_type():
    # Arrange
    test_string = "array<real64, {2, 3}>"
    # Act
    ast = get_ast("array_data_type", test_string)
    # Assert
    assert str(ast) == (
        "(ArrayDataType"
        " (ScalarDataType real64)"
        " (ArrayLiteral1D (IntLiteral 2) (IntLiteral 3))"
        ")"
    )