#!/usr/bin/env python3

import pytest

import antlr4 as a4


from gelb.antlr4.generated_code.GDLexer import GDLexer
from gelb.antlr4.generated_code.GDParser import GDParser
from gelb.antlr4.generated_code.GDVisitor import GDVisitor


def test_zero():
    # Arrange
    input = a4.InputStream("  gd_version=     0;")  # test for weird spacing
    lexer = GDLexer(input)
    stream = a4.CommonTokenStream(lexer)
    parser = GDParser(stream)
    tree = parser.gd_version_stmt()
    # Act (trigger parsing)
    result = tree.toStringTree(recog=parser)
    # Assert (test the parse tree)
    assert result == "(gd_version_stmt gd_version = 0 ;)"


@pytest.mark.parametrize(
    "test_string, expected_parse_tree",
    [
        ("gd_version = 0;", "(gd_version_stmt gd_version = 0 ;)"),
        ("gd_version = 1;", "(gd_version_stmt gd_version = 1 ;)"),
        ("gd_version = 10;", "(gd_version_stmt gd_version = 10 ;)"),
        ("gd_version = 999;", "(gd_version_stmt gd_version = 999 ;)"),
    ],
)
def test_with_param(test_string, expected_parse_tree):
    # Arrange
    input = a4.InputStream(test_string)
    lexer = GDLexer(input)
    stream = a4.CommonTokenStream(lexer)
    parser = GDParser(stream)
    tree = parser.gd_version_stmt()
    # Act (trigger parsing)
    result = tree.toStringTree(recog=parser)
    # Assert (test the parse tree)
    assert result == expected_parse_tree


def test_negative_version():
    # Arrange
    input = a4.InputStream("  gd_version=     -123;")  # test for weird spacing
    lexer = GDLexer(input)
    stream = a4.CommonTokenStream(lexer)
    parser = GDParser(stream)
    tree = parser.gd_version_stmt()
    # Act (test the parse tree)
    with pytest.raises(Exception):
        result = tree.toStringTree(recog=parser)
        assert result == "(gd_version_stmt gd_version = 0 ;)"
