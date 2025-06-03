#!/usr/bin/env python3

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.gelb_ast.ASTNodes import *
from gelb.gelb_ast.SymbolDefinition import SymbolDefinition


class ImplicitSymbolsAdderVisitor(ASTBaseVisitor):
    """
    Concrete visitor for adding to symbol_defs tables the symbols
    corresponding to the implicit variables & constants.

    Adds the following implicit symbols:
    - Nx, Ny, Nz: Grid dimensions (constants derived from lattices block grid_size)
    - x, y, z: Lattice site coordinates (like CUDA thread indices, uint64 at runtime)

    The x, y, z variables represent the current lattice site being processed,
    similar to threadIdx in CUDA. They are available in initializer, dynamic,
    and gauge blocks where lattice operations occur.

    NOTE: Should be invoked *after* SymbolsTablesBuilderVisitor (
    build_symbols_tables).
    """
    
    def __init__(self):
        super().__init__()
        self.grid_dimensions = None  # Will store [Nx_value, Ny_value, Nz_value]
        self.dimensionality = 0      # 1D, 2D, or 3D
    
    def visitProgram_N(self, node: Program_N, ast_root_node: Program_N):
        """
        Main entry point. Extract grid dimensions from lattices and add
        implicit symbols to relevant blocks.
        """
        # First, extract grid dimensions from lattices block
        if node.lattices:
            self._extract_grid_dimensions(node.lattices)
        
        # Add implicit constants (Nx, Ny, Nz) to the Program level symbol table
        if hasattr(node, 'symbol_defs') and node.symbol_defs is not None:
            self._add_dimension_constants_to_table(node.symbol_defs)
        else:
            # If Program doesn't have a symbol table yet, check if global_constants exists
            if node.global_constants:
                self._add_dimension_constants(node.global_constants)
            else:
                # Find the shared parent symbol table from any block that has one
                parent_table = self._find_shared_parent_table(node)
                if parent_table is not None and self.dimensionality > 0:
                    self._add_dimension_constants_to_table(parent_table)
        
        # Add implicit lattice coordinate variables (x, y, z) to blocks that need them
        blocks_needing_coordinates = []
        
        if node.initializers:
            blocks_needing_coordinates.extend(node.initializers)
            
        if node.dynamics:
            blocks_needing_coordinates.extend(node.dynamics)
            
        if node.gauges:
            blocks_needing_coordinates.extend(node.gauges)
        
        for block in blocks_needing_coordinates:
            self._add_lattice_coordinates(block)
        
        return node
    
    def _extract_grid_dimensions(self, lattices_block):
        """
        Extract grid dimensions from the lattices block's first lattice grid_size parameter.
        For GeLB v1, all lattices must have identical grid sizes.
        
        The lattice syntax is:
        lattice name(d, q, df_type, grid_size, periodicity);
        
        Examples:
        - 1D: lattice f(1, 1, int, 32, false);              // grid_size is IntLiteral_N(32)
        - 2D: lattice f(2, 9, real, {64, 32}, {true, false});  // grid_size is Array1DLiteral_N
        - 3D: lattice f(3, 27, real, {64, 32, 16}, {true, false, true});
        """
        if not lattices_block.stmts or not lattices_block.stmts.elements:
            # No lattices specified, use default 1D with size 1
            self.grid_dimensions = [IntLiteral_N(None, 1)]
            self.dimensionality = 1
            return
        
        # Get the first lattice instantiation statement
        first_lattice = lattices_block.stmts.elements[0]
        
        if not isinstance(first_lattice, LatticeInstaStmt_N):
            # Not a lattice instantiation, use default
            self.grid_dimensions = [IntLiteral_N(None, 1)]
            self.dimensionality = 1
            return
        
        if not hasattr(first_lattice, 'grid_size') or not first_lattice.grid_size:
            # No grid size specified, use default 1D with size 1
            self.grid_dimensions = [IntLiteral_N(None, 1)]
            self.dimensionality = 1
            return
        
        grid_size = first_lattice.grid_size
        
        if isinstance(grid_size, IntLiteral_N):
            # 1D case: lattice f(1, 1, int, 32, false)
            self.grid_dimensions = [grid_size]
            self.dimensionality = 1
            
        elif isinstance(grid_size, Array1DLiteral_N):
            # Multi-dimensional case: lattice f(2, 9, real, {64, 32}, {true, false})
            # grid_size.value is a List_N object containing the elements
            if hasattr(grid_size, 'value') and hasattr(grid_size.value, 'elements'):
                self.grid_dimensions = grid_size.value.elements
                self.dimensionality = len(grid_size.value.elements)
            elif hasattr(grid_size, 'value') and isinstance(grid_size.value, list):
                # Direct list case
                self.grid_dimensions = grid_size.value
                self.dimensionality = len(grid_size.value)
            else:
                # Fallback: treat as 1D
                self.grid_dimensions = [grid_size]
                self.dimensionality = 1
            
        else:
            # Handle expressions (like identifiers that reference constants)
            # For now, assume 1D and use the expression as is
            self.grid_dimensions = [grid_size]
            self.dimensionality = 1
            
        # Validate dimensionality matches the d parameter
        if hasattr(first_lattice, 'd') and isinstance(first_lattice.d, IntLiteral_N):
            expected_dim = first_lattice.d.value
            if expected_dim != self.dimensionality:
                # Log warning but continue - this should be caught by validation elsewhere
                pass
    
    def _add_dimension_constants(self, global_constants_block):
        """
        Add Nx, Ny, Nz constants to the global_constants symbol table.
        These represent the grid dimensions and are compile-time constants.
        """
        dimension_names = ['Nx', 'Ny', 'Nz']
        
        # The symbol table should already exist from SymbolsTablesBuilderVisitor
        if not hasattr(global_constants_block, 'symbol_defs') or global_constants_block.symbol_defs is None:
            raise ValueError("global_constants_block should have a symbol table by this point in the pipeline")
        
        # Add dimension constants based on actual dimensionality
        for i in range(self.dimensionality):
            dim_name = dimension_names[i]
            dim_value = self.grid_dimensions[i]
            
            # Create a symbol definition for the dimension constant
            symbol_def = SymbolDefinition(
                name=dim_name,
                tag="implicit dimension constant",
                value=dim_value
            )
            
            # Add to symbol table (only if not already present)
            if not global_constants_block.symbol_defs.contains_local(dim_name):
                global_constants_block.symbol_defs.append(symbol_def)
    
    def _add_lattice_coordinates(self, block):
        """
        Add x, y, z lattice coordinate variables to blocks that need them.
        
        These are like CUDA thread indices - they represent the current lattice
        site coordinates being processed. At runtime, they will be uint64 variables
        that range from 0 to Nx-1, Ny-1, Nz-1 respectively.
        """
        coordinate_names = ['x', 'y', 'z']
        
        # The symbol table should already exist from SymbolsTablesBuilderVisitor
        if not hasattr(block, 'symbol_defs') or block.symbol_defs is None:
            raise ValueError(f"{block.__class__.__name__} should have a symbol table by this point in the pipeline")
        
        # Add lattice coordinate variables based on dimensionality
        for i in range(self.dimensionality):
            coord_name = coordinate_names[i]
            
            # Create a synthetic identifier node for the coordinate variable
            # These will be uint64 variables at runtime, representing current lattice site
            coord_identifier = Identifier_N(None, coord_name)
            
            # Create a symbol definition for the lattice coordinate
            symbol_def = SymbolDefinition(
                name=coord_name,
                tag="implicit lattice coordinate",
                value=coord_identifier
            )
            
            # Add to symbol table (only if not already present)
            if not block.symbol_defs.contains_local(coord_name):
                block.symbol_defs.append(symbol_def)
    
    def _find_shared_parent_table(self, node):
        """
        Find the shared parent symbol table when there's no global_constants block.
        All blocks should share the same parent table created by SymbolsTablesBuilderVisitor.
        """
        # Check various blocks to find the parent table
        blocks_to_check = []
        if node.lattices:
            blocks_to_check.append(node.lattices)
        if node.initializers:
            blocks_to_check.extend(node.initializers)
        if node.dynamics:
            blocks_to_check.extend(node.dynamics)
        if node.gauges:
            blocks_to_check.extend(node.gauges)
        if node.geometry:
            blocks_to_check.append(node.geometry)
        
        for block in blocks_to_check:
            if hasattr(block, 'symbol_defs') and block.symbol_defs and hasattr(block.symbol_defs, 'parent_table'):
                return block.symbol_defs.parent_table
        
        return None
    
    def _add_dimension_constants_to_table(self, symbol_table):
        """
        Add Nx, Ny, Nz constants directly to a symbol table.
        Used when there's no global_constants block.
        """
        dimension_names = ['Nx', 'Ny', 'Nz']
        
        # Add dimension constants based on actual dimensionality
        for i in range(self.dimensionality):
            dim_name = dimension_names[i]
            dim_value = self.grid_dimensions[i]
            
            # Create a symbol definition for the dimension constant
            symbol_def = SymbolDefinition(
                name=dim_name,
                tag="implicit dimension constant",
                value=dim_value
            )
            
            # Add to symbol table (only if not already present)
            if not symbol_table.contains_local(dim_name):
                symbol_table.append(symbol_def)
