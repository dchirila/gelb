#!/usr/bin/env python3

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.gelb_ast.ASTNodes import (
    Range_N, IntLiteral_N, Sub_N, Identifier_N, Div_N, Add_N, Mul_N,
    RectSelOfLatticeOutDFs_N, RectSelOfLatticeInDFs_N,
    RectSelOfArrayElems_N, PaintNodesStmt_N
)


class RangeResolverVisitor(ASTBaseVisitor):
    """
    Replaces None bounds in Range_N nodes with concrete values:
    - None lower bound → 0
    - None upper bound → Nx-1, Ny-1, or Nz-1 (based on dimension)
    
    This visitor must run after symbol tables are built but before
    type checking and other validations.
    """
    
    def __init__(self):
        super().__init__()
        self.current_dimension = None  # Track which dimension we're processing
        self.in_dfs_range = False  # Track if we're in a DFs range
        
    def visitProgram_N(self, node, ast_root_node):
        # Visit all blocks that might contain ranges
        if node.initializers:
            for initializer in node.initializers:
                self.visit(initializer, ast_root_node)
                
        if node.dynamics:
            for dynamic in node.dynamics:
                self.visit(dynamic, ast_root_node)
                
        if node.gauges:
            for gauge in node.gauges:
                self.visit(gauge, ast_root_node)
                
        if node.geometry:
            self.visit(node.geometry, ast_root_node)
            
        return node
        
    def visitGeometryBlock_N(self, node, ast_root_node):
        # Visit paint_nodes statements
        if node.stmts:
            for stmt in node.stmts:
                self.visit(stmt, ast_root_node)
        return node
        
    def visitInitializerBlock_N(self, node, ast_root_node):
        # Visit all statements that might contain ranges
        for stmt in node.stmts:
            self.visit(stmt, ast_root_node)
        return node
        
    def visitDynamicBlock_N(self, node, ast_root_node):
        # Visit all statements that might contain ranges
        for stmt in node.stmts:
            self.visit(stmt, ast_root_node)
        return node
        
    def visitGaugeBlock_N(self, node, ast_root_node):
        # Visit all statements that might contain ranges
        for stmt in node.stmts:
            self.visit(stmt, ast_root_node)
        return node
        
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
            self.in_dfs_range = True
            self.visit(node.element_ranges[-1], ast_root_node)
            self.in_dfs_range = False
        
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
            self.in_dfs_range = True
            self.visit(node.element_ranges[-1], ast_root_node)
            self.in_dfs_range = False
        
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
                # For DFs ranges, we need q-1
                # For now, we'll use a placeholder that will be resolved later
                # when we have access to the lattice's q value
                # TODO: This needs to be improved to get the actual q value
                q_var = Identifier_N(node.code_range, 'q')
                one = IntLiteral_N(node.code_range, 1)
                node.high = Sub_N(node.code_range, q_var, one)
            elif self.current_dimension is not None:
                # For spatial dimensions, use Nx-1, Ny-1, or Nz-1
                dim_names = ['Nx', 'Ny', 'Nz']
                if self.current_dimension < len(dim_names):
                    # Create expression: Nx-1, Ny-1, or Nz-1
                    dim_var = Identifier_N(node.code_range, dim_names[self.current_dimension])
                    one = IntLiteral_N(node.code_range, 1)
                    node.high = Sub_N(node.code_range, dim_var, one)
                else:
                    # For dimensions beyond 3D, we might need different handling
                    raise ValueError(f"Dimension {self.current_dimension} not supported")
            else:
                # This shouldn't happen in well-formed AST
                raise ValueError("Range_N with None high bound found outside expected context")
                
    def visitIntLiteral_N(self, node, ast_root_node):
        # IntLiteral nodes don't need modification
        return node
        
    def visitRealLiteral_N(self, node, ast_root_node):
        # RealLiteral nodes don't need modification
        return node
        
    def visitIdentifier_N(self, node, ast_root_node):
        # Identifier nodes don't need modification
        return node
        
    def visitSub_N(self, node, ast_root_node):
        # Visit operands
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node
        
    def visitAdd_N(self, node, ast_root_node):
        # Visit operands
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node
        
    def visitDiv_N(self, node, ast_root_node):
        # Visit operands
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node
        
    def visitMul_N(self, node, ast_root_node):
        # Visit operands
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node
        
    # Generic handlers for nodes that don't contain ranges
    def visitVariableAssignmentStmt_N(self, node, ast_root_node):
        # Variable assignments might have ranges in the RHS expression
        self.visit(node.rhs, ast_root_node)
        return node
        
    def visitConstantDefinitionStmt_N(self, node, ast_root_node):
        # Constants have a variable assignment statement
        self.visit(node.assignment, ast_root_node)
        return node
        
    def visitVariableDeclarationStmt_N(self, node, ast_root_node):
        # Variable declarations don't contain ranges
        return node
        
    # Default handler for expressions without ranges
    def visitExpr_N(self, node, ast_root_node):
        # For any expression we don't specifically handle,
        # just visit its children if they are AST nodes
        for child in node.get_children():
            if child is not None and hasattr(child, '__class__') and \
               child.__class__.__name__.endswith('_N'):
                self.visit(child, ast_root_node)
        return node