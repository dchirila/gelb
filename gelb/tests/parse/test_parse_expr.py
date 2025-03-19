#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import get_cst_as_string


def test_zero():
    # Arrange
    test_string = "0"
    # Act (trigger parsing)
    result = get_cst_as_string("expr", test_string)
    # Assert (test the parse tree)
    assert result == "(expr 0)"

def test_zero_inside_parens():
    # Arrange
    test_string = "(0)"
    # Act (trigger parsing)
    result = get_cst_as_string("expr", test_string)
    # Assert (test the parse tree)
    assert result == "(expr ( (expr 0) ))"

def test_positive_int():
    # Arrange
    test_string = "123"
    # Act (trigger parsing)
    result = get_cst_as_string("expr", test_string)
    # Assert (test the parse tree)
    assert result == "(expr 123)"

# def test_positive_float():
#     # Arrange
#     test_string = "3.14"
#     # Act (trigger parsing)
#     result = get_cst_as_string("expr", test_string)
#     # Assert (test the parse tree)
#     assert result == "(expr 123)"

# def test_negative_int():
#     # Arrange
#     test_string = "-981"
#     # Act (trigger parsing)
#     result = get_cst_as_string("expr", test_string)
#     # Assert (test the parse tree)
#     assert result == "(expr 123)"
#
# def test_int_plus_int():
#     # Arrange
#     test_string = "123 + 321"
#     # Act (trigger parsing)
#     result = get_cst_as_string("expr", test_string)
#     # Assert (test the parse tree)
#     assert result == "(expr 123)"
