#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import get_cst_as_string


def test_expr_shape():
    # Arrange
    test_string = "5"
    # Act (trigger parsing)
    result = get_cst_as_string("array_shape", test_string)
    # Assert (test the parse tree)
    assert result == "(array_shape (expr 5))"

def test_expr_identifier_shape():
    # Arrange
    test_string = "N"
    # Act (trigger parsing)
    result = get_cst_as_string("array_shape", test_string)
    # Assert (test the parse tree)
    assert result == "(array_shape (expr (identifier N)))"

def test_array_literal_1d_shape():
    # Arrange
    test_string = "{2, 3}"
    # Act (trigger parsing)
    result = get_cst_as_string("array_shape", test_string)
    # Assert (test the parse tree)
    expected = "(array_shape (array_literal_1d { (expr 2) , (expr 3) }))"
    assert result == expected

def test_array_literal_1d_complex_shape():
    # Arrange
    test_string = "{3, 4, 5}"
    # Act (trigger parsing)
    result = get_cst_as_string("array_shape", test_string)
    # Assert (test the parse tree)
    expected = "(array_shape (array_literal_1d { (expr 3) , (expr 4) , (expr 5) }))"
    assert result == expected