#!/usr/bin/env python3

import antlr4 as a4
from gelb.antlr4.generated_code import GeLBLexer, GeLBParser, GeLBVisitor
# from gelb.ASTNodes import *

def get_parse_tree_as_string(start_rule, test_string):
    input_stream = a4.InputStream(test_string)
    lexer = GeLBLexer(input_stream)
    token_stream = a4.CommonTokenStream(lexer)
    token_stream.fill()
    parser = GeLBParser(token_stream)
    if hasattr(parser, start_rule):
        func_start_rule = getattr(parser, start_rule)
        parser_ret = func_start_rule()
        return parser_ret.toStringTree(recog=parser)
    else:
        print("[ERROR] Can't find start rule '{}' @GeLBParser".format(start_rule))

# def GeLBASTGeneratorVisitor(GeLBVisitor):
#     def __init__(self, ctx:GeLBParser.Gelb_programContext):
#         pass
#
#     def visitGelb_program(self, ctx:GeLBParser.Gelb_programContext):
#         return Program_N()
#
#     def visitGelb_version_stmt(self, ctx:GeLBParser.Gelb_version_stmtContext):
#         print(ctx)
#         return IntLiteral_N(TODO)
