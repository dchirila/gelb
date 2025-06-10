#!/usr/bin/env python3

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.frontend.visitor_mixins import ProgramTraversalMixin
from gelb.gelb_ast.ASTNodes import *
from gelb.utils.exceptions import GeLBExTypeError


class DivisionByZeroValidator(ASTBaseVisitor, ProgramTraversalMixin):
    """
    Validates that there are no division by zero operations in the AST.
    
    This validator must run AFTER constant folding and propagation to catch:
    - Direct literal zeros: 1 / 0
    - Constants propagated to zeros: const int ZERO = 0; ... 1 / ZERO
    - Expressions folded to zeros: const int ZERO = 1 - 1; ... 1 / ZERO
    
    Running after constant folding ensures we catch all compile-time
    detectable division by zero errors.
    """
    
    def __init__(self):
        super().__init__()
    
    # Program traversal
    
    def visitProgram_N(self, node: Program_N, ast_root_node: Program_N):
        """Visit all blocks in the program to check for division by zero."""
        self.traverse_program_blocks(node, ast_root_node)
        return node
    
    def _store_global_constants(self, node):
        """Hook for storing global constants block."""
        self.global_constants_block = node.global_constants
    
    def _before_block_visit(self, block_node, block_type):
        """Set current block context before visiting."""
        self.current_block = block_node
    
    # Division operation
    
    def visitDiv_N(self, node: Div_N, ast_root_node: Program_N):
        """Check division for zero divisor."""
        # Visit children first
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        
        # Check if divisor is zero
        divisor = node.right
        
        # Check for literal zero (after constant folding/propagation)
        if isinstance(divisor, IntLiteral_N) and divisor.value == 0:
            raise GeLBExTypeError(
                divisor,
                "Division by zero: cannot divide by zero",
                "Remove the division by zero or use a non-zero divisor"
            )
        
        if isinstance(divisor, RealLiteral_N) and divisor.value == 0.0:
            raise GeLBExTypeError(
                divisor,
                "Division by zero: cannot divide by zero", 
                "Remove the division by zero or use a non-zero divisor"
            )
        
        return node
    
    # Standard block traversal methods
    
    def visitGlobalConstantsBlock_N(self, node: GlobalConstantsBlock_N, ast_root_node: Program_N):
        """Process statements in global constants block."""
        for stmt in node.stmts:
            self.visit(stmt, ast_root_node)
        return node
    
    def visitInitializerBlock_N(self, node: InitializerBlock_N, ast_root_node: Program_N):
        """Process statements in initializer block."""
        for stmt in node.stmts:
            self.visit(stmt, ast_root_node)
        return node
    
    def visitDynamicBlock_N(self, node: DynamicBlock_N, ast_root_node: Program_N):
        """Process statements in dynamic block."""
        for stmt in node.stmts:
            self.visit(stmt, ast_root_node)
        return node
    
    def visitGaugeBlock_N(self, node: GaugeBlock_N, ast_root_node: Program_N):
        """Process statements in gauge block."""
        for stmt in node.stmts:
            self.visit(stmt, ast_root_node)
        return node
    
    # Statement traversal
    
    def visitConstantDefinitionStmt_N(self, node: ConstantDefinitionStmt_N, ast_root_node: Program_N):
        """Check constant definition value."""
        self.visit(node.value, ast_root_node)
        return node
    
    def visitVariableAssignmentStmt_N(self, node: VariableAssignmentStmt_N, ast_root_node: Program_N):
        """Check both sides of assignment."""
        self.visit(node.lhs, ast_root_node)
        self.visit(node.rhs, ast_root_node)
        return node
    
    def visitLatticeOutSelectionAssignmentStmt_N(self, node: LatticeOutSelectionAssignmentStmt_N, ast_root_node: Program_N):
        """Check right side of lattice assignment."""
        self.visit(node.rhs, ast_root_node)
        return node
    
    def visitArraySelectionAssignmentStmt_N(self, node: ArraySelectionAssignmentStmt_N, ast_root_node: Program_N):
        """Check right side of array assignment."""
        self.visit(node.rhs, ast_root_node)
        return node
    
    def visitVariableDeclarationStmt_N(self, node: VariableDeclarationStmt_N, ast_root_node: Program_N):
        """Check initial value if present."""
        if node.initial_value:
            self.visit(node.initial_value, ast_root_node)
        return node
    
    # Broadcast node (added by type promotion)
    
    def visitBroadcastNode_N(self, node: BroadcastNode_N, ast_root_node: Program_N):
        """Check broadcast node's scalar expression."""
        self.visit(node.scalar_expr, ast_root_node)
        return node
    
    # Binary operations (visit children)
    
    def visitAdd_N(self, node: Add_N, ast_root_node: Program_N):
        """Visit children of addition."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node
    
    def visitSub_N(self, node: Sub_N, ast_root_node: Program_N):
        """Visit children of subtraction."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node
    
    def visitMul_N(self, node: Mul_N, ast_root_node: Program_N):
        """Visit children of multiplication."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node
    
    def visitPow_N(self, node: Pow_N, ast_root_node: Program_N):
        """Visit children of exponentiation."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node
    
    # Comparison operations
    
    def visitLess_N(self, node: Less_N, ast_root_node: Program_N):
        """Visit children of less-than."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node
    
    def visitGreater_N(self, node: Greater_N, ast_root_node: Program_N):
        """Visit children of greater-than."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node
    
    def visitLessEqual_N(self, node: LessEqual_N, ast_root_node: Program_N):
        """Visit children of less-equal."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node
    
    def visitGreaterEqual_N(self, node: GreaterEqual_N, ast_root_node: Program_N):
        """Visit children of greater-equal."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node
    
    def visitEqual_N(self, node: Equal_N, ast_root_node: Program_N):
        """Visit children of equality."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node
    
    def visitNotEqual_N(self, node: NotEqual_N, ast_root_node: Program_N):
        """Visit children of not-equal."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node
    
    # Logical operations
    
    def visitAnd_N(self, node: And_N, ast_root_node: Program_N):
        """Visit children of logical AND."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node
    
    def visitOr_N(self, node: Or_N, ast_root_node: Program_N):
        """Visit children of logical OR."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node
    
    # Unary operations
    
    def visitUnaryMinusExpr_N(self, node: UnaryMinusExpr_N, ast_root_node: Program_N):
        """Visit child of unary minus."""
        self.visit(node.operand, ast_root_node)
        return node
    
    def visitNotExpr_N(self, node: NotExpr_N, ast_root_node: Program_N):
        """Visit child of logical NOT."""
        self.visit(node.operand, ast_root_node)
        return node
    
    # Array literals
    
    def visitArray1DLiteral_N(self, node: Array1DLiteral_N, ast_root_node: Program_N):
        """Visit elements of 1D array literal."""
        for elem in node.value.elements:
            self.visit(elem, ast_root_node)
        return node
    
    def visitArray2DLiteral_N(self, node: Array2DLiteral_N, ast_root_node: Program_N):
        """Visit elements of 2D array literal."""
        for row in node.value.elements:
            self.visit(row, ast_root_node)
        return node
    
    def visitArray3DLiteral_N(self, node: Array3DLiteral_N, ast_root_node: Program_N):
        """Visit elements of 3D array literal."""
        for plane in node.value.elements:
            self.visit(plane, ast_root_node)
        return node
    
    def visitArray4DLiteral_N(self, node: Array4DLiteral_N, ast_root_node: Program_N):
        """Visit elements of 4D array literal."""
        for cube in node.value.elements:
            self.visit(cube, ast_root_node)
        return node
    
    # Terminal nodes (no division possible)
    
    def visitIntLiteral_N(self, node: IntLiteral_N, ast_root_node: Program_N):
        """Integer literals don't contain division."""
        return node
    
    def visitRealLiteral_N(self, node: RealLiteral_N, ast_root_node: Program_N):
        """Real literals don't contain division."""
        return node
    
    def visitBoolLiteral_N(self, node: BoolLiteral_N, ast_root_node: Program_N):
        """Boolean literals don't contain division."""
        return node
    
    def visitStringLiteral_N(self, node: StringLiteral_N, ast_root_node: Program_N):
        """String literals don't contain division."""
        return node
    
    def visitIdentifier_N(self, node: Identifier_N, ast_root_node: Program_N):
        """Identifiers don't contain division."""
        return node
    
    # Lattice and array selection nodes (no division possible)
    
    def visitRectSelOfLatticeInDFs_N(self, node, ast_root_node: Program_N):
        """Lattice input selections don't contain division."""
        return node
    
    def visitRectSelOfLatticeOutDFs_N(self, node, ast_root_node: Program_N):
        """Lattice output selections don't contain division."""
        return node
    
    def visitRectSelOfArrayElems_N(self, node, ast_root_node: Program_N):
        """Array selections don't contain division."""
        return node