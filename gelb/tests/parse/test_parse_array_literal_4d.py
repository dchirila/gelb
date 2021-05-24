#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import get_cst_as_string


def test_simple():
    # Arrange
    test_string = (
        "{{{{1,2},{3,4}},{{5,6},{7,8}}},{{{9,10},{11,12}},{{13,14},{15,16}}}}"
    )
    # Act (trigger parsing)
    result = get_cst_as_string("array_literal_4d", test_string)
    # Assert (test the parse tree)
    assert result == (
            "(array_literal_4d { " +
            "(array_literal_3d { " +
            "(array_literal_2d { " +
            "(array_literal_1d { (scalar_expr 1) , (scalar_expr 2) }) , " +
            "(array_literal_1d { (scalar_expr 3) , (scalar_expr 4) }) " +
            "}) , " +
            "(array_literal_2d { " +
            "(array_literal_1d { (scalar_expr 5) , (scalar_expr 6) }) , " +
            "(array_literal_1d { (scalar_expr 7) , (scalar_expr 8) }) " +
            "}) " +
            "}) , " +
            "(array_literal_3d { " +
            "(array_literal_2d { " +
            "(array_literal_1d { (scalar_expr 9) , (scalar_expr 10) }) , " +
            "(array_literal_1d { (scalar_expr 11) , (scalar_expr 12) }) " +
            "}) , " +
            "(array_literal_2d { " +
            "(array_literal_1d { (scalar_expr 13) , (scalar_expr 14) }) , " +
            "(array_literal_1d { (scalar_expr 15) , (scalar_expr 16) }) " +
            "}) " +
            "}) " +
            "})"
    )