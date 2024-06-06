#!/usr/bin/env python3

import pytest
from frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_01():
    # Arrange
    test_string = "my_array[x]"
    # Act
    ast = get_ast("rect_sel_of_array_elems", test_string)
    # Assert
    assert str(ast) == (
        "(RectSelOfArrayElems"
        " (Identifier my_array)"
        " (Range (Identifier x) (Identifier x))"
        ")"
    )

def test_02():
    # Arrange
    test_string = "my_array[:x]"
    # Act
    ast = get_ast("rect_sel_of_array_elems", test_string)
    # Assert
    assert str(ast) == (
        "(RectSelOfArrayElems"
        " (Identifier my_array)"
        " (Range (RangePlaceholder Min) (Identifier x))"
        ")"
    )

def test_03():
    # Arrange
    test_string = "my_array[x:]"
    # Act
    ast = get_ast("rect_sel_of_array_elems", test_string)
    # Assert
    assert str(ast) == (
        "(RectSelOfArrayElems"
        " (Identifier my_array)"
        " (Range (Identifier x) (RangePlaceholder Max))"
        ")"
    )

def test_04():
    # Arrange
    test_string = "my_array[x-1:y+2]"
    # Act
    ast = get_ast("rect_sel_of_array_elems", test_string)
    # Assert
    assert str(ast) == (
        "(RectSelOfArrayElems"
        " (Identifier my_array)"
        " (Range"
        " (Sub (Identifier x) (IntLiteral 1))"
        " (Add (Identifier y) (IntLiteral 2))"
        ")"
        ")"
    )

def test_05():
    # Arrange
    test_string = "__YOUR__array[2*x+1:3*x-1, :y-1]"
    # Act
    ast = get_ast("rect_sel_of_array_elems", test_string)
    # Assert
    assert str(ast) == (
        "(RectSelOfArrayElems"
        " (Identifier __YOUR__array)"
        " (Range"
            " (Add"
                " (Mul"
                    " (IntLiteral 2)"
                    " (Identifier x)"
                ")"
            " (IntLiteral 1)"
            ")"
            " (Sub"
                " (Mul"
                    " (IntLiteral 3)"
                    " (Identifier x)"
                ")"
            " (IntLiteral 1)"
            ")"
        ")"
        " (Range"
            " (RangePlaceholder Min)"
            " (Sub"
                " (Identifier y)"
                " (IntLiteral 1)"
            ")"
        ")"
        ")"
    )

def test_06():
    # Arrange
    test_string = "__YOUR__array[x+1, y-1]"
    # Act
    ast = get_ast("rect_sel_of_array_elems", test_string)
    # Assert
    assert str(ast) == (
        "(RectSelOfArrayElems"
        " (Identifier __YOUR__array)"
        " (Range"
        " (Add"
        " (Identifier x)"
        " (IntLiteral 1)"
        ")"
        " (Add"
        " (Identifier x)"
        " (IntLiteral 1)"
        ")"
        ")"
        " (Range"
        " (Sub"
        " (Identifier y)"
        " (IntLiteral 1)"
        ")"
        " (Sub"
        " (Identifier y)"
        " (IntLiteral 1)"
        ")"
        ")"
        ")"
    )
