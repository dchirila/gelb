#!/usr/bin/env python3

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.frontend.visitor_mixins import ProgramTraversalMixin
from gelb.gelb_ast.ASTNodes import *
from gelb.utils.exceptions import GeLBException
from gelb.utils.CodeRange import CodeRange


class TypePromotionVisitor(ASTBaseVisitor, ProgramTraversalMixin):
    """
    Handles implicit type promotions by inserting TypePromotionNode_N
    where needed. Must run after TypeInferenceVisitor.
    
    This visitor modifies the AST by wrapping expressions that need
    implicit type promotion in TypePromotionNode_N instances.
    
    Type promotion hierarchy: bool → int → real
    """
    
    def __init__(self):
        super().__init__()
        self.promotion_hierarchy = self._build_promotion_hierarchy()
    
    def _build_promotion_hierarchy(self):
        """
        Define the type promotion hierarchy.
        Returns a dict mapping each type to its promotion level.
        """
        return {
            'bool': 0,
            'int': 1,
            'real': 2,
            # 'string' does not participate in promotions
        }
    
    def _can_promote(self, from_type, to_type):
        """
        Check if a type can be promoted to another type.
        
        Args:
            from_type: ArrayDataType_N or string
            to_type: ArrayDataType_N or string
            
        Returns:
            bool: True if promotion is valid
        """
        # Extract type names if ArrayDataType_N objects
        from_name = self._get_type_name(from_type)
        to_name = self._get_type_name(to_type)
        
        # Check if types participate in promotion
        if from_name not in self.promotion_hierarchy:
            return False
        if to_name not in self.promotion_hierarchy:
            return False
        
        # Can promote if from_type has lower or equal level
        return self.promotion_hierarchy[from_name] <= self.promotion_hierarchy[to_name]
    
    def _needs_promotion(self, expr_type, target_type):
        """
        Check if an expression needs promotion to a target type.
        
        Returns:
            bool: True if promotion is needed
        """
        expr_name = self._get_type_name(expr_type)
        target_name = self._get_type_name(target_type)
        
        # No promotion needed if types are the same
        if expr_name == target_name:
            return False
        
        # Check if promotion is valid
        return self._can_promote(expr_type, target_type)
    
    def _get_type_name(self, data_type):
        """Extract type name from ArrayDataType_N or string."""
        if isinstance(data_type, ArrayDataType_N):
            # For arrays, return the base scalar type
            return data_type.element_dtype
        elif isinstance(data_type, str):
            return data_type
        else:
            return None
    
    def _get_common_type(self, type1, type2):
        """
        Find the common type that both types can be promoted to.
        
        Returns:
            str: The common type name, or None if no common type exists
        """
        name1 = self._get_type_name(type1)
        name2 = self._get_type_name(type2)
        
        # If either type doesn't participate in promotion, no common type
        if name1 not in self.promotion_hierarchy:
            return None
        if name2 not in self.promotion_hierarchy:
            return None
        
        # Return the type with higher level
        if self.promotion_hierarchy[name1] >= self.promotion_hierarchy[name2]:
            return name1
        else:
            return name2
    
    def _create_promotion(self, expr, target_type_name):
        """
        Create a TypePromotionNode_N wrapping the expression.
        
        Args:
            expr: Expression to promote
            target_type_name: Target type name (string)
            
        Returns:
            TypePromotionNode_N: The promotion node
        """
        # Create target type with same shape as source expression
        if hasattr(expr, 'inferred_type') and isinstance(expr.inferred_type, ArrayDataType_N):
            # Preserve the shape from the source expression
            shape = expr.inferred_type.shape
            target_type = ArrayDataType_N(expr.code_range, target_type_name, shape)
        else:
            # Fallback to scalar array type (0-dimensional)
            empty_shape = List_N(expr.code_range)
            target_type = ArrayDataType_N(expr.code_range, target_type_name, empty_shape)
        return TypePromotionNode_N(expr.code_range, expr, target_type)
    
    # Program traversal
    
    def visitProgram_N(self, node: Program_N, ast_root_node: Program_N):
        """Visit all blocks in the program to apply type promotions."""
        self.traverse_program_blocks(node, ast_root_node)
        return node
    
    def _store_global_constants(self, node):
        """Hook for storing global constants block."""
        self.global_constants_block = node.global_constants
    
    def _before_block_visit(self, block_node, block_type):
        """Set current block context before visiting."""
        self.current_block = block_node
    
    # Binary operations
    
    def visitAdd_N(self, node: Add_N, ast_root_node: Program_N):
        """Handle type promotion for addition."""
        return self._handle_arithmetic_binary_op(node, ast_root_node)
    
    def visitSub_N(self, node: Sub_N, ast_root_node: Program_N):
        """Handle type promotion for subtraction."""
        return self._handle_arithmetic_binary_op(node, ast_root_node)
    
    def visitMul_N(self, node: Mul_N, ast_root_node: Program_N):
        """Handle type promotion for multiplication."""
        return self._handle_arithmetic_binary_op(node, ast_root_node)
    
    def visitDiv_N(self, node: Div_N, ast_root_node: Program_N):
        """Handle type promotion for division."""
        return self._handle_arithmetic_binary_op(node, ast_root_node)
    
    def visitPow_N(self, node: Pow_N, ast_root_node: Program_N):
        """Handle type promotion for exponentiation."""
        return self._handle_arithmetic_binary_op(node, ast_root_node)
    
    def _handle_arithmetic_binary_op(self, node, ast_root_node):
        """
        Handle type promotion for arithmetic binary operations.
        Both operands are promoted to a common type.
        """
        # Visit children first
        node.left = self.visit(node.left, ast_root_node)
        node.right = self.visit(node.right, ast_root_node)
        
        # Check if operands have inferred types
        if not hasattr(node.left, 'inferred_type') or not hasattr(node.right, 'inferred_type'):
            raise GeLBException(
                f"Type promotion requires type inference to run first",
                "Internal compiler error"
            )
        
        left_type = node.left.inferred_type
        right_type = node.right.inferred_type
        
        # Find common type
        common_type = self._get_common_type(left_type, right_type)
        if common_type is None:
            # This will be caught by type validation
            return node
        
        # Promote left operand if needed
        if self._needs_promotion(left_type, common_type):
            node.left = self._create_promotion(node.left, common_type)
        
        # Promote right operand if needed
        if self._needs_promotion(right_type, common_type):
            node.right = self._create_promotion(node.right, common_type)
        
        # Update the operation's inferred type to match new array-based system
        # Create 0-dimensional array type for scalar result
        empty_shape = List_N(node.code_range)
        node.inferred_type = ArrayDataType_N(node.code_range, common_type, empty_shape)
        
        return node
    
    # Comparison operations
    
    def visitLess_N(self, node: Less_N, ast_root_node: Program_N):
        """Handle type promotion for less-than comparison."""
        return self._handle_comparison_op(node, ast_root_node)
    
    def visitGreater_N(self, node: Greater_N, ast_root_node: Program_N):
        """Handle type promotion for greater-than comparison."""
        return self._handle_comparison_op(node, ast_root_node)
    
    def visitLessEqual_N(self, node: LessEqual_N, ast_root_node: Program_N):
        """Handle type promotion for less-equal comparison."""
        return self._handle_comparison_op(node, ast_root_node)
    
    def visitGreaterEqual_N(self, node: GreaterEqual_N, ast_root_node: Program_N):
        """Handle type promotion for greater-equal comparison."""
        return self._handle_comparison_op(node, ast_root_node)
    
    def visitEqual_N(self, node: Equal_N, ast_root_node: Program_N):
        """Handle type promotion for equality comparison."""
        return self._handle_comparison_op(node, ast_root_node)
    
    def visitNotEqual_N(self, node: NotEqual_N, ast_root_node: Program_N):
        """Handle type promotion for not-equal comparison."""
        return self._handle_comparison_op(node, ast_root_node)
    
    def _handle_comparison_op(self, node, ast_root_node):
        """
        Handle type promotion for comparison operations.
        Both operands are promoted to a common type.
        Result is always bool.
        """
        # Visit children first
        node.left = self.visit(node.left, ast_root_node)
        node.right = self.visit(node.right, ast_root_node)
        
        # Check if operands have inferred types
        if not hasattr(node.left, 'inferred_type') or not hasattr(node.right, 'inferred_type'):
            raise GeLBException(
                f"Type promotion requires type inference to run first",
                "Internal compiler error"
            )
        
        left_type = node.left.inferred_type
        right_type = node.right.inferred_type
        
        # Find common type
        common_type = self._get_common_type(left_type, right_type)
        if common_type is None:
            # This will be caught by type validation
            return node
        
        # Promote left operand if needed
        if self._needs_promotion(left_type, common_type):
            node.left = self._create_promotion(node.left, common_type)
        
        # Promote right operand if needed
        if self._needs_promotion(right_type, common_type):
            node.right = self._create_promotion(node.right, common_type)
        
        # Comparison always returns array[bool, ()]
        empty_shape = List_N(node.code_range)
        node.inferred_type = ArrayDataType_N(node.code_range, 'bool', empty_shape)
        
        return node
    
    # Logical operations (no promotion)
    
    def visitAnd_N(self, node: And_N, ast_root_node: Program_N):
        """Logical AND requires bool operands - no promotion."""
        # Just visit children
        node.left = self.visit(node.left, ast_root_node)
        node.right = self.visit(node.right, ast_root_node)
        return node
    
    def visitOr_N(self, node: Or_N, ast_root_node: Program_N):
        """Logical OR requires bool operands - no promotion."""
        # Just visit children
        node.left = self.visit(node.left, ast_root_node)
        node.right = self.visit(node.right, ast_root_node)
        return node
    
    # Unary operations
    
    def visitNotExpr_N(self, node: NotExpr_N, ast_root_node: Program_N):
        """Logical NOT requires bool operand - no promotion."""
        # Just visit child
        node.value = self.visit(node.value, ast_root_node)
        return node
    
    def visitUnaryMinusExpr_N(self, node: UnaryMinusExpr_N, ast_root_node: Program_N):
        """Unary minus preserves type - no promotion."""
        # Just visit child
        node.value = self.visit(node.value, ast_root_node)
        return node
    
    # Assignment statements
    
    def visitVariableAssignmentStmt_N(self, node: VariableAssignmentStmt_N, ast_root_node: Program_N):
        """Handle type promotion in variable assignment."""
        return self._handle_assignment(node, ast_root_node)
    
    def visitConstantDefinitionStmt_N(self, node: ConstantDefinitionStmt_N, ast_root_node: Program_N):
        """Handle type promotion in constant definition."""
        # Visit the value expression
        node.value = self.visit(node.value, ast_root_node)
        
        # Check if value needs promotion to declared type
        if not hasattr(node.value, 'inferred_type'):
            raise GeLBException(
                f"Type promotion requires type inference to run first",
                "Internal compiler error"
            )
        
        value_type = node.value.inferred_type
        declared_type = node.data_type
        
        # Check if promotion is needed
        if self._needs_promotion(value_type, declared_type):
            declared_type_name = self._get_type_name(declared_type)
            node.value = self._create_promotion(node.value, declared_type_name)
        
        return node
    
    def visitLatticeOutSelectionAssignmentStmt_N(self, node: LatticeOutSelectionAssignmentStmt_N, ast_root_node: Program_N):
        """Handle type promotion in lattice assignment."""
        return self._handle_assignment(node, ast_root_node)
    
    def visitArraySelectionAssignmentStmt_N(self, node: ArraySelectionAssignmentStmt_N, ast_root_node: Program_N):
        """Handle type promotion in array assignment."""
        return self._handle_assignment(node, ast_root_node)
    
    def _handle_assignment(self, node, ast_root_node):
        """
        Handle type promotion in assignment statements.
        RHS is promoted to LHS type if compatible.
        """
        # Visit both sides
        node.lhs = self.visit(node.lhs, ast_root_node)
        node.rhs = self.visit(node.rhs, ast_root_node)
        
        # Check if both sides have inferred types
        if not hasattr(node.lhs, 'inferred_type') or not hasattr(node.rhs, 'inferred_type'):
            raise GeLBException(
                f"Type promotion requires type inference to run first",
                "Internal compiler error"
            )
        
        lhs_type = node.lhs.inferred_type
        rhs_type = node.rhs.inferred_type
        
        # For array selections, we need the element type, not the array type
        target_type = lhs_type
        if hasattr(lhs_type, 'element_dtype'):  # It's an ArrayDataType_N
            target_type = lhs_type.element_dtype
        
        # Check if RHS needs promotion to target type
        if self._needs_promotion(rhs_type, target_type):
            target_type_name = self._get_type_name(target_type)
            node.rhs = self._create_promotion(node.rhs, target_type_name)
        
        return node
    
    # Block traversal (from mixin)
    
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
    
    def visitGeometryBlock_N(self, node: GeometryBlock_N, ast_root_node: Program_N):
        """Process statements in geometry block."""
        for stmt in node.stmts:
            self.visit(stmt, ast_root_node)
        return node
    
    # Pass-through for other nodes
    
    def visitLatticesBlock_N(self, node: LatticesBlock_N, ast_root_node: Program_N):
        """Lattices block doesn't need type promotion."""
        return node
    
    def visitNodeClassesBlock_N(self, node: NodeClassesBlock_N, ast_root_node: Program_N):
        """Node classes block doesn't need type promotion."""
        return node
    
    # Literals and identifiers (terminals)
    
    def visitIntLiteral_N(self, node: IntLiteral_N, ast_root_node: Program_N):
        """Integer literals don't need promotion."""
        return node
    
    def visitRealLiteral_N(self, node: RealLiteral_N, ast_root_node: Program_N):
        """Real literals don't need promotion."""
        return node
    
    def visitBoolLiteral_N(self, node: BoolLiteral_N, ast_root_node: Program_N):
        """Boolean literals don't need promotion."""
        return node
    
    def visitStringLiteral_N(self, node: StringLiteral_N, ast_root_node: Program_N):
        """String literals don't need promotion."""
        return node
    
    def visitIdentifier_N(self, node: Identifier_N, ast_root_node: Program_N):
        """Identifiers don't need promotion."""
        return node
    
    # Array literals
    
    def visitArray1DLiteral_N(self, node: Array1DLiteral_N, ast_root_node: Program_N):
        """Handle type promotion in array literals."""
        return self._handle_array_literal(node, ast_root_node)
    
    def visitArray2DLiteral_N(self, node: Array2DLiteral_N, ast_root_node: Program_N):
        """Handle type promotion in array literals."""
        return self._handle_array_literal(node, ast_root_node)
    
    def visitArray3DLiteral_N(self, node: Array3DLiteral_N, ast_root_node: Program_N):
        """Handle type promotion in array literals."""
        return self._handle_array_literal(node, ast_root_node)
    
    def visitArray4DLiteral_N(self, node: Array4DLiteral_N, ast_root_node: Program_N):
        """Handle type promotion in array literals."""
        return self._handle_array_literal(node, ast_root_node)
    
    def _handle_array_literal(self, node, ast_root_node):
        """
        Handle type promotion in array literals.
        All elements are promoted to a common type.
        """
        # Visit all elements first
        if hasattr(node, 'value') and hasattr(node.value, 'elements'):
            for i, elem in enumerate(node.value.elements):
                node.value.elements[i] = self.visit(elem, ast_root_node)
            
            # Find common type among all elements
            # For simplicity, we'll use the array's inferred type
            if hasattr(node, 'inferred_type') and isinstance(node.inferred_type, ArrayDataType_N):
                target_type_name = node.inferred_type.element_dtype
                
                # Promote each element if needed
                for i, elem in enumerate(node.value.elements):
                    if hasattr(elem, 'inferred_type'):
                        elem_type = elem.inferred_type
                        if self._needs_promotion(elem_type, target_type_name):
                            node.value.elements[i] = self._create_promotion(elem, target_type_name)
        
        return node
    
    # Other nodes that may contain expressions
    
    def visitPaintNodesStmt_N(self, node: PaintNodesStmt_N, ast_root_node: Program_N):
        """Paint statements don't involve type promotion."""
        # The RHS is a node class name, not an expression
        if node.lhs is not None:
            node.lhs = self.visit(node.lhs, ast_root_node)
        return node
    
    def visitRange_N(self, node: Range_N, ast_root_node: Program_N):
        """Process range bounds."""
        if node.low is not None:
            node.low = self.visit(node.low, ast_root_node)
        if node.high is not None:
            node.high = self.visit(node.high, ast_root_node)
        return node
    
    def visitList_N(self, node: List_N, ast_root_node: Program_N):
        """Process all elements in a list."""
        for i, elem in enumerate(node.elements):
            node.elements[i] = self.visit(elem, ast_root_node)
        return node
    
    def visitRectSelOfLatticeInDFs_N(self, node: RectSelOfLatticeInDFs_N, ast_root_node: Program_N):
        """Lattice selections don't need promotion."""
        return node
    
    def visitRectSelOfLatticeOutDFs_N(self, node: RectSelOfLatticeOutDFs_N, ast_root_node: Program_N):
        """Lattice selections don't need promotion."""
        return node
    
    def visitRectSelOfArrayElems_N(self, node: RectSelOfArrayElems_N, ast_root_node: Program_N):
        """Array selections don't need promotion."""
        return node
    
    def visitVariableDeclarationStmt_N(self, node: VariableDeclarationStmt_N, ast_root_node: Program_N):
        """Variable declarations don't have expressions to promote."""
        return node
    
    def visitLatticeInstaStmt_N(self, node: LatticeInstaStmt_N, ast_root_node: Program_N):
        """Process expressions in lattice instantiation."""
        # Visit dimension and q parameters if they are expressions
        if node.d is not None:
            node.d = self.visit(node.d, ast_root_node)
        if node.q is not None:
            node.q = self.visit(node.q, ast_root_node)
        
        # Visit grid_size and periodicity if present
        if hasattr(node, 'grid_size') and node.grid_size is not None:
            node.grid_size = self.visit(node.grid_size, ast_root_node)
        if hasattr(node, 'periodicity') and node.periodicity is not None:
            node.periodicity = self.visit(node.periodicity, ast_root_node)
        
        return node