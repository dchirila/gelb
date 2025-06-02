#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import get_cst_as_string

def test_simple():
    # Arrange
    test_string = """
    global_constants {
        const int CX = 0;//a nasty comment
        const int Z = /*why not another comment */123;
        }
    """
    # Act (trigger parsing)
    result = get_cst_as_string("global_constants_block", test_string)
    # Assert (test the parse tree)
    assert result == (
        "(global_constants_block global_constants {"
        " (constant_definition_stmt const"
            " (data_type"
                " (scalar_data_type"
                " (scalar_int_data_type int)"
                ")"
            ")"
            " (variable_assignment_stmt"
            " (identifier CX)"
            " ="
            " (expr 0)"
            " ;)"
        ")"
        " (constant_definition_stmt const"
            " (data_type"
                " (scalar_data_type"
                " (scalar_int_data_type int)"
                ")"
            ")"
            " (variable_assignment_stmt"
            " (identifier Z)"
            " ="
            " (expr 123)"
            " ;)"
        ")"
        " })"
    )
