#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import get_cst_as_string


def test_one_lattice_instance():
    # Arrange
    test_string = """lattices {
        TODO
    }"""
    # Act (trigger parsing)
    result = get_cst_as_string("lattices_block", test_string)
    # Assert (test the parse tree)
    assert result == "(lattices_block lattices { TODO })"