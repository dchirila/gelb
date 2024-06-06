#!/usr/bin/env python3

from frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb_ast.ASTNodes import *


class ASTInitialValidationVisitor(ASTBaseVisitor):
    """
    Concrete visitor for initial AST validation
    """

    def visitList_N(
            self,
            node: List_N,
            ast_root_node: Program_N
    ):
        # descend into child nodes, to check that they are valid
        # NOTE: List_N is the only component of the GeLB AST which has a field
        # that is NOT derived from Node_N (specifically, List_N.elements is a
        # plain Python list). So, we need to use some custom logic here.
        for field in node.elements:
            self.visit(field, ast_root_node)

    # def visitScalarDataType_N(
    #         self,
    #         node: ScalarDataType_N,
    #         ast_root_node: Program_N
    # ):
    #     supported_scalar_types = [
    #         'bool',  # boolean
    #         'int64', 'int32', 'int16', 'int8', 'int',  # integer
    #         'real64', 'real32', 'real16', 'real'  # real
    #     ]
    #     if node.data_type not in supported_scalar_types:
    #         raise TypeError(
    #             f"<<<GeLB-Error>>> {str(node.data_type)} is not a valid"
    #             f" scalar data-type!"
    #             f"\nHint: you can use one of the following values: "
    #             f"{supported_scalar_types}"
    #         )

    # def visitIntLiteral_N(
    #         self,
    #         node: IntLiteral_N,
    #         ast_root_node: Program_N
    # ):
    #     return isinstance(node.value, int)

    # def visitRealLiteral_N(
    #         self,
    #         node: RealLiteral_N,
    #         ast_root_node: Program_N
    # ):
    #     return isinstance(node.value, float)

    # def visitBoolLiteral_N(
    #         self,
    #         node: BoolLiteral_N,
    #         ast_root_node: Program_N
    # ):
    #     return isinstance(node.value, bool)

    # def visitStringLiteral_N(
    #         self,
    #         node: StringLiteral_N,
    #         ast_root_node: Program_N
    # ):
    #     return (
    #             isinstance(node.value, str) and
    #             isinstance(node.field_name, str) and (
    #                     (node.field_name == "simulation_name") or
    #                     (node.field_name == "simulation_description")
    #             )
    #     )

    def visitLatticeOutSelectionAssignmentStmt_N(
            self,
            node: LatticeOutSelectionAssignmentStmt_N,
            ast_root_node: Program_N
    ):
        # (1) check that all required elements are present
        # TODO ensure they are not None, by iterating over node.get_children()

        # (2) descend into child nodes, to check that they are valid
        for field in node.get_children():
            print(f"<<<DEBUG>>> {field}, {type(getattr(node, field))}")
            self.visit(getattr(node, field), ast_root_node)

    def visitProgram_N(
            self,
            node: Program_N,
            ast_root_node: Program_N
    ):
        # (1) check that all required children are present, a valid number of
        #     times
        # TODO

        # (2) descend into child nodes, to check that they are valid
        for field in node.get_children():
            self.visit(getattr(node, field), ast_root_node)

    def visitSetSimulationNameStmt_N(
            self,
            node: SetSimulationNameStmt_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitSetSimulationDescriptionStmt_N(
            self,
            node: SetSimulationDescriptionStmt_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitGlobalConstantsBlock_N(
            self,
            node: GlobalConstantsBlock_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitLatticesBlock_N(
            self,
            node: LatticesBlock_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitLatticeInstaStmt_N(
            self,
            node: LatticeInstaStmt_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitNodeClassesBlock_N(
            self,
            node: NodeClassesBlock_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitNodeClassInstaStmt_N(
            self,
            node: NodeClassInstaStmt_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitInitializerBlock_N(
            self,
            node: InitializerBlock_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitDynamicBlock_N(
            self,
            node: DynamicBlock_N,
            ast_root_node: Program_N
    ):
        # (1) check that all required elements are present
        # TODO ensure they are not None, by iterating over node.get_children()

        # (2) descend into child nodes, to check that they are valid
        for field in node.get_children():
            self.visit(getattr(node, field), ast_root_node)

    def visitGaugeBlock_N(
            self,
            node: GaugeBlock_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitGeometryBlock_N(
            self,
            node: GeometryBlock_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitIdentifier_N(self, node: Identifier_N):
        # Nothing to do here, because ANTLR4 already catches problems with
        # identifiers (including the case when the user tries to use a GeLB
        # keyword as an identifier).
        # TODO: improve the error-message for the keyword-used-as-identifier
        #       error, by capturing the =msg= text produced by ANTLR4.
        pass

    def visitRange_N(
            self,
            node: Range_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitRectSelOfLatticeInDFs_N(
            self,
            node: RectSelOfLatticeInDFs_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitRectSelOfLatticeOutDFs_N(
            self,
            node: RectSelOfLatticeOutDFs_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitRectSelOfArrayElems_N(
            self,
            node: RectSelOfArrayElems_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitScalarDataType_N(
            self,
            node: ScalarDataType_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitArrayDataType_N(
            self,
            node: ArrayDataType_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitMul_N(
            self,
            node: Mul_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitDiv_N(
            self,
            node: Div_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitAdd_N(
            self,
            node: Add_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitSub_N(
            self,
            node: Sub_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitPow_N(
            self,
            node: Pow_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitNotExpr_N(
            self,
            node: NotExpr_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitUnaryMinusExpr_N(
            self,
            node: UnaryMinusExpr_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitIntLiteral_N(
            self,
            node: IntLiteral_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitRealLiteral_N(
            self,
            node: RealLiteral_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitBoolLiteral_N(
            self,
            node: BoolLiteral_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitStringLiteral_N(
            self,
            node: StringLiteral_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitArray1DLiteral_N(
            self,
            node: Array1DLiteral_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitArray2DLiteral_N(
            self,
            node: Array2DLiteral_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitArray3DLiteral_N(
            self,
            node: Array3DLiteral_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitArray4DLiteral_N(
            self,
            node: Array4DLiteral_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitConstantDefinitionStmt_N(
            self,
            node: ConstantDefinitionStmt_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitVariableDeclarationStmt_N(
            self,
            node: VariableDeclarationStmt_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitPaintNodesStmt_N(
            self,
            node: PaintNodesStmt_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()

    def visitVariableAssignmentStmt_N(
            self,
            node: VariableAssignmentStmt_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()
