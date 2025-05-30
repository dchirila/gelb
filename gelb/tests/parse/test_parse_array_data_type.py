#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import get_cst_as_string


def test_1d_array_type():
    # Arrange
    test_string = "array[int64, 3]"
    # Act (trigger parsing)
    result = get_cst_as_string("array_data_type", test_string)
    # Assert (test the parse tree)
    assert result == (
        "(array_data_type array [ "
            "(scalar_data_type (scalar_int_data_type int64)) , "
            "(array_shape (expr 3)) "
        "])")

def test_2d_array_type():
    # Arrange
    test_string = "array[real64, {2, 3}]"
    # Act (trigger parsing)
    result = get_cst_as_string("array_data_type", test_string)
    # Assert (test the parse tree)
    assert result == (
            "(array_data_type array [ "
            "(scalar_data_type (scalar_real_data_type real64)) , "
            "(array_shape (array_literal_1d { (expr 2) , (expr 3) })) "
            "])")
