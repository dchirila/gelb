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
    expression node containing its data type (ScalarDataType_N or ArrayDataType_N).
    
    The type inference rules are:
    - Literals have their obvious types (int, real, bool, etc.)
    - Identifiers get their types from symbol tables
    - Binary operations follow standard type promotion rules
    - Array literals have array types based on their structure
    - Lattice selections have array types based on the lattice definition
    """
    
    def __init__(self):
        super().__init__()
        # Track current block context for symbol lookup
        self.current_block = None
    
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
        """Variable declarations don't have expressions to infer."""
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
        """Integer literals have type 'int'."""
        node.inferred_type = ScalarDataType_N(node.code_range, "int")
        return node
    
    def visitRealLiteral_N(self, node: RealLiteral_N, ast_root_node: Program_N):
        """Real literals have type 'real'."""
        node.inferred_type = ScalarDataType_N(node.code_range, "real")
        return node
    
    def visitBoolLiteral_N(self, node: BoolLiteral_N, ast_root_node: Program_N):
        """Boolean literals have type 'bool'."""
        node.inferred_type = ScalarDataType_N(node.code_range, "bool")
        return node
    
    def visitStringLiteral_N(self, node: StringLiteral_N, ast_root_node: Program_N):
        """String literals have type 'string'."""
        node.inferred_type = ScalarDataType_N(node.code_range, "string")
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
            node.inferred_type = symbol_def.value.data_type
        elif symbol_def.tag == "variable" or symbol_def.tag == "variable declaration":
            # For variables, value is VariableDeclarationStmt_N
            node.inferred_type = symbol_def.value.data_type
        elif symbol_def.tag == "lattice":
            # For lattices, value is LatticeInstaStmt_N
            # A lattice reference itself doesn't have a type, only selections do
            raise GeLBException(
                f"Cannot infer type of lattice '{node.name}' directly",
                "Lattices must be accessed through selections like f.in[x,y|:]"
            )
        elif symbol_def.tag == "output variable declaration":
            # For gauge outputs, value is VariableDeclarationStmt_N  
            node.inferred_type = symbol_def.value.data_type
        elif symbol_def.tag == "implicit constant" or symbol_def.tag == "implicit dimension constant":
            # For implicit constants like Nx, Ny, Nz
            node.inferred_type = ScalarDataType_N(node.code_range, "int")
        elif symbol_def.tag == "implicit variable" or symbol_def.tag == "implicit lattice coordinate":
            # For implicit variables like x, y, z
            node.inferred_type = ScalarDataType_N(node.code_range, "int")
        else:
            # Handle any remaining cases
            if node.name in ['x', 'y', 'z']:
                node.inferred_type = ScalarDataType_N(node.code_range, "int")
            elif node.name in ['Nx', 'Ny', 'Nz']:
                node.inferred_type = ScalarDataType_N(node.code_range, "int")
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
        """Logical NOT requires bool operand and returns bool."""
        self.visit(node.expr, ast_root_node)
        node.inferred_type = ScalarDataType_N(node.code_range, "bool")
        return node
    
    def visitUnaryMinusExpr_N(self, node: UnaryMinusExpr_N, ast_root_node: Program_N):
        """Unary minus preserves the operand type."""
        self.visit(node.expr, ast_root_node)
        node.inferred_type = node.expr.inferred_type
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
        
        # For now, assume selection preserves array type
        # TODO: Implement proper shape inference based on ranges
        node.inferred_type = array_type
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
        """Extract scalar type from a DataType_N node."""
        if isinstance(data_type, ScalarDataType_N):
            return data_type.scalar_dtype
        elif isinstance(data_type, ArrayDataType_N):
            return data_type.scalar_dtype
        else:
            raise GeLBException(
                f"Unknown data type: {type(data_type).__name__}",
                "This is likely an internal compiler error"
            )
    
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
            
            node.inferred_type = ScalarDataType_N(node.code_range, result_type)
        
        elif op_category == "comparison":
            # Comparison operations always return bool
            node.inferred_type = ScalarDataType_N(node.code_range, "bool")
        
        elif op_category == "logical":
            # Logical operations require bool operands and return bool
            node.inferred_type = ScalarDataType_N(node.code_range, "bool")
        
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
        # For now, assume selections preserve the lattice df_type as array
        # TODO: Implement proper shape inference based on selection ranges
        
        # Get the df_type from lattice definition
        df_type = lattice_def.df_type
        if isinstance(df_type, ScalarDataType_N):
            base_type = df_type.scalar_dtype
        else:
            base_type = "real"  # Default to real if not specified
        
        # For now, return scalar type for single DF selection
        # TODO: This needs to be refined based on actual selection
        node.inferred_type = ScalarDataType_N(node.code_range, base_type)
        return node