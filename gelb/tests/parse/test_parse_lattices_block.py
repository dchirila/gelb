#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import get_cst_as_string


def test_one_lattice_instance_no_arg_keywords():
    # Arrange
    test_string = """lattices {
        lattice f(2, 9, bool, 32);
    }"""
    # Act (trigger parsing)
    result = get_cst_as_string("lattices_block", test_string)
    # Assert (test the parse tree)
    assert result == (
        "(lattices_block lattices {"
        " (lattice_insta_stmt lattice"
            " (identifier f)"
            " ("
                " (expr 2)"
                " ,"
                " (expr 9)"
                " ,"
                " (scalar_data_type (scalar_bool_data_type bool))"
                " ,"
                " (expr 32)"
            " )"
        " ;)"
        " })"
    )
