#!/usr/bin/env python3

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.gelb_ast.ASTNodes import *
from gelb.utils.exceptions import GeLBExTypeError


class ConstantsResolverVisitor(ASTBaseVisitor):
    """
    Concrete visitor for resolving ALL constants:
    - explicit AND implicit,
    - in AND scopes.

    As implicit constants, we need to resolve:
    - D ~> the dimensionality of the simulation
    - Q ~> the number of DFs of each lattice
    - Nx ~> size of the simulation domain along the X axis
    - [optional, if D>1] Ny ~> size of the simulation domain along the Y axis
    - [optional, if D>2] Nz ~> size of the simulation domain along the Z axis
    """
    def visitProgram_N(
            self,
            node: Program_N,
            ast_root_node: Program_N
    ):
        # resolve constants @GlobalConstantsBlock_N
        if node.global_constants is not None:
            node.global_constants = self.visit(
                node.global_constants, ast_root_node
            )
        
        # resolve constants @LatticesBlock_N
        if node.lattices is not None:
            node.lattices = self.visit(
                node.lattices, ast_root_node
            )
        return node

    def visitGlobalConstantsBlock_N(
            self,
            node: GlobalConstantsBlock_N,
            ast_root_node: Program_N
    ):
        for stmt in node.stmts:  # iterate over statements
            # first, get all symbol references @current statement
            referenced_symbols_rhs = stmt.value.get_referenced_symbols()
            # then, we obtain a set (no repetitions) of symbol reference
            # names, s.t. we can invoke =replace_symbol_references=
            referenced_symbols_names_rhs = set()
            for sref in referenced_symbols_rhs:
                referenced_symbols_names_rhs.add(
                    sref.name
                )
            # next, we iterate over the names of the referenced symbols,
            # and replace all of their occurrences with the actual definitions
            # NOTE: when we replace symbol occurrences, they are also
            #       automatically reflected in the SymbolsTable
            for srefname in referenced_symbols_names_rhs:
                sdef = node.symbol_defs.get_symbol_definition(
                    srefname
                ).value.value
                stmt.value.replace_symbol_references(
                    srefname,
                    sdef
                )
        return node

    def visitLatticesBlock_N(
            self,
            node: LatticesBlock_N,
            ast_root_node: Program_N
    ):
        """Resolve constants in lattice instantiation statements."""
        for stmt in node.stmts:  # iterate over lattice statements
            self.visit(stmt, ast_root_node)
        return node

    def visitLatticeInstaStmt_N(
            self,
            node: LatticeInstaStmt_N,
            ast_root_node: Program_N
    ):
        """Resolve constants in lattice instantiation parameters."""
        # Get the lattices block's symbol table which has hierarchical access to global constants
        parent_lattices_block = self._find_parent_lattices_block(ast_root_node)
        if parent_lattices_block is None or parent_lattices_block.symbol_defs is None:
            return node
        
        # Resolve constants in all parameter expressions
        expressions_to_resolve = [
            (node.d, "d parameter"),
            (node.q, "q parameter")
        ]
        
        # Add new parameters if they exist
        if hasattr(node, 'grid_size') and node.grid_size is not None:
            expressions_to_resolve.append((node.grid_size, "grid_size parameter"))
        if hasattr(node, 'periodicity') and node.periodicity is not None:
            expressions_to_resolve.append((node.periodicity, "periodicity parameter"))
        
        # Resolve constants in lattice parameters using the hierarchical symbol table
        # We need to get all referenced symbols in the entire lattice statement and replace them
        referenced_symbols = node.get_referenced_symbols()
        referenced_symbols_names = set()
        for sref in referenced_symbols:
            referenced_symbols_names.add(sref.name)
        
        # Filter out the lattice name itself - we only want to resolve constants, not the lattice being defined
        lattice_name = node.name.name if hasattr(node.name, 'name') else str(node.name)
        referenced_symbols_names.discard(lattice_name)
        
        # Replace each referenced symbol with its definition (only constants)
        for srefname in referenced_symbols_names:
            if parent_lattices_block.symbol_defs.contains(srefname):  # Uses hierarchical lookup
                symbol_def = parent_lattices_block.symbol_defs.get_symbol_definition(srefname)
                # Only resolve constants, not other symbol types
                if symbol_def.tag == "constant definition":
                    sdef = symbol_def.value.value
                    node.replace_symbol_references(srefname, sdef)
        
        # Validate lattice parameters after constants are resolved
        self._validate_lattice_parameters(node)
        
        return node

    def _find_parent_lattices_block(self, ast_root_node):
        """Find the lattices block in the program."""
        if hasattr(ast_root_node, 'lattices') and ast_root_node.lattices is not None:
            return ast_root_node.lattices
        return None
    
    def _extract_literal_value(self, expr):
        """
        Extract integer value from expression if it's a compile-time constant.
        Handles literals, unary minus, and simple arithmetic expressions.
        Returns None if the expression cannot be evaluated at compile time.
        """
        if isinstance(expr, IntLiteral_N):
            return expr.value
        elif isinstance(expr, UnaryMinusExpr_N):
            inner_value = self._extract_literal_value(expr.value)
            return -inner_value if inner_value is not None else None
        elif isinstance(expr, Add_N):
            left_val = self._extract_literal_value(expr.left)
            right_val = self._extract_literal_value(expr.right)
            return left_val + right_val if left_val is not None and right_val is not None else None
        elif isinstance(expr, Sub_N):
            left_val = self._extract_literal_value(expr.left)
            right_val = self._extract_literal_value(expr.right)
            return left_val - right_val if left_val is not None and right_val is not None else None
        elif isinstance(expr, Mul_N):
            left_val = self._extract_literal_value(expr.left)
            right_val = self._extract_literal_value(expr.right)
            return left_val * right_val if left_val is not None and right_val is not None else None
        elif isinstance(expr, Div_N):
            left_val = self._extract_literal_value(expr.left)
            right_val = self._extract_literal_value(expr.right)
            return left_val // right_val if left_val is not None and right_val is not None and right_val != 0 else None
        else:
            return None
    
    def _validate_lattice_parameters(self, node: LatticeInstaStmt_N):
        """
        Validate lattice instantiation parameters according to GeLB constraints:
        1. 1 <= d <= 3 (dimensionality)
        2. q > 0 (number of distribution functions)
        3. each element of grid_size should be > 0
        4. grid_size shape must match dimensionality d
        5. periodicity shape must match grid_size shape
        
        This validation happens after constants are resolved.
        """
        # Validate d (dimensionality): 1 <= d <= 3
        d_value = self._extract_literal_value(node.d)
        if d_value is not None:
            if not (1 <= d_value <= 3):
                raise GeLBExTypeError(
                    node.d,
                    f"Lattice dimensionality d={d_value} is invalid",
                    f"Dimensionality must be between 1 and 3 (inclusive), got {d_value}"
                )
        
        # Validate q (distribution functions): q > 0  
        q_value = self._extract_literal_value(node.q)
        if q_value is not None:
            if q_value <= 0:
                raise GeLBExTypeError(
                    node.q,
                    f"Number of distribution functions q={q_value} is invalid",
                    f"Number of distribution functions must be positive, got {q_value}"
                )
        
        # Validate grid_size: each element should be > 0
        if hasattr(node, 'grid_size') and node.grid_size is not None:
            self._validate_grid_size_positive(node.grid_size, node)
            
            # Validate grid_size shape matches dimensionality d
            if d_value is not None:
                self._validate_grid_size_shape(node.grid_size, d_value, node)
                
            # Validate periodicity shape matches grid_size shape
            if hasattr(node, 'periodicity') and node.periodicity is not None:
                self._validate_periodicity_shape(node.grid_size, node.periodicity, node)
    
    def _validate_grid_size_positive(self, grid_size, lattice_node):
        """Validate that all grid size values are positive."""
        grid_value = self._extract_literal_value(grid_size)
        if grid_value is not None:
            # 1D case: single integer
            if grid_value <= 0:
                raise GeLBExTypeError(
                    grid_size,
                    f"Grid size {grid_value} is invalid",
                    f"Grid size must be positive, got {grid_value}"
                )
        elif isinstance(grid_size, Array1DLiteral_N):
            # Multi-D case: array of integers
            for i, element in enumerate(grid_size.value.elements):
                element_value = self._extract_literal_value(element)
                if element_value is not None:
                    if element_value <= 0:
                        raise GeLBExTypeError(
                            element,
                            f"Grid size element [{i}] = {element_value} is invalid",
                            f"All grid size elements must be positive, got {element_value}"
                        )
    
    def _validate_grid_size_shape(self, grid_size, d_value, lattice_node):
        """Validate that grid_size shape matches the dimensionality d."""
        if isinstance(grid_size, IntLiteral_N) or isinstance(grid_size, UnaryMinusExpr_N):
            # Scalar grid_size is only valid for d=1
            if d_value != 1:
                raise GeLBExTypeError(
                    grid_size,
                    f"Grid size scalar is invalid for d={d_value}",
                    f"For d={d_value}, grid_size must be a {d_value}-element array, not a scalar"
                )
        elif isinstance(grid_size, Array1DLiteral_N):
            # Array grid_size: check number of elements matches d
            num_elements = len(grid_size.value.elements)
            if num_elements != d_value:
                raise GeLBExTypeError(
                    grid_size,
                    f"Grid size has {num_elements} elements but d={d_value}",
                    f"Grid size must have exactly {d_value} element{'s' if d_value > 1 else ''} to match dimensionality"
                )
    
    def _validate_periodicity_shape(self, grid_size, periodicity, lattice_node):
        """Validate that periodicity shape matches grid_size shape."""
        grid_is_scalar = isinstance(grid_size, (IntLiteral_N, UnaryMinusExpr_N))
        grid_is_array = isinstance(grid_size, Array1DLiteral_N)
        
        period_is_scalar = isinstance(periodicity, (BoolLiteral_N, Identifier_N))
        period_is_array = isinstance(periodicity, Array1DLiteral_N)
        
        if grid_is_scalar and period_is_array:
            raise GeLBExTypeError(
                periodicity,
                f"Periodicity is an array but grid_size is scalar",
                f"Periodicity must be scalar (true/false) to match scalar grid_size"
            )
        elif grid_is_array and period_is_scalar:
            grid_size_len = len(grid_size.value.elements)
            raise GeLBExTypeError(
                periodicity,
                f"Periodicity is scalar but grid_size has {grid_size_len} elements",
                f"Periodicity must be a {grid_size_len}-element boolean array to match grid_size"
            )
        elif grid_is_array and period_is_array:
            # Both are arrays - check they have same length
            grid_size_len = len(grid_size.value.elements)
            period_len = len(periodicity.value.elements)
            if grid_size_len != period_len:
                raise GeLBExTypeError(
                    periodicity,
                    f"Periodicity has {period_len} elements but grid_size has {grid_size_len}",
                    f"Periodicity must have exactly {grid_size_len} element{'s' if grid_size_len > 1 else ''} to match grid_size"
                )
