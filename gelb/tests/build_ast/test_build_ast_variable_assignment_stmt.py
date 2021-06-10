#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import ASTBuilderVisitor, get_ast


def test_simple():
    # Arrange
    test_string = "alpha = 123 ;"
    # Act
    ast = get_ast("variable_assignment_stmt", test_string)
    # Assert
    assert str(ast) == (
        "(VariableAssignmentStmt"
        " (Identifier alpha)"
        " (IntLiteral 123)"
        ")"
    )

def test_with_comments_and_whitespace():
    # Arrange
    test_string = "beta_quadrant \n/*this is */\n = //something\n980 ;"
    # Act
    ast = get_ast("variable_assignment_stmt", test_string)
    # Assert
    assert str(ast) == (
        "(VariableAssignmentStmt"
        " (Identifier beta_quadrant)"
        " (IntLiteral 980)"
        ")"
    )

def test_rhs_array1d_literal():
    # Arrange
    test_string = "alpha = {1, 2, 3} ;"
    # Act
    ast = get_ast("variable_assignment_stmt", test_string)
    # Assert
    assert str(ast) == (
        "(VariableAssignmentStmt"
        " (Identifier alpha)"
        " (ArrayLiteral1D (IntLiteral 1) (IntLiteral 2) (IntLiteral 3))"
        ")"
    )

def test_rhs_rect_sel_of_lattice_in_dfs():
    # Arrange
    test_string = "state = f.in[x | 0];"
    # Act
    ast = get_ast("variable_assignment_stmt", test_string)
    # Assert
    assert str(ast) == (
        "(VariableAssignmentStmt"
        " (Identifier state)"
        " (RectSelOfLatticeInDFs"
            " (Identifier f)"
            " (Range (Identifier x) (Identifier x))"
            " (Range (IntLiteral 0) (IntLiteral 0))"
        ")"
        ")"
    )
