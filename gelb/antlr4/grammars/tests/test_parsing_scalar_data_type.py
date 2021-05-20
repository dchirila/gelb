#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import get_cst_as_string


def test_bool():
    # Arrange
    test_string = "bool"
    # Act (trigger parsing)
    result = get_cst_as_string("scalar_data_type", test_string)
    # Assert (test the parse tree)
    assert result == "(scalar_data_type (scalar_bool_data_type bool))"

def test_int64():
    # Arrange
    test_string = "int64"
    # Act (trigger parsing)
    result = get_cst_as_string("scalar_data_type", test_string)
    # Assert (test the parse tree)
    assert result == "(scalar_data_type (scalar_int_data_type int64))"

def test_int32():
    # Arrange
    test_string = "int32"
    # Act (trigger parsing)
    result = get_cst_as_string("scalar_data_type", test_string)
    # Assert (test the parse tree)
    assert result == "(scalar_data_type (scalar_int_data_type int32))"

def test_int16():
    # Arrange
    test_string = "int16"
    # Act (trigger parsing)
    result = get_cst_as_string("scalar_data_type", test_string)
    # Assert (test the parse tree)
    assert result == "(scalar_data_type (scalar_int_data_type int16))"

def test_int8():
    # Arrange
    test_string = "int8"
    # Act (trigger parsing)
    result = get_cst_as_string("scalar_data_type", test_string)
    # Assert (test the parse tree)
    assert result == "(scalar_data_type (scalar_int_data_type int8))"

def test_int():
    # Arrange
    test_string = "int"
    # Act (trigger parsing)
    result = get_cst_as_string("scalar_data_type", test_string)
    # Assert (test the parse tree)
    assert result == "(scalar_data_type (scalar_int_data_type int))"

def test_real64():
    # Arrange
    test_string = "real64"
    # Act (trigger parsing)
    result = get_cst_as_string("scalar_data_type", test_string)
    # Assert (test the parse tree)
    assert result == "(scalar_data_type (scalar_real_data_type real64))"

def test_real32():
    # Arrange
    test_string = "real32"
    # Act (trigger parsing)
    result = get_cst_as_string("scalar_data_type", test_string)
    # Assert (test the parse tree)
    assert result == "(scalar_data_type (scalar_real_data_type real32))"

def test_real16():
    # Arrange
    test_string = "real16"
    # Act (trigger parsing)
    result = get_cst_as_string("scalar_data_type", test_string)
    # Assert (test the parse tree)
    assert result == "(scalar_data_type (scalar_real_data_type real16))"

def test_real():
    # Arrange
    test_string = "real"
    # Act (trigger parsing)
    result = get_cst_as_string("scalar_data_type", test_string)
    # Assert (test the parse tree)
    assert result == "(scalar_data_type (scalar_real_data_type real))"