#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import get_cst_as_string


def test_simple():
    # Arrange
    test_string = "123"
    # Act (trigger parsing)
    result = get_cst_as_string("expr", test_string)
    # Assert (test the parse tree)
    assert result == "(expr 123)"
