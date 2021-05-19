#!/usr/bin/env python3

import antlr4 as a4
from gelb.antlr4.generated_code import GeLBLexer, GeLBParser, GeLBVisitor
from gelb.ASTNodes import *

# TODO: "flesh it out!"
# INPUT: ANTLR4-generated ParseTree
# OUTPUT: GeLB AST (*root* node)
class ASTBuilderVisitor(GeLBVisitor):

    # Visit a parse tree produced by GeLBParser#set_simulation_name_stmt.
    def visitSet_simulation_name_stmt(self, ctx:GeLBParser.Set_simulation_name_stmtContext):
        return StringLiteral_N(ctx.STRING().__str__())

    # Visit a parse tree produced by GeLBParser#set_simulation_description_stmt.
    def visitSet_simulation_description_stmt(self, ctx:GeLBParser.Set_simulation_description_stmtContext):
        return StringLiteral_N(ctx.STRING().__str__())


def get_cst_as_string(start_rule, input_string):
    input_stream = a4.InputStream(input_string)
    lexer = GeLBLexer(input_stream)
    token_stream = a4.CommonTokenStream(lexer)
    token_stream.fill()
    parser = GeLBParser(token_stream)

    if hasattr(parser, start_rule):
        func_start_rule = getattr(parser, start_rule)
        cst = func_start_rule()
        return cst.toStringTree(recog=parser)
    else:
        print("[ERROR] Can't find start rule '{}' @GeLBParser".format(start_rule))


def get_ast(start_rule, input_string):
    input_stream = a4.InputStream(input_string)
    lexer = GeLBLexer(input_stream)
    token_stream = a4.CommonTokenStream(lexer)
    token_stream.fill()
    parser = GeLBParser(token_stream)

    if hasattr(parser, start_rule):
        func_start_rule = getattr(parser, start_rule)
        cst = func_start_rule()
        ast_builder = ASTBuilderVisitor()
        visitor_method_name = "visit" + start_rule.capitalize()
        if hasattr(ast_builder, visitor_method_name):
            # TODO: trigger creation of (sub-)AST & return
            visitor_method = getattr(ast_builder, visitor_method_name)
            ast = visitor_method(cst)
            return ast
        else:
            print("[ERROR] Can't find method '{}' @ASTBUilderVisitor".format(
                visitor_method_name)
            )
    else:
        print("[ERROR] Can't find start rule '{}' @GeLBParser".format(start_rule))

