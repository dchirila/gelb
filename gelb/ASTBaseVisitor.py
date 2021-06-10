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
    def visitList_N(node:List_N):
        pass

    @abstractmethod
    def visitProgram_N(node:Program_N):
        pass

    @abstractmethod
    def visitGlobalConstantsBlock_N(node:GlobalConstantsBlock_N):
        pass

    @abstractmethod
    def visitLatticeConstantsBlock_N(node:LatticeConstantsBlock_N):
        pass

    @abstractmethod
    def visitLatticesBlock_N(node:LatticesBlock_N):
        pass

    @abstractmethod
    def visitLatticeInstaStmt_N(node:LatticeInstaStmt_N):
        pass

    @abstractmethod
    def visitNodeClassesBlock_N(node:NodeClassesBlock_N):
        pass

    @abstractmethod
    def visitNodeClassInstaStmt_N(node:NodeClassInstaStmt_N):
        pass

    @abstractmethod
    def visitInitializerBlock_N(node:InitializerBlock_N):
        pass

    @abstractmethod
    def visitDynamicBlock_N(node:DynamicBlock_N):
        pass

    @abstractmethod
    def visitGaugeBlock_N(node:GaugeBlock_N):
        pass

    @abstractmethod
    def visitGeometryBlock_N(node:GeometryBlock_N):
        pass

    @abstractmethod
    def visitIdentifier_N(node:Identifier_N):
        pass

    @abstractmethod
    def visitRange_N(node:Range_N):
        pass

    @abstractmethod
    def visitRectSelOfLatticeDFs_N(node:RectSelOfLatticeDFs_N):
        pass

    @abstractmethod
    def visitRectSelOfLatticeInDFs_N(node:RectSelOfLatticeInDFs_N):
        pass

    @abstractmethod
    def visitRectSelOfLatticeOutDFs_N(node:RectSelOfLatticeOutDFs_N):
        pass

    @abstractmethod
    def visitRectSelOfArrayElems_N(node:RectSelOfArrayElems_N):
        pass

    @abstractmethod
    def visitScalarDataType_N(node:ScalarDataType_N):
        pass

    @abstractmethod
    def visitArrayDataType_N(node:ArrayDataType_N):
        pass

    @abstractmethod
    def visitBinaryExpr_N(node:BinaryExpr_N):
        pass

    @abstractmethod
    def visitMul_N(node:Mul_N):
        pass

    @abstractmethod
    def visitDiv_N(node:Div_N):
        pass

    @abstractmethod
    def visitAdd_N(node:Add_N):
        pass

    @abstractmethod
    def visitSub_N(node:Sub_N):
        pass

    @abstractmethod
    def visitPow_N(node:Pow_N):
        pass

    @abstractmethod
    def visitNotExpr_N(node:NotExpr_N):
        pass

    @abstractmethod
    def visitUnaryMinusExpr_N(node:UnaryMinusExpr_N):
        pass

    @abstractmethod
    def visitIntLiteral_N(node:IntLiteral_N):
        pass

    @abstractmethod
    def visitRealLiteral_N(node:RealLiteral_N):
        pass

    @abstractmethod
    def visitBoolLiteral_N(node:BoolLiteral_N):
        pass

    @abstractmethod
    def visitStringLiteral_N(node:StringLiteral_N):
        pass

    @abstractmethod
    def visitArray1DLiteral_N(node:Array1DLiteral_N):
        pass

    @abstractmethod
    def visitArray2DLiteral_N(node:Array2DLiteral_N):
        pass

    @abstractmethod
    def visitArray3DLiteral_N(node:Array3DLiteral_N):
        pass

    @abstractmethod
    def visitArray4DLiteral_N(node:Array4DLiteral_N):
        pass

    @abstractmethod
    def visitFunctionCall_N(node:FunctionCall_N):
        pass

    @abstractmethod
    def visitConstantDefinitionStmt_N(node:ConstantDefinitionStmt_N):
        pass

    @abstractmethod
    def visitVariableDeclarationStmt_N(node:VariableDeclarationStmt_N):
        pass

    @abstractmethod
    def visitPaintNodesStmt_N(node:PaintNodesStmt_N):
        pass

    @abstractmethod
    def visitVariableAssignmentStmt_N(node:VariableAssignmentStmt_N):
        pass

    @abstractmethod
    def visitLatticeAssignmentStmt_N(node:LatticeAssignmentStmt_N):
        pass

    @abstractmethod
    def visitReturnStmt_N(node:ReturnStmt_N):
        pass

    @abstractmethod
    def visitFunctionBlock_N(node:FunctionBlock_N):
        pass

    # @abstractmethod
    # def visitTODO(node:TODO):
    #     pass
