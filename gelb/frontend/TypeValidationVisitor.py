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
        _numeric = {'int', 'int8', 'int16', 'int32', 'int64',
                    'real', 'real16', 'real32', 'real64'}
        return {
            'arithmetic': _numeric,
            'comparison': _numeric | {'bool', 'string'},
            'logical': {'bool'},
            'unary_minus': _numeric,
            'logical_not': {'bool'},
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

    def _require_inferred_type(self, typed_node, error_node):
        """Return ``typed_node.inferred_type`` or raise the standard guard."""
        if (not hasattr(typed_node, 'inferred_type')
                or typed_node.inferred_type is None):
            raise GeLBExTypeError(
                error_node.code_range,
                "Type validation requires type inference to run first",
                "Internal compiler error")
        return typed_node.inferred_type
    
    def _get_user_friendly_type_description(self, data_type):
        """Create user-friendly type description for error messages."""
        if isinstance(data_type, ArrayDataType_N):
            element_type = data_type.element_dtype
            shape = data_type.shape
            
            # Check if it's a scalar (0-dimensional array)
            if isinstance(shape, List_N) and len(shape.elements) == 0:
                return f"scalar '{element_type}'"
            
            # Build shape description
            if isinstance(shape, List_N):
                if len(shape.elements) == 0:
                    # 0D - scalar
                    return f"scalar '{element_type}'"
                else:
                    # Multi-dimensional array from List_N
                    shape_str = ", ".join(str(elem.value) if hasattr(elem, 'value') else str(elem) 
                                        for elem in shape.elements)
                    return f"array[{element_type}, {{{shape_str}}}]"
            elif isinstance(shape, IntLiteral_N):
                # 1D array
                return f"array[{element_type}, {shape.value}]"
            elif isinstance(shape, Array1DLiteral_N):
                # 2D+ array
                shape_elements = []
                for elem in shape.value.elements:
                    if hasattr(elem, 'value'):
                        shape_elements.append(str(elem.value))
                    else:
                        shape_elements.append(str(elem))
                shape_str = ", ".join(shape_elements)
                return f"array[{element_type}, {{{shape_str}}}]"
            else:
                # Unknown shape format, fallback
                return f"array[{element_type}, ?]"
        elif isinstance(data_type, str):
            return f"'{data_type}'"
        else:
            return str(type(data_type).__name__)
    
    _REAL_FAMILY = {'real', 'real16', 'real32', 'real64'}

    def _types_match(self, type1, type2):
        """Check if two types match (exact or same-family real precision)."""
        # For array types, we need to check both base type and shape
        if isinstance(type1, ArrayDataType_N) and isinstance(type2, ArrayDataType_N):
            # Check base types match (allow same-family real conversions)
            if type1.element_dtype != type2.element_dtype:
                if not (type1.element_dtype in self._REAL_FAMILY
                        and type2.element_dtype in self._REAL_FAMILY):
                    return False
            # Check shape compatibility
            return self._shapes_match(type1.shape, type2.shape)
        else:
            # Fallback to name comparison
            name1 = self._get_type_name(type1)
            name2 = self._get_type_name(type2)
            if name1 == name2:
                return True
            return (name1 in self._REAL_FAMILY
                    and name2 in self._REAL_FAMILY)
    
    def _shapes_match(self, shape1, shape2):
        """Check if two shapes match.

        Shape representations in the AST:
        - Scalar (0D): List_N with 0 elements
        - 1D array:    IntLiteral_N(size) [normalized] or List_N([IntLiteral_N(size)]) [denormalized]
        - 2D+ array:   Array1DLiteral_N or List_N with multiple elements

        Normalized and denormalized forms of the same 1D shape must compare as equal.
        """
        # Normalize both shapes to a canonical form for comparison
        ndims1, sizes1 = self._extract_shape_dims(shape1)
        ndims2, sizes2 = self._extract_shape_dims(shape2)

        if ndims1 != ndims2:
            return False
        # Sizes are compared where both are known integers; a symbolic
        # size (identifier, expression) is accepted against anything.
        for s1, s2 in zip(sizes1, sizes2):
            if (isinstance(s1, IntLiteral_N) and isinstance(s2, IntLiteral_N)
                    and s1.value != s2.value):
                return False
        return True

    def _shape_text(self, data_type):
        """``[3]``, ``[2, 2]`` or ``scalar`` for error messages."""
        if not isinstance(data_type, ArrayDataType_N):
            return "scalar"
        ndims, sizes = self._extract_shape_dims(data_type.shape)
        if ndims == 0:
            return "scalar"
        return "[" + ", ".join(
            str(s.value) if isinstance(s, IntLiteral_N) else "?"
            for s in sizes) + "]"

    def _same_base_type(self, type1, type2):
        """True when only the shapes can differ between two array types."""
        if not (isinstance(type1, ArrayDataType_N)
                and isinstance(type2, ArrayDataType_N)):
            return False
        if type1.element_dtype == type2.element_dtype:
            return True
        return (type1.element_dtype in self._REAL_FAMILY
                and type2.element_dtype in self._REAL_FAMILY)

    @staticmethod
    def _extract_shape_dims(shape):
        """Extract dimensionality info from a shape node.

        Returns (ndims, sizes_list_or_none).
        """
        if isinstance(shape, List_N):
            return (len(shape.elements), shape.elements)
        elif isinstance(shape, IntLiteral_N):
            # Normalized 1D: IntLiteral_N(size) -> 1 dimension
            return (1, [shape])
        elif isinstance(shape, Identifier_N):
            # Symbolic 1D size
            return (1, [shape])
        elif isinstance(shape, Array1DLiteral_N):
            return (len(shape.value.elements), shape.value.elements)
        else:
            return (0, [])
    
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
        Enforces strict rules for array/scalar operations to prevent mathematically ambiguous operations.
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
        
        # Check array/scalar operation validity
        left_is_scalar = self._is_scalar_array(left_type)
        right_is_scalar = self._is_scalar_array(right_type)
        
        # Allow scalar op scalar
        if left_is_scalar and right_is_scalar:
            return True
        
        # Allow array op scalar for all operations (mathematically clear)
        if not left_is_scalar and right_is_scalar:
            return True
        
        # Allow scalar op array for all operations (element-wise broadcast)
        if left_is_scalar and not right_is_scalar:
            return True
        
        # Allow array op array when shapes are compatible (element-wise)
        if not left_is_scalar and not right_is_scalar:
            if not self._shapes_match(left_type.shape, right_type.shape):
                raise GeLBExTypeError(
                    node,
                    f"Cannot perform array {op_name} by array: incompatible shapes",
                    f"Element-wise array operations require arrays of the same shape"
                )
            return True
        
        return True
    
    # The ordering comparisons, by the name the visits pass.  Booleans
    # have no order in GeLB: ``a < b`` on two bools type-checked and
    # reached gfortran, which has no ``<`` on logicals; it is a type
    # error here, on every backend (user manual, Numerical semantics:
    # Types and promotion).
    _ORDERING_OPS = {
        "less-than": "<", "greater-than": ">",
        "less-equal": "<=", "greater-equal": ">=",
    }

    def _validate_comparison_op(self, left_type, right_type, op_name, node):
        """
        Validate comparison operation compatibility.
        After promotion, both operands should have the same type; an
        ordering comparison needs a numeric type.
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

        symbol = self._ORDERING_OPS.get(op_name)
        if symbol is not None and 'bool' in (left_name, right_name):
            raise GeLBExTypeError(
                node,
                f"Boolean values have no order: '{symbol}' on bool operands",
                "Booleans compare with == and != only.  To order them as "
                "0 and 1, convert first: int(a) < int(b)."
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
        # After promotion, types should match
        if not self._types_match(lhs_type, rhs_type):
            # Use user-friendly type descriptions for error messages
            lhs_desc = self._get_user_friendly_type_description(lhs_type)
            rhs_desc = self._get_user_friendly_type_description(rhs_type)
            
            # Provide specific hints based on the type mismatch
            hint = self._generate_assignment_hint(lhs_type, rhs_type)
            
            raise GeLBExTypeError(
                node,
                f"Cannot assign {rhs_desc} to {lhs_desc}",
                hint
            )
        
        return True
    
    def _generate_assignment_hint(self, lhs_type, rhs_type):
        """Generate specific hint based on assignment type mismatch."""
        lhs_is_scalar = self._is_scalar_type(lhs_type)
        rhs_is_scalar = self._is_scalar_type(rhs_type)
        
        if not lhs_is_scalar and rhs_is_scalar:
            # NOTE: Scalar to array assignment is actually valid (handled by broadcasting)
            # This case should not occur after type promotion, but if it does:
            return "Scalar to array assignment should be handled by type promotion with broadcasting"
        elif lhs_is_scalar and not rhs_is_scalar:
            # Trying to assign array to scalar - the main case we're fixing
            return "Scalars cannot hold array values. Use array indexing like 'array[0, 1]' to get a single element"
        elif not lhs_is_scalar and not rhs_is_scalar:
            # Array to array with shape mismatch
            return "Arrays must have compatible shapes for assignment"
        else:
            # Both scalars but different base types (shouldn't happen after promotion)
            return "Assignment requires compatible types"
    
    def _is_scalar_type(self, data_type):
        """Check if a type represents a scalar (0-dimensional array)."""
        if isinstance(data_type, ArrayDataType_N):
            shape = data_type.shape
            if isinstance(shape, List_N):
                return len(shape.elements) == 0
            else:
                # Non-List_N shapes are for 1D+ arrays
                return False
        return True  # Non-ArrayDataType_N are treated as scalars
    
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
        self._validate_binary_operation(
            node, ast_root_node, "addition", self._validate_arithmetic_op)
        return node
    
    def visitSub_N(self, node: Sub_N, ast_root_node: Program_N):
        """Validate subtraction operation."""
        self._validate_binary_operation(
            node, ast_root_node, "subtraction", self._validate_arithmetic_op)
        return node
    
    def visitMul_N(self, node: Mul_N, ast_root_node: Program_N):
        """Validate multiplication operation."""
        self._validate_binary_operation(
            node, ast_root_node, "multiplication",
            self._validate_arithmetic_op)
        return node
    
    def visitDiv_N(self, node: Div_N, ast_root_node: Program_N):
        """Validate division operation."""
        self._validate_binary_operation(
            node, ast_root_node, "division", self._validate_arithmetic_op)
        return node
    
    def visitPow_N(self, node: Pow_N, ast_root_node: Program_N):
        """Validate exponentiation operation."""
        self._validate_binary_operation(
            node, ast_root_node, "exponentiation",
            self._validate_arithmetic_op)
        return node
    
    # Comparison operations
    
    def visitLess_N(self, node: Less_N, ast_root_node: Program_N):
        """Validate less-than comparison."""
        self._validate_binary_operation(
            node, ast_root_node, "less-than", self._validate_comparison_op)
        return node
    
    def visitGreater_N(self, node: Greater_N, ast_root_node: Program_N):
        """Validate greater-than comparison."""
        self._validate_binary_operation(
            node, ast_root_node, "greater-than", self._validate_comparison_op)
        return node
    
    def visitLessEqual_N(self, node: LessEqual_N, ast_root_node: Program_N):
        """Validate less-equal comparison."""
        self._validate_binary_operation(
            node, ast_root_node, "less-equal", self._validate_comparison_op)
        return node
    
    def visitGreaterEqual_N(self, node: GreaterEqual_N, ast_root_node: Program_N):
        """Validate greater-equal comparison."""
        self._validate_binary_operation(
            node, ast_root_node, "greater-equal",
            self._validate_comparison_op)
        return node
    
    def visitEqual_N(self, node: Equal_N, ast_root_node: Program_N):
        """Validate equality comparison."""
        self._validate_binary_operation(
            node, ast_root_node, "equality", self._validate_comparison_op)
        return node
    
    def visitNotEqual_N(self, node: NotEqual_N, ast_root_node: Program_N):
        """Validate not-equal comparison."""
        self._validate_binary_operation(
            node, ast_root_node, "not-equal", self._validate_comparison_op)
        return node
    
    # Logical operations
    
    def visitAnd_N(self, node: And_N, ast_root_node: Program_N):
        """Validate logical AND operation."""
        self._validate_binary_operation(
            node, ast_root_node, "logical AND", self._validate_logical_op)
        return node
    
    def visitOr_N(self, node: Or_N, ast_root_node: Program_N):
        """Validate logical OR operation."""
        self._validate_binary_operation(
            node, ast_root_node, "logical OR", self._validate_logical_op)
        return node
    
    def _validate_binary_operation(self, node, ast_root_node, op_name, validator):
        """Visit and validate a binary operation using ``validator``."""
        # Visit children first
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        
        left_type = self._require_inferred_type(node.left, node)
        right_type = self._require_inferred_type(node.right, node)
        
        validator(left_type, right_type, op_name, node)
    
    # Unary operations
    
    def visitNotExpr_N(self, node: NotExpr_N, ast_root_node: Program_N):
        """Validate logical NOT operation."""
        # Visit child first
        self.visit(node.value, ast_root_node)
        
        expr_type = self._require_inferred_type(node.value, node)
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
        
        expr_type = self._require_inferred_type(node.value, node)
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
        
        value_type = self._require_inferred_type(node.value, node)
        declared_type = node.data_type
        
        # After promotion, types should match
        if not self._types_match(declared_type, value_type):
            name = getattr(node.name, "name", node.name)
            if self._same_base_type(declared_type, value_type):
                raise GeLBExTypeError(
                    node,
                    f"Constant '{name}' is declared with shape "
                    f"{self._shape_text(declared_type)} but initialized with "
                    f"shape {self._shape_text(value_type)}",
                    "The initializer must have exactly the declared number "
                    "of elements in every dimension"
                )
            declared_name = self._get_type_name(declared_type)
            value_name = self._get_type_name(value_type)
            raise GeLBExTypeError(node, f"Constant '{node.name}' declared as '{declared_name}' but initialized with '{value_name}'", f"Constant initialization type must match declared type")
        
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
        
        lhs_type = self._require_inferred_type(node.lhs, node)
        rhs_type = self._require_inferred_type(node.rhs, node)
        
        # Compare the full types (including shapes)
        self._validate_assignment(lhs_type, rhs_type, node)
    
    # Block traversal
    
    def visitGlobalConstantsBlock_N(self, node: GlobalConstantsBlock_N, ast_root_node: Program_N):
        """Process statements in global constants block."""
        return self._visit_block_stmts(node, ast_root_node)
    
    def visitInitializerBlock_N(self, node: InitializerBlock_N, ast_root_node: Program_N):
        """Process statements in initializer block."""
        return self._visit_block_stmts(node, ast_root_node)
    
    def visitDynamicBlock_N(self, node: DynamicBlock_N, ast_root_node: Program_N):
        """Process statements in dynamic block."""
        return self._visit_block_stmts(node, ast_root_node)
    
    def visitGaugeBlock_N(self, node: GaugeBlock_N, ast_root_node: Program_N):
        """Process statements in gauge block."""
        return self._visit_block_stmts(node, ast_root_node)
    
    def visitGeometryBlock_N(self, node: GeometryBlock_N, ast_root_node: Program_N):
        """Process statements in geometry block."""
        return self._visit_block_stmts(node, ast_root_node)
    
    # Pass-through for nodes without type checking
    
    def visitLatticesBlock_N(self, node: LatticesBlock_N, ast_root_node: Program_N):
        """Visit lattice instantiation statements for parameter validation."""
        return self._visit_block_stmts(node, ast_root_node)
    
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
                                elem,
                                f"Array element at index {i} has type '{elem_type_name}', expected '{expected_type}'",
                                f"All array elements must have the same type"
                            )
        
        return node

    # Intrinsic function calls

    def visitIntrinsicFunctionCall_N(self, node, ast_root_node: Program_N):
        """Validate sub-expressions within intrinsic function arguments."""
        for arg in node.arguments.elements:
            self.visit(arg, ast_root_node)
        return node

    def visitUserFunctionCall_N(self, node, ast_root_node: Program_N):
        """Validate sub-expressions within user function call arguments."""
        for arg in node.arguments.elements:
            self.visit(arg, ast_root_node)
        return node

    def visitDestructuringAssignmentStmt_N(self, node, ast_root_node: Program_N):
        """Validate types in destructuring assignment.

        Two RHS shapes are accepted:

        1. ``UserFunctionCall_N`` -- multi-output function call.  The
           function must have N output parameters where N == number of
           targets.  (The grammar lets the user write
           ``{a, b} = SingleOutputFunc(x);`` which is invalid; this
           check catches it.)

        2. Any other expression -- must have a 1D-array inferred type
           whose statically-known length matches the number of targets.
           This covers array literals, array variables, lattice
           selections, etc.

        For both shapes, the result element type must be uniform --
        every target shares the same type as the array element type.
        Mixed-type destructuring (e.g. ``{int_a, real_b} = {1, 2.5};``)
        is out of scope for v1; users can apply explicit casts on the
        RHS array elements if needed.
        """
        self.visit(node.rhs, ast_root_node)

        n_targets = len(node.targets)
        rhs = node.rhs

        if isinstance(rhs, UserFunctionCall_N):
            # The function block was attached during type inference for
            # multi-output calls.  Single-output calls have inferred_type
            # set instead -- those don't make sense in a destructuring
            # context.
            func_block = getattr(rhs, 'function_block', None)
            if func_block is None:
                raise GeLBExTypeError(
                    node,
                    f"Destructuring assignment requires a multi-output "
                    f"function call, but '{rhs.function_name.name}' "
                    f"returns a single value",
                    "Use a regular assignment instead, or call a "
                    "function with multiple output parameters."
                )
            n_outputs = len(func_block.outputs.elements)
            if n_outputs != n_targets:
                raise GeLBExTypeError(
                    node,
                    f"Destructuring expects {n_outputs} target"
                    f"{'' if n_outputs == 1 else 's'} (one per output of "
                    f"'{rhs.function_name.name}'), got {n_targets}",
                    "The number of LHS targets must match the number "
                    "of function outputs."
                )
            return node

        # Non-function-call RHS: must be a 1D array of statically-known
        # length matching the number of targets.
        rhs_type = getattr(rhs, 'inferred_type', None)
        if rhs_type is None or not isinstance(rhs_type, ArrayDataType_N):
            raise GeLBExTypeError(
                node,
                "Destructuring RHS must be a multi-output function "
                "call or a 1D array expression",
                "Got an expression with no array type."
            )

        # Extract the static length of the RHS array.
        shape = rhs_type.shape
        rhs_length = None
        if isinstance(shape, IntLiteral_N):
            rhs_length = shape.value
        elif (isinstance(shape, List_N)
                and len(shape.elements) == 1
                and isinstance(shape.elements[0], IntLiteral_N)):
            rhs_length = shape.elements[0].value
        elif isinstance(shape, List_N) and len(shape.elements) == 0:
            # Scalar -- not destructurable
            raise GeLBExTypeError(
                node,
                "Cannot destructure a scalar value",
                "Destructuring requires a 1D array RHS."
            )
        else:
            # Multi-dimensional array, or non-static shape
            n_dims = (len(shape.elements)
                      if isinstance(shape, List_N) else 'unknown')
            raise GeLBExTypeError(
                node,
                f"Destructuring RHS must be a 1D array; got an array "
                f"with {n_dims} dimensions",
                "Multi-dimensional destructuring is not supported in v1."
            )

        if rhs_length != n_targets:
            raise GeLBExTypeError(
                node,
                f"Destructuring expects {rhs_length} target"
                f"{'' if rhs_length == 1 else 's'} to match the RHS "
                f"array length, got {n_targets}",
                "The number of LHS targets must match the RHS array length."
            )

        return node

    def visitFunctionBlock_N(self, node, ast_root_node: Program_N):
        """Validate types within function body."""
        return self._visit_block_stmts(node, ast_root_node)

    # Other nodes

    def visitPaintNodesStmt_N(self, node: PaintNodesStmt_N, ast_root_node: Program_N):
        """Paint statements don't involve type checking."""
        if node.lhs is not None:
            self.visit(node.lhs, ast_root_node)
        return node

    def visitBorderStmt_N(self, node, ast_root_node):
        return node  # No expressions to validate

    def visitConditionalPaintStmt_N(self, node, ast_root_node):
        self.visit(node.predicate, ast_root_node)
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
        """A declaration without an initial value needs no validation; with
        one, the value must have the declared type (a scalar may initialise
        an array by broadcasting)."""
        initial = getattr(node, "initial_value", None)
        if initial is None:
            return node
        self.visit(initial, ast_root_node)
        value_type = self._require_inferred_type(initial, node)
        declared_type = node.data_type
        if (self._is_scalar_type(value_type)
                and not self._is_scalar_type(declared_type)):
            return node
        if not self._types_match(declared_type, value_type):
            name = getattr(node.name, "name", node.name)
            if self._same_base_type(declared_type, value_type):
                raise GeLBExTypeError(
                    node,
                    f"Variable '{name}' is declared with shape "
                    f"{self._shape_text(declared_type)} but initialized with "
                    f"shape {self._shape_text(value_type)}",
                    "The initializer must have exactly the declared number "
                    "of elements in every dimension"
                )
            raise GeLBExTypeError(
                node,
                f"Variable '{name}' declared as "
                f"'{self._get_type_name(declared_type)}' but initialized with "
                f"'{self._get_type_name(value_type)}'",
                "Initialization type must match declared type"
            )
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
        
        # Note: Lattice parameter validation is now done in ConstantsResolverVisitor
        # after constants are resolved
        
        return node
    
