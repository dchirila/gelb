# Generated from gelb/antlr_part/grammars/GeLB.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .GeLBParser import GeLBParser
else:
    from GeLBParser import GeLBParser

# This class defines a complete generic visitor for a parse tree produced by GeLBParser.

class GeLBVisitor(ParseTreeVisitor):

    # Visit a parse tree produced by GeLBParser#gelb_program.
    def visitGelb_program(self, ctx:GeLBParser.Gelb_programContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#set_simulation_description_stmt.
    def visitSet_simulation_description_stmt(self, ctx:GeLBParser.Set_simulation_description_stmtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#global_constants_block.
    def visitGlobal_constants_block(self, ctx:GeLBParser.Global_constants_blockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#lattices_block.
    def visitLattices_block(self, ctx:GeLBParser.Lattices_blockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#lattice_insta_stmt.
    def visitLattice_insta_stmt(self, ctx:GeLBParser.Lattice_insta_stmtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#block_stmt.
    def visitBlock_stmt(self, ctx:GeLBParser.Block_stmtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#destructuring_assignment_stmt.
    def visitDestructuring_assignment_stmt(self, ctx:GeLBParser.Destructuring_assignment_stmtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#initializer_block.
    def visitInitializer_block(self, ctx:GeLBParser.Initializer_blockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#dynamic_block.
    def visitDynamic_block(self, ctx:GeLBParser.Dynamic_blockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#gauge_block.
    def visitGauge_block(self, ctx:GeLBParser.Gauge_blockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#function_block.
    def visitFunction_block(self, ctx:GeLBParser.Function_blockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#node_classes_block.
    def visitNode_classes_block(self, ctx:GeLBParser.Node_classes_blockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#node_class_insta_stmt.
    def visitNode_class_insta_stmt(self, ctx:GeLBParser.Node_class_insta_stmtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#geometry_block.
    def visitGeometry_block(self, ctx:GeLBParser.Geometry_blockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#geometry_stmt.
    def visitGeometry_stmt(self, ctx:GeLBParser.Geometry_stmtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#paint_nodes_stmt.
    def visitPaint_nodes_stmt(self, ctx:GeLBParser.Paint_nodes_stmtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#conditional_paint_stmt.
    def visitConditional_paint_stmt(self, ctx:GeLBParser.Conditional_paint_stmtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#border_stmt.
    def visitBorder_stmt(self, ctx:GeLBParser.Border_stmtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#lattice_out_selection_assignment_stmt.
    def visitLattice_out_selection_assignment_stmt(self, ctx:GeLBParser.Lattice_out_selection_assignment_stmtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#rect_sel_of_lattice_out_dfs.
    def visitRect_sel_of_lattice_out_dfs(self, ctx:GeLBParser.Rect_sel_of_lattice_out_dfsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#rect_sel_of_lattice_in_dfs.
    def visitRect_sel_of_lattice_in_dfs(self, ctx:GeLBParser.Rect_sel_of_lattice_in_dfsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#rect_sel_of_array_elems.
    def visitRect_sel_of_array_elems(self, ctx:GeLBParser.Rect_sel_of_array_elemsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#lattice_dfs_range.
    def visitLattice_dfs_range(self, ctx:GeLBParser.Lattice_dfs_rangeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#singleElementRange.
    def visitSingleElementRange(self, ctx:GeLBParser.SingleElementRangeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#lowhighBoundRange.
    def visitLowhighBoundRange(self, ctx:GeLBParser.LowhighBoundRangeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#lowBoundRange.
    def visitLowBoundRange(self, ctx:GeLBParser.LowBoundRangeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#highBoundRange.
    def visitHighBoundRange(self, ctx:GeLBParser.HighBoundRangeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#allElementsRange.
    def visitAllElementsRange(self, ctx:GeLBParser.AllElementsRangeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#constant_definition_stmt.
    def visitConstant_definition_stmt(self, ctx:GeLBParser.Constant_definition_stmtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#variable_declaration_stmt.
    def visitVariable_declaration_stmt(self, ctx:GeLBParser.Variable_declaration_stmtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#param_decl.
    def visitParam_decl(self, ctx:GeLBParser.Param_declContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#variable_declaration_with_init_stmt.
    def visitVariable_declaration_with_init_stmt(self, ctx:GeLBParser.Variable_declaration_with_init_stmtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#data_type.
    def visitData_type(self, ctx:GeLBParser.Data_typeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#scalar_data_type.
    def visitScalar_data_type(self, ctx:GeLBParser.Scalar_data_typeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#scalar_bool_data_type.
    def visitScalar_bool_data_type(self, ctx:GeLBParser.Scalar_bool_data_typeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#scalar_int_data_type.
    def visitScalar_int_data_type(self, ctx:GeLBParser.Scalar_int_data_typeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#scalar_real_data_type.
    def visitScalar_real_data_type(self, ctx:GeLBParser.Scalar_real_data_typeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#array_data_type.
    def visitArray_data_type(self, ctx:GeLBParser.Array_data_typeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#array_shape.
    def visitArray_shape(self, ctx:GeLBParser.Array_shapeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#array_literal_4d.
    def visitArray_literal_4d(self, ctx:GeLBParser.Array_literal_4dContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#array_literal_3d.
    def visitArray_literal_3d(self, ctx:GeLBParser.Array_literal_3dContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#array_literal_2d.
    def visitArray_literal_2d(self, ctx:GeLBParser.Array_literal_2dContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#array_literal_1d.
    def visitArray_literal_1d(self, ctx:GeLBParser.Array_literal_1dContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#variable_assignment_stmt.
    def visitVariable_assignment_stmt(self, ctx:GeLBParser.Variable_assignment_stmtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#array_selection_assignment_stmt.
    def visitArray_selection_assignment_stmt(self, ctx:GeLBParser.Array_selection_assignment_stmtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#identifier.
    def visitIdentifier(self, ctx:GeLBParser.IdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#rectSelOfLatticeInDFsExpr.
    def visitRectSelOfLatticeInDFsExpr(self, ctx:GeLBParser.RectSelOfLatticeInDFsExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#intrinsicFunctionCallExpr.
    def visitIntrinsicFunctionCallExpr(self, ctx:GeLBParser.IntrinsicFunctionCallExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#nonNegRealLiteralExpr.
    def visitNonNegRealLiteralExpr(self, ctx:GeLBParser.NonNegRealLiteralExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#logicalAndExpr.
    def visitLogicalAndExpr(self, ctx:GeLBParser.LogicalAndExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#comparisonExpr.
    def visitComparisonExpr(self, ctx:GeLBParser.ComparisonExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#parensExpr.
    def visitParensExpr(self, ctx:GeLBParser.ParensExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#nonNegIntLiteralExpr.
    def visitNonNegIntLiteralExpr(self, ctx:GeLBParser.NonNegIntLiteralExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#logicalOrExpr.
    def visitLogicalOrExpr(self, ctx:GeLBParser.LogicalOrExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#infixExpr.
    def visitInfixExpr(self, ctx:GeLBParser.InfixExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#unaryExpr.
    def visitUnaryExpr(self, ctx:GeLBParser.UnaryExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#rectSelOfArrayElemsExpr.
    def visitRectSelOfArrayElemsExpr(self, ctx:GeLBParser.RectSelOfArrayElemsExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#userFunctionCallExpr.
    def visitUserFunctionCallExpr(self, ctx:GeLBParser.UserFunctionCallExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#arrayLiteralExpr.
    def visitArrayLiteralExpr(self, ctx:GeLBParser.ArrayLiteralExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#powExpr.
    def visitPowExpr(self, ctx:GeLBParser.PowExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#boolLiteralExpr.
    def visitBoolLiteralExpr(self, ctx:GeLBParser.BoolLiteralExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#equalityExpr.
    def visitEqualityExpr(self, ctx:GeLBParser.EqualityExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#identifierExpr.
    def visitIdentifierExpr(self, ctx:GeLBParser.IdentifierExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#intrinsic_function_call.
    def visitIntrinsic_function_call(self, ctx:GeLBParser.Intrinsic_function_callContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#intrinsic_function_name.
    def visitIntrinsic_function_name(self, ctx:GeLBParser.Intrinsic_function_nameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GeLBParser#user_function_call.
    def visitUser_function_call(self, ctx:GeLBParser.User_function_callContext):
        return self.visitChildren(ctx)



del GeLBParser