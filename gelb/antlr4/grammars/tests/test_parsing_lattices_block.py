#!/usr/bin/env python3

import pytest
import antlr4 as a4
from gelb.antlr4.generated_code import GeLBLexer, GeLBParser, GeLBVisitor

def test_one_lattice_instance():
    # Arrange
    input = a4.InputStream("""lattices {
        TODO
    }""")
    lexer = GeLBLexer(input)
    stream = a4.CommonTokenStream(lexer)
    parser = GeLBParser(stream)
    tree = parser.lattices_block()
    # Act (trigger parsing)
    result = tree.toStringTree(recog=parser)
    # Assert (test the parse tree)
    assert result == "(lattices_block lattices { TODO })"