#!/usr/bin/env python3

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.frontend.visitor_mixins import ProgramTraversalMixin
from gelb.gelb_ast.ASTNodes import *
from gelb.utils.exceptions import GeLBExTypeError


class TypeValidationVisitor(ASTBaseVisitor, ProgramTraversalMixin):
    """
    Validates type compatibility in operations and assignments.
    Must run after TypeInferenceVisitor and TypePromotionVisitor.
    
    This visitor checks that all operations have type-compatible operands
    after promotions have been applied. It does not modify the AST.
    """
    
    def __init__(self):
        super().__init__()
        self.validation_rules = self._build_validation_rules()
    
    def _build_validation_rules(self):
        """
        Define what operations are valid on what types.
        Returns a dict mapping operation categories to allowed types.
        """
        return {
            'arithmetic': {'int', 'real'},  # Only numeric types
            'comparison': {'int', 'real', 'bool', 'string'},  # All types can be compared
            'logical': {'bool'},  # Only bool
            'unary_minus': {'int', 'real'},  # Only numeric
            'logical_not': {'bool'},  # Only bool
        }
    
    def _get_type_name(self, data_type):
        """Extract type name from ArrayDataType_N or string."""
        if isinstance(data_type, ArrayDataType_N):
            # Return just the base type for validation purposes
            # Shape compatibility would be checked separately if needed
            return data_type.element_dtype
        elif isinstance(data_type, str):
            return data_type
        else:
            return str(type(data_type).__name__)
    
    def _types_match(self, type1, type2):
        """Check if two types match exactly."""
        # For array types, we need to check both base type and shape
        if isinstance(type1, ArrayDataType_N) and isinstance(type2, ArrayDataType_N):
            # Check base types match
            if type1.element_dtype != type2.element_dtype:
                return False
            # Check shape compatibility
            return self._shapes_match(type1.shape, type2.shape)
        else:
            # Fallback to name comparison
            name1 = self._get_type_name(type1)
            name2 = self._get_type_name(type2)
            return name1 == name2
    
    def _shapes_match(self, shape1, shape2):
        """Check if two shapes match exactly."""
        # Handle List_N shapes (0D and 2D+)
        if isinstance(shape1, List_N) and isinstance(shape2, List_N):
            if len(shape1.elements) != len(shape2.elements):
                return False
            # For now, assume shapes match if they have the same number of dimensions
            # A more sophisticated implementation would check dimension values
            return True
        
        # Handle 1D shapes (IntLiteral_N or Identifier_N)
        elif isinstance(shape1, (IntLiteral_N, Identifier_N)) and isinstance(shape2, (IntLiteral_N, Identifier_N)):
            # Both are 1D arrays - for now assume they match
            # A more sophisticated implementation would check dimension values
            return True
        
        # Handle Array1DLiteral_N shapes (2D+)
        elif isinstance(shape1, Array1DLiteral_N) and isinstance(shape2, Array1DLiteral_N):
            return self._shapes_match(shape1.value, shape2.value)
        
        # Different shape types - no match
        else:
            return False
    
    def _is_scalar_array(self, array_type):
        """Check if an ArrayDataType_N represents a scalar (0-dimensional)."""
        if not isinstance(array_type, ArrayDataType_N):
            return False
        # Check if shape represents 0 dimensions
        if isinstance(array_type.shape, List_N):
            return len(array_type.shape.elements) == 0
        else:
            # Non-List_N shapes (IntLiteral_N, Identifier_N, Array1DLiteral_N) represent non-scalar arrays
            return False
    
    def _validate_arithmetic_op(self, left_type, right_type, op_name, node):
        """
        Validate arithmetic operation compatibility.
        After promotion, both operands should have the same numeric type.
        """
        left_name = self._get_type_name(left_type)
        right_name = self._get_type_name(right_type)
        
        # Check if both types are numeric
        allowed_types = self.validation_rules['arithmetic']
        if left_name not in allowed_types:
            raise GeLBExTypeError(
                node.left,
                f"Left operand of {op_name} has non-numeric type '{left_name}'",
                f"Arithmetic operations require numeric types (int or real)"
            )
        
        if right_name not in allowed_types:
            raise GeLBExTypeError(
                node.right,
                f"Right operand of {op_name} has non-numeric type '{right_name}'",
                f"Arithmetic operations require numeric types (int or real)"
            )
        
        # Array arithmetic is allowed - shape compatibility is handled by TypePromotionVisitor
        # This includes:
        # - scalar + scalar (both are 0-dimensional arrays)
        # - array + scalar (broadcasting)
        # - scalar + array (broadcasting)
        # - array + array (if shapes are compatible)
        
        # Type promotion will handle shape broadcasting and type conversion
        # We've already validated that both operands have numeric element types
        return True
    
    def _validate_comparison_op(self, left_type, right_type, op_name, node):
        """
        Validate comparison operation compatibility.
        After promotion, both operands should have the same type.
        """
        left_name = self._get_type_name(left_type)
        right_name = self._get_type_name(right_type)
        
        # After promotion, types should match
        if not self._types_match(left_type, right_type):
            raise GeLBExTypeError(
                node,
                f"Type mismatch in {op_name}: '{left_name}' and '{right_name}'",
                f"Comparison requires operands of the same type"
            )
        
        return True
    
    def _validate_logical_op(self, left_type, right_type, op_name, node):
        """
        Validate logical operation compatibility.
        Both operands must be bool.
        """
        left_name = self._get_type_name(left_type)
        right_name = self._get_type_name(right_type)
        
        allowed_types = self.validation_rules['logical']
        if left_name not in allowed_types:
            raise GeLBExTypeError(
                node.left,
                f"Left operand of {op_name} has type '{left_name}', expected 'bool'",
                f"Logical operations require boolean operands"
            )
        
        if right_name not in allowed_types:
            raise GeLBExTypeError(
                node.right,
                f"Right operand of {op_name} has type '{right_name}', expected 'bool'",
                f"Logical operations require boolean operands"
            )
        
        return True
    
    def _validate_assignment(self, lhs_type, rhs_type, node):
        """
        Validate assignment compatibility.
        After promotion, RHS type should match LHS type.
        """
        lhs_name = self._get_type_name(lhs_type)
        rhs_name = self._get_type_name(rhs_type)
        
        # After promotion, types should match
        if not self._types_match(lhs_type, rhs_type):
            raise GeLBExTypeError(
                node,
                f"Cannot assign '{rhs_name}' to '{lhs_name}'",
                f"Assignment requires compatible types"
            )
        
        return True
    
    # Program traversal
    
    def visitProgram_N(self, node: Program_N, ast_root_node: Program_N):
        """Visit all blocks in the program to validate types."""
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
        """Validate addition operation."""
        self._validate_arithmetic_operation(node, ast_root_node, "addition")
        return node
    
    def visitSub_N(self, node: Sub_N, ast_root_node: Program_N):
        """Validate subtraction operation."""
        self._validate_arithmetic_operation(node, ast_root_node, "subtraction")
        return node
    
    def visitMul_N(self, node: Mul_N, ast_root_node: Program_N):
        """Validate multiplication operation."""
        self._validate_arithmetic_operation(node, ast_root_node, "multiplication")
        return node
    
    def visitDiv_N(self, node: Div_N, ast_root_node: Program_N):
        """Validate division operation."""
        self._validate_arithmetic_operation(node, ast_root_node, "division")
        return node
    
    def visitPow_N(self, node: Pow_N, ast_root_node: Program_N):
        """Validate exponentiation operation."""
        self._validate_arithmetic_operation(node, ast_root_node, "exponentiation")
        return node
    
    def _validate_arithmetic_operation(self, node, ast_root_node, op_name):
        """Helper to validate arithmetic binary operations."""
        # Visit children first
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        
        # Validate types
        if not hasattr(node.left, 'inferred_type') or not hasattr(node.right, 'inferred_type'):
            raise GeLBExTypeError(node.code_range, f"Type validation requires type inference to run first", "Internal compiler error")
        
        left_type = node.left.inferred_type
        right_type = node.right.inferred_type
        
        self._validate_arithmetic_op(left_type, right_type, op_name, node)
    
    # Comparison operations
    
    def visitLess_N(self, node: Less_N, ast_root_node: Program_N):
        """Validate less-than comparison."""
        self._validate_comparison_operation(node, ast_root_node, "less-than")
        return node
    
    def visitGreater_N(self, node: Greater_N, ast_root_node: Program_N):
        """Validate greater-than comparison."""
        self._validate_comparison_operation(node, ast_root_node, "greater-than")
        return node
    
    def visitLessEqual_N(self, node: LessEqual_N, ast_root_node: Program_N):
        """Validate less-equal comparison."""
        self._validate_comparison_operation(node, ast_root_node, "less-equal")
        return node
    
    def visitGreaterEqual_N(self, node: GreaterEqual_N, ast_root_node: Program_N):
        """Validate greater-equal comparison."""
        self._validate_comparison_operation(node, ast_root_node, "greater-equal")
        return node
    
    def visitEqual_N(self, node: Equal_N, ast_root_node: Program_N):
        """Validate equality comparison."""
        self._validate_comparison_operation(node, ast_root_node, "equality")
        return node
    
    def visitNotEqual_N(self, node: NotEqual_N, ast_root_node: Program_N):
        """Validate not-equal comparison."""
        self._validate_comparison_operation(node, ast_root_node, "not-equal")
        return node
    
    def _validate_comparison_operation(self, node, ast_root_node, op_name):
        """Helper to validate comparison operations."""
        # Visit children first
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        
        # Validate types
        if not hasattr(node.left, 'inferred_type') or not hasattr(node.right, 'inferred_type'):
            raise GeLBExTypeError(node.code_range, f"Type validation requires type inference to run first", "Internal compiler error")
        
        left_type = node.left.inferred_type
        right_type = node.right.inferred_type
        
        self._validate_comparison_op(left_type, right_type, op_name, node)
    
    # Logical operations
    
    def visitAnd_N(self, node: And_N, ast_root_node: Program_N):
        """Validate logical AND operation."""
        self._validate_logical_operation(node, ast_root_node, "logical AND")
        return node
    
    def visitOr_N(self, node: Or_N, ast_root_node: Program_N):
        """Validate logical OR operation."""
        self._validate_logical_operation(node, ast_root_node, "logical OR")
        return node
    
    def _validate_logical_operation(self, node, ast_root_node, op_name):
        """Helper to validate logical operations."""
        # Visit children first
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        
        # Validate types
        if not hasattr(node.left, 'inferred_type') or not hasattr(node.right, 'inferred_type'):
            raise GeLBExTypeError(node.code_range, f"Type validation requires type inference to run first", "Internal compiler error")
        
        left_type = node.left.inferred_type
        right_type = node.right.inferred_type
        
        self._validate_logical_op(left_type, right_type, op_name, node)
    
    # Unary operations
    
    def visitNotExpr_N(self, node: NotExpr_N, ast_root_node: Program_N):
        """Validate logical NOT operation."""
        # Visit child first
        self.visit(node.value, ast_root_node)
        
        # Validate type
        if not hasattr(node.value, 'inferred_type'):
            raise GeLBExTypeError(node.code_range, f"Type validation requires type inference to run first", "Internal compiler error")
        
        expr_type = node.value.inferred_type
        expr_name = self._get_type_name(expr_type)
        
        allowed_types = self.validation_rules['logical_not']
        if expr_name not in allowed_types:
            raise GeLBExTypeError(
                node.value,
                f"Operand of logical NOT has type '{expr_name}', expected 'bool'",
                f"Logical NOT requires a boolean operand"
            )
        
        return node
    
    def visitUnaryMinusExpr_N(self, node: UnaryMinusExpr_N, ast_root_node: Program_N):
        """Validate unary minus operation."""
        # Visit child first
        self.visit(node.value, ast_root_node)
        
        # Validate type
        if not hasattr(node.value, 'inferred_type'):
            raise GeLBExTypeError(node.code_range, f"Type validation requires type inference to run first", "Internal compiler error")
        
        expr_type = node.value.inferred_type
        expr_name = self._get_type_name(expr_type)
        
        allowed_types = self.validation_rules['unary_minus']
        if expr_name not in allowed_types:
            raise GeLBExTypeError(
                node.value,
                f"Operand of unary minus has type '{expr_name}'",
                f"Unary minus requires a numeric operand (int or real)"
            )
        
        return node
    
    # Assignment validation
    
    def visitVariableAssignmentStmt_N(self, node: VariableAssignmentStmt_N, ast_root_node: Program_N):
        """Validate variable assignment."""
        self._validate_assignment_stmt(node, ast_root_node)
        return node
    
    def visitConstantDefinitionStmt_N(self, node: ConstantDefinitionStmt_N, ast_root_node: Program_N):
        """Validate constant definition."""
        # Visit the value expression
        self.visit(node.value, ast_root_node)
        
        # Validate type compatibility
        if not hasattr(node.value, 'inferred_type'):
            raise GeLBExTypeError(node.code_range, f"Type validation requires type inference to run first", "Internal compiler error")
        
        value_type = node.value.inferred_type
        declared_type = node.data_type
        
        # After promotion, types should match
        if not self._types_match(declared_type, value_type):
            declared_name = self._get_type_name(declared_type)
            value_name = self._get_type_name(value_type)
            raise GeLBExTypeError(f"Constant '{node.name}' declared as '{declared_name}' but initialized with '{value_name}' at {node.code_range}", f"Constant initialization type must match declared type")
        
        return node
    
    def visitLatticeOutSelectionAssignmentStmt_N(self, node: LatticeOutSelectionAssignmentStmt_N, ast_root_node: Program_N):
        """Validate lattice assignment."""
        self._validate_assignment_stmt(node, ast_root_node)
        return node
    
    def visitArraySelectionAssignmentStmt_N(self, node: ArraySelectionAssignmentStmt_N, ast_root_node: Program_N):
        """Validate array assignment."""
        self._validate_assignment_stmt(node, ast_root_node)
        return node
    
    def _validate_assignment_stmt(self, node, ast_root_node):
        """Helper to validate assignment statements."""
        # Visit both sides
        self.visit(node.lhs, ast_root_node)
        self.visit(node.rhs, ast_root_node)
        
        # Validate types
        if not hasattr(node.lhs, 'inferred_type') or not hasattr(node.rhs, 'inferred_type'):
            raise GeLBExTypeError(node.code_range, f"Type validation requires type inference to run first", "Internal compiler error")
        
        lhs_type = node.lhs.inferred_type
        rhs_type = node.rhs.inferred_type
        
        # Compare the full types (including shapes)
        self._validate_assignment(lhs_type, rhs_type, node)
    
    # Block traversal
    
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
    
    # Pass-through for nodes without type checking
    
    def visitLatticesBlock_N(self, node: LatticesBlock_N, ast_root_node: Program_N):
        """Lattices block doesn't need type validation."""
        return node
    
    def visitNodeClassesBlock_N(self, node: NodeClassesBlock_N, ast_root_node: Program_N):
        """Node classes block doesn't need type validation."""
        return node
    
    # Literals and identifiers (terminals)
    
    def visitIntLiteral_N(self, node: IntLiteral_N, ast_root_node: Program_N):
        """Integer literals are always valid."""
        return node
    
    def visitRealLiteral_N(self, node: RealLiteral_N, ast_root_node: Program_N):
        """Real literals are always valid."""
        return node
    
    def visitBoolLiteral_N(self, node: BoolLiteral_N, ast_root_node: Program_N):
        """Boolean literals are always valid."""
        return node
    
    def visitStringLiteral_N(self, node: StringLiteral_N, ast_root_node: Program_N):
        """String literals are always valid."""
        return node
    
    def visitIdentifier_N(self, node: Identifier_N, ast_root_node: Program_N):
        """Identifiers are validated during type inference."""
        return node
    
    def visitTypePromotionNode_N(self, node: TypePromotionNode_N, ast_root_node: Program_N):
        """Type promotion nodes are always valid (created by TypePromotionVisitor)."""
        # Visit the wrapped expression
        self.visit(node.expr, ast_root_node)
        return node
    
    def visitBroadcastNode_N(self, node: BroadcastNode_N, ast_root_node: Program_N):
        """Broadcast nodes are always valid (created by TypePromotionVisitor)."""
        # Visit the wrapped scalar expression
        self.visit(node.scalar_expr, ast_root_node)
        return node
    
    # Array literals
    
    def visitArray1DLiteral_N(self, node: Array1DLiteral_N, ast_root_node: Program_N):
        """Validate array literal elements."""
        return self._validate_array_literal(node, ast_root_node)
    
    def visitArray2DLiteral_N(self, node: Array2DLiteral_N, ast_root_node: Program_N):
        """Validate array literal elements."""
        return self._validate_array_literal(node, ast_root_node)
    
    def visitArray3DLiteral_N(self, node: Array3DLiteral_N, ast_root_node: Program_N):
        """Validate array literal elements."""
        return self._validate_array_literal(node, ast_root_node)
    
    def visitArray4DLiteral_N(self, node: Array4DLiteral_N, ast_root_node: Program_N):
        """Validate array literal elements."""
        return self._validate_array_literal(node, ast_root_node)
    
    def _validate_array_literal(self, node, ast_root_node):
        """
        Validate that all elements in array literal have same type.
        After promotion, all elements should have been promoted to common type.
        """
        # Visit all elements
        if hasattr(node, 'value') and hasattr(node.value, 'elements'):
            for elem in node.value.elements:
                self.visit(elem, ast_root_node)
            
            # After promotion, all elements should have same type
            if len(node.value.elements) > 1 and hasattr(node, 'inferred_type'):
                expected_type = None
                if isinstance(node.inferred_type, ArrayDataType_N):
                    expected_type = node.inferred_type.element_dtype
                
                # Check all elements match expected type
                for i, elem in enumerate(node.value.elements):
                    if hasattr(elem, 'inferred_type'):
                        elem_type_name = self._get_type_name(elem.inferred_type)
                        if expected_type and elem_type_name != expected_type:
                            raise GeLBExTypeError(
                                f"Array element at index {i} has type '{elem_type_name}', expected '{expected_type}' at {elem.code_range}",
                                f"All array elements must have the same type"
                            )
        
        return node
    
    # Other nodes
    
    def visitPaintNodesStmt_N(self, node: PaintNodesStmt_N, ast_root_node: Program_N):
        """Paint statements don't involve type checking."""
        if node.lhs is not None:
            self.visit(node.lhs, ast_root_node)
        return node
    
    def visitRange_N(self, node: Range_N, ast_root_node: Program_N):
        """Process range bounds."""
        if node.low is not None:
            self.visit(node.low, ast_root_node)
        if node.high is not None:
            self.visit(node.high, ast_root_node)
        return node
    
    def visitList_N(self, node: List_N, ast_root_node: Program_N):
        """Process all elements in a list."""
        for elem in node.elements:
            self.visit(elem, ast_root_node)
        return node
    
    def visitRectSelOfLatticeInDFs_N(self, node: RectSelOfLatticeInDFs_N, ast_root_node: Program_N):
        """Lattice selections are validated during type inference."""
        return node
    
    def visitRectSelOfLatticeOutDFs_N(self, node: RectSelOfLatticeOutDFs_N, ast_root_node: Program_N):
        """Lattice selections are validated during type inference."""
        return node
    
    def visitRectSelOfArrayElems_N(self, node: RectSelOfArrayElems_N, ast_root_node: Program_N):
        """Array selections are validated during type inference."""
        return node
    
    def visitVariableDeclarationStmt_N(self, node: VariableDeclarationStmt_N, ast_root_node: Program_N):
        """Variable declarations don't need type validation."""
        return node
    
    def visitLatticeInstaStmt_N(self, node: LatticeInstaStmt_N, ast_root_node: Program_N):
        """Process expressions in lattice instantiation."""
        # Visit dimension and q parameters if they are expressions
        if node.d is not None:
            self.visit(node.d, ast_root_node)
        if node.q is not None:
            self.visit(node.q, ast_root_node)
        
        # Visit grid_size and periodicity if present
        if hasattr(node, 'grid_size') and node.grid_size is not None:
            self.visit(node.grid_size, ast_root_node)
        if hasattr(node, 'periodicity') and node.periodicity is not None:
            self.visit(node.periodicity, ast_root_node)
        
        return node