#!/usr/bin/env python3

from gelb.gelb_ast.ASTNodes import *
from gelb.utils.exceptions import *


class ASTBaseVisitor(ABC):
    """
    Abstract base-class for all AST node-visitors.
    """

    # @abstractmethod
    # def __init__(self):
    #     pass

    def visit(self, node, ast_root_node):
        """
        Visit a node.

        Calls ``visitNODE_CLASS_NAME`` on itself passing ``node``,
        where ``NODE_CLASS_NAME`` is the node's class.

        :param node: The node to visit.
        :param ast_root_node: The root node for the entire program.
               NOTE: To avoid having the AST as a global constant, we always
               pass the ast_root_node to the visitor-methods (some of which
               need to access information available near the top of the tree).
        :return: The return value of the called visitation method.
        """
        ast_node_type_name = type(node).__name__
        visitor_subclass_name = self.__class__.__name__
        visitation_method_name = f"visit{ast_node_type_name}"
        if hasattr(self, visitation_method_name):
            visitation_method = getattr(self, visitation_method_name, None)
            result = visitation_method(node, ast_root_node)
            return result
        else:
            raise GeLBExMissingASTVisitationMethod(
                visitor_subclass_name,
                visitation_method_name
            )

    # def visitList_N(
    #         self,
    #         node: List_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitProgram_N(
    #         self,
    #         node: Program_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitSetSimulationNameStmt_N(
    #         self,
    #         node: SetSimulationNameStmt_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitSetSimulationDescriptionStmt_N(
    #         self,
    #         node: SetSimulationDescriptionStmt_N):,
    #         ast_root_node: Program_N
    #     raise NotImplementedError()
    #
    # def visitGlobalConstantsBlock_N(
    #         self,
    #         node: GlobalConstantsBlock_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitLatticesBlock_N(
    #         self,
    #         node: LatticesBlock_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitLatticeInstaStmt_N(
    #         self,
    #         node: LatticeInstaStmt_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitNodeClassesBlock_N(
    #         self,
    #         node: NodeClassesBlock_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitNodeClassInstaStmt_N(
    #         self,
    #         node: NodeClassInstaStmt_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitInitializerBlock_N(
    #         self,
    #         node: InitializerBlock_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitDynamicBlock_N(
    #         self,
    #         node: DynamicBlock_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitGaugeBlock_N(
    #         self,
    #         node: GaugeBlock_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitGeometryBlock_N(
    #         self,
    #         node: GeometryBlock_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitIdentifier_N(
    #         self,
    #         node: Identifier_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitRange_N(
    #         self,
    #         node: Range_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitRectSelOfLatticeInDFs_N(
    #         self,
    #         node: RectSelOfLatticeInDFs_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitRectSelOfLatticeOutDFs_N(
    #         self,
    #         node: RectSelOfLatticeOutDFs_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitRectSelOfArrayElems_N(
    #         self,
    #         node: RectSelOfArrayElems_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitScalarDataType_N(
    #         self,
    #         node: ScalarDataType_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitArrayDataType_N(
    #         self,
    #         node: ArrayDataType_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitMul_N(
    #         self,
    #         node: Mul_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitDiv_N(
    #         self,
    #         node: Div_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitAdd_N(
    #         self,
    #         node: Add_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitSub_N(
    #         self,
    #         node: Sub_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitPow_N(
    #         self,
    #         node: Pow_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitNotExpr_N(
    #         self,
    #         node: NotExpr_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitUnaryMinusExpr_N(
    #         self,
    #         node: UnaryMinusExpr_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitIntLiteral_N(
    #         self,
    #         node: IntLiteral_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitRealLiteral_N(
    #         self,
    #         node: RealLiteral_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitBoolLiteral_N(
    #         self,
    #         node: BoolLiteral_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitStringLiteral_N(
    #         self,
    #         node: StringLiteral_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitArray1DLiteral_N(
    #         self,
    #         node: Array1DLiteral_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitArray2DLiteral_N(
    #         self,
    #         node: Array2DLiteral_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitArray3DLiteral_N(
    #         self,
    #         node: Array3DLiteral_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitArray4DLiteral_N(
    #         self,
    #         node: Array4DLiteral_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitConstantDefinitionStmt_N(
    #         self,
    #         node: ConstantDefinitionStmt_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitVariableDeclarationStmt_N(
    #         self,
    #         node: VariableDeclarationStmt_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitPaintNodesStmt_N(
    #         self,
    #         node: PaintNodesStmt_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitVariableAssignmentStmt_N(
    #         self,
    #         node: VariableAssignmentStmt_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()
    #
    # def visitLatticeOutSelectionAssignmentStmt_N(
    #         self,
    #         node: LatticeOutSelectionAssignmentStmt_N,
    #         ast_root_node: Program_N
    # ):
    #     raise NotImplementedError()

    # def visitTODO(node: TODO):,
    #         ast_root_node: Program_N
    #     raise NotImplementedError()
