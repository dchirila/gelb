#!/usr/bin/env python3

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.frontend.visitor_mixins import ProgramTraversalMixin
from gelb.gelb_ast.ASTNodes import *
from gelb.utils.exceptions import GeLBException
from gelb.utils.CodeRange import CodeRange


class ConstantFoldingVisitor(ASTBaseVisitor, ProgramTraversalMixin):
    """
    Performs constant folding optimizations on the AST.
    
    This visitor evaluates constant expressions at compile time and replaces
    them with their computed literal values. This optimization:
    
    1. Improves runtime performance by eliminating redundant calculations
    2. Enables better optimization in subsequent passes
    3. Supports division by zero detection by simplifying expressions like (1-1) to 0
    4. Works with type promotion expansion to maximize constant propagation
    
    Must run after:
    - Type inference (needs inferred_type on nodes)
    - Constant resolution (needs constants to be resolved)
    
    Should run before:
    - Type promotion expansion (to maximize constant promotion opportunities)
    - Division by zero detection (to detect zeros in expressions)
    """
    
    def __init__(self):
        super().__init__()
    
    # Program traversal
    
    def visitProgram_N(self, node: Program_N, ast_root_node: Program_N):
        """Visit all blocks in the program to apply constant folding."""
        self.traverse_program_blocks(node, ast_root_node)
        return node
    
    def _store_global_constants(self, node):
        """Hook for storing global constants block."""
        self.global_constants_block = node.global_constants
    
    def _before_block_visit(self, block_node, block_type):
        """Set current block context before visiting."""
        self.current_block = block_node
    
    # Arithmetic operations
    
    def visitAdd_N(self, node: Add_N, ast_root_node: Program_N):
        """Fold addition operations."""
        return self._handle_arithmetic_binary_op(node, ast_root_node, self._evaluate_add)
    
    def visitSub_N(self, node: Sub_N, ast_root_node: Program_N):
        """Fold subtraction operations."""
        return self._handle_arithmetic_binary_op(node, ast_root_node, self._evaluate_sub)
    
    def visitMul_N(self, node: Mul_N, ast_root_node: Program_N):
        """Fold multiplication operations."""
        return self._handle_arithmetic_binary_op(node, ast_root_node, self._evaluate_mul)
    
    def visitDiv_N(self, node: Div_N, ast_root_node: Program_N):
        """Fold division operations."""
        return self._handle_arithmetic_binary_op(node, ast_root_node, self._evaluate_div)
    
    def visitPow_N(self, node: Pow_N, ast_root_node: Program_N):
        """Fold exponentiation operations."""
        return self._handle_arithmetic_binary_op(node, ast_root_node, self._evaluate_pow)
    
    def _handle_arithmetic_binary_op(self, node, ast_root_node, evaluator):
        """
        Generic handler for arithmetic binary operations.
        
        Args:
            node: The binary operation node
            ast_root_node: Root of the AST
            evaluator: Function to evaluate the operation
        """
        # Visit children first (bottom-up processing)
        node.left = self.visit(node.left, ast_root_node)
        node.right = self.visit(node.right, ast_root_node)
        
        # Check if both operands are constant literals
        if self._is_constant_literal(node.left) and self._is_constant_literal(node.right):
            try:
                result_value = evaluator(node.left, node.right)
                result_literal = self._create_literal_from_value(result_value, node)
                if result_literal is not None:
                    return result_literal
            except (ZeroDivisionError, OverflowError, ValueError):
                # Don't fold if evaluation fails - let runtime or validation handle it
                pass
        
        return node
    
    # Comparison operations
    
    def visitLess_N(self, node: Less_N, ast_root_node: Program_N):
        """Fold less-than comparison."""
        return self._handle_comparison_op(node, ast_root_node, lambda l, r: l < r)
    
    def visitGreater_N(self, node: Greater_N, ast_root_node: Program_N):
        """Fold greater-than comparison."""
        return self._handle_comparison_op(node, ast_root_node, lambda l, r: l > r)
    
    def visitLessEqual_N(self, node: LessEqual_N, ast_root_node: Program_N):
        """Fold less-equal comparison."""
        return self._handle_comparison_op(node, ast_root_node, lambda l, r: l <= r)
    
    def visitGreaterEqual_N(self, node: GreaterEqual_N, ast_root_node: Program_N):
        """Fold greater-equal comparison."""
        return self._handle_comparison_op(node, ast_root_node, lambda l, r: l >= r)
    
    def visitEqual_N(self, node: Equal_N, ast_root_node: Program_N):
        """Fold equality comparison."""
        return self._handle_comparison_op(node, ast_root_node, lambda l, r: l == r)
    
    def visitNotEqual_N(self, node: NotEqual_N, ast_root_node: Program_N):
        """Fold not-equal comparison."""
        return self._handle_comparison_op(node, ast_root_node, lambda l, r: l != r)
    
    def _handle_comparison_op(self, node, ast_root_node, comparator):
        """
        Generic handler for comparison operations.
        
        Args:
            node: The comparison operation node
            ast_root_node: Root of the AST
            comparator: Function to perform the comparison
        """
        # Visit children first
        node.left = self.visit(node.left, ast_root_node)
        node.right = self.visit(node.right, ast_root_node)
        
        # Check if both operands are constant literals
        if self._is_constant_literal(node.left) and self._is_constant_literal(node.right):
            try:
                left_val = self._get_literal_value(node.left)
                right_val = self._get_literal_value(node.right)
                result = comparator(left_val, right_val)
                
                # Convert Python boolean result to string for consistency
                result_str = self._bool_to_string(result)
                return self._create_typed_bool_literal(node.code_range, result_str, node)
            except (TypeError, ValueError):
                # Don't fold if comparison fails (e.g., incompatible types)
                pass
        
        return node
    
    # Logical operations
    
    def visitAnd_N(self, node: And_N, ast_root_node: Program_N):
        """Fold logical AND operations."""
        return self._handle_logical_binary_op(node, ast_root_node, lambda l, r: l and r)
    
    def visitOr_N(self, node: Or_N, ast_root_node: Program_N):
        """Fold logical OR operations."""
        return self._handle_logical_binary_op(node, ast_root_node, lambda l, r: l or r)
    
    def _handle_logical_binary_op(self, node, ast_root_node, operator):
        """
        Generic handler for logical binary operations.
        
        Args:
            node: The logical operation node
            ast_root_node: Root of the AST
            operator: Function to perform the logical operation
        """
        # Visit children first
        node.left = self.visit(node.left, ast_root_node)
        node.right = self.visit(node.right, ast_root_node)
        
        # Check if both operands are boolean literals
        if (isinstance(node.left, BoolLiteral_N) and 
            isinstance(node.right, BoolLiteral_N)):
            # Convert string boolean values to Python booleans
            left_bool = self._string_to_bool(node.left.value)
            right_bool = self._string_to_bool(node.right.value)
            result = operator(left_bool, right_bool)
            # Convert result back to string for consistency with GeLB AST
            result_str = self._bool_to_string(result)
            return self._create_typed_bool_literal(node.code_range, result_str, node)
        
        return node
    
    # Unary operations
    
    def visitNotExpr_N(self, node: NotExpr_N, ast_root_node: Program_N):
        """Fold logical NOT operations."""
        node.value = self.visit(node.value, ast_root_node)
        
        if isinstance(node.value, BoolLiteral_N):
            # Convert string boolean to Python boolean, apply NOT, convert back
            bool_val = self._string_to_bool(node.value.value)
            result = not bool_val
            result_str = self._bool_to_string(result)
            return self._create_typed_bool_literal(node.code_range, result_str, node.value)
        
        return node
    
    def visitUnaryMinusExpr_N(self, node: UnaryMinusExpr_N, ast_root_node: Program_N):
        """Fold unary minus operations."""
        node.value = self.visit(node.value, ast_root_node)
        
        if isinstance(node.value, IntLiteral_N):
            return self._create_typed_int_literal(node.code_range, -node.value.value, node.value)
        elif isinstance(node.value, RealLiteral_N):
            return self._create_typed_real_literal(node.code_range, -node.value.value, node.value)
        
        return node
    
    # Helper methods
    
    def _is_constant_literal(self, node):
        """Check if a node is a constant literal that can be folded."""
        return (isinstance(node, IntLiteral_N) or 
                isinstance(node, RealLiteral_N) or
                isinstance(node, BoolLiteral_N))
    
    def _get_literal_value(self, node):
        """Extract the Python value from a literal node."""
        if isinstance(node, (IntLiteral_N, RealLiteral_N)):
            return node.value
        elif isinstance(node, BoolLiteral_N):
            # Convert GeLB boolean string to Python boolean for comparisons
            return self._string_to_bool(node.value)
        raise ValueError(f"Not a literal node: {type(node)}")
    
    def _create_literal_from_value(self, value, original_node):
        """
        Create appropriate literal node from a Python value.
        
        Args:
            value: Python value (int, float, bool)
            original_node: Original AST node for code range
            
        Returns:
            Literal_N node or None if value type not supported
        """
        if isinstance(value, bool):
            # Convert Python boolean to GeLB boolean string
            bool_str = self._bool_to_string(value)
            result = BoolLiteral_N(original_node.code_range, bool_str)
        elif isinstance(value, int):
            result = IntLiteral_N(original_node.code_range, value)
        elif isinstance(value, float):
            result = RealLiteral_N(original_node.code_range, value)
        else:
            return None
        
        # Preserve ArrayDataType_N inferred_type if available
        self._preserve_inferred_type(result, original_node)
        return result
    
    def _preserve_inferred_type(self, new_literal, original_node):
        """
        Preserve the inferred_type from the original node to the new literal.
        
        This is crucial for maintaining ArrayDataType_N consistency after constant folding.
        The original node should have an inferred_type set by TypeInferenceVisitor.
        """
        if hasattr(original_node, 'inferred_type'):
            new_literal.inferred_type = original_node.inferred_type
        else:
            # Fallback: create appropriate ArrayDataType_N based on literal type
            self._set_default_array_type(new_literal)
    
    def _set_default_array_type(self, literal_node):
        """Set default ArrayDataType_N for a literal node."""
        if isinstance(literal_node, IntLiteral_N):
            element_dtype = "int"
        elif isinstance(literal_node, RealLiteral_N):
            element_dtype = "real"
        elif isinstance(literal_node, BoolLiteral_N):
            element_dtype = "bool"
        else:
            return  # Unknown type, skip
        
        # Create 0-dimensional array type (scalar as array)
        empty_shape = List_N(literal_node.code_range)
        literal_node.inferred_type = ArrayDataType_N(literal_node.code_range, element_dtype, empty_shape)
    
    def _create_typed_bool_literal(self, code_range, bool_str, reference_node=None):
        """Create a BoolLiteral_N with proper ArrayDataType_N type."""
        result = BoolLiteral_N(code_range, bool_str)
        if reference_node and hasattr(reference_node, 'inferred_type'):
            result.inferred_type = reference_node.inferred_type
        else:
            self._set_default_array_type(result)
        return result
    
    def _create_typed_int_literal(self, code_range, value, reference_node=None):
        """Create an IntLiteral_N with proper ArrayDataType_N type."""
        result = IntLiteral_N(code_range, value)
        if reference_node and hasattr(reference_node, 'inferred_type'):
            result.inferred_type = reference_node.inferred_type
        else:
            self._set_default_array_type(result)
        return result
    
    def _create_typed_real_literal(self, code_range, value, reference_node=None):
        """Create a RealLiteral_N with proper ArrayDataType_N type."""
        result = RealLiteral_N(code_range, value)
        if reference_node and hasattr(reference_node, 'inferred_type'):
            result.inferred_type = reference_node.inferred_type
        else:
            self._set_default_array_type(result)
        return result
    
    # Arithmetic evaluators
    
    def _evaluate_add(self, left_node, right_node):
        """Evaluate addition of two literal nodes."""
        left_val = self._get_literal_value(left_node)
        right_val = self._get_literal_value(right_node)
        return left_val + right_val
    
    def _evaluate_sub(self, left_node, right_node):
        """Evaluate subtraction of two literal nodes."""
        left_val = self._get_literal_value(left_node)
        right_val = self._get_literal_value(right_node)
        return left_val - right_val
    
    def _evaluate_mul(self, left_node, right_node):
        """Evaluate multiplication of two literal nodes."""
        left_val = self._get_literal_value(left_node)
        right_val = self._get_literal_value(right_node)
        return left_val * right_val
    
    def _evaluate_div(self, left_node, right_node):
        """Evaluate division of two literal nodes."""
        left_val = self._get_literal_value(left_node)
        right_val = self._get_literal_value(right_node)
        
        # Let ZeroDivisionError propagate - caller will handle it
        return left_val / right_val
    
    def _evaluate_pow(self, left_node, right_node):
        """Evaluate exponentiation of two literal nodes."""
        left_val = self._get_literal_value(left_node)
        right_val = self._get_literal_value(right_node)
        return left_val ** right_val
    
    # Block traversal (from mixin)
    
    def visitGlobalConstantsBlock_N(self, node: GlobalConstantsBlock_N, ast_root_node: Program_N):
        """Process statements in global constants block."""
        for i, stmt in enumerate(node.stmts):
            node.stmts[i] = self.visit(stmt, ast_root_node)
        return node
    
    def visitInitializerBlock_N(self, node: InitializerBlock_N, ast_root_node: Program_N):
        """Process statements in initializer block."""
        for i, stmt in enumerate(node.stmts):
            node.stmts[i] = self.visit(stmt, ast_root_node)
        return node
    
    def visitDynamicBlock_N(self, node: DynamicBlock_N, ast_root_node: Program_N):
        """Process statements in dynamic block."""
        for i, stmt in enumerate(node.stmts):
            node.stmts[i] = self.visit(stmt, ast_root_node)
        return node
    
    def visitGaugeBlock_N(self, node: GaugeBlock_N, ast_root_node: Program_N):
        """Process statements in gauge block."""
        for i, stmt in enumerate(node.stmts):
            node.stmts[i] = self.visit(stmt, ast_root_node)
        return node
    
    def visitGeometryBlock_N(self, node: GeometryBlock_N, ast_root_node: Program_N):
        """Process statements in geometry block."""
        for i, stmt in enumerate(node.stmts):
            node.stmts[i] = self.visit(stmt, ast_root_node)
        return node
    
    # Pass-through for blocks that don't contain expressions
    
    def visitLatticesBlock_N(self, node: LatticesBlock_N, ast_root_node: Program_N):
        """Lattices block may contain expressions in lattice instantiation."""
        for i, stmt in enumerate(node.stmts):
            node.stmts[i] = self.visit(stmt, ast_root_node)
        return node
    
    def visitNodeClassesBlock_N(self, node: NodeClassesBlock_N, ast_root_node: Program_N):
        """Node classes block doesn't contain expressions to fold."""
        return node
    
    # Statement processing
    
    def visitConstantDefinitionStmt_N(self, node: ConstantDefinitionStmt_N, ast_root_node: Program_N):
        """Fold expressions in constant definitions."""
        node.value = self.visit(node.value, ast_root_node)
        return node
    
    def visitVariableAssignmentStmt_N(self, node: VariableAssignmentStmt_N, ast_root_node: Program_N):
        """Fold expressions in variable assignments."""
        node.lhs = self.visit(node.lhs, ast_root_node)
        node.rhs = self.visit(node.rhs, ast_root_node)
        return node
    
    def visitLatticeOutSelectionAssignmentStmt_N(self, node: LatticeOutSelectionAssignmentStmt_N, ast_root_node: Program_N):
        """Fold expressions in lattice assignments."""
        node.lhs = self.visit(node.lhs, ast_root_node)
        node.rhs = self.visit(node.rhs, ast_root_node)
        return node
    
    def visitArraySelectionAssignmentStmt_N(self, node: ArraySelectionAssignmentStmt_N, ast_root_node: Program_N):
        """Fold expressions in array assignments."""
        node.lhs = self.visit(node.lhs, ast_root_node)
        node.rhs = self.visit(node.rhs, ast_root_node)
        return node
    
    def visitLatticeInstaStmt_N(self, node: LatticeInstaStmt_N, ast_root_node: Program_N):
        """Fold expressions in lattice instantiation."""
        if node.d is not None:
            node.d = self.visit(node.d, ast_root_node)
        if node.q is not None:
            node.q = self.visit(node.q, ast_root_node)
        if hasattr(node, 'grid_size') and node.grid_size is not None:
            node.grid_size = self.visit(node.grid_size, ast_root_node)
        if hasattr(node, 'periodicity') and node.periodicity is not None:
            node.periodicity = self.visit(node.periodicity, ast_root_node)
        return node
    
    def visitPaintNodesStmt_N(self, node: PaintNodesStmt_N, ast_root_node: Program_N):
        """Process paint statements."""
        if node.lhs is not None:
            node.lhs = self.visit(node.lhs, ast_root_node)
        return node
    
    def visitRange_N(self, node: Range_N, ast_root_node: Program_N):
        """Fold expressions in range bounds."""
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
    
    # Array literals
    
    def visitArray1DLiteral_N(self, node: Array1DLiteral_N, ast_root_node: Program_N):
        """Fold expressions in 1D array literals."""
        return self._handle_array_literal(node, ast_root_node)
    
    def visitArray2DLiteral_N(self, node: Array2DLiteral_N, ast_root_node: Program_N):
        """Fold expressions in 2D array literals."""
        return self._handle_array_literal(node, ast_root_node)
    
    def visitArray3DLiteral_N(self, node: Array3DLiteral_N, ast_root_node: Program_N):
        """Fold expressions in 3D array literals."""
        return self._handle_array_literal(node, ast_root_node)
    
    def visitArray4DLiteral_N(self, node: Array4DLiteral_N, ast_root_node: Program_N):
        """Fold expressions in 4D array literals."""
        return self._handle_array_literal(node, ast_root_node)
    
    def _handle_array_literal(self, node, ast_root_node):
        """Fold expressions within array literals."""
        if hasattr(node, 'value') and hasattr(node.value, 'elements'):
            for i, elem in enumerate(node.value.elements):
                node.value.elements[i] = self.visit(elem, ast_root_node)
        return node
    
    # Terminal nodes (no folding needed)
    
    def visitIntLiteral_N(self, node: IntLiteral_N, ast_root_node: Program_N):
        """Integer literals are already constants."""
        return node
    
    def visitRealLiteral_N(self, node: RealLiteral_N, ast_root_node: Program_N):
        """Real literals are already constants."""
        return node
    
    def visitBoolLiteral_N(self, node: BoolLiteral_N, ast_root_node: Program_N):
        """Boolean literals are already constants."""
        return node
    
    def visitStringLiteral_N(self, node: StringLiteral_N, ast_root_node: Program_N):
        """String literals are already constants."""
        return node
    
    def visitIdentifier_N(self, node: Identifier_N, ast_root_node: Program_N):
        """Replace constant identifiers with their literal values for constant propagation."""
        # Check if this identifier refers to a constant
        if hasattr(self, 'current_block') and self.current_block is not None:
            symbol_table = getattr(self.current_block, 'symbol_defs', None)
            if symbol_table:
                symbol_def = symbol_table.get_symbol_definition(node.name)
                # Try parent table if not found locally
                if symbol_def is None and hasattr(symbol_table, 'parent_table') and symbol_table.parent_table:
                    symbol_def = symbol_table.parent_table.get_symbol_definition(node.name)
                
                # If it's a constant, return its value
                if symbol_def and symbol_def.tag in ['constant', 'constant definition']:
                    const_stmt = symbol_def.value
                    if hasattr(const_stmt, 'value') and isinstance(const_stmt.value, (IntLiteral_N, RealLiteral_N, BoolLiteral_N)):
                        # Clone the literal to avoid shared references
                        # Keep the original identifier's code range for error reporting
                        if isinstance(const_stmt.value, IntLiteral_N):
                            new_literal = IntLiteral_N(node.code_range, const_stmt.value.value)
                            new_literal.inferred_type = const_stmt.value.inferred_type if hasattr(const_stmt.value, 'inferred_type') else None
                            return new_literal
                        elif isinstance(const_stmt.value, RealLiteral_N):
                            new_literal = RealLiteral_N(node.code_range, const_stmt.value.value)
                            new_literal.inferred_type = const_stmt.value.inferred_type if hasattr(const_stmt.value, 'inferred_type') else None
                            return new_literal
                        elif isinstance(const_stmt.value, BoolLiteral_N):
                            new_literal = BoolLiteral_N(node.code_range, const_stmt.value.value)
                            new_literal.inferred_type = const_stmt.value.inferred_type if hasattr(const_stmt.value, 'inferred_type') else None
                            return new_literal
        
        # Not a constant or can't be resolved - return as is
        return node
    
    def visitVariableDeclarationStmt_N(self, node: VariableDeclarationStmt_N, ast_root_node: Program_N):
        """Variable declarations don't have expressions to fold."""
        return node
    
    def visitRectSelOfLatticeInDFs_N(self, node: RectSelOfLatticeInDFs_N, ast_root_node: Program_N):
        """Lattice selections don't contain expressions to fold."""
        return node
    
    def visitRectSelOfLatticeOutDFs_N(self, node: RectSelOfLatticeOutDFs_N, ast_root_node: Program_N):
        """Lattice selections don't contain expressions to fold."""
        return node
    
    def visitRectSelOfArrayElems_N(self, node: RectSelOfArrayElems_N, ast_root_node: Program_N):
        """Array selections don't contain expressions to fold."""
        return node
    
    # Type promotion nodes
    
    def visitTypePromotionNode_N(self, node: TypePromotionNode_N, ast_root_node: Program_N):
        """
        Fold the wrapped expression in type promotion nodes.
        
        This allows constant folding to work through type promotions,
        enabling promotion expansion to work more effectively.
        """
        node.expr = self.visit(node.expr, ast_root_node)
        return node
    
    def visitBroadcastNode_N(self, node: BroadcastNode_N, ast_root_node: Program_N):
        """
        Fold the scalar expression in broadcast nodes.
        
        Broadcasting itself cannot be folded (it's a runtime operation),
        but we can fold the scalar expression being broadcast.
        """
        node.scalar_expr = self.visit(node.scalar_expr, ast_root_node)
        return node
    
    # Helper methods for boolean conversion
    
    def _string_to_bool(self, string_value):
        """Convert GeLB boolean string to Python boolean."""
        if string_value == 'true':
            return True
        elif string_value == 'false':
            return False
        else:
            raise ValueError(f"Invalid boolean string: {string_value}")
    
    def _bool_to_string(self, bool_value):
        """Convert Python boolean to GeLB boolean string."""
        return 'true' if bool_value else 'false'