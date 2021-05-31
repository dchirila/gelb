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
            "(array_literal_4d { "
            "(array_literal_3d { "
            "(array_literal_2d { "
            "(array_literal_1d { (expr 1) , (expr 2) }) , "
            "(array_literal_1d { (expr 3) , (expr 4) }) "
            "}) , "
            "(array_literal_2d { "
            "(array_literal_1d { (expr 5) , (expr 6) }) , "
            "(array_literal_1d { (expr 7) , (expr 8) }) "
            "}) "
            "}) , "
            "(array_literal_3d { "
            "(array_literal_2d { "
            "(array_literal_1d { (expr 9) , (expr 10) }) , "
            "(array_literal_1d { (expr 11) , (expr 12) }) "
            "}) , "
            "(array_literal_2d { "
            "(array_literal_1d { (expr 13) , (expr 14) }) , "
            "(array_literal_1d { (expr 15) , (expr 16) }) "
            "}) "
            "}) "
            "})"
    )