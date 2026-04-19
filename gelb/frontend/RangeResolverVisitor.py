#!/usr/bin/env python3

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.frontend.implicit_symbols import DIMENSION_CONSTANT_NAMES
from gelb.frontend.visitor_mixins import BinaryOperationMixin, ProgramTraversalMixin
from gelb.gelb_ast.ASTNodes import (
    Range_N, IntLiteral_N, Sub_N, Identifier_N, Div_N, Add_N, Mul_N,
    RectSelOfLatticeOutDFs_N, RectSelOfLatticeInDFs_N,
    RectSelOfArrayElems_N, PaintNodesStmt_N,
    LatticeInstaStmt_N
)


class RangeResolverVisitor(ASTBaseVisitor, BinaryOperationMixin, ProgramTraversalMixin):
    """
    Replaces None bounds in Range_N nodes with concrete values:
    - None lower bound -> 0
    - None upper bound -> Nx-1, Ny-1, or Nz-1 (based on dimension)
    
    This visitor must run after symbol tables are built but before
    type checking and other validations.
    """
    
    def __init__(self):
        super().__init__()
        self.current_dimension = None  # Track which dimension we're processing
        self.in_dfs_range = False  # Track if we're in a DFs range
        self.current_lattice_name = None  # Track which lattice we're processing
        
    def visitProgram_N(self, node, ast_root_node):
        # Use mixin for standard traversal
        self.traverse_program_blocks(node, ast_root_node)
        return node
        
    def visitGeometryBlock_N(self, node, ast_root_node):
        """Visit paint_nodes statements."""
        return self._visit_block_stmts(node, ast_root_node)
        
    def visitInitializerBlock_N(self, node, ast_root_node):
        """Visit all statements that might contain ranges."""
        return self._visit_block_stmts(node, ast_root_node)
        
    def visitDynamicBlock_N(self, node, ast_root_node):
        """Visit all statements that might contain ranges."""
        return self._visit_block_stmts(node, ast_root_node)
        
    def visitGaugeBlock_N(self, node, ast_root_node):
        """Visit all statements that might contain ranges."""
        return self._visit_block_stmts(node, ast_root_node)

    def visitFunctionBlock_N(self, node, ast_root_node):
        """Visit all statements that might contain ranges."""
        return self._visit_block_stmts(node, ast_root_node)

    def visitLatticeOutSelectionAssignmentStmt_N(self, node, ast_root_node):
        # Visit the left-hand side (which contains ranges)
        self.visit(node.lhs, ast_root_node)
        # Also visit the right-hand side in case it contains ranges
        self.visit(node.rhs, ast_root_node)
        return node
        
    def visitPaintNodesStmt_N(self, node, ast_root_node):
        # In paint_nodes_stmt, the lhs contains the spatial ranges
        # The lhs is a List_N of Range_N nodes
        if hasattr(node.lhs, 'elements'):
            # It's a List_N
            for i, coord_range in enumerate(node.lhs.elements):
                self.current_dimension = i
                self.visit(coord_range, ast_root_node)
        else:
            # Single range
            self.current_dimension = 0
            self.visit(node.lhs, ast_root_node)
        self.current_dimension = None

    def visitBorderStmt_N(self, node, ast_root_node):
        return node  # No ranges to resolve

    def visitConditionalPaintStmt_N(self, node, ast_root_node):
        # The predicate may index constant arrays; resolve those ranges.
        self.current_dimension = None
        self.visit(node.predicate, ast_root_node)
        return node

    def visitRectSelOfLatticeOutDFs_N(self, node, ast_root_node):
        # The element_ranges contains both spatial ranges and DFs range
        # The last element is the DFs range
        num_ranges = len(node.element_ranges)

        # Process spatial ranges (all but the last)
        for i in range(num_ranges - 1):
            self.current_dimension = i
            self.visit(node.element_ranges[i], ast_root_node)
        self.current_dimension = None

        # Process DFs range (the last element)
        if num_ranges > 0:
            lattice_name = node.lattice_name
            if isinstance(lattice_name, Identifier_N):
                lattice_name = lattice_name.name
            self.current_lattice_name = lattice_name
            self.in_dfs_range = True
            self.visit(node.element_ranges[-1], ast_root_node)
            self.in_dfs_range = False
            self.current_lattice_name = None

    def visitRectSelOfLatticeInDFs_N(self, node, ast_root_node):
        # Same as above
        num_ranges = len(node.element_ranges)

        # Process spatial ranges (all but the last)
        for i in range(num_ranges - 1):
            self.current_dimension = i
            self.visit(node.element_ranges[i], ast_root_node)
        self.current_dimension = None

        # Process DFs range (the last element)
        if num_ranges > 0:
            lattice_name = node.lattice_name
            if isinstance(lattice_name, Identifier_N):
                lattice_name = lattice_name.name
            self.current_lattice_name = lattice_name
            self.in_dfs_range = True
            self.visit(node.element_ranges[-1], ast_root_node)
            self.in_dfs_range = False
            self.current_lattice_name = None
        
    def visitRectSelOfArrayElems_N(self, node, ast_root_node):
        # Process array dimensions
        for i, range_elem in enumerate(node.element_ranges):
            self.current_dimension = i
            self.visit(range_elem, ast_root_node)
        self.current_dimension = None
        
            
    def visitRange_N(self, node, ast_root_node):
        # Replace None bounds with concrete values
        if node.low is None:
            node.low = IntLiteral_N(node.code_range, 0)
            
        if node.high is None:
            if self.in_dfs_range:
                # Look up the lattice's q value (already resolved to IntLiteral_N
                # by the constants resolver which runs before this pass)
                q_val = self._get_lattice_q(ast_root_node, self.current_lattice_name)
                node.high = IntLiteral_N(node.code_range, q_val - 1)
                # Tag so type inference can distinguish `:` from e.g. `0` when q=1
                node.is_full_df_range = True
            elif self.current_dimension is not None:
                # For spatial dimensions, use Nx-1, Ny-1, or Nz-1
                if self.current_dimension < len(DIMENSION_CONSTANT_NAMES):
                    # Create expression: Nx-1, Ny-1, or Nz-1
                    dim_var = Identifier_N(
                        node.code_range,
                        DIMENSION_CONSTANT_NAMES[self.current_dimension],
                    )
                    one = IntLiteral_N(node.code_range, 1)
                    node.high = Sub_N(node.code_range, dim_var, one)
                else:
                    # For dimensions beyond 3D, we might need different handling
                    raise ValueError(f"Dimension {self.current_dimension} not supported")
            else:
                # This shouldn't happen in well-formed AST
                raise ValueError("Range_N with None high bound found outside expected context")
                
    def _get_lattice_q(self, ast_root_node, lattice_name):
        """Look up the q value for a lattice from the AST's lattice declarations."""
        for stmt in ast_root_node.lattices.stmts:
            if isinstance(stmt, LatticeInstaStmt_N):
                stmt_name = stmt.name
                if isinstance(stmt_name, Identifier_N):
                    stmt_name = stmt_name.name
                if stmt_name == lattice_name:
                    return stmt.q.value
        raise ValueError(f"Lattice '{lattice_name}' not found in lattice declarations")

    def visitIntLiteral_N(self, node, ast_root_node):
        # IntLiteral nodes don't need modification
        return node
        
    def visitRealLiteral_N(self, node, ast_root_node):
        # RealLiteral nodes don't need modification
        return node
        
    def visitBoolLiteral_N(self, node, ast_root_node):
        # BoolLiteral nodes don't need modification
        return node
        
    def visitStringLiteral_N(self, node, ast_root_node):
        # StringLiteral nodes don't need modification
        return node
        
    def visitIdentifier_N(self, node, ast_root_node):
        # Identifier nodes don't need modification
        return node
        
    # Binary operations handled by mixin
    def _handle_binary_operation(self, node, ast_root_node, operation_type):
        """Handle binary operations by visiting operands."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node
        
    # Generic handlers for nodes that don't contain ranges
    def visitVariableAssignmentStmt_N(self, node, ast_root_node):
        # Variable assignments might have ranges in the RHS expression
        self.visit(node.rhs, ast_root_node)
        return node
    
    def visitArraySelectionAssignmentStmt_N(self, node, ast_root_node):
        # Array selection assignments might have ranges in both LHS and RHS
        self.visit(node.lhs, ast_root_node)
        self.visit(node.rhs, ast_root_node)
        return node
        
    def visitConstantDefinitionStmt_N(self, node, ast_root_node):
        # Constants have a value expression
        self.visit(node.value, ast_root_node)
        return node
        
    def visitVariableDeclarationStmt_N(self, node, ast_root_node):
        # Visit initial value in case it contains lattice selections with ranges
        if node.initial_value is not None:
            self.visit(node.initial_value, ast_root_node)
        return node
        
    def visitUnaryMinusExpr_N(self, node, ast_root_node):
        # Visit the operand expression
        self.visit(node.value, ast_root_node)
        return node

    def visitTypePromotionNode_N(self, node, ast_root_node):
        # Inserted by the constant resolver around a substituted array
        # constant; nothing to resolve in the target type
        self.visit(node.expr, ast_root_node)
        return node
        
    def visitNotExpr_N(self, node, ast_root_node):
        # Visit the operand expression
        self.visit(node.value, ast_root_node)
        return node

    def visitIntrinsicFunctionCall_N(self, node, ast_root_node):
        # Visit arguments in case they contain ranges
        for arg in node.arguments.elements:
            self.visit(arg, ast_root_node)
        return node

    def visitUserFunctionCall_N(self, node, ast_root_node):
        # Visit arguments in case they contain ranges
        for arg in node.arguments.elements:
            self.visit(arg, ast_root_node)
        return node

    def visitDestructuringAssignmentStmt_N(self, node, ast_root_node):
        # Visit the RHS expression
        self.visit(node.rhs, ast_root_node)
        return node

    def visitArray1DLiteral_N(self, node, ast_root_node):
        # Visit array elements in case they contain ranges
        if hasattr(node, 'value') and hasattr(node.value, 'elements'):
            for elem in node.value.elements:
                self.visit(elem, ast_root_node)
        return node

    # Nested literals: the rows are literals themselves, so the same
    # element walk reaches every leaf expression.
    def visitArray2DLiteral_N(self, node, ast_root_node):
        return self.visitArray1DLiteral_N(node, ast_root_node)

    def visitArray3DLiteral_N(self, node, ast_root_node):
        return self.visitArray1DLiteral_N(node, ast_root_node)

    def visitArray4DLiteral_N(self, node, ast_root_node):
        return self.visitArray1DLiteral_N(node, ast_root_node)

    # Default handler for expressions without ranges
    def visitExpr_N(self, node, ast_root_node):
        # For any expression we don't specifically handle,
        # just visit its children if they are AST nodes
        for child in node.get_children():
            if child is not None and hasattr(child, '__class__') and \
               child.__class__.__name__.endswith('_N'):
                self.visit(child, ast_root_node)
        return node
