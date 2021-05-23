#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import get_cst_as_string


def test_simple():
    # Arrange
    test_string = "simulation_description(\"\");"
    # Act (trigger parsing)
    result = get_cst_as_string("set_simulation_description_stmt", test_string)
    # Assert (test the parse tree)
    assert result == "(set_simulation_description_stmt simulation_description ( \"\" ) ;)"

@pytest.mark.parametrize(
    "test_string, expected_parse_tree",
    [
        ("simulation_description(\"test\");"
        , "(set_simulation_description_stmt simulation_description ( \"test\" ) ;)"),
        ("simulation_description (\"with spaces\" );"
        , "(set_simulation_description_stmt simulation_description ( \"with spaces\" ) ;)"),
        ("simulation_description( \"with a \nnewline\") ;"
        , "(set_simulation_description_stmt simulation_description ( \"with a \\nnewline\" ) ;)"),
        ("simulation_description  \n(\n  \"weird\n\nformatting\"\n)\n;"
        , "(set_simulation_description_stmt simulation_description ( \"weird\\n\\nformatting\" ) ;)"),
    ]
)
def test_with_param(test_string, expected_parse_tree):
    # Act (trigger parsing)
    result = get_cst_as_string("set_simulation_description_stmt", test_string)
    # Assert (test the parse tree)
    assert result == expected_parse_tree