#!/usr/bin/env python3

import pytest
import antlr4 as a4
from gelb.antlr4.generated_code import GeLBLexer, GeLBParser, GeLBVisitor


def test_parsing_set_description_stmt():
    # Arrange
    input = a4.InputStream("description=\"\";")
    lexer = GeLBLexer(input)
    stream = a4.CommonTokenStream(lexer)
    parser = GeLBParser(stream)
    tree = parser.set_description_stmt()
    # Act (trigger parsing)
    result = tree.toStringTree(recog=parser)
    # Assert (test the parse tree)
    assert result == "(set_description_stmt description = \"\" ;)"

@pytest.mark.parametrize(
    "test_string, expected_parse_tree",
    [
        ("description=\"test\";"
        , "(set_description_stmt description = \"test\" ;)"),
        ("description =\"with spaces\";"
        , "(set_description_stmt description = \"with spaces\" ;)"),
        ("description= \"with a \nnewline\";"
        , "(set_description_stmt description = \"with a \\nnewline\" ;)"),
        ("description  \n\n=  \"weird\n\nformatting\";"
        , "(set_description_stmt description = \"weird\\n\\nformatting\" ;)"),
    ]
)
def test_with_param(test_string, expected_parse_tree):
    # Arrange
    input = a4.InputStream(test_string)
    lexer = GeLBLexer(input)
    stream = a4.CommonTokenStream(lexer)
    parser = GeLBParser(stream)
    tree = parser.set_description_stmt()
    # Act (trigger parsing)
    result = tree.toStringTree(recog=parser)
    # Assert (test the parse tree)
    assert result == expected_parse_tree