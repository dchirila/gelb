#!/usr/bin/env python3

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.frontend.implicit_symbols import DIMENSION_CONSTANT_NAMES
from gelb.frontend.visitor_mixins import BinaryOperationMixin, ArrayLiteralProcessingMixin, ProgramTraversalMixin
from gelb.gelb_ast.ASTNodes import *
from gelb.frontend.type_rules import arithmetic_result_type
from gelb.midware.ast_eval import collect_lattice_info, eval_const_expr
from gelb.utils.exceptions import *


class TypeInferenceVisitor(ASTBaseVisitor, BinaryOperationMixin, ArrayLiteralProcessingMixin, ProgramTraversalMixin):
    """
    Concrete visitor for inferring types of all expression elements in the AST.
    
    This visitor traverses the AST and adds a 'inferred_type' attribute to each
    expression node containing its data type. ALL types are represented as ArrayDataType_N,
    with scalars being 0-dimensional arrays.
    
    The type inference rules are:
    - Literals are 0-dimensional arrays of their type (e.g., int literal -> array[int, ()])
    - Identifiers get their types from symbol tables (wrapped as arrays if needed)
    - Binary operations follow standard type promotion rules
    - Array literals have array types based on their structure
    - Lattice selections have array types based on the lattice definition and selection
    """
    
    def __init__(self):
        super().__init__()
        # Track current block context for symbol lookup
        self.current_block = None
        self._lattice_info = None
    
    # Helper method to create scalar array types
    def _create_scalar_array_type(self, code_range, element_dtype):
        """Create a 0-dimensional array type representing a scalar."""
        empty_shape = List_N(code_range)
        return ArrayDataType_N(code_range, element_dtype, empty_shape)
    
    def _is_scalar_array(self, array_type):
        """Check if an ArrayDataType_N represents a scalar (0-dimensional)."""
        if not isinstance(array_type, ArrayDataType_N):
            return False
        return len(array_type.shape.elements) == 0
    
    def visitProgram_N(self, node: Program_N, ast_root_node: Program_N):
        """Visit all blocks in the program to infer types."""
        self._lattice_info = collect_lattice_info(node)
        # Use the mixin for standard traversal
        self.traverse_program_blocks(node, ast_root_node)
        return node
    
    def _store_global_constants(self, node):
        """Hook for storing global constants block."""
        self.global_constants_block = node.global_constants
    
    def _before_block_visit(self, block_node, block_type):
        """Set current block context before visiting."""
        self.current_block = block_node

    def visitGlobalConstantsBlock_N(self, node: GlobalConstantsBlock_N, ast_root_node: Program_N):
        """Process constant definitions to infer types of their values."""
        return self._visit_block_stmts(node, ast_root_node)
    
    def visitConstantDefinitionStmt_N(self, node: ConstantDefinitionStmt_N, ast_root_node: Program_N):
        """Infer type of the constant's value expression."""
        self._validate_declared_data_type_shape(node.data_type, ast_root_node)

        # First infer the type of the value expression
        self.visit(node.value, ast_root_node)
        
        # The constant's declared type should match the inferred type
        # This will be validated in a separate validation pass
        return node
    
    def visitVariableDeclarationStmt_N(self, node: VariableDeclarationStmt_N, ast_root_node: Program_N):
        """Variable declarations may have initial value expressions to infer."""
        self._validate_declared_data_type_shape(node.data_type, ast_root_node)

        if node.initial_value:
            # Infer type of the initial value expression
            self.visit(node.initial_value, ast_root_node)
        return node
    
    def visitVariableAssignmentStmt_N(self, node: VariableAssignmentStmt_N, ast_root_node: Program_N):
        """Infer types of both LHS and RHS expressions."""
        self.visit(node.lhs, ast_root_node)
        self.visit(node.rhs, ast_root_node)
        return node
    
    def visitLatticeOutSelectionAssignmentStmt_N(self, node: LatticeOutSelectionAssignmentStmt_N, ast_root_node: Program_N):
        """Infer types of both LHS and RHS expressions."""
        self.visit(node.lhs, ast_root_node)
        self.visit(node.rhs, ast_root_node)
        return node
    
    def visitArraySelectionAssignmentStmt_N(self, node: ArraySelectionAssignmentStmt_N, ast_root_node: Program_N):
        """Infer types of both LHS and RHS expressions."""
        self.visit(node.lhs, ast_root_node)
        self.visit(node.rhs, ast_root_node)
        return node
    
    # Literal type inference
    
    def visitIntLiteral_N(self, node: IntLiteral_N, ast_root_node: Program_N):
        """Integer literals have type array[int, ()]."""
        node.inferred_type = self._create_scalar_array_type(node.code_range, "int")
        return node
    
    def visitRealLiteral_N(self, node: RealLiteral_N, ast_root_node: Program_N):
        """Real literals have type array[real, ()]."""
        node.inferred_type = self._create_scalar_array_type(node.code_range, "real")
        return node
    
    def visitBoolLiteral_N(self, node: BoolLiteral_N, ast_root_node: Program_N):
        """Boolean literals have type array[bool, ()]."""
        node.inferred_type = self._create_scalar_array_type(node.code_range, "bool")
        return node
    
    def visitStringLiteral_N(self, node: StringLiteral_N, ast_root_node: Program_N):
        """String literals have StringType_N (separate from computational type system)."""
        node.inferred_type = StringType_N(node.code_range)
        return node
    
    # Array literal type inference
    
    def visitArray1DLiteral_N(self, node: Array1DLiteral_N, ast_root_node: Program_N):
        """Infer type of 1D array literal from its elements."""
        return self._process_array_literal(node, ast_root_node, 1)
    
    def visitArray2DLiteral_N(self, node: Array2DLiteral_N, ast_root_node: Program_N):
        """Infer type of 2D array literal from its structure."""
        return self._process_array_literal(node, ast_root_node, 2)
    
    def visitArray3DLiteral_N(self, node: Array3DLiteral_N, ast_root_node: Program_N):
        """Infer type of 3D array literal from its structure."""
        return self._process_array_literal(node, ast_root_node, 3)
    
    def visitArray4DLiteral_N(self, node: Array4DLiteral_N, ast_root_node: Program_N):
        """Infer type of 4D array literal from its structure."""
        return self._process_array_literal(node, ast_root_node, 4)
    
    # Identifier type inference
    
    # Symbol tag classification for type inference.
    #
    # Each symbol in the symbol table has a "tag" string describing its origin.
    # Instead of a long if/elif chain comparing against individual tags, we group
    # tags that share the same type-inference behavior into frozensets for O(1)
    # membership testing.
    #
    # _DECLARED_VALUE_TAGS: symbols whose type comes from their declaration's
    #   data_type attribute (e.g. ConstantDefinitionStmt_N.data_type,
    #   VariableDeclarationStmt_N.data_type). Covers user-defined constants,
    #   variables, and gauge output variables.
    _DECLARED_VALUE_TAGS = frozenset({
        "constant", "constant definition",
        "variable", "variable declaration",
        "output variable declaration",
        "input parameter", "output parameter",
    })
    #
    # _IMPLICIT_INT_TAGS: compiler-injected symbols that are always scalar int.
    #   Covers spatial coordinates (x, y, z), the iteration counter (t), and
    #   grid dimension constants (Nx, Ny, Nz).
    _IMPLICIT_INT_TAGS = frozenset({
        "implicit constant", "implicit dimension constant",
        "implicit variable", "implicit lattice coordinate",
        "implicit timestep variable",
    })
    #
    # _LATTICE_TAGS: lattice instances. These cannot be used as values directly;
    #   the user must use a selection like f.in[x|0] or f.out[x|0].
    _LATTICE_TAGS = frozenset({"lattice", "lattice instance"})

    def visitIdentifier_N(self, node: Identifier_N, ast_root_node: Program_N):
        """Look up identifier type from symbol table."""
        symbol_def = self._lookup_symbol(node)
        # Stash the symbol tag on the node so later passes (backends) can
        # distinguish e.g. an implicit timestep symbol from a user-declared
        # scalar of the same name without re-doing the symbol table walk.
        node.symbol_tag = symbol_def.tag

        if symbol_def.tag in self._DECLARED_VALUE_TAGS:
            # Type comes from the symbol's declaration node (data_type attribute)
            node.inferred_type = symbol_def.value.data_type
        elif symbol_def.tag in self._IMPLICIT_INT_TAGS:
            # Compiler-injected symbols (x, y, z, Nx, Ny, Nz) are always scalar int
            node.inferred_type = self._create_scalar_array_type(node.code_range, "int")
        elif symbol_def.tag in self._LATTICE_TAGS:
            # Lattice references can't be used as values -- must use f.in/f.out selections
            raise GeLBExTypeError(
                node,
                f"Cannot use lattice '{node.name}' directly as a value",
                f"Lattices must be accessed through selections like '{node.name}.in[x,y|:]' or '{node.name}.out[x,y|:]'"
            )
        else:
            raise GeLBExTypeError(
                node,
                f"Symbol '{node.name}' has unrecognized type '{symbol_def.tag}'",
                "This appears to be an internal compiler error. Please report this issue."
            )
        return node

    def _lookup_symbol(self, node):
        """Look up a symbol definition with hierarchical (child -> parent) search.

        Searches the current block's symbol table first, then falls back to the
        parent table (which holds global constants like Nx, Ny, Nz).
        Raises GeLBException if no symbol table is available, or GeLBExTypeError
        if the identifier is not found in any reachable scope.
        """
        if self.current_block is None or self.current_block.symbol_defs is None:
            raise GeLBException(
                f"Cannot infer type of identifier '{node.name}' - no symbol table available",
                "This is likely an internal compiler error"
            )

        symbol_def = self.current_block.symbol_defs.get_symbol_definition(node.name)
        if symbol_def is None:
            parent_table = self.current_block.symbol_defs.parent_table
            if parent_table:
                symbol_def = parent_table.get_symbol_definition(node.name)

        if symbol_def is None:
            raise GeLBExTypeError(
                node,
                f"Identifier '{node.name}' is not defined",
                f"You need to declare '{node.name}' before using it, or check if it's spelled correctly"
            )
        return symbol_def
    
    # Binary operation type inference - handled by mixin
    
    # Implementation of mixin abstract methods
    
    def _handle_binary_operation(self, node, ast_root_node, operation_type):
        """Handle binary operations for the mixin."""
        return self._infer_binary_op_type(node, ast_root_node, operation_type)
    
    def _check_rectangular(self, node, dimensions):
        """Every nested literal at the same depth must have the same number
        of entries; the first one that differs is reported at its own
        location.  The shape below is taken from the first entry at each
        depth, which is only meaningful once this holds."""
        level = [node]
        for depth in range(dimensions):
            expected = len(level[0].value.elements)
            for literal in level:
                n = len(literal.value.elements)
                if n != expected:
                    raise GeLBExTypeError(
                        literal,
                        f"Array literal is not rectangular: a nested literal "
                        f"has {n} elements where {expected} were expected",
                        "Every row of a multi-dimensional array literal must "
                        "have the same number of elements"
                    )
            if depth < dimensions - 1:
                level = [e for literal in level
                         for e in literal.value.elements]

    def _handle_array_literal_dimensions(self, node, ast_root_node, dimensions):
        """Handle dimension-specific array literal processing."""
        self._check_rectangular(node, dimensions)
        # Get base type from first element (after recursive processing)
        first_element = node.value.elements[0]
        # Navigate to the deepest element based on dimensions
        current = first_element
        for _ in range(dimensions - 1):
            current = current.value.elements[0]
        
        # Now current should have an inferred_type
        base_type = self._get_base_scalar_type(current.inferred_type)
        
        # Create shape based on dimensions
        shape_values = List_N(node.code_range)
        current_level = node.value.elements
        
        for dim in range(dimensions):
            shape_values.append(IntLiteral_N(node.code_range, len(current_level)))
            if dim < dimensions - 1:
                current_level = current_level[0].value.elements
        
        if dimensions == 1:
            shape = IntLiteral_N(node.code_range, len(node.value.elements))
        else:
            shape = Array1DLiteral_N(node.code_range, shape_values)
        
        node.inferred_type = ArrayDataType_N(node.code_range, base_type, shape)
        return node
    
    # Unary operation type inference
    
    def visitNotExpr_N(self, node: NotExpr_N, ast_root_node: Program_N):
        """Logical NOT requires bool operand and returns array[bool, ()]."""
        self.visit(node.value, ast_root_node)
        node.inferred_type = self._create_scalar_array_type(node.code_range, "bool")
        return node
    
    def visitTypePromotionNode_N(self, node: TypePromotionNode_N, ast_root_node: Program_N):
        """A promotion inserted before this pass: the constant resolver
        substitutes an array constant as a copy of its value promoted to
        the declared array type, so its width is kept.  Its type is its
        target."""
        self.visit(node.expr, ast_root_node)
        node.inferred_type = node.target_type
        return node

    def visitUnaryMinusExpr_N(self, node: UnaryMinusExpr_N, ast_root_node: Program_N):
        """Unary minus preserves the operand type."""
        self.visit(node.value, ast_root_node)
        node.inferred_type = node.value.inferred_type
        return node
    
    # Lattice and array selection type inference
    
    def visitRectSelOfLatticeInDFs_N(self, node: RectSelOfLatticeInDFs_N, ast_root_node: Program_N):
        """Infer type of lattice input DF selection."""
        return self._infer_lattice_selection_type(node, ast_root_node)
    
    def visitRectSelOfLatticeOutDFs_N(self, node: RectSelOfLatticeOutDFs_N, ast_root_node: Program_N):
        """Infer type of lattice output DF selection."""
        return self._infer_lattice_selection_type(node, ast_root_node)
    
    def visitRectSelOfArrayElems_N(self, node: RectSelOfArrayElems_N, ast_root_node: Program_N):
        """Infer type of array element selection."""
        # Look up array in symbol table
        if self.current_block is None or self.current_block.symbol_defs is None:
            raise GeLBException(
                f"Cannot infer type of array selection '{node.array_name}' - no symbol table available",
                "This is likely an internal compiler error"
            )
        
        # Extract array name string from Identifier_N
        array_name_str = str(node.array_name.name) if hasattr(node.array_name, 'name') else str(node.array_name)
        
        # Look up symbol definition with hierarchical lookup
        symbol_def = self.current_block.symbol_defs.get_symbol_definition(array_name_str)
        if symbol_def is None:
            # Try the parent symbol table (for global constants)
            parent_table = self.current_block.symbol_defs.parent_table
            if parent_table:
                symbol_def = parent_table.get_symbol_definition(array_name_str)
            
            if symbol_def is None:
                raise GeLBException(
                    f"Undefined array '{array_name_str}'",
                    f"at {node.code_range}"
                )
        
        # Get base type from array
        array_type = symbol_def.data_type if hasattr(symbol_def, 'data_type') else symbol_def.value.data_type
        if not isinstance(array_type, ArrayDataType_N):
            raise GeLBExTypeError(
                node,
                f"Cannot index '{array_name_str}' because it is not an array",
                f"Only arrays can be indexed with []. '{array_name_str}' appears to be a scalar or other non-indexable type"
            )
        
        # Infer type based on selection ranges
        # For single element selections, result is scalar (element type)
        # For range selections, result is array with reduced dimensionality
        
        base_type = array_type.element_dtype
        
        # Get array dimensions first to check for too many indices
        original_shape = self._get_shape_if_array(array_type)
        original_dimensions = self._extract_dimension_sizes(original_shape, ast_root_node)
        
        # Check for too many indices before proceeding
        if len(node.element_ranges.elements) > len(original_dimensions):
            # Determine user-friendly description
            if len(original_dimensions) == 0:
                type_description = "scalar"
                hint = f"'{array_name_str}' is a scalar value and cannot be indexed. Only arrays can be indexed with []"
            else:
                type_description = f"{len(original_dimensions)}D array"
                hint = f"Remove {len(node.element_ranges.elements) - len(original_dimensions)} index(es) to match the array dimensions"
            
            raise GeLBExTypeError(
                node,
                f"Cannot index {type_description} '{array_name_str}' with {len(node.element_ranges.elements)} indices",
                hint
            )
        
        # Count how many ranges select single elements vs ranges
        single_element_count = 0
        range_count = 0
        
        for r in node.element_ranges.elements:
            if isinstance(r, Range_N):
                if r.low is not None and r.high is not None and self._are_range_bounds_equal(r.low, r.high):
                    # Single element: arr[3] or arr[3:3]
                    single_element_count += 1
                elif r.low is None and r.high is None:
                    # Full range: arr[:]
                    range_count += 1
                else:
                    # Partial range: arr[1:3]
                    range_count += 1
        
        # If all selections are single elements, result is scalar (0D array)
        if single_element_count == len(node.element_ranges.elements):
            # Validate that all single element expressions are compile-time evaluable
            for r in node.element_ranges.elements:
                if isinstance(r, Range_N):
                    self._evaluate_compile_time_int(
                        r.low, ast_root_node, "array index",
                        original_dimensions)
                    if r.high != r.low:  # Only validate high if it's different from low
                        self._evaluate_compile_time_int(
                            r.high, ast_root_node, "array index",
                            original_dimensions)
            
            empty_shape = List_N(node.code_range)
            node.inferred_type = ArrayDataType_N(node.code_range, base_type, empty_shape)
        else:
            # Calculate reduced shape based on range selections
            reduced_type = self._reduce_array_shape(array_type, node.element_ranges, ast_root_node)
            node.inferred_type = reduced_type
        
        return node
    
    # Block traversal
    
    def visitInitializerBlock_N(self, node: InitializerBlock_N, ast_root_node: Program_N):
        """Process statements in initializer block."""
        return self._visit_block_stmts(node, ast_root_node)

    def visitDynamicBlock_N(self, node: DynamicBlock_N, ast_root_node: Program_N):
        """Process statements in dynamic block."""
        return self._visit_block_stmts(node, ast_root_node)

    def visitGaugeBlock_N(self, node: GaugeBlock_N, ast_root_node: Program_N):
        """Process statements in gauge block."""
        for output_decl in node.outputs:
            self.visit(output_decl, ast_root_node)
        return self._visit_block_stmts(node, ast_root_node)

    def visitGeometryBlock_N(self, node: GeometryBlock_N, ast_root_node: Program_N):
        """Process statements in geometry block."""
        return self._visit_block_stmts(node, ast_root_node)
    
    def visitPaintNodesStmt_N(self, node: PaintNodesStmt_N, ast_root_node: Program_N):
        """Process expressions in paint statement ranges."""
        # The LHS contains spatial ranges that may have expressions
        if node.lhs is not None:
            self.visit(node.lhs, ast_root_node)
        # The RHS is a node class name, not an expression that needs type inference
        return node

    def visitBorderStmt_N(self, node, ast_root_node):
        return node  # No expressions to infer

    def visitConditionalPaintStmt_N(self, node, ast_root_node):
        """A ``where`` predicate is an ordinary expression that must be a
        scalar bool; it is evaluated per cell when the geometry is resolved."""
        self.visit(node.predicate, ast_root_node)
        inferred = getattr(node.predicate, 'inferred_type', None)
        if (not self._is_scalar_array(inferred)
                or str(inferred.element_dtype) != 'bool'):
            if isinstance(inferred, ArrayDataType_N):
                got = (f"a {inferred.element_dtype} "
                       + ("scalar" if self._is_scalar_array(inferred)
                          else "array"))
            else:
                got = "an expression of unknown type"
            raise GeLBExTypeError(
                node.predicate,
                f"The predicate of a 'where' paint must be a scalar bool,"
                f" but this is {got}",
                "Write a comparison or a logical expression over the"
                " coordinates and constants, or call a function that"
                " returns bool, e.g."
                " nodes[where InCircle(x, y, CX, CY, R)] = SOLID;",
            )
        return node

    def visitLatticesBlock_N(self, node: LatticesBlock_N, ast_root_node: Program_N):
        """Process lattice instantiation statements."""
        return self._visit_block_stmts(node, ast_root_node)
    
    def visitLatticeInstaStmt_N(self, node: LatticeInstaStmt_N, ast_root_node: Program_N):
        """Process expressions in lattice instantiation."""
        # Infer types of dimension and q parameters if they are expressions
        if node.d is not None:
            self.visit(node.d, ast_root_node)
        if node.q is not None:
            self.visit(node.q, ast_root_node)
        
        # Infer types of new grid_size and periodicity parameters
        if hasattr(node, 'grid_size') and node.grid_size is not None:
            self.visit(node.grid_size, ast_root_node)
        if hasattr(node, 'periodicity') and node.periodicity is not None:
            self.visit(node.periodicity, ast_root_node)
        return node
    
    def visitNodeClassesBlock_N(self, node: NodeClassesBlock_N, ast_root_node: Program_N):
        """Node classes block doesn't have expressions."""
        return node
    
    def visitRange_N(self, node: Range_N, ast_root_node: Program_N):
        """Process range bounds if they are expressions."""
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
    
    # Helper methods
    
    def _get_base_scalar_type(self, data_type):
        """Extract scalar type from an ArrayDataType_N node."""
        if isinstance(data_type, ArrayDataType_N):
            return data_type.element_dtype
        else:
            raise GeLBException(
                f"Unknown data type: {type(data_type).__name__}",
                "This is likely an internal compiler error"
            )
    
    
    def _get_shape_if_array(self, expr_type):
        """Normalize an ArrayDataType_N's shape to List_N format.

        The AST uses three representations for array shapes:
          - List_N          -> 0D (scalar, empty) or already normalized
          - scalar expression -> 1D (single dimension value)
          - Array1DLiteral_N -> 2D+ (wraps a List_N of per-dim sizes)

        This method converts all three to a uniform List_N of dimension sizes,
        making shape comparisons and broadcasting straightforward.
        See _denormalize_shape() for the inverse operation.
        """
        if not isinstance(expr_type, ArrayDataType_N):
            return List_N(expr_type.code_range if hasattr(expr_type, 'code_range') else None)

        shape = expr_type.shape
        if isinstance(shape, List_N):
            return shape
        elif isinstance(shape, Array1DLiteral_N):
            return shape.value
        elif shape is not None:
            result = List_N(expr_type.code_range)
            result.elements = [shape]
            return result
        else:
            return List_N(expr_type.code_range)

    def _denormalize_shape(self, normalized_shape, code_range):
        """Convert a normalized List_N shape back to the AST's native format.

        Inverse of _get_shape_if_array():
          - 0 dims -> empty List_N (scalar)
          - 1 dim  -> bare IntLiteral_N / Identifier_N
          - 2+ dims -> Array1DLiteral_N wrapping the List_N
        """
        if not isinstance(normalized_shape, List_N):
            return normalized_shape

        num_dims = len(normalized_shape.elements)
        if num_dims == 0:
            return List_N(code_range)
        elif num_dims == 1:
            return normalized_shape.elements[0]
        else:
            return Array1DLiteral_N(code_range, normalized_shape)
    
    def _infer_binary_op_type(self, node, ast_root_node, op_category):
        """Infer type of binary operation based on operand types."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)

        if op_category == "arithmetic":
            self._infer_arithmetic_type(node)
        elif op_category == "comparison":
            self._infer_comparison_type(node)
        elif op_category == "logical":
            self._infer_logical_type(node)

        return node

    def _infer_arithmetic_type(self, node):
        """Infer type of arithmetic operation with broadcasting."""
        left_type = node.left.inferred_type
        right_type = node.right.inferred_type

        # The element type follows the one table (gelb.frontend.type_rules),
        # the one rule the promotion pass and the intrinsic table use too.
        left_base = self._get_base_scalar_type(left_type)
        right_base = self._get_base_scalar_type(right_type)
        result_type = arithmetic_result_type(left_base, right_base)
        if result_type is None:
            # An operand that takes no part in arithmetic (a string):
            # TypeValidationVisitor rejects the operation with its own
            # diagnostic; the placeholder keeps the node well-formed.
            result_type = "int"

        # Shape broadcasting: scalar broadcasts to array shape
        result_shape = self._broadcast_shapes(left_type, right_type, node.code_range)
        final_shape = self._denormalize_shape(result_shape, node.code_range)
        node.inferred_type = ArrayDataType_N(node.code_range, result_type, final_shape)

    def _infer_comparison_type(self, node):
        """Comparison operations always return scalar bool."""
        node.inferred_type = self._create_scalar_array_type(node.code_range, "bool")

    def _infer_logical_type(self, node):
        """Logical operations always return scalar bool."""
        node.inferred_type = self._create_scalar_array_type(node.code_range, "bool")

    def _broadcast_shapes(self, left_type, right_type, code_range):
        """Compute result shape from two operand types using broadcasting rules."""
        left_shape = self._get_shape_if_array(left_type)
        right_shape = self._get_shape_if_array(right_type)
        left_dims = len(left_shape.elements)
        right_dims = len(right_shape.elements)

        if left_dims == 0 and right_dims == 0:
            return List_N(code_range)
        elif left_dims == 0:
            return right_shape
        elif right_dims == 0:
            return left_shape
        elif left_dims == right_dims:
            return left_shape  # Assume shapes are compatible
        else:
            # Rank mismatch: GeLB defines no broadcasting between arrays
            # of different rank, so there is no result shape.  Leave the
            # inferred shape scalar; TypeValidationVisitor rejects the
            # operation afterwards with a source-located diagnostic.
            return List_N(code_range)
    
    def _infer_lattice_selection_type(self, node, ast_root_node):
        """Infer type of lattice selection based on lattice definition."""
        # Look up lattice in global lattices block
        if ast_root_node.lattices is None:
            raise GeLBException(
                f"No lattices block found",
                "Cannot infer type of lattice selection"
            )
        
        # Find lattice definition
        lattice_def = None
        lattice_name = node.lattice_name
        if isinstance(lattice_name, Identifier_N):
            lattice_name = lattice_name.name
            
        # Debug: print available lattices
        # print(f"Looking for lattice '{lattice_name}'")
        # print(f"Available lattices: {[stmt.name for stmt in ast_root_node.lattices.stmts.elements if isinstance(stmt, LatticeInstaStmt_N)]}")
            
        for stmt in ast_root_node.lattices.stmts.elements:
            if isinstance(stmt, LatticeInstaStmt_N):
                stmt_name = stmt.name
                if isinstance(stmt_name, Identifier_N):
                    stmt_name = stmt_name.name
                if stmt_name == lattice_name:
                    lattice_def = stmt
                    break
        
        if lattice_def is None:
            raise GeLBExTypeError(
                node,
                f"Lattice '{lattice_name}' is not defined",
                f"You need to declare the lattice '{lattice_name}' in the lattices block before using it"
            )
        
        # Lattice selections have the df_type of the lattice
        # The shape depends on the selection ranges
        
        # Get the df_type from lattice definition
        df_type = lattice_def.df_type
        if isinstance(df_type, ArrayDataType_N):
            base_type = df_type.element_dtype
        else:
            base_type = "real"  # Default to real if not specified
        
        # Determine shape based on DF selection
        # The DF range is the last element in element_ranges
        df_range = node.element_ranges[-1] if node.element_ranges else None
        
        # If DF range spans full DF dimension, result is 1D array of size q
        # Otherwise, it's a scalar (0-dimensional array)
        if df_range is not None and isinstance(df_range, Range_N):
            # Check if this is a full DF range (0 to q-1)
            # This covers both explicit ranges like [0:q-1] and colon ranges [:]
            is_full_range = False
            
            # Pattern 1: Range tagged as full DF range by the range resolver
            # (set when expanding `:` to `0:q-1`)
            if getattr(df_range, 'is_full_df_range', False):
                is_full_range = True

            # Pattern 2: True colon range (low=None, high=None) -- before range resolution
            elif df_range.low is None and df_range.high is None:
                is_full_range = True
            
            if is_full_range:
                # Full DF selection: f.in[x,y|:] or f.in[x,y|0:q-1] returns array of size q
                q_value = lattice_def.q
                if isinstance(q_value, IntLiteral_N):
                    shape_elements = [IntLiteral_N(node.code_range, q_value.value)]
                else:
                    # q is an expression, use it as-is
                    shape_elements = [q_value]
                
                shape = List_N(node.code_range)
                shape.elements = shape_elements
                node.inferred_type = ArrayDataType_N(node.code_range, base_type, shape)
            else:
                # Partial DF selection: f.in[x,y|0] or f.in[x,y|1:3] returns scalar
                node.inferred_type = self._create_scalar_array_type(node.code_range, base_type)
        else:
            # No DF range specified, treat as scalar
            node.inferred_type = self._create_scalar_array_type(node.code_range, base_type)
        
        return node
    
    # Array range selection shape reduction methods
    
    def _reduce_array_shape(self, base_array_type, element_ranges, ast_root_node):
        """Calculate the resulting shape after applying range selections."""
        if not isinstance(base_array_type, ArrayDataType_N):
            raise GeLBException(
                "Cannot reduce shape of non-array type",
                "This is likely an internal compiler error"
            )
        
        base_element_type = base_array_type.element_dtype
        original_shape = self._get_shape_if_array(base_array_type)
        
        # Get original dimension sizes
        original_dimensions = self._extract_dimension_sizes(original_shape, ast_root_node)
        
        if len(element_ranges.elements) > len(original_dimensions):
            raise GeLBException(
                f"Too many indices: array has {len(original_dimensions)} dimensions but {len(element_ranges.elements)} indices provided",
                f"at {element_ranges.code_range}"
            )
        
        # Calculate resulting dimensions after range selections
        resulting_dimensions = []
        
        for i, range_elem in enumerate(element_ranges.elements):
            if i >= len(original_dimensions):
                break  # Safety check
            
            dimension_size = original_dimensions[i]
            range_type, new_size = self._classify_range_selection(range_elem, dimension_size, ast_root_node, original_dimensions)
            
            if range_type != "single_element":
                # Keep this dimension with the new size
                resulting_dimensions.append(new_size)
            # For single_element, dimension is removed (not added to resulting_dimensions)
        
        # Add any remaining dimensions that weren't selected
        for i in range(len(element_ranges.elements), len(original_dimensions)):
            resulting_dimensions.append(original_dimensions[i])
        
        # Construct the new array type
        new_shape = self._construct_reduced_shape(resulting_dimensions, base_array_type.code_range)
        return ArrayDataType_N(base_array_type.code_range, base_element_type, new_shape)
    
    def _extract_dimension_sizes(self, shape, ast_root_node):
        """Extract dimension sizes from array shape as a list of integers."""
        if isinstance(shape, List_N) and len(shape.elements) == 0:
            # 0D array (scalar)
            return []
        elif isinstance(shape, List_N) and len(shape.elements) == 1:
            # 1D array
            size = self._evaluate_size_expression(shape.elements[0], ast_root_node)
            return [size]
        elif isinstance(shape, List_N):
            # Multi-dimensional array from Array1DLiteral_N.value
            sizes = []
            for size_expr in shape.elements:
                size = self._evaluate_size_expression(size_expr, ast_root_node)
                sizes.append(size)
            return sizes
        else:
            # Handle legacy cases or single dimension
            size = self._evaluate_size_expression(shape, ast_root_node)
            return [size]

    def _validate_declared_data_type_shape(self, data_type, ast_root_node):
        """Validate declared array shapes before any value use."""
        if not isinstance(data_type, ArrayDataType_N):
            return

        shape = self._get_shape_if_array(data_type)
        self._extract_dimension_sizes(shape, ast_root_node)
    
    def _evaluate_size_expression(self, expr, ast_root_node, array_dimensions=None):
        """Evaluate a size expression to get its integer value.

        An extent must be at least 1: a zero or negative extent is an
        error here, at the extent, instead of a native compiler's
        complaint about the declaration or a reduction over it.
        """
        size = self._evaluate_compile_time_int(
            expr, ast_root_node, "array shape", array_dimensions)
        if size is not None and size < 1:
            raise GeLBExTypeError(
                expr,
                f"Array extent must be at least 1, got {size}",
                "Every extent in array[type, extent] or array[type, "
                "{extent, ...}] is the number of elements along that "
                "axis, so it is a positive integer; an empty array is "
                "not in this version.",
            )
        return size
    
    def _classify_range_selection(self, range_elem, dimension_size, ast_root_node, array_dimensions=None):
        """Classify range selection type and calculate result size."""
        if not isinstance(range_elem, Range_N):
            # Treat non-range as single element
            return "single_element", 0
        
        range_node = range_elem
        
        # Evaluate range bounds
        low_val = self._evaluate_range_bound(range_node.low, ast_root_node, array_dimensions) if range_node.low else 0
        high_val = self._evaluate_range_bound(range_node.high, ast_root_node, array_dimensions) if range_node.high else dimension_size - 1
        
        # Check for single element ranges
        if low_val == high_val:
            return "single_element", 0
        
        # Check for full dimension ranges
        if low_val == 0 and high_val == dimension_size - 1:
            return "full_range", dimension_size
        
        # Calculate partial range size
        if high_val >= low_val:
            size = high_val - low_val + 1
            return "partial_range", size
        else:
            # Invalid range
            return "partial_range", 1  # Fallback
    
    def _evaluate_range_bound(self, expr, ast_root_node, array_dimensions=None):
        """Evaluate a range bound expression to get its integer value."""
        if expr is None:
            return None

        return self._evaluate_compile_time_int(
            expr, ast_root_node, "range bound", array_dimensions)

    def _evaluate_compile_time_int(
            self, expr, ast_root_node, context, array_dimensions=None):
        """Evaluate a compile-time expression that must produce an integer."""
        if expr is None:
            return None

        self._validate_compile_time_symbol_refs(
            expr, context, array_dimensions)
        bindings = self._compile_time_bindings(ast_root_node, array_dimensions)
        try:
            value = eval_const_expr(
                expr,
                bindings=bindings,
                ast=ast_root_node,
                lattice_info=self._lattice_info,
            )
        except (IndexError, TypeError, ValueError, ZeroDivisionError,
                OverflowError) as exc:
            raise GeLBExTypeError(
                expr,
                f"Expression in {context} must be compile-time evaluable",
                (
                    "Only integer literals, constant integer expressions, "
                    "and active grid dimension constants such as Nx/Ny/Nz "
                    f"are permitted here. {exc}"
                ),
            ) from exc

        if isinstance(value, bool) or not isinstance(value, int):
            raise GeLBExTypeError(
                expr,
                f"Expression in {context} must evaluate to an integer",
                (
                    f"Got value {value!r} of type "
                    f"{type(value).__name__}. Use an integer-valued "
                    "compile-time expression here."
                ),
            )

        return value

    def _validate_compile_time_symbol_refs(
            self, expr, context, array_dimensions=None):
        if self.current_block is None or self.current_block.symbol_defs is None:
            return

        array_dim_names = set()
        if array_dimensions is not None:
            array_dim_names = set(DIMENSION_CONSTANT_NAMES[:len(array_dimensions)])

        for symbol_ref in expr.get_referenced_symbols():
            name = symbol_ref.name
            if name in array_dim_names:
                continue

            symbol_def = self.current_block.symbol_defs.get_symbol_definition_local(
                name)
            if symbol_def is None or symbol_def.tag == "constant definition":
                continue

            raise GeLBExTypeError(
                symbol_ref,
                f"Expression in {context} must be compile-time evaluable",
                (
                    f"'{name}' is not a compile-time constant in this scope. "
                    "Only integer literals, constant integer expressions, "
                    "and active grid dimension constants such as Nx/Ny/Nz "
                    "are permitted here."
                ),
            )

    def _compile_time_bindings(self, ast_root_node, array_dimensions=None):
        """Build bindings for local constants and array-dimension aliases."""
        bindings = {}

        if array_dimensions is not None:
            for dim_name, dim_size in zip(DIMENSION_CONSTANT_NAMES, array_dimensions):
                bindings[dim_name] = dim_size

        if self.current_block is None or self.current_block.symbol_defs is None:
            return bindings

        for symbol_def in self.current_block.symbol_defs.symbol_defs:
            if symbol_def.tag != "constant definition":
                continue

            name = symbol_def.name
            if name in bindings:
                continue

            value_expr = symbol_def.value.value
            try:
                bindings[name] = eval_const_expr(
                    value_expr,
                    bindings=bindings,
                    ast=ast_root_node,
                    lattice_info=self._lattice_info,
                )
            except (IndexError, TypeError, ValueError, ZeroDivisionError,
                    OverflowError):
                # If this constant is actually used in a compile-time
                # shape/range expression, evaluating that expression will
                # raise a source-located GeLBExTypeError.  An overflowing
                # real constant (``real32(1.0e300)``, ``1.0e300 *
                # 1.0e300``) is an infinity at run time and no
                # shape; it is simply not bound here.
                pass

        return bindings
    
    def _are_range_bounds_equal(self, bound1, bound2):
        """Check if two range bounds represent the same value."""
        # Same object reference
        if bound1 is bound2:
            return True
        
        # Both are literals with same value
        if isinstance(bound1, IntLiteral_N) and isinstance(bound2, IntLiteral_N):
            return bound1.value == bound2.value
        
        # Both are identifiers with same name
        if isinstance(bound1, Identifier_N) and isinstance(bound2, Identifier_N):
            return bound1.name == bound2.name
        
        # For now, assume other expression types are not equal
        # This could be extended to handle more complex expression equality
        return False
    
    def _construct_reduced_shape(self, remaining_dimensions, code_range):
        """Create appropriate shape node for reduced array."""
        if len(remaining_dimensions) == 0:
            # Scalar result
            return List_N(code_range)
        elif len(remaining_dimensions) == 1:
            # 1D array
            return IntLiteral_N(code_range, remaining_dimensions[0])
        else:
            # Multi-dimensional array
            shape_elements = List_N(code_range)
            for dim_size in remaining_dimensions:
                shape_elements.append(IntLiteral_N(code_range, dim_size))
            return Array1DLiteral_N(code_range, shape_elements)

    def visitFunctionBlock_N(self, node, ast_root_node):
        """Infer types within a user-defined function body."""
        for param in node.inputs:
            self.visit(param, ast_root_node)
        for param in node.outputs:
            self.visit(param, ast_root_node)
        return self._visit_block_stmts(node, ast_root_node)

    def visitDestructuringAssignmentStmt_N(self, node, ast_root_node):
        """Infer types of destructuring assignment."""
        for target in node.targets:
            self.visit(target, ast_root_node)
        self.visit(node.rhs, ast_root_node)
        return node

    # Intrinsic function type inference
    
    def visitIntrinsicFunctionCall_N(self, node: IntrinsicFunctionCall_N, ast_root_node: Program_N):
        """
        Infer type of intrinsic function call.
        
        First infers types of all arguments, then looks up the function definition
        to validate arguments and compute the return type.
        """
        from gelb.frontend.intrinsic_functions import get_intrinsic_function
        
        # For streaming intrinsics, skip type inference on the lattice
        # name argument (first arg) -- it's a lattice reference, not a value
        _STREAMING_INTRINSICS = frozenset({'upstream_dfs', 'bounce_back_dfs'})
        start = 1 if node.function_name in _STREAMING_INTRINSICS else 0
        for i, arg in enumerate(node.arguments):
            if i >= start:
                self.visit(arg, ast_root_node)
        
        # Look up the intrinsic function definition
        func_def = get_intrinsic_function(node.function_name)
        if func_def is None:
            raise GeLBExTypeError(
                node,
                f"Unknown intrinsic function '{node.function_name}'",
                f"Available intrinsic functions: sum, dot_prod, sin, cos, sqrt"
            )
        
        # Validate argument count
        arg_count = len(node.arguments.elements)
        if func_def.min_args == func_def.max_args:
            # Exact argument count required
            if arg_count != func_def.min_args:
                raise GeLBExTypeError(
                    node,
                    f"Function '{node.function_name}' expects exactly {func_def.min_args} argument{'s' if func_def.min_args != 1 else ''}, got {arg_count}",
                    f"Usage: {node.function_name}({', '.join(f'arg{i+1}' for i in range(func_def.min_args))})"
                )
        else:
            # Range of argument counts allowed
            if arg_count < func_def.min_args:
                raise GeLBExTypeError(
                    node,
                    f"Function '{node.function_name}' expects at least {func_def.min_args} arguments, got {arg_count}",
                    f"Check the function signature for '{node.function_name}'"
                )
            if func_def.max_args is not None and arg_count > func_def.max_args:
                raise GeLBExTypeError(
                    node,
                    f"Function '{node.function_name}' expects at most {func_def.max_args} arguments, got {arg_count}",
                    f"Check the function signature for '{node.function_name}'"
                )
        
        # Validate argument types using the function's type checker
        func_def.type_checker(node.function_name, node.arguments.elements, node)
        
        # Compute and set the return type
        node.inferred_type = func_def.return_type_computer(
            node.function_name,
            node.arguments.elements,
            node,
            node.code_range
        )

        # The streaming intrinsics return one DF per lattice direction:
        # array[real, q] of the named lattice, whatever the lengths of
        # the velocity arrays.  Those lengths are checked against q by
        # the stencil-argument pass, whose message names the array; if
        # the shape were taken from the arrays instead, a declaration
        # such as ``array[real, 9] fIn = upstream_dfs(...)`` would be
        # rejected first with a less specific shape mismatch.
        if node.function_name in _STREAMING_INTRINSICS:
            lattice_arg = node.arguments.elements[0]
            info = (self._lattice_info or {}).get(
                getattr(lattice_arg, "name", None))
            if info is not None and isinstance(info.get("q"), int):
                node.inferred_type = ArrayDataType_N(
                    node.code_range, "real",
                    IntLiteral_N(node.code_range, info["q"]))

        return node

    def visitUserFunctionCall_N(self, node, ast_root_node):
        """
        Infer type of user-defined function call.

        Looks up the function definition from the program symbol table,
        validates argument count, and sets inferred_type from the function's
        output declarations.
        """
        # Look up the function definition first: a call to an unknown
        # name is reported as such, not as a fault in its arguments
        # (a lattice passed to it, say).
        func_name = node.function_name.name
        func_sdef = ast_root_node.symbol_defs.get_symbol_definition(func_name)
        if func_sdef is None or func_sdef.tag != "function":
            raise GeLBExTypeError(
                node,
                f"Unknown function '{func_name}'",
                "Make sure the function is defined with a 'function' block"
            )

        # Infer types of all arguments
        for arg in node.arguments:
            self.visit(arg, ast_root_node)

        func_block = func_sdef.value  # FunctionBlock_N

        # Validate argument count matches input parameters
        expected = len(func_block.inputs.elements)
        actual = len(node.arguments.elements)
        if actual != expected:
            raise GeLBExTypeError(
                node,
                f"Function '{func_name}' expects {expected} argument{'s' if expected != 1 else ''}, got {actual}",
                f"Check the function's input parameters"
            )

        # Determine return type from output declarations
        outputs = func_block.outputs.elements
        if len(outputs) == 1:
            # Single output: return type is the output's data type
            out_decl = outputs[0]
            out_dtype = out_decl.data_type
            if isinstance(out_dtype, ArrayDataType_N):
                node.inferred_type = out_dtype
            elif isinstance(out_dtype, ScalarDataType_N):
                node.inferred_type = self._create_scalar_array_type(
                    node.code_range, out_dtype.name
                )
            else:
                # String data type name (e.g., "real", "int")
                node.inferred_type = self._create_scalar_array_type(
                    node.code_range, str(out_dtype)
                )
        else:
            # Multi-output: store all output types for destructuring
            # The call itself doesn't have a single type; it produces multiple values
            # We store the function block reference for later use by
            # DestructuringAssignmentStmt_N or chained call expansion
            node.inferred_type = None
            node.function_block = func_block

        return node
