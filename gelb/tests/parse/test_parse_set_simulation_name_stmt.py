#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import get_cst_as_string


def test_simple():
    # Arrange
    test_string = "simulation_name(\"\");"
    # Act (trigger parsing)
    result = get_cst_as_string("set_simulation_name_stmt", test_string)
    # Assert (test the parse tree)
    assert result == "(set_simulation_name_stmt simulation_name ( \"\" ) ;)"

def test_with_single_line_comments():
    # Arrange
    test_string = "// comment 1\nsimulation_name // comment 2\n(\"test1\");"
    # Act (trigger parsing)
    result = get_cst_as_string("set_simulation_name_stmt", test_string)
    # Assert (test the parse tree)
    assert result == "(set_simulation_name_stmt simulation_name ( \"test1\" ) ;)"

def test_with_multi_line_comments():
    # Arrange
    # crazy amount of comments, just because we can :)
    test_string = "/*com 1 */ simulation_name /* c2*/ ( /*c3*/\n/* c 4 */ \"test2\" /*c5 */);/* c6*/"
    # Act (trigger parsing)
    result = get_cst_as_string("set_simulation_name_stmt", test_string)
    # Assert (test the parse tree)
    assert result == "(set_simulation_name_stmt simulation_name ( \"test2\" ) ;)"

@pytest.mark.parametrize(
    "test_string, expected_parse_tree",
    [
        ("simulation_name(\"test\");"
        , "(set_simulation_name_stmt simulation_name ( \"test\" ) ;)"),
        ("simulation_name (\"with spaces\" );"
        , "(set_simulation_name_stmt simulation_name ( \"with spaces\" ) ;)"),
        ("simulation_name( \"with a \nnewline\") ;"
        , "(set_simulation_name_stmt simulation_name ( \"with a \\nnewline\" ) ;)"),
        ("simulation_name  \n(\n  \"weird\n\nformatting\"\n)\n;"
        , "(set_simulation_name_stmt simulation_name ( \"weird\\n\\nformatting\" ) ;)"),
    ]
)
def test_with_param(test_string, expected_parse_tree):
    # Act (trigger parsing)
    result = get_cst_as_string("set_simulation_name_stmt", test_string)
    # Assert (test the parse tree)
    assert result == expected_parse_tree