#!/usr/bin/env python3

import pytest

import antlr4 as a4


from gelb.antlr4.generated_code.GeLBLexer import GeLBLexer
from gelb.antlr4.generated_code.GeLBParser import GeLBParser
from gelb.antlr4.generated_code.GeLBVisitor import GeLBVisitor
from gelb.ASTNodes import *


# """TODO: move to =stage1_frontend.py="""
# def GeLBASTGeneratorVisitor(GeLBVisitor):
#     def __init__(self, ctx:GeLBParser.Gelb_programContext):
#         pass

#     def visitGelb_program(self, ctx:GeLBParser.Gelb_programContext):
#         return Program_N()

#     def visitGelb_version_stmt(self, ctx:GeLBParser.Gelb_version_stmtContext):
#         print(ctx)
#         return IntLiteral_N(TODO)


# def test_zero():
#     # Arrange
#     input = a4.InputStream("  gelb_version=     0;")  # test for weird spacing
#     lexer = GeLBLexer(input)
#     stream = a4.CommonTokenStream(lexer)
#     parser = GeLBParser(stream)
#     tree = parser.gelb_version_stmt()
#     print("<<<DEBUG>>>", type(tree))
#     raise AssertionError
#     # Act (trigger parsing)
#     result = tree.toStringTree(recog=parser)
#     # Assert (test the parse tree)
#     assert result == "(gelb_version_stmt gelb_version = 0 ;)"


# @pytest.mark.parametrize(
#     "test_string, expected_parse_tree",
#     [
#         ("gelb_version = 0;", "(gelb_version_stmt gelb_version = 0 ;)"),
#         ("gelb_version = 1;", "(gelb_version_stmt gelb_version = 1 ;)"),
#         ("gelb_version = 10;", "(gelb_version_stmt gelb_version = 10 ;)"),
#         ("gelb_version = 999;", "(gelb_version_stmt gelb_version = 999 ;)"),
#     ],
# )
# def test_with_param(test_string, expected_parse_tree):
#     # Arrange
#     input = a4.InputStream(test_string)
#     lexer = GeLBLexer(input)
#     stream = a4.CommonTokenStream(lexer)
#     parser = GeLBParser(stream)
#     tree = parser.gelb_version_stmt()
#     # Act (trigger parsing)
#     result = tree.toStringTree(recog=parser)
#     # Assert (test the parse tree)
#     assert result == expected_parse_tree


# def test_negative_version():
#     # Arrange
#     input = a4.InputStream("  gelb_version=     -123;")  # test for weird spacing
#     lexer = GeLBLexer(input)
#     stream = a4.CommonTokenStream(lexer)
#     parser = GeLBParser(stream)
#     tree = parser.gelb_version_stmt()
#     # Act (test the parse tree)
#     with pytest.raises(Exception):
#         result = tree.toStringTree(recog=parser)
#         assert result == "(gelb_version_stmt gelb_version = 0 ;)"
