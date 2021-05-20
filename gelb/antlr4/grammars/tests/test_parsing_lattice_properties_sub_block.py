#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import get_cst_as_string


def test_simple():
    # Arrange
    test_string = """
    lattice_properties D2Q1 {
        const int D = 2;
        const int Q = 1;
        }
    """
    # Act (trigger parsing)
    result = get_cst_as_string("lattice_properties_sub_block", test_string)
    # Assert (test the parse tree)
    assert result == (
            "(lattice_properties_sub_block lattice_properties D2Q1 { " +
            "(constant_definition_stmt const (data_type (scalar_data_type " +
            "(scalar_int_data_type int))) (variable_assignment_stmt D = 2 ;)) " +
            "(constant_definition_stmt const (data_type (scalar_data_type " +
            "(scalar_int_data_type int))) (variable_assignment_stmt Q = 1 ;)) })"
    )
