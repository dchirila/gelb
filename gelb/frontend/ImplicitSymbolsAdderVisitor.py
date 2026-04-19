#!/usr/bin/env python3

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.frontend.implicit_symbols import (
    TIMESTEP_SYMBOL_NAME,
    active_coordinate_names,
    active_dimension_names,
    grid_dimensions_from_lattices,
)
from gelb.gelb_ast.ASTNodes import *
from gelb.gelb_ast.SymbolDefinition import SymbolDefinition


class ImplicitSymbolsAdderVisitor(ASTBaseVisitor):
    """
    Concrete visitor for adding to symbol_defs tables the symbols
    corresponding to the implicit variables & constants.

    Adds the following implicit symbols:
    - Nx, Ny, Nz: Grid dimensions (constants derived from lattices block grid_size)
    - x, y, z: Lattice site coordinates (like CUDA thread indices, uint64 at runtime)
    - t:        Current iteration index (0 during the pre-loop gauge snapshot of
                initial conditions, 1..num_timesteps during the main time loop)

    The x, y, z variables represent the current lattice site being processed,
    similar to threadIdx in CUDA. The t variable is the current outer-loop
    iteration and enables time-dependent forcing, ramps, pulses, etc. All
    four are available in initializer, dynamic, and gauge blocks where
    lattice operations occur.

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
        # First, extract grid dimensions from lattices block.  The rank of
        # grid_size was validated against d when the symbol tables were
        # built, so the shape can be trusted here.
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
            self._add_timestep_symbol(block)

        # The geometry block gets the coordinates too: a `where` paint
        # predicate is evaluated per cell with x, y, z bound to that
        # cell.  It does not get `t`: the geometry is fixed for the run.
        if node.geometry is not None and node.geometry.symbol_defs is not None:
            self._add_lattice_coordinates(node.geometry)

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
        self.grid_dimensions = grid_dimensions_from_lattices(lattices_block)
        self.dimensionality = len(self.grid_dimensions)
    
    def _add_dimension_constants(self, global_constants_block):
        """
        Add Nx, Ny, Nz constants to the global_constants symbol table.
        These represent the grid dimensions and are compile-time constants.
        """
        # The symbol table should already exist from SymbolsTablesBuilderVisitor
        if not hasattr(global_constants_block, 'symbol_defs') or global_constants_block.symbol_defs is None:
            raise ValueError("global_constants_block should have a symbol table by this point in the pipeline")
        
        # Add dimension constants based on actual dimensionality
        for i, dim_name in enumerate(active_dimension_names(self.dimensionality)):
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
        # The symbol table should already exist from SymbolsTablesBuilderVisitor
        if not hasattr(block, 'symbol_defs') or block.symbol_defs is None:
            raise ValueError(f"{block.__class__.__name__} should have a symbol table by this point in the pipeline")
        
        # Add lattice coordinate variables based on dimensionality
        for coord_name in active_coordinate_names(self.dimensionality):
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
    
    def _add_timestep_symbol(self, block):
        """
        Add the implicit timestep variable ``t`` to blocks that need it.

        ``t`` is a scalar ``int`` holding the current outer-loop iteration
        index. It is 0 during the pre-loop gauge pass (which captures the
        initial conditions) and ranges over 1..num_timesteps during the
        main time loop. Unlike ``x``/``y``/``z``, which are added only for
        the dimensions the lattice actually has, ``t`` is added
        unconditionally to every initializer/dynamic/gauge block.

        Not added if the user has already defined a symbol of the same name
        (e.g. a global constant ``const int t = 5``) -- in that case the
        user-defined symbol wins, mirroring the ``x``/``y``/``z`` policy.
        """
        if not hasattr(block, 'symbol_defs') or block.symbol_defs is None:
            raise ValueError(f"{block.__class__.__name__} should have a symbol table by this point in the pipeline")

        # Synthetic identifier for the timestep variable; the backend maps
        # this name to the outer time-loop iterator (gelb_timestep in the
        # Fortran backends).
        t_identifier = Identifier_N(None, TIMESTEP_SYMBOL_NAME)

        symbol_def = SymbolDefinition(
            name=TIMESTEP_SYMBOL_NAME,
            tag="implicit timestep variable",
            value=t_identifier,
        )

        if not block.symbol_defs.contains_local(TIMESTEP_SYMBOL_NAME):
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
        # Add dimension constants based on actual dimensionality
        for i, dim_name in enumerate(active_dimension_names(self.dimensionality)):
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
