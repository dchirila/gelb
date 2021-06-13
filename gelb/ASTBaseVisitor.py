#!/usr/bin/env python3

from abc import ABC, abstractmethod

from gelb.ASTNodes import *
from gelb.utils.exceptions import *


class ASTBaseVisitor(ABC):
    """
    Abstract base-class for all AST node-visitors.
    """

    # @abstractmethod
    # def __init__(self):
    #     pass

    def visit(self, node):
        """
        Visit a node.

        Calls ``visitNODE_CLASS_NAME`` on itself passing ``node``,
        where ``NODE_CLASS_NAME`` is the node's class.

        :param node: The node to visit.
        :return: The return value of the called visitation method.
        """
        node_class_name = type(node).__name__
        visitor_subclass_name = self.__class__.__name__
        visitation_method_name = f"visit{node_class_name}"
        if hasattr(self, visitation_method_name):
            visitation_method = getattr(self, visitation_method_name, None)
            result = visitation_method(node)
            return result
        else:
            raise GeLBExMissingASTVisitationMethod(
                visitor_subclass_name,
                visitation_method_name
            )

    # def visitList_N(
    #         self,
    #         node: List_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitProgram_N(
    #         self,
    #         node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitSetSimulationNameStmt_N(
    #         self,
    #         node: SetSimulationNameStmt_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitSetSimulationDescriptionStmt_N(
    #         self,
    #         node: SetSimulationDescriptionStmt_N):
    #     raise NotImplementedError()
    #
    # def visitGlobalConstantsBlock_N(
    #         self,
    #         node: GlobalConstantsBlock_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitLatticeConstantsBlock_N(
    #         self,
    #         node: LatticeConstantsBlock_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitLatticesBlock_N(
    #         self,
    #         node: LatticesBlock_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitLatticeInstaStmt_N(
    #         self,
    #         node: LatticeInstaStmt_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitNodeClassesBlock_N(
    #         self,
    #         node: NodeClassesBlock_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitNodeClassInstaStmt_N(
    #         self,
    #         node: NodeClassInstaStmt_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitInitializerBlock_N(
    #         self,
    #         node: InitializerBlock_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitDynamicBlock_N(
    #         self,
    #         node: DynamicBlock_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitGaugeBlock_N(
    #         self,
    #         node: GaugeBlock_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitGeometryBlock_N(
    #         self,
    #         node: GeometryBlock_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitIdentifier_N(
    #         self,
    #         node: Identifier_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitRange_N(
    #         self,
    #         node: Range_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitRectSelOfLatticeInDFs_N(
    #         self,
    #         node: RectSelOfLatticeInDFs_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitRectSelOfLatticeOutDFs_N(
    #         self,
    #         node: RectSelOfLatticeOutDFs_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitRectSelOfArrayElems_N(
    #         self,
    #         node: RectSelOfArrayElems_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitScalarDataType_N(
    #         self,
    #         node: ScalarDataType_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitArrayDataType_N(
    #         self,
    #         node: ArrayDataType_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitMul_N(
    #         self,
    #         node: Mul_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitDiv_N(
    #         self,
    #         node: Div_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitAdd_N(
    #         self,
    #         node: Add_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitSub_N(
    #         self,
    #         node: Sub_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitPow_N(
    #         self,
    #         node: Pow_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitNotExpr_N(
    #         self,
    #         node: NotExpr_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitUnaryMinusExpr_N(
    #         self,
    #         node: UnaryMinusExpr_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitIntLiteral_N(
    #         self,
    #         node: IntLiteral_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitRealLiteral_N(
    #         self,
    #         node: RealLiteral_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitBoolLiteral_N(
    #         self,
    #         node: BoolLiteral_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitStringLiteral_N(
    #         self,
    #         node: StringLiteral_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitArray1DLiteral_N(
    #         self,
    #         node: Array1DLiteral_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitArray2DLiteral_N(
    #         self,
    #         node: Array2DLiteral_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitArray3DLiteral_N(
    #         self,
    #         node: Array3DLiteral_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitArray4DLiteral_N(
    #         self,
    #         node: Array4DLiteral_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitConstantDefinitionStmt_N(
    #         self,
    #         node: ConstantDefinitionStmt_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitVariableDeclarationStmt_N(
    #         self,
    #         node: VariableDeclarationStmt_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitPaintNodesStmt_N(
    #         self,
    #         node: PaintNodesStmt_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitVariableAssignmentStmt_N(
    #         self,
    #         node: VariableAssignmentStmt_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitLatticeOutSelectionAssignmentStmt_N(
    #         self,
    #         node: LatticeOutSelectionAssignmentStmt_N
    # ):
    #     raise NotImplementedError()

    # def visitTODO(node: TODO):
    #     raise NotImplementedError()
