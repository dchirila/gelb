#!/usr/bin/env python3

from gelb.ASTBaseVisitor import ASTBaseVisitor
from gelb.ASTNodes import *


class ASTInitialValidationVisitor(ASTBaseVisitor):
    """
    Concrete visitor for initial AST validation
    """


    def visitList_N(
            self,
            node: List_N
    ):
        # descend into child nodes, to check that they are valid
        # NOTE: List_N is the only component of the GeLB AST which has a field
        # that is NOT derived from Node_N (specifically, List_N.elements is a
        # plain Python list). So, we need to use some custom logic here.
        for field in node.elements:
            self.visit(field)

    # def visitScalarDataType_N(node:ScalarDataType_N):
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


    # def visitIntLiteral_N(node:IntLiteral_N):
    #     return isinstance(node.value, int)
    #
    # def visitRealLiteral_N(node:RealLiteral_N):
    #     return isinstance(node.value, float)
    #
    # def visitBoolLiteral_N(node:BoolLiteral_N):
    #     return isinstance(node.value, bool)
    #
    # def visitStringLiteral_N(node:StringLiteral_N):
    #     return (
    #             isinstance(node.value, str) and
    #             isinstance(node.field_name, str) and (
    #                     (node.field_name == "simulation_name") or
    #                     (node.field_name == "simulation_description")
    #             )
    #     )

    def visitLatticeOutSelectionAssignmentStmt_N(
            self,
            node: LatticeOutSelectionAssignmentStmt_N
    ):
        # (1) check that all required elements are present
        # TODO ensure they are not None, by iterating over node.get_ast_fields()

        # (2) descend into child nodes, to check that they are valid
        for field in node.get_ast_fields():
            print(f"<<<DEBUG>>> {field}, {type(getattr(node, field))}")
            self.visit(getattr(node, field))

    def visitProgram_N(self, node: Program_N):
        # (1) check that all required children are present, a valid number of
        #     times
        # TODO

        # (2) descend into child nodes, to check that they are valid
        for field in node.get_ast_fields():
            self.visit(getattr(node, field))

    def visitSetSimulationNameStmt_N(
            self,
            node: SetSimulationNameStmt_N
    ):
        raise NotImplementedError()

    def visitSetSimulationDescriptionStmt_N(
            self,
            node: SetSimulationDescriptionStmt_N):
        raise NotImplementedError()

    def visitGlobalConstantsBlock_N(
            self,
            node: GlobalConstantsBlock_N
    ):
        raise NotImplementedError()

    def visitLatticeConstantsBlock_N(
            self,
            node: LatticeConstantsBlock_N
    ):
        raise NotImplementedError()

    def visitLatticesBlock_N(
            self,
            node: LatticesBlock_N
    ):
        raise NotImplementedError()

    def visitLatticeInstaStmt_N(
            self,
            node: LatticeInstaStmt_N
    ):
        raise NotImplementedError()

    def visitNodeClassesBlock_N(
            self,
            node: NodeClassesBlock_N
    ):
        raise NotImplementedError()

    def visitNodeClassInstaStmt_N(
            self,
            node: NodeClassInstaStmt_N
    ):
        raise NotImplementedError()

    def visitInitializerBlock_N(
            self,
            node: InitializerBlock_N
    ):
        raise NotImplementedError()

    def visitDynamicBlock_N(
            self,
            node: DynamicBlock_N
    ):
        # (1) check that all required elements are present
        # TODO ensure they are not None, by iterating over node.get_ast_fields()

        # (2) descend into child nodes, to check that they are valid
        for field in node.get_ast_fields():
            self.visit(getattr(node, field))

    def visitGaugeBlock_N(
            self,
            node: GaugeBlock_N
    ):
        raise NotImplementedError()

    def visitGeometryBlock_N(
            self,
            node: GeometryBlock_N
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
            node: Range_N
    ):
        raise NotImplementedError()

    def visitRectSelOfLatticeInDFs_N(
            self,
            node: RectSelOfLatticeInDFs_N
    ):
        raise NotImplementedError()

    def visitRectSelOfLatticeOutDFs_N(
            self,
            node: RectSelOfLatticeOutDFs_N
    ):
        raise NotImplementedError()

    def visitRectSelOfArrayElems_N(
            self,
            node: RectSelOfArrayElems_N
    ):
        raise NotImplementedError()

    def visitScalarDataType_N(
            self,
            node: ScalarDataType_N
    ):
        raise NotImplementedError()

    def visitArrayDataType_N(
            self,
            node: ArrayDataType_N
    ):
        raise NotImplementedError()

    def visitMul_N(
            self,
            node: Mul_N
    ):
        raise NotImplementedError()

    def visitDiv_N(
            self,
            node: Div_N
    ):
        raise NotImplementedError()

    def visitAdd_N(
            self,
            node: Add_N
    ):
        raise NotImplementedError()

    def visitSub_N(
            self,
            node: Sub_N
    ):
        raise NotImplementedError()

    def visitPow_N(
            self,
            node: Pow_N
    ):
        raise NotImplementedError()

    def visitNotExpr_N(
            self,
            node: NotExpr_N
    ):
        raise NotImplementedError()

    def visitUnaryMinusExpr_N(
            self,
            node: UnaryMinusExpr_N
    ):
        raise NotImplementedError()

    def visitIntLiteral_N(
            self,
            node: IntLiteral_N
    ):
        raise NotImplementedError()

    def visitRealLiteral_N(
            self,
            node: RealLiteral_N
    ):
        raise NotImplementedError()

    def visitBoolLiteral_N(
            self,
            node: BoolLiteral_N
    ):
        raise NotImplementedError()

    def visitStringLiteral_N(
            self,
            node: StringLiteral_N
    ):
        raise NotImplementedError()

    def visitArray1DLiteral_N(
            self,
            node: Array1DLiteral_N
    ):
        raise NotImplementedError()

    def visitArray2DLiteral_N(
            self,
            node: Array2DLiteral_N
    ):
        raise NotImplementedError()

    def visitArray3DLiteral_N(
            self,
            node: Array3DLiteral_N
    ):
        raise NotImplementedError()

    def visitArray4DLiteral_N(
            self,
            node: Array4DLiteral_N
    ):
        raise NotImplementedError()

    def visitConstantDefinitionStmt_N(
            self,
            node: ConstantDefinitionStmt_N
    ):
        raise NotImplementedError()

    def visitVariableDeclarationStmt_N(
            self,
            node: VariableDeclarationStmt_N
    ):
        raise NotImplementedError()

    def visitPaintNodesStmt_N(
            self,
            node: PaintNodesStmt_N
    ):
        raise NotImplementedError()

    def visitVariableAssignmentStmt_N(
            self,
            node: VariableAssignmentStmt_N
    ):
        raise NotImplementedError()

    def visitLatticeOutSelectionAssignmentStmt_N(
            self,
            node: LatticeOutSelectionAssignmentStmt_N
    ):
        print(node)
        raise NotImplementedError()

