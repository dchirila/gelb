#!/usr/bin/env python3

import pytest
import antlr4 as a4
from gelb.antlr4.generated_code import GeLBLexer, GeLBParser, GeLBVisitor

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