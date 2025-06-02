#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_simple_element_assignment():
    """Test assignment to a single array element: my_array[0] = 42;"""
    # Arrange
    test_string = "my_array[0] = 42;"
    # Act
    ast = get_ast("array_selection_assignment_stmt", test_string)
    # Assert
    assert str(ast) == (
        "(ArraySelectionAssignmentStmt"
        " (RectSelOfArrayElems"
        " (Identifier my_array)"
        " (Range (IntLiteral 0) (IntLiteral 0))"
        ")"
        " (IntLiteral 42)"
        ")"
    )


def test_variable_index_assignment():
    """Test assignment with variable index: arr[i] = value;"""
    # Arrange  
    test_string = "arr[i] = value;"
    # Act
    ast = get_ast("array_selection_assignment_stmt", test_string)
    # Assert
    assert str(ast) == (
        "(ArraySelectionAssignmentStmt"
        " (RectSelOfArrayElems"
        " (Identifier arr)"
        " (Range (Identifier i) (Identifier i))"
        ")"
        " (Identifier value)"
        ")"
    )


def test_slice_assignment():
    """Test assignment to array slice: my_array[1:3] = some_expr;"""
    # Arrange
    test_string = "my_array[1:3] = some_expr;"
    # Act
    ast = get_ast("array_selection_assignment_stmt", test_string)
    # Assert
    assert str(ast) == (
        "(ArraySelectionAssignmentStmt"
        " (RectSelOfArrayElems"
        " (Identifier my_array)"
        " (Range (IntLiteral 1) (IntLiteral 3))"
        ")"
        " (Identifier some_expr)"
        ")"
    )


def test_2d_array_assignment():
    """Test assignment to 2D array element: matrix[x, y] = value;"""
    # Arrange
    test_string = "matrix[x, y] = value;"
    # Act
    ast = get_ast("array_selection_assignment_stmt", test_string)
    # Assert
    assert str(ast) == (
        "(ArraySelectionAssignmentStmt"
        " (RectSelOfArrayElems"
        " (Identifier matrix)"
        " (Range (Identifier x) (Identifier x))"
        " (Range (Identifier y) (Identifier y))"
        ")"
        " (Identifier value)"
        ")"
    )


def test_complex_rhs_expression():
    """Test with complex RHS expression: arr[0] = a + b * 2;"""
    # Arrange
    test_string = "arr[0] = a + b * 2;"
    # Act
    ast = get_ast("array_selection_assignment_stmt", test_string)
    # Assert
    assert str(ast) == (
        "(ArraySelectionAssignmentStmt"
        " (RectSelOfArrayElems"
        " (Identifier arr)"
        " (Range (IntLiteral 0) (IntLiteral 0))"
        ")"
        " (Add"
        " (Identifier a)"
        " (Mul (Identifier b) (IntLiteral 2))"
        ")"
        ")"
    )


def test_complex_index_expression():
    """Test with complex index expression: arr[i + j] = value;"""
    # Arrange
    test_string = "arr[i + j] = value;"
    # Act
    ast = get_ast("array_selection_assignment_stmt", test_string)
    # Assert
    assert str(ast) == (
        "(ArraySelectionAssignmentStmt"
        " (RectSelOfArrayElems"
        " (Identifier arr)"
        " (Range (Add (Identifier i) (Identifier j)) (Add (Identifier i) (Identifier j)))"
        ")"
        " (Identifier value)"
        ")"
    )


def test_range_with_expressions():
    """Test slice with expression bounds: arr[i-1:j+2] = expr;"""
    # Arrange
    test_string = "arr[i-1:j+2] = expr;"
    # Act
    ast = get_ast("array_selection_assignment_stmt", test_string)
    # Assert
    assert str(ast) == (
        "(ArraySelectionAssignmentStmt"
        " (RectSelOfArrayElems"
        " (Identifier arr)"
        " (Range"
        " (Sub (Identifier i) (IntLiteral 1))"
        " (Add (Identifier j) (IntLiteral 2))"
        ")"
        ")"
        " (Identifier expr)"
        ")"
    )


def test_array_literal_rhs():
    """Test with array literal on RHS: arr[0] = {1, 2, 3};"""
    # Arrange
    test_string = "arr[0] = {1, 2, 3};"
    # Act
    ast = get_ast("array_selection_assignment_stmt", test_string)
    # Assert
    assert str(ast) == (
        "(ArraySelectionAssignmentStmt"
        " (RectSelOfArrayElems"
        " (Identifier arr)"
        " (Range (IntLiteral 0) (IntLiteral 0))"
        ")"
        " (ArrayLiteral1D (IntLiteral 1) (IntLiteral 2) (IntLiteral 3))"
        ")"
    )


def test_with_comments_and_whitespace():
    """Test parsing with comments and whitespace: arr[/*comment*/0] = value;"""
    # Arrange
    test_string = "arr \n/*this is a comment*/\n [ 0 ] = // another comment\n value ;"
    # Act
    ast = get_ast("array_selection_assignment_stmt", test_string)
    # Assert
    assert str(ast) == (
        "(ArraySelectionAssignmentStmt"
        " (RectSelOfArrayElems"
        " (Identifier arr)"
        " (Range (IntLiteral 0) (IntLiteral 0))"
        ")"
        " (Identifier value)"
        ")"
    )