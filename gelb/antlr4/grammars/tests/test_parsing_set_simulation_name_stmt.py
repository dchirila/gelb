#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import a4, GeLBLexer, GeLBParser


def test_simple():
    # Arrange
    input = a4.InputStream("simulation_name=\"\";")
    lexer = GeLBLexer(input)
    stream = a4.CommonTokenStream(lexer)
    parser = GeLBParser(stream)
    tree = parser.set_simulation_name_stmt()
    # Act (trigger parsing)
    result = tree.toStringTree(recog=parser)
    # Assert (test the parse tree)
    assert result == "(set_simulation_name_stmt simulation_name = \"\" ;)"

def test_with_single_line_comments():
    # Arrange
    input = a4.InputStream("// comment 1\nsimulation_name // comment 2\n=\"test1\";")
    lexer = GeLBLexer(input)
    stream = a4.CommonTokenStream(lexer)
    parser = GeLBParser(stream)
    tree = parser.set_simulation_name_stmt()
    # Act (trigger parsing)
    result = tree.toStringTree(recog=parser)
    # Assert (test the parse tree)
    assert result == "(set_simulation_name_stmt simulation_name = \"test1\" ;)"

def test_with_multi_line_comments():
    # Arrange
    input = a4.InputStream(
        # crazy amount of comments, just because we can :)
        "/*com 1 */ simulation_name /* c2*/ = /*c3*/\n/* c 4 */ \"test2\" /*c5 */;/* c6*/"
    )
    lexer = GeLBLexer(input)
    stream = a4.CommonTokenStream(lexer)
    parser = GeLBParser(stream)
    tree = parser.set_simulation_name_stmt()
    # Act (trigger parsing)
    result = tree.toStringTree(recog=parser)
    # Assert (test the parse tree)
    assert result == "(set_simulation_name_stmt simulation_name = \"test2\" ;)"

@pytest.mark.parametrize(
    "test_string, expected_parse_tree",
    [
        ("simulation_name=\"test\";"
        , "(set_simulation_name_stmt simulation_name = \"test\" ;)"),
        ("simulation_name =\"with spaces\";"
        , "(set_simulation_name_stmt simulation_name = \"with spaces\" ;)"),
        ("simulation_name= \"with a \nnewline\";"
        , "(set_simulation_name_stmt simulation_name = \"with a \\nnewline\" ;)"),
        ("simulation_name  \n\n=  \"weird\n\nformatting\";"
        , "(set_simulation_name_stmt simulation_name = \"weird\\n\\nformatting\" ;)"),
    ]
)
def test_with_param(test_string, expected_parse_tree):
    # Arrange
    input = a4.InputStream(test_string)
    lexer = GeLBLexer(input)
    stream = a4.CommonTokenStream(lexer)
    parser = GeLBParser(stream)
    tree = parser.set_simulation_name_stmt()
    # Act (trigger parsing)
    result = tree.toStringTree(recog=parser)
    # Assert (test the parse tree)
    assert result == expected_parse_tree