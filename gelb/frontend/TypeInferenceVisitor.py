#!/usr/bin/env python3

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.frontend.visitor_mixins import BinaryOperationMixin, ArrayLiteralProcessingMixin, ProgramTraversalMixin
from gelb.gelb_ast.ASTNodes import *
from gelb.utils.exceptions import *
from gelb.utils.CodeRange import CodeRange


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
        for stmt in node.stmts:
            self.visit(stmt, ast_root_node)
        return node
    
    def visitConstantDefinitionStmt_N(self, node: ConstantDefinitionStmt_N, ast_root_node: Program_N):
        """Infer type of the constant's value expression."""
        # First infer the type of the value expression
        self.visit(node.value, ast_root_node)
        
        # The constant's declared type should match the inferred type
        # This will be validated in a separate validation pass
        return node
    
    def visitVariableDeclarationStmt_N(self, node: VariableDeclarationStmt_N, ast_root_node: Program_N):
        """Variable declarations may have initial value expressions to infer."""
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
    
    def visitIdentifier_N(self, node: Identifier_N, ast_root_node: Program_N):
        """Look up identifier type from symbol table."""
        if self.current_block is None or self.current_block.symbol_defs is None:
            raise GeLBException(
                f"Cannot infer type of identifier '{node.name}' - no symbol table available",
                "This is likely an internal compiler error"
            )
        
        # Look up symbol definition
        symbol_def = self.current_block.symbol_defs.get_symbol_definition(node.name)
        if symbol_def is None:
            # Try the parent symbol table (for global constants like Nx)
            parent_table = self.current_block.symbol_defs.parent_table
            if parent_table:
                symbol_def = parent_table.get_symbol_definition(node.name)
            
            if symbol_def is None:
                raise GeLBException(
                    f"Undefined identifier '{node.name}'",
                    f"at {node.code_range}"
                )
        
        # Get type from symbol definition based on tag
        if symbol_def.tag == "constant" or symbol_def.tag == "constant definition":
            # For constants, value is ConstantDefinitionStmt_N
            data_type = symbol_def.value.data_type
            # All data types are now ArrayDataType_N (scalars are 0D arrays)
            node.inferred_type = data_type
        elif symbol_def.tag == "variable" or symbol_def.tag == "variable declaration":
            # For variables, value is VariableDeclarationStmt_N
            data_type = symbol_def.value.data_type
            # All data types are now ArrayDataType_N (scalars are 0D arrays)
            node.inferred_type = data_type
        elif symbol_def.tag == "lattice":
            # For lattices, value is LatticeInstaStmt_N
            # A lattice reference itself doesn't have a type, only selections do
            raise GeLBException(
                f"Cannot infer type of lattice '{node.name}' directly",
                "Lattices must be accessed through selections like f.in[x,y|:]"
            )
        elif symbol_def.tag == "output variable declaration":
            # For gauge outputs, value is VariableDeclarationStmt_N
            data_type = symbol_def.value.data_type
            # All data types are now ArrayDataType_N (scalars are 0D arrays)
            node.inferred_type = data_type
        elif symbol_def.tag == "implicit constant" or symbol_def.tag == "implicit dimension constant":
            # For implicit constants like Nx, Ny, Nz
            node.inferred_type = self._create_scalar_array_type(node.code_range, "int")
        elif symbol_def.tag == "implicit variable" or symbol_def.tag == "implicit lattice coordinate":
            # For implicit variables like x, y, z
            node.inferred_type = self._create_scalar_array_type(node.code_range, "int")
        else:
            # Handle any remaining cases
            if node.name in ['x', 'y', 'z']:
                node.inferred_type = self._create_scalar_array_type(node.code_range, "int")
            elif node.name in ['Nx', 'Ny', 'Nz']:
                node.inferred_type = self._create_scalar_array_type(node.code_range, "int")
            else:
                raise GeLBException(
                    f"Unknown symbol type '{symbol_def.tag}' for '{node.name}'",
                    "This is likely an internal compiler error"
                )
        return node
    
    # Binary operation type inference - handled by mixin
    
    # Implementation of mixin abstract methods
    
    def _handle_binary_operation(self, node, ast_root_node, operation_type):
        """Handle binary operations for the mixin."""
        return self._infer_binary_op_type(node, ast_root_node, operation_type)
    
    def _handle_array_literal_dimensions(self, node, ast_root_node, dimensions):
        """Handle dimension-specific array literal processing."""
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
            raise GeLBException(
                f"'{array_name_str}' is not an array",
                f"at {node.code_range}"
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
            raise GeLBException(
                f"Too many indices: array has {len(original_dimensions)} dimensions but {len(node.element_ranges.elements)} indices provided",
                f"at {node.code_range}"
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
                    self._validate_compile_time_evaluable(r.low, "array index")
                    if r.high != r.low:  # Only validate high if it's different from low
                        self._validate_compile_time_evaluable(r.high, "array index")
            
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
        # Geometry block no longer has grid_size and grid_periodicity
        # These are now part of lattice instantiation statements
        
        # Process paint statements
        for stmt in node.stmts:
            self.visit(stmt, ast_root_node)
        return node
    
    def visitPaintNodesStmt_N(self, node: PaintNodesStmt_N, ast_root_node: Program_N):
        """Process expressions in paint statement ranges."""
        # The LHS contains spatial ranges that may have expressions
        if node.lhs is not None:
            self.visit(node.lhs, ast_root_node)
        # The RHS is a node class name, not an expression that needs type inference
        return node
    
    def visitLatticesBlock_N(self, node: LatticesBlock_N, ast_root_node: Program_N):
        """Process lattice instantiation statements."""
        for stmt in node.stmts:
            self.visit(stmt, ast_root_node)
        return node
    
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
        """Get shape of array type as List_N, or empty list for scalars."""
        if isinstance(expr_type, ArrayDataType_N):
            shape = expr_type.shape
            # Normalize shape to List_N format
            if isinstance(shape, List_N):
                return shape
            elif isinstance(shape, (IntLiteral_N, Identifier_N)):
                # 1D array with single dimension
                result = List_N(expr_type.code_range)
                result.elements = [shape]
                return result
            elif isinstance(shape, Array1DLiteral_N):
                # 2D+ array with Array1DLiteral_N shape
                return shape.value  # Return the List_N inside the Array1DLiteral_N
            else:
                # Unknown shape format, treat as empty
                return List_N(expr_type.code_range)
        else:
            # This shouldn't happen after our changes, but handle legacy code
            return List_N(expr_type.code_range if hasattr(expr_type, 'code_range') else None)
    
    def _denormalize_shape(self, normalized_shape, code_range):
        """Convert normalized List_N shape back to the appropriate format."""
        if not isinstance(normalized_shape, List_N):
            return normalized_shape
        
        num_dims = len(normalized_shape.elements)
        
        if num_dims == 0:
            # 0D (scalar) - return empty List_N
            return List_N(code_range)
        elif num_dims == 1:
            # 1D array - return the single IntLiteral_N directly
            return normalized_shape.elements[0]
        else:
            # 2D+ array - return Array1DLiteral_N
            return Array1DLiteral_N(code_range, normalized_shape)
    
    def _infer_binary_op_type(self, node, ast_root_node, op_category):
        """Infer type of binary operation based on operand types."""
        # First infer types of operands
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        
        left_type = node.left.inferred_type
        right_type = node.right.inferred_type
        
        if op_category == "arithmetic":
            # Arithmetic operations preserve types (with promotion rules)
            # For now, implement simple rules:
            # - If either operand is real, result is real
            # - Otherwise, result is int
            left_base = self._get_base_scalar_type(left_type)
            right_base = self._get_base_scalar_type(right_type)
            
            if left_base == "real" or right_base == "real":
                result_type = "real"
            else:
                result_type = "int"
            
            # For arithmetic ops, result shape follows broadcasting rules
            # Implement basic broadcasting: larger shape wins, or scalar broadcasts to array
            left_shape = self._get_shape_if_array(left_type)
            right_shape = self._get_shape_if_array(right_type)
            
            # Basic broadcasting rule: if one operand is scalar (0D), result takes shape of other operand
            # If both are arrays, they must have compatible shapes (for now, require identical shapes)
            left_dims = len(left_shape.elements)
            right_dims = len(right_shape.elements)
            
            if left_dims == 0 and right_dims == 0:
                # Both scalars -> scalar result
                result_shape = List_N(node.code_range)
            elif left_dims == 0:
                # Left is scalar, right is array -> result has right's shape
                result_shape = right_shape
            elif right_dims == 0:
                # Right is scalar, left is array -> result has left's shape  
                result_shape = left_shape
            else:
                # Both are arrays - for now, require identical shapes
                # TODO: Implement full broadcasting rules
                if left_dims == right_dims:
                    result_shape = left_shape  # Assume shapes are compatible
                else:
                    # For now, default to scalar if shapes are incompatible
                    result_shape = List_N(node.code_range)
            
            # Convert normalized List_N shape back to proper format
            final_shape = self._denormalize_shape(result_shape, node.code_range)
            node.inferred_type = ArrayDataType_N(node.code_range, result_type, final_shape)
        
        elif op_category == "comparison":
            # Comparison operations always return array[bool, ()]
            node.inferred_type = self._create_scalar_array_type(node.code_range, "bool")
        
        elif op_category == "logical":
            # Logical operations require bool operands and return array[bool, ()]
            node.inferred_type = self._create_scalar_array_type(node.code_range, "bool")
        
        return node
    
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
            raise GeLBException(
                f"Undefined lattice '{lattice_name}'",
                f"at {node.code_range}"
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
            
            # Pattern 1: Range from 0 to q-1 (or similar)
            if (isinstance(df_range.low, IntLiteral_N) and df_range.low.value == 0 and
                isinstance(df_range.high, Sub_N) and
                isinstance(df_range.high.left, Identifier_N) and df_range.high.left.name == "q" and
                isinstance(df_range.high.right, IntLiteral_N) and df_range.high.right.value == 1):
                is_full_range = True
            
            # Pattern 2: True colon range (low=None, high=None)
            elif df_range.low is None and df_range.high is None:
                is_full_range = True
            
            if is_full_range:
                # Full DF selection: f.in[x,y|:] or f.in[x,y|0:q-1] returns array of size q
                q_value = lattice_def.q
                if isinstance(q_value, IntLiteral_N):
                    shape_elements = [Identifier_N(node.code_range, "q")]
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
    
    def _evaluate_size_expression(self, expr, ast_root_node, array_dimensions=None):
        """Evaluate a size expression to get its integer value."""
        if isinstance(expr, IntLiteral_N):
            return expr.value
        elif isinstance(expr, Identifier_N):
            # Look up symbolic dimension (Nx, Ny, Nz, or constants)
            return self._resolve_symbolic_dimension(expr.name, ast_root_node, array_dimensions)
        else:
            # For now, return a reasonable default for complex expressions
            # TODO: Implement full constant expression evaluation
            return 1  # Placeholder
    
    def _resolve_symbolic_dimension(self, identifier_name, ast_root_node, array_dimensions=None):
        """Resolve symbolic dimension identifiers to their values."""
        # If we have array dimensions provided and this is Nx/Ny/Nz, use array dimensions first
        if array_dimensions and identifier_name in ['Nx', 'Ny', 'Nz']:
            dim_index = {'Nx': 0, 'Ny': 1, 'Nz': 2}[identifier_name]
            if dim_index < len(array_dimensions):
                return array_dimensions[dim_index]
        
        # Try to look up in current block's symbol table
        if self.current_block and self.current_block.symbol_defs:
            symbol_def = self.current_block.symbol_defs.get_symbol_definition(identifier_name)
            if symbol_def is None and self.current_block.symbol_defs.parent_table:
                symbol_def = self.current_block.symbol_defs.parent_table.get_symbol_definition(identifier_name)
            
            if symbol_def and hasattr(symbol_def, 'value'):
                if hasattr(symbol_def.value, 'value') and isinstance(symbol_def.value.value, IntLiteral_N):
                    return symbol_def.value.value.value
        
        # For implicit dimensions like Nx, Ny, Nz, try to extract from lattice
        if identifier_name in ['Nx', 'Ny', 'Nz']:
            return self._extract_grid_dimension(identifier_name, ast_root_node)
        
        # Default fallback for unknown dimensions
        return 1
    
    def _extract_grid_dimension(self, dim_name, ast_root_node):
        """Extract grid dimensions from lattice definitions."""
        # Look for lattice instantiations to get grid size
        if ast_root_node.lattices:
            for stmt in ast_root_node.lattices.stmts.elements:
                if isinstance(stmt, LatticeInstaStmt_N):
                    if hasattr(stmt, 'grid_size') and stmt.grid_size:
                        # Extract appropriate dimension from grid_size
                        if isinstance(stmt.grid_size, IntLiteral_N):
                            return stmt.grid_size.value  # 1D case
                        elif isinstance(stmt.grid_size, Array1DLiteral_N):
                            # Multi-dimensional case
                            if dim_name == 'Nx' and len(stmt.grid_size.value.elements) > 0:
                                return self._evaluate_size_expression(stmt.grid_size.value.elements[0], ast_root_node)
                            elif dim_name == 'Ny' and len(stmt.grid_size.value.elements) > 1:
                                return self._evaluate_size_expression(stmt.grid_size.value.elements[1], ast_root_node)
                            elif dim_name == 'Nz' and len(stmt.grid_size.value.elements) > 2:
                                return self._evaluate_size_expression(stmt.grid_size.value.elements[2], ast_root_node)
        
        # Fallback to reasonable defaults
        return {'Nx': 32, 'Ny': 32, 'Nz': 32}.get(dim_name, 1)
    
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
    
    def _validate_compile_time_evaluable(self, expr, context="range expression"):
        """Ensure expression can be evaluated at compile time."""
        if expr is None:
            return True  # None is valid (open-ended ranges)
        elif isinstance(expr, (IntLiteral_N, RealLiteral_N, BoolLiteral_N)):
            return True  # Literals are always compile-time
        elif isinstance(expr, Identifier_N):
            # Check if it's a compile-time constant or grid dimension
            if self._is_compile_time_constant(expr.name):
                return True
            else:
                # Variable is not a compile-time constant
                raise GeLBExTypeError(
                    expr,
                    f"Expression in {context} must be compile-time evaluable",
                    f"Variable '{expr.name}' is not allowed here. Only compile-time constants (literals, const values, or grid dimensions like Nx/Ny/Nz) are permitted in range expressions."
                )
        elif isinstance(expr, (Add_N, Sub_N, Mul_N, Div_N)):
            # Recursively check operands for arithmetic expressions
            self._validate_compile_time_evaluable(expr.left, context)
            self._validate_compile_time_evaluable(expr.right, context)
            return True
        else:
            # Any other expression type is not allowed
            raise GeLBExTypeError(
                expr,
                f"Expression in {context} must be compile-time evaluable",
                f"Complex expressions of type {type(expr).__name__} are not allowed in range expressions. Only literals, constants, and simple arithmetic with constants are permitted."
            )
    
    def _is_compile_time_constant(self, identifier_name):
        """Check if an identifier represents a compile-time constant."""
        # Grid dimensions (Nx, Ny, Nz) are compile-time constants
        if identifier_name in ['Nx', 'Ny', 'Nz']:
            return True
        
        # Check if it's a user-defined constant in symbol table
        if self.current_block and self.current_block.symbol_defs:
            symbol_def = self.current_block.symbol_defs.get_symbol_definition(identifier_name)
            if symbol_def is None and self.current_block.symbol_defs.parent_table:
                symbol_def = self.current_block.symbol_defs.parent_table.get_symbol_definition(identifier_name)
            
            if symbol_def:
                # Only actual constants are compile-time evaluable
                # Variables (even if they have assigned values) are NOT compile-time
                if symbol_def.tag in ["constant", "constant definition", 
                                     "implicit constant", "implicit dimension constant"]:
                    return True
                elif symbol_def.tag in ["variable", "variable declaration", 
                                       "output variable declaration"]:
                    # Variables are runtime values, not compile-time constants
                    return False
        
        return False
    
    def _evaluate_range_bound(self, expr, ast_root_node, array_dimensions=None):
        """Evaluate a range bound expression to get its integer value."""
        if expr is None:
            return None
        
        # First validate that the expression is compile-time evaluable
        self._validate_compile_time_evaluable(expr, "range bound")
        
        # Now evaluate the compile-time expression
        if isinstance(expr, IntLiteral_N):
            return expr.value
        elif isinstance(expr, Identifier_N):
            return self._resolve_symbolic_dimension(expr.name, ast_root_node, array_dimensions)
        elif isinstance(expr, Sub_N):
            # Handle expressions like "Nx-1"
            left_val = self._evaluate_range_bound(expr.left, ast_root_node, array_dimensions)
            right_val = self._evaluate_range_bound(expr.right, ast_root_node, array_dimensions)
            if left_val is not None and right_val is not None:
                return left_val - right_val
        elif isinstance(expr, Add_N):
            # Handle expressions like "i+1"
            left_val = self._evaluate_range_bound(expr.left, ast_root_node, array_dimensions)
            right_val = self._evaluate_range_bound(expr.right, ast_root_node, array_dimensions)
            if left_val is not None and right_val is not None:
                return left_val + right_val
        elif isinstance(expr, Mul_N):
            # Handle expressions like "N*2"
            left_val = self._evaluate_range_bound(expr.left, ast_root_node, array_dimensions)
            right_val = self._evaluate_range_bound(expr.right, ast_root_node, array_dimensions)
            if left_val is not None and right_val is not None:
                return left_val * right_val
        elif isinstance(expr, Div_N):
            # Handle expressions like "N/2"
            left_val = self._evaluate_range_bound(expr.left, ast_root_node, array_dimensions)
            right_val = self._evaluate_range_bound(expr.right, ast_root_node, array_dimensions)
            if left_val is not None and right_val is not None and right_val != 0:
                return left_val // right_val  # Integer division
        
        # If we get here, the validation should have caught it
        raise GeLBException(
            f"Failed to evaluate compile-time range bound: {expr}",
            f"This should have been caught by validation"
        )
    
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