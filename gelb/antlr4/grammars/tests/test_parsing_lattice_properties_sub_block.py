#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import get_parse_tree_as_string

def test_parsing_lattice_properties_block():
    # Arrange
    test_string = "lattice_properties D2Q1 {\n TODO\n }"
    # Act (trigger parsing)
    result = get_parse_tree_as_string("lattice_properties_block", test_string)
    # Assert (test the parse tree)
    assert result == "(lattice_properties_block lattice_properties D2Q1 { TODO })"