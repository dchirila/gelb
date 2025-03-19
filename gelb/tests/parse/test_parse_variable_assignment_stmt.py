#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import get_cst_as_string


def test_simple():
    # Arrange
    test_string = "alpha = 123 ;"
    # Act (trigger parsing)
    result = get_cst_as_string("variable_assignment_stmt", test_string)
    # Assert (test the parse tree)
    assert result == (
        "(variable_assignment_stmt"
        " (identifier alpha)"
        " ="
        " (expr 123)"
        " ;)"
    )

def test_with_comments_and_whitespace():
    # Arrange
    test_string = "beta_quadrant \n/*this is */\n = //something\n980 ;"
    # Act (trigger parsing)
    result = get_cst_as_string("variable_assignment_stmt", test_string)
    # Assert (test the parse tree)
    assert result == (
        "(variable_assignment_stmt"
        " (identifier beta_quadrant)"
        " ="
        " (expr 980)"
        " ;)"
    )

