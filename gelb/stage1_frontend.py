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

    # Visit a parse tree produced by GeLBParser#scalar_bool_data_type.
    def visitScalar_bool_data_type(self, ctx:GeLBParser.Scalar_bool_data_typeContext):
        return ScalarDataType_N("bool")

    # Visit a parse tree produced by GeLBParser#scalar_int_data_type.
    def visitScalar_int_data_type(self, ctx:GeLBParser.Scalar_int_data_typeContext):
        if ctx.INT64():
            return ScalarDataType_N("int64")
        elif ctx.INT32():
            return ScalarDataType_N("int32")
        elif ctx.INT16():
            return ScalarDataType_N("int16")
        elif ctx.INT8():
            return ScalarDataType_N("int8")
        elif ctx.INT():
            return ScalarDataType_N("int")
        else:
            raise TypeError(
                "<<<GeLB-Error>>> Invalid scalar INTEGER data-type specified!"
            )

    # Visit a parse tree produced by GeLBParser#scalar_real_data_type.
    def visitScalar_real_data_type(self, ctx:GeLBParser.Scalar_real_data_typeContext):
        if ctx.REAL64():
            return ScalarDataType_N("real64")
        elif ctx.REAL32():
            return ScalarDataType_N("real32")
        elif ctx.REAL16():
            return ScalarDataType_N("real16")
        elif ctx.REAL():
            return ScalarDataType_N("real")
        else:
            raise TypeError(
                "<<<GeLB-Error>>> Invalid scalar REAL data-type specified!"
            )

    # Visit a parse tree produced by GeLBParser#array_data_type.
    def visitArray_data_type(self, ctx:GeLBParser.Array_data_typeContext):
        list_of_children_sub_asts = self.get_list_of_children_sub_asts(ctx)
        return ArrayDataType_N(
            # should contain the element data-type
            list_of_children_sub_asts[0],
            # should contain the shape
            list_of_children_sub_asts[1]
        )

    # Visit a parse tree produced by GeLBParser#array_literal_4d.
    def visitArray_literal_4d(self, ctx:GeLBParser.Array_literal_4dContext):
        return Array4DLiteral_N(self.get_list_of_children_sub_asts(ctx))

    # Visit a parse tree produced by GeLBParser#array_literal_3d.
    def visitArray_literal_3d(self, ctx:GeLBParser.Array_literal_3dContext):
        return Array3DLiteral_N(self.get_list_of_children_sub_asts(ctx))

    # Visit a parse tree produced by GeLBParser#array_literal_2d.
    def visitArray_literal_2d(self, ctx:GeLBParser.Array_literal_2dContext):
        return Array2DLiteral_N(self.get_list_of_children_sub_asts(ctx))

    # Visit a parse tree produced by GeLBParser#array_literal_1d.
    def visitArray_literal_1d(self, ctx:GeLBParser.Array_literal_1dContext):
        return Array1DLiteral_N(self.get_list_of_children_sub_asts(ctx))

    # Visit a parse tree produced by GeLBParser#scalar_expr.
    def visitScalar_expr(self, ctx:GeLBParser.Scalar_exprContext):
        return IntLiteral_N(int(ctx.NON_NEGATIVE_INTEGER().__str__()))

    def get_list_of_children_sub_asts(self, ctx):
        list_of_children_sub_asts = []
        # Strategy: visit all children nodes (based on the implementation of
        # ParseTreeVisitor.visitChildren), and append non-trivial children to
        # the list_of_children_sub_asts.
        n = ctx.getChildCount()
        for i in range(n):
            c = ctx.getChild(i)
            # NOTE: boring children (i.e. syntax elements which don't belong
            # inside the AST) yield childResult == None, because we DON'T
            # implement a visitor-method override for them!
            childResult = c.accept(self)
            if childResult:
                list_of_children_sub_asts.append(childResult)

        return list_of_children_sub_asts


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

