#!/usr/bin/env python3

import pytest
from antlr4 import InputStream, Token
from gelb.antlr_part.generated_code.GeLBLexer import GeLBLexer


def get_tokens(input_string):
    """Helper function to get all tokens from an input string."""
    input_stream = InputStream(input_string)
    lexer = GeLBLexer(input_stream)
    tokens = []
    while True:
        token = lexer.nextToken()
        if token.type == Token.EOF:
            break
        tokens.append(token)
    return tokens


def test_empty_string():
    # Arrange
    test_string = '""'
    # Act
    tokens = get_tokens(test_string)
    # Assert
    assert len(tokens) == 1
    assert tokens[0].type == GeLBLexer.STRING_LITERAL
    assert tokens[0].text == '""'


def test_simple_string():
    # Arrange
    test_string = '"Hello, World!"'
    # Act
    tokens = get_tokens(test_string)
    # Assert
    assert len(tokens) == 1
    assert tokens[0].type == GeLBLexer.STRING_LITERAL
    assert tokens[0].text == '"Hello, World!"'


def test_string_with_single_quotes():
    # Arrange
    test_string = '"Don\'t worry, be happy!"'
    # Act
    tokens = get_tokens(test_string)
    # Assert
    assert len(tokens) == 1
    assert tokens[0].type == GeLBLexer.STRING_LITERAL
    assert tokens[0].text == '"Don\'t worry, be happy!"'


def test_multiline_string():
    # Arrange
    test_string = '"Line 1\nLine 2\nLine 3"'
    # Act
    tokens = get_tokens(test_string)
    # Assert
    assert len(tokens) == 1
    assert tokens[0].type == GeLBLexer.STRING_LITERAL
    assert tokens[0].text == '"Line 1\nLine 2\nLine 3"'


def test_string_with_special_chars():
    # Arrange
    test_string = '"Special chars: @#$%^&*()[]{}|,./<>?`~"'
    # Act
    tokens = get_tokens(test_string)
    # Assert
    assert len(tokens) == 1
    assert tokens[0].type == GeLBLexer.STRING_LITERAL
    assert tokens[0].text == '"Special chars: @#$%^&*()[]{}|,./<>?`~"'


def test_string_with_backslash():
    # Arrange
    test_string = '"C:\\Program Files\\App"'
    # Act
    tokens = get_tokens(test_string)
    # Assert
    assert len(tokens) == 1
    assert tokens[0].type == GeLBLexer.STRING_LITERAL
    assert tokens[0].text == '"C:\\Program Files\\App"'


def test_invalid_string_missing_end_quote():
    # Arrange
    test_string = '"Unclosed string'
    # Act
    tokens = get_tokens(test_string)
    # Assert
    # Since the string is not properly closed, it should not be recognized as a STRING_LITERAL token
    assert not any(t.type == GeLBLexer.STRING_LITERAL for t in tokens)


def test_invalid_string_missing_start_quote():
    # Arrange
    test_string = 'Unclosed string"'
    # Act
    tokens = get_tokens(test_string)
    # Assert
    # Since the string doesn't start with a quote, it should not be recognized as a STRING_LITERAL token
    assert not any(t.type == GeLBLexer.STRING_LITERAL for t in tokens)


def test_invalid_string_single_quotes():
    # Arrange
    test_string = "'Single quoted string'"
    # Act
    tokens = get_tokens(test_string)
    # Assert
    # Since GeLB only supports double-quoted strings, this should not be recognized as a STRING_LITERAL token
    assert not any(t.type == GeLBLexer.STRING_LITERAL for t in tokens)
