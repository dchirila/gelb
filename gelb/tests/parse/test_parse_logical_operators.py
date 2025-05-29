#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import get_cst_as_string


def test_parse_logical_and():
    # Arrange
    test_string = "true && false"
    # Act (trigger parsing)
    result = get_cst_as_string("expr", test_string)
    # Assert (test the parse tree)
    assert result == "(expr (expr true) && (expr false))"

def test_parse_logical_or():
    # Arrange
    test_string = "true || false"
    # Act (trigger parsing)
    result = get_cst_as_string("expr", test_string)
    # Assert (test the parse tree)
    assert result == "(expr (expr true) || (expr false))"

def test_parse_complex_logical_expr():
    # Arrange - test precedence: && has higher precedence than ||
    test_string = "x && y || z"
    # Act (trigger parsing)
    result = get_cst_as_string("expr", test_string)
    # Assert (test the parse tree)
    assert result == "(expr (expr (expr (identifier x)) && (expr (identifier y))) || (expr (identifier z)))"

def test_parse_nested_logical_expr():
    # Arrange
    test_string = "(a && b) || (c && d)"
    # Act (trigger parsing)
    result = get_cst_as_string("expr", test_string)
    # Assert (test the parse tree)
    assert result == "(expr (expr ( (expr (expr (identifier a)) && (expr (identifier b))) )) || (expr ( (expr (expr (identifier c)) && (expr (identifier d))) )))"