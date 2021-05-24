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

    # Visit a parse tree produced by GeLBParser#array_literal_4d.
    def visitArray_literal_4d(self, ctx:GeLBParser.Array_literal_4dContext):
        list_of_children_sub_asts = []
        # Strategy: visit all children nodes (based on the implementation of
        # ParseTreeVisitor.visitChildren), and append non-trivial children to
        # the list_of_children_sub_asts.
        n = ctx.getChildCount()
        # print("<<<DEBUG>>>", ctx.getChildCount())
        for i in range(n):
            c = ctx.getChild(i)
            # NOTE: boring children (i.e. syntax elements which don't belong
            # inside the AST) yield childResult == None, because we DON'T
            # implement a visitor-method override for them!
            childResult = c.accept(self)
            if childResult:
                # print("<<<DEBUG-CHILD>>>", str(childResult))
                list_of_children_sub_asts.append(childResult)

        return Array4DLiteral_N(list_of_children_sub_asts)

    # Visit a parse tree produced by GeLBParser#array_literal_3d.
    def visitArray_literal_3d(self, ctx:GeLBParser.Array_literal_3dContext):
        list_of_children_sub_asts = []
        # Strategy: visit all children nodes (based on the implementation of
        # ParseTreeVisitor.visitChildren), and append non-trivial children to
        # the list_of_children_sub_asts.
        n = ctx.getChildCount()
        # print("<<<DEBUG>>>", ctx.getChildCount())
        for i in range(n):
            c = ctx.getChild(i)
            # NOTE: boring children (i.e. syntax elements which don't belong
            # inside the AST) yield childResult == None, because we DON'T
            # implement a visitor-method override for them!
            childResult = c.accept(self)
            if childResult:
                # print("<<<DEBUG-CHILD>>>", str(childResult))
                list_of_children_sub_asts.append(childResult)

        return Array3DLiteral_N(list_of_children_sub_asts)

    # Visit a parse tree produced by GeLBParser#array_literal_2d.
    def visitArray_literal_2d(self, ctx:GeLBParser.Array_literal_2dContext):
        list_of_children_sub_asts = []
        # Strategy: visit all children nodes (based on the implementation of
        # ParseTreeVisitor.visitChildren), and append non-trivial children to
        # the list_of_children_sub_asts.
        n = ctx.getChildCount()
        # print("<<<DEBUG>>>", ctx.getChildCount())
        for i in range(n):
            c = ctx.getChild(i)
            # NOTE: boring children (i.e. syntax elements which don't belong
            # inside the AST) yield childResult == None, because we DON'T
            # implement a visitor-method override for them!
            childResult = c.accept(self)
            if childResult:
                # print("<<<DEBUG-CHILD>>>", str(childResult))
                list_of_children_sub_asts.append(childResult)

        return Array2DLiteral_N(list_of_children_sub_asts)

    # Visit a parse tree produced by GeLBParser#array_literal_1d.
    def visitArray_literal_1d(self, ctx:GeLBParser.Array_literal_1dContext):
        list_of_children_sub_asts = []
        # Strategy: visit all children nodes (based on the implementation of
        # ParseTreeVisitor.visitChildren), and append non-trivial children to
        # the list_of_children_sub_asts.
        n = ctx.getChildCount()
        # print("<<<DEBUG>>>", ctx.getChildCount())
        for i in range(n):
            c = ctx.getChild(i)
            # NOTE: boring children (i.e. syntax elements which don't belong
            # inside the AST) yield childResult == None, because we DON'T
            # implement a visitor-method override for them!
            childResult = c.accept(self)
            if childResult:
                # print("<<<DEBUG-CHILD>>>", str(childResult))
                list_of_children_sub_asts.append(childResult)

        return Array1DLiteral_N(list_of_children_sub_asts)

    # Visit a parse tree produced by GeLBParser#scalar_expr.
    def visitScalar_expr(self, ctx:GeLBParser.Scalar_exprContext):
        return IntLiteral_N(int(ctx.NON_NEGATIVE_INTEGER().__str__()))


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

