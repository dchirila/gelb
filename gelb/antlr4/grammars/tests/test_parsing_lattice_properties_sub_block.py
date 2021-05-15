#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import a4, GeLBLexer, GeLBParser


def test_parsing_lattice_properties_block():
    # Arrange
    input = a4.InputStream("lattice_properties D2Q1 {\n TODO\n }")
    lexer = GeLBLexer(input)
    stream = a4.CommonTokenStream(lexer)
    parser = GeLBParser(stream)
    tree = parser.lattice_properties_block()
    # Act (trigger parsing)
    result = tree.toStringTree(recog=parser)
    # Assert (test the parse tree)
    assert result == "(lattice_properties_block lattice_properties D2Q1 { TODO })"