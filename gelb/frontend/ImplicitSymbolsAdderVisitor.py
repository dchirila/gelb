#!/usr/bin/env python3

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.gelb_ast.ASTNodes import *
from gelb.gelb_ast.SymbolDefinition import SymbolDefinition


class ImplicitSymbolsAdderVisitor(ASTBaseVisitor):
    """
    Concrete visitor for adding to symbol_defs tables the symbols
    corresponding to the implicit variables & constants.

    Adds the following implicit symbols:
    - Nx, Ny, Nz: Grid dimensions (constants derived from geometry block)
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
        Main entry point. Extract grid dimensions from geometry and add
        implicit symbols to relevant blocks.
        """
        # First, extract grid dimensions from geometry block
        if node.geometry:
            self._extract_grid_dimensions(node.geometry)
        
        # Add implicit constants (Nx, Ny, Nz) to global_constants block
        if node.global_constants:
            self._add_dimension_constants(node.global_constants)
        else:
            # If there's no global_constants block, we still need Nx, Ny, Nz to be accessible
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
    
    def _extract_grid_dimensions(self, geometry_block):
        """
        Extract grid dimensions from the geometry block's set_grid_size call.
        """
        if not geometry_block.grid_size:
            # No grid size specified, use default 1D with size 1
            self.grid_dimensions = [IntLiteral_N(None, 1)]
            self.dimensionality = 1
            return
        
        grid_size = geometry_block.grid_size
        
        if isinstance(grid_size, IntLiteral_N):
            # 1D case: set_grid_size(32)
            self.grid_dimensions = [grid_size]
            self.dimensionality = 1
            
        elif isinstance(grid_size, Array1DLiteral_N):
            # Multi-dimensional case: set_grid_size({64, 32}) or set_grid_size({64, 32, 16})
            # grid_size.value is a List_N object containing the elements
            if hasattr(grid_size.value, 'elements'):
                self.grid_dimensions = grid_size.value.elements
                self.dimensionality = len(grid_size.value.elements)
            else:
                # Fallback: assume the value itself is a list-like
                self.grid_dimensions = grid_size.value
                self.dimensionality = len(grid_size.value)
            
        else:
            # Handle expressions (like identifiers that reference constants)
            # For now, assume 1D and use the expression as is
            self.grid_dimensions = [grid_size]
            self.dimensionality = 1
    
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
