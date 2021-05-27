#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import get_cst_as_string


def test_simple():
    # Arrange
    test_string = "{1, 2, 3}"
    # Act (trigger parsing)
    result = get_cst_as_string("array_literal_1d", test_string)
    # Assert (test the parse tree)
    assert result == (
        "(array_literal_1d { (scalar_expr 1) , (scalar_expr 2) , (scalar_expr 3) })"
    )

def test_with_comments_and_whitespace():
    # Arrange
    test_string = "/* comment 1*/{\n123// comment 2\n, 456//\n}"
    # Act (trigger parsing)
    result = get_cst_as_string("array_literal_1d", test_string)
    # Assert (test the parse tree)
    assert result == (
            "(array_literal_1d "
            "{ (scalar_expr 123) , (scalar_expr 456) }"
            ")"
    )
