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