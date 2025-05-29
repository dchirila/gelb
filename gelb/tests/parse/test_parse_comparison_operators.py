#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import get_cst_as_string


def test_parse_less_than():
    # Arrange
    test_string = "x < y"
    # Act (trigger parsing)
    result = get_cst_as_string("expr", test_string)
    # Assert (test the parse tree)
    assert result == "(expr (expr (identifier x)) < (expr (identifier y)))"

def test_parse_greater_than():
    # Arrange
    test_string = "x > y"
    # Act (trigger parsing)
    result = get_cst_as_string("expr", test_string)
    # Assert (test the parse tree)
    assert result == "(expr (expr (identifier x)) > (expr (identifier y)))"

def test_parse_less_equal():
    # Arrange
    test_string = "x <= y"
    # Act (trigger parsing)
    result = get_cst_as_string("expr", test_string)
    # Assert (test the parse tree)
    assert result == "(expr (expr (identifier x)) <= (expr (identifier y)))"

def test_parse_greater_equal():
    # Arrange
    test_string = "x >= y"
    # Act (trigger parsing)
    result = get_cst_as_string("expr", test_string)
    # Assert (test the parse tree)
    assert result == "(expr (expr (identifier x)) >= (expr (identifier y)))"

def test_parse_equal():
    # Arrange
    test_string = "x == y"
    # Act (trigger parsing)
    result = get_cst_as_string("expr", test_string)
    # Assert (test the parse tree)
    assert result == "(expr (expr (identifier x)) == (expr (identifier y)))"

def test_parse_not_equal():
    # Arrange
    test_string = "x != y"
    # Act (trigger parsing)
    result = get_cst_as_string("expr", test_string)
    # Assert (test the parse tree)
    assert result == "(expr (expr (identifier x)) != (expr (identifier y)))"

def test_parse_comparison_with_numbers():
    # Arrange
    test_string = "5 < 10"
    # Act (trigger parsing)
    result = get_cst_as_string("expr", test_string)
    # Assert (test the parse tree)
    assert result == "(expr (expr 5) < (expr 10))"

def test_parse_complex_comparison():
    # Arrange - test precedence with arithmetic
    test_string = "x + 1 < y * 2"
    # Act (trigger parsing)
    result = get_cst_as_string("expr", test_string)
    # Assert (test the parse tree)
    assert result == "(expr (expr (expr (identifier x)) + (expr 1)) < (expr (expr (identifier y)) * (expr 2)))"

def test_parse_chained_comparisons_with_logical():
    # Arrange - test precedence: comparisons should bind tighter than logical operators
    test_string = "x > 0 && y < 10"
    # Act (trigger parsing)
    result = get_cst_as_string("expr", test_string)
    # Assert (test the parse tree)
    assert result == "(expr (expr (expr (identifier x)) > (expr 0)) && (expr (expr (identifier y)) < (expr 10)))"

def test_parse_equality_with_logical():
    # Arrange - test precedence: equality should bind tighter than logical operators
    test_string = "x == 5 || y != 3"
    # Act (trigger parsing)
    result = get_cst_as_string("expr", test_string)
    # Assert (test the parse tree)
    assert result == "(expr (expr (expr (identifier x)) == (expr 5)) || (expr (expr (identifier y)) != (expr 3)))"