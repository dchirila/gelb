#!/usr/bin/env python3

import pytest
import antlr4 as a4
from gelb.antlr4.generated_code import GeLBLexer, GeLBParser, GeLBVisitor


def test_simple():
    # Arrange
    input = a4.InputStream("simulation_description=\"\";")
    lexer = GeLBLexer(input)
    stream = a4.CommonTokenStream(lexer)
    parser = GeLBParser(stream)
    tree = parser.set_simulation_description_stmt()
    # Act (trigger parsing)
    result = tree.toStringTree(recog=parser)
    # Assert (test the parse tree)
    assert result == "(set_simulation_description_stmt simulation_description = \"\" ;)"

@pytest.mark.parametrize(
    "test_string, expected_parse_tree",
    [
        ("simulation_description=\"test\";"
        , "(set_simulation_description_stmt simulation_description = \"test\" ;)"),
        ("simulation_description =\"with spaces\";"
        , "(set_simulation_description_stmt simulation_description = \"with spaces\" ;)"),
        ("simulation_description= \"with a \nnewline\";"
        , "(set_simulation_description_stmt simulation_description = \"with a \\nnewline\" ;)"),
        ("simulation_description  \n\n=  \"weird\n\nformatting\";"
        , "(set_simulation_description_stmt simulation_description = \"weird\\n\\nformatting\" ;)"),
    ]
)
def test_with_param(test_string, expected_parse_tree):
    # Arrange
    input = a4.InputStream(test_string)
    lexer = GeLBLexer(input)
    stream = a4.CommonTokenStream(lexer)
    parser = GeLBParser(stream)
    tree = parser.set_simulation_description_stmt()
    # Act (trigger parsing)
    result = tree.toStringTree(recog=parser)
    # Assert (test the parse tree)
    assert result == expected_parse_tree