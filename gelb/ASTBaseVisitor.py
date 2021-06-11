#!/usr/bin/env python3

from abc import ABC, abstractmethod

from gelb.ASTNodes import *


class ASTBaseVisitor(ABC):
    """
    Abstract base-class for all AST node-visitors.
    """

    @abstractmethod
    def __init__(self):
        pass

    @abstractmethod
    def visitList_N(
            self,
            node: List_N
    ):
        pass

    @abstractmethod
    def visitProgram_N(
            self,
            node: Program_N
    ):
        pass

    @abstractmethod
    def visitSetSimulationNameStmt_N(
            self,
            node: SetSimulationNameStmt_N
    ):
        pass

    @abstractmethod
    def visitSetSimulationDescriptionStmt_N(
            self,
            node: SetSimulationDescriptionStmt_N):
        pass

    @abstractmethod
    def visitGlobalConstantsBlock_N(
            self,
            node: GlobalConstantsBlock_N
    ):
        pass

    @abstractmethod
    def visitLatticeConstantsBlock_N(
            self,
            node: LatticeConstantsBlock_N
    ):
        pass

    @abstractmethod
    def visitLatticesBlock_N(
            self,
            node: LatticesBlock_N
    ):
        pass

    @abstractmethod
    def visitLatticeInstaStmt_N(
            self,
            node: LatticeInstaStmt_N
    ):
        pass

    @abstractmethod
    def visitNodeClassesBlock_N(
            self,
            node: NodeClassesBlock_N
    ):
        pass

    @abstractmethod
    def visitNodeClassInstaStmt_N(
            self,
            node: NodeClassInstaStmt_N
    ):
        pass

    @abstractmethod
    def visitInitializerBlock_N(
            self,
            node: InitializerBlock_N
    ):
        pass

    @abstractmethod
    def visitDynamicBlock_N(
            self,
            node: DynamicBlock_N
    ):
        pass

    @abstractmethod
    def visitGaugeBlock_N(
            self,
            node: GaugeBlock_N
    ):
        pass

    @abstractmethod
    def visitGeometryBlock_N(
            self,
            node: GeometryBlock_N
    ):
        pass

    @abstractmethod
    def visitIdentifier_N(
            self,
            node: Identifier_N
    ):
        pass

    @abstractmethod
    def visitRange_N(
            self,
            node: Range_N
    ):
        pass

    @abstractmethod
    def visitRectSelOfLatticeInDFs_N(
            self,
            node: RectSelOfLatticeInDFs_N
    ):
        pass

    @abstractmethod
    def visitRectSelOfLatticeOutDFs_N(
            self,
            node: RectSelOfLatticeOutDFs_N
    ):
        pass

    @abstractmethod
    def visitRectSelOfArrayElems_N(
            self,
            node: RectSelOfArrayElems_N
    ):
        pass

    @abstractmethod
    def visitScalarDataType_N(
            self,
            node: ScalarDataType_N
    ):
        pass

    @abstractmethod
    def visitArrayDataType_N(
            self,
            node: ArrayDataType_N
    ):
        pass

    @abstractmethod
    def visitMul_N(
            self,
            node: Mul_N
    ):
        pass

    @abstractmethod
    def visitDiv_N(
            self,
            node: Div_N
    ):
        pass

    @abstractmethod
    def visitAdd_N(
            self,
            node: Add_N
    ):
        pass

    @abstractmethod
    def visitSub_N(
            self,
            node: Sub_N
    ):
        pass

    @abstractmethod
    def visitPow_N(
            self,
            node: Pow_N
    ):
        pass

    @abstractmethod
    def visitNotExpr_N(
            self,
            node: NotExpr_N
    ):
        pass

    @abstractmethod
    def visitUnaryMinusExpr_N(
            self,
            node: UnaryMinusExpr_N
    ):
        pass

    @abstractmethod
    def visitIntLiteral_N(
            self,
            node: IntLiteral_N
    ):
        pass

    @abstractmethod
    def visitRealLiteral_N(
            self,
            node: RealLiteral_N
    ):
        pass

    @abstractmethod
    def visitBoolLiteral_N(
            self,
            node: BoolLiteral_N
    ):
        pass

    @abstractmethod
    def visitStringLiteral_N(
            self,
            node: StringLiteral_N
    ):
        pass

    @abstractmethod
    def visitArray1DLiteral_N(
            self,
            node: Array1DLiteral_N
    ):
        pass

    @abstractmethod
    def visitArray2DLiteral_N(
            self,
            node: Array2DLiteral_N
    ):
        pass

    @abstractmethod
    def visitArray3DLiteral_N(
            self,
            node: Array3DLiteral_N
    ):
        pass

    @abstractmethod
    def visitArray4DLiteral_N(
            self,
            node: Array4DLiteral_N
    ):
        pass

    @abstractmethod
    def visitConstantDefinitionStmt_N(
            self,
            node: ConstantDefinitionStmt_N
    ):
        pass

    @abstractmethod
    def visitVariableDeclarationStmt_N(
            self,
            node: VariableDeclarationStmt_N
    ):
        pass

    @abstractmethod
    def visitPaintNodesStmt_N(
            self,
            node: PaintNodesStmt_N
    ):
        pass

    @abstractmethod
    def visitVariableAssignmentStmt_N(
            self,
            node: VariableAssignmentStmt_N
    ):
        pass

    @abstractmethod
    def visitLatticeOutSelectionAssignmentStmt_N(
            self,
            node: LatticeOutSelectionAssignmentStmt_N
    ):
        pass

    # @abstractmethod
    # def visitTODO(node: TODO):
    #     pass
