#!/usr/bin/env python3

import antlr4 as a4
from gelb.antlr4.generated_code import GeLBLexer, GeLBParser, GeLBVisitor
# from gelb.ASTNodes import *


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
