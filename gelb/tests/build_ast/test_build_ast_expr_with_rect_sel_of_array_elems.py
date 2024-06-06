#!/usr/bin/env python3

import pytest
from frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_rect_sel_array_plus_int():
    # Arrange
    test_string = "myarray[j:j+1, k-1:k+1] + 12"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == (
        "(Add"
        " (RectSelOfArrayElems"
        " (Identifier myarray)"
        " (Range"
        " (Identifier j)"
        " (Add (Identifier j) (IntLiteral 1))"
        ")"
        " (Range"
        " (Sub (Identifier k) (IntLiteral 1))"
        " (Add (Identifier k) (IntLiteral 1))"
        ")"
        ")"
        " (IntLiteral 12)"
        ")"
    )

def test_rect_sel_array_plus_array_literal_real():
    # Arrange
    test_string = "myarray[j:j+1, k-1:k+1] + {9.8, 7.6, 5.4}"
    # Act
    ast = get_ast("expr", test_string)
    # Assert
    assert str(ast) == (
        "(Add"
        " (RectSelOfArrayElems"
        " (Identifier myarray)"
        " (Range"
        " (Identifier j)"
        " (Add (Identifier j) (IntLiteral 1))"
        ")"
        " (Range"
        " (Sub (Identifier k) (IntLiteral 1))"
        " (Add (Identifier k) (IntLiteral 1))"
        ")"
        ")"
        " (ArrayLiteral1D"
        " (RealLiteral 9.8)"
        " (RealLiteral 7.6)"
        " (RealLiteral 5.4)"
        ")"
        ")"
    )
