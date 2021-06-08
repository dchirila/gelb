#!/usr/bin/env python3

from gelb.ASTNodes import *


class ASTBaseVisitor(object):
    """
    Abstract base-class for all AST node-visitors.
    """

    def __init__(self):
        raise NotImplementedError()

    def visitList_N(node:List_N):
        raise NotImplementedError()

    def visitProgram_N(node:Program_N):
        raise NotImplementedError()

    def visitGlobalConstantsBlock_N(node:GlobalConstantsBlock_N):
        raise NotImplementedError()

    def visitLatticeConstantsBlock_N(node:LatticeConstantsBlock_N):
        raise NotImplementedError()

    def visitLatticesBlock_N(node:LatticesBlock_N):
        raise NotImplementedError()

    def visitLatticeInstaStmt_N(node:LatticeInstaStmt_N):
        raise NotImplementedError()

    def visitNodeClassesBlock_N(node:NodeClassesBlock_N):
        raise NotImplementedError()

    def visitNodeClassInstaStmt_N(node:NodeClassInstaStmt_N):
        raise NotImplementedError()

    def visitInitializerBlock_N(node:InitializerBlock_N):
        raise NotImplementedError()

    def visitDynamicBlock_N(node:DynamicBlock_N):
        raise NotImplementedError()

    def visitGaugeBlock_N(node:GaugeBlock_N):
        raise NotImplementedError()

    def visitGeometryBlock_N(node:GeometryBlock_N):
        raise NotImplementedError()

    def visitIdentifier_N(node:Identifier_N):
        raise NotImplementedError()

    def visitRange_N(node:Range_N):
        raise NotImplementedError()

    def visitRectSelOfLatticeDFs_N(node:RectSelOfLatticeDFs_N):
        raise NotImplementedError()

    def visitRectSelOfLatticeInDFs_N(node:RectSelOfLatticeInDFs_N):
        raise NotImplementedError()

    def visitRectSelOfLatticeOutDFs_N(node:RectSelOfLatticeOutDFs_N):
        raise NotImplementedError()

    def visitRectSelOfArrayElems_N(node:RectSelOfArrayElems_N):
        raise NotImplementedError()

    def visitScalarDataType_N(node:ScalarDataType_N):
        raise NotImplementedError()

    def visitArrayDataType_N(node:ArrayDataType_N):
        raise NotImplementedError()

    def visitBinaryExpr_N(node:BinaryExpr_N):
        raise NotImplementedError()

    def visitMul_N(node:Mul_N):
        raise NotImplementedError()

    def visitDiv_N(node:Div_N):
        raise NotImplementedError()

    def visitAdd_N(node:Add_N):
        raise NotImplementedError()

    def visitSub_N(node:Sub_N):
        raise NotImplementedError()

    def visitPow_N(node:Pow_N):
        raise NotImplementedError()

    def visitNotExpr_N(node:NotExpr_N):
        raise NotImplementedError()

    def visitUnaryMinusExpr_N(node:UnaryMinusExpr_N):
        raise NotImplementedError()

    def visitIntLiteral_N(node:IntLiteral_N):
        raise NotImplementedError()

    def visitRealLiteral_N(node:RealLiteral_N):
        raise NotImplementedError()

    def visitBoolLiteral_N(node:BoolLiteral_N):
        raise NotImplementedError()

    def visitStringLiteral_N(node:StringLiteral_N):
        raise NotImplementedError()

    def visitArray1DLiteral_N(node:Array1DLiteral_N):
        raise NotImplementedError()

    def visitArray2DLiteral_N(node:Array2DLiteral_N):
        raise NotImplementedError()

    def visitArray3DLiteral_N(node:Array3DLiteral_N):
        raise NotImplementedError()

    def visitArray4DLiteral_N(node:Array4DLiteral_N):
        raise NotImplementedError()

    def visitFunctionCall_N(node:FunctionCall_N):
        raise NotImplementedError()

    def visitConstantDefinitionStmt_N(node:ConstantDefinitionStmt_N):
        raise NotImplementedError()

    def visitVariableDeclarationStmt_N(node:VariableDeclarationStmt_N):
        raise NotImplementedError()

    def visitPaintNodesStmt_N(node:PaintNodesStmt_N):
        raise NotImplementedError()

    def visitVariableAssignmentStmt_N(node:VariableAssignmentStmt_N):
        raise NotImplementedError()

    def visitLatticeAssignmentStmt_N(node:LatticeAssignmentStmt_N):
        raise NotImplementedError()

    def visitReturnStmt_N(node:ReturnStmt_N):
        raise NotImplementedError()

    def visitFunctionBlock_N(node:FunctionBlock_N):
        raise NotImplementedError()

    # def visitTODO(node:TODO):
    #     raise NotImplementedError()
