#!/usr/bin/env python3

import pytest
import antlr4 as a4
from gelb.antlr4.generated_code import GeLBLexer, GeLBParser, GeLBVisitor


def test_parsing_set_short_name_stmt():
    # Arrange
    input = a4.InputStream("short_name=\"\";")
    lexer = GeLBLexer(input)
    stream = a4.CommonTokenStream(lexer)
    parser = GeLBParser(stream)
    tree = parser.set_short_name_stmt()
    # Act (trigger parsing)
    result = tree.toStringTree(recog=parser)
    # Assert (test the parse tree)
    assert result == "(set_short_name_stmt short_name = \"\" ;)"

@pytest.mark.parametrize(
    "test_string, expected_parse_tree",
    [
        ("short_name=\"test\";"
        , "(set_short_name_stmt short_name = \"test\" ;)"),
        ("short_name =\"with spaces\";"
        , "(set_short_name_stmt short_name = \"with spaces\" ;)"),
        ("short_name= \"with a \nnewline\";"
        , "(set_short_name_stmt short_name = \"with a \\nnewline\" ;)"),
        ("short_name  \n\n=  \"weird\n\nformatting\";"
        , "(set_short_name_stmt short_name = \"weird\\n\\nformatting\" ;)"),
    ]
)
def test_with_param(test_string, expected_parse_tree):
    # Arrange
    input = a4.InputStream(test_string)
    lexer = GeLBLexer(input)
    stream = a4.CommonTokenStream(lexer)
    parser = GeLBParser(stream)
    tree = parser.set_short_name_stmt()
    # Act (trigger parsing)
    result = tree.toStringTree(recog=parser)
    # Assert (test the parse tree)
    assert result == expected_parse_tree