#!/usr/bin/env python3

import pytest
from frontend.stage1_frontend import get_cst_as_string


def test_scalar_int():
    # Arrange
    test_string = "const int LENGTH = 32;"
    # Act (trigger parsing)
    result = get_cst_as_string("constant_definition_stmt", test_string)
    # Assert (test the parse tree)
    assert result == (
        "(constant_definition_stmt const"
        " (data_type"
        " (scalar_data_type (scalar_int_data_type int))"
        ")"
        " (variable_assignment_stmt"
        " (identifier LENGTH)"
        " ="
        " (expr 32)"
        " ;)"
        ")"
    )
