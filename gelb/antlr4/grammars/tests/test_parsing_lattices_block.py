#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import a4, GeLBLexer, GeLBParser


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