#!/usr/bin/env python3

import pytest
from frontend.stage1_frontend import get_cst_as_string


def test_no_arg_keywords():
    # Arrange
    test_string = "lattice f(2, 9, bool);"
    # Act (trigger parsing)
    result = get_cst_as_string("lattice_insta_stmt", test_string)
    # Assert (test the parse tree)
    assert result == (
        "(lattice_insta_stmt lattice"
        " (identifier f)"
        " ("
            " (expr 2)"
            " ,"
            " (expr 9)"
            " ,"
            " (scalar_data_type (scalar_bool_data_type bool))"
        " )"
        " ;)"
    )
