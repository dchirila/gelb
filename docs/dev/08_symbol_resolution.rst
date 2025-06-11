============================
Symbol Resolution and Hierarchical Lookup
============================

GeLB implements a hierarchical symbol resolution system that allows blocks to access symbols from global_constants while maintaining proper scoping rules. Understanding this system is crucial for compiler development and debugging.

Overview
========

Symbol resolution in GeLB follows a hierarchical model where:

* ``global_constants`` serves as the top-level symbol table
* All other blocks (``lattices``, ``geometry``, ``node_classes``, etc.) have hierarchical access to global constants
* Local symbols always take precedence over global symbols (shadowing)
* Symbol lookup follows the chain: local scope → parent scope → error if not found

Architecture
============

SymbolsTable Class
------------------

The core data structure implementing hierarchical lookup (``gelb/frontend/SymbolsTable.py``):

* ``__init__(parent_table=None)`` - Creates table with optional parent reference
* ``contains(symbol_name)`` - Hierarchical lookup (local first, then parent)
* ``contains_local(symbol_name)`` - Local-only lookup (prevents infinite recursion)
* ``get_symbol_definition(symbol_name)`` - Returns SymbolDefinition with hierarchical lookup
* ``get_symbol_definition_local(symbol_name)`` - Returns SymbolDefinition from local scope only

SymbolsTablesBuilderVisitor
---------------------------

Constructs the hierarchical symbol table structure (``gelb/frontend/SymbolsTablesBuilderVisitor.py``):

* Stores ``global_constants`` symbol table as ``self.global_constants_symbol_table``
* Passes global_constants as parent table to all other blocks
* Maintains proper scoping by using local-only methods for symbol addition

Symbol Lookup Rules
====================

Lookup Order
------------

1. Check local symbol table first
2. If not found and parent table exists, check parent recursively
3. If not found anywhere, raise ``GeLBExSymbolUnknown``

Conflict Resolution
-------------------

* Local symbols shadow global symbols (no error)
* Duplicate symbols in the same scope raise ``GeLBExSymbolExists``
* Cross-block references are resolved through parent lookup

Example Scenarios
=================

Basic Global Constants Access
-----------------------------

.. code-block:: gelb

    global_constants {
        const int N = 64;
        const int Q = 9;
    }

    lattices {
        lattice f(1, Q, real);  // Q resolved from global_constants
    }

    geometry {
        set_grid_size(N);       // N resolved from global_constants
        nodes[:] = BULK;
    }

Local Symbol Shadowing
----------------------

.. code-block:: gelb

    global_constants {
        const int SIZE = 100;   // Global SIZE
    }

    lattices {
        // No local SIZE, uses global
        lattice f(1, 9, real);
    }

    // In another block (hypothetically):
    some_block {
        const int SIZE = 50;    // Local SIZE shadows global
        // References to SIZE here use local value (50)
    }

Error Cases
-----------

.. code-block:: gelb

    global_constants {
        const int KNOWN = 42;
    }

    lattices {
        lattice f(1, UNKNOWN, real);  // Error: UNKNOWN not defined anywhere
    }

Implementation Details
======================

Symbol Storage
--------------

* SymbolDefinition objects store: ``name`` (string), ``tag`` (string), ``value`` (AST node)
* Names are stored as strings, not Identifier_N objects
* Values contain the complete AST subtree for the symbol definition

Parent Table Setup
------------------

The hierarchical structure is established in ``SymbolsTablesBuilderVisitor.visitProgram_N()``:

.. code-block:: python

    # Store global constants for use as parent table
    self.global_constants_symbol_table = node.global_constants.symbol_defs

    # Set up parent table for each block type
    if node.lattices:
        node.lattices.symbol_defs = SymbolsTable(self.global_constants_symbol_table)

    if node.geometry:
        node.geometry.symbol_defs = SymbolsTable(self.global_constants_symbol_table)

Lookup Implementation
---------------------

The ``contains()`` method implements the hierarchical lookup:

.. code-block:: python

    def contains(self, symbol_name):
        # First check local scope
        if self.symbol_defs:
            for sdef in self.symbol_defs:
                if str(sdef.name) == symbol_name:
                    return True
        # Then check parent scope if available
        if self.parent_table:
            return self.parent_table.contains(symbol_name)
        return False

Compilation Pipeline Integration
===============================

Symbol resolution occurs early in the compilation pipeline:

.. code-block:: python

    ast = get_ast("gelb_program", input_string)
    validate_ast_root_is_program(ast)      # Ensure proper AST structure
    ast = build_symbols_tables(ast)        # ← Hierarchical setup happens here
    ast = resolve_all_constants(ast)       # Uses symbol resolution
    ast = resolve_ranges(ast)

The hierarchical symbol table structure is essential for later stages that need to resolve symbol references in expressions.

Implicit Symbols and Lattice Coordinates
=========================================

GeLB automatically provides implicit symbols that represent grid dimensions and lattice site coordinates. These symbols work similarly to CUDA thread indices, allowing each lattice site to know its position in the simulation grid.

Overview of Implicit Symbols
-----------------------------

GeLB provides two categories of implicit symbols:

**Dimension Constants (Nx, Ny, Nz):**
* Compile-time constants representing grid dimensions
* Derived from the ``set_grid_size()`` call in the geometry block
* Available in ``global_constants`` and all other blocks via hierarchical lookup

**Lattice Coordinates (x, y, z):**
* Runtime variables representing current lattice site coordinates
* Similar to CUDA ``threadIdx`` - each lattice site knows its position
* Available in ``initializer``, ``dynamic``, and ``gauge`` blocks
* Range from 0 to Nx-1, Ny-1, Nz-1 respectively (uint64 at runtime)

Dimension Detection
-------------------

The compiler automatically detects grid dimensionality from the geometry block:

**1D Programs:**

.. code-block:: gelb

    geometry {
        set_grid_size(32);          // Creates: Nx = 32
        nodes[:] = BULK;            // Available coordinates: x
    }

**2D Programs:**

.. code-block:: gelb

    geometry {
        set_grid_size({64, 32});    // Creates: Nx = 64, Ny = 32
        nodes[:,:] = BULK;          // Available coordinates: x, y
    }

**3D Programs:**

.. code-block:: gelb

    geometry {
        set_grid_size({64, 32, 16}); // Creates: Nx = 64, Ny = 32, Nz = 16
        nodes[:,:,:] = BULK;         // Available coordinates: x, y, z
    }

Lattice Coordinate Usage
------------------------

The x, y, z coordinates work like CUDA thread indices, representing the current lattice site being processed:

**Initializer Example:**

.. code-block:: gelb

    initializer SetInitialValues {
        // x, y represent the current lattice site coordinates
        f.out[x,y | :] = initial_density(x, y);
        
        // Each lattice site (x,y) executes this independently
        // x ranges from 0 to Nx-1, y ranges from 0 to Ny-1
    }

**Dynamic Example:**

.. code-block:: gelb

    dynamic CollisionStep {
        // Current lattice site coordinates are x, y
        // Access neighboring sites using offsets
        real density = f.in[x,y | :].sum();
        
        // Each site processes its local data
        f.out[x,y | :] = collision_operator(f.in[x,y | :]);
    }

**Gauge Example:**

.. code-block:: gelb

    gauge ComputeVelocity(out = {real u; real v;}) {
        // Extract velocity at current lattice site (x,y)
        {u, v} = compute_velocity(f.in[x,y | :]);
    }

Dimension Constants Usage
-------------------------

Nx, Ny, Nz constants are available throughout the program for boundary checks and computations:

**In Global Constants:**

.. code-block:: gelb

    global_constants {
        const int HALF_NX = Nx / 2;     // Use Nx in expressions
        const real DX = 1.0 / Nx;       // Grid spacing calculation
    }

**In Expressions:**

.. code-block:: gelb

    dynamic BoundaryConditions {
        // Use dimension constants in boundary calculations
        real distance_from_edge = x * (Nx - 1 - x);
        f.out[x,y | :] = base_value + distance_from_edge;
    }

Implementation Architecture
===========================

ImplicitSymbolsAdderVisitor
---------------------------

The visitor that adds implicit symbols to the AST (``gelb/frontend/ImplicitSymbolsAdderVisitor.py``):

* ``_extract_grid_dimensions()`` - Analyzes geometry block to determine dimensionality
* ``_add_dimension_constants()`` - Adds Nx, Ny, Nz to global_constants
* ``_add_lattice_coordinates()`` - Adds x, y, z to simulation blocks

Grid Dimension Extraction
--------------------------

.. code-block:: python

    if isinstance(grid_size, IntLiteral_N):
        # 1D case: set_grid_size(32)
        self.grid_dimensions = [grid_size]
        self.dimensionality = 1
    elif isinstance(grid_size, Array1DLiteral_N):
        # Multi-dimensional: set_grid_size({64, 32})
        self.grid_dimensions = grid_size.value.elements
        self.dimensionality = len(grid_size.value.elements)

Symbol Addition
---------------

.. code-block:: python

    # Add dimension constants to global_constants
    for i in range(self.dimensionality):
        dim_name = ['Nx', 'Ny', 'Nz'][i]
        symbol_def = SymbolDefinition(
            name=dim_name,
            tag="implicit dimension constant",
            value=self.grid_dimensions[i]
        )

Compilation Pipeline Integration
--------------------------------

The implicit symbols are added after symbol table construction:

.. code-block:: python

    ast = build_symbols_tables(ast)
    ast = add_implicit_symbols(ast)        # ← Implicit symbols added here
    ast = resolve_all_constants(ast)

Symbol Scoping Rules
====================

Dimension Constants (Nx, Ny, Nz)
---------------------------------

* Added to ``global_constants`` symbol table
* Accessible in all blocks via hierarchical lookup
* Take precedence: user-defined → implicit → error

Lattice Coordinates (x, y, z)
------------------------------

* Added only to simulation blocks: ``initializer``, ``dynamic``, ``gauge``
* Not added to structural blocks: ``lattices``, ``node_classes``, ``geometry``
* Local to each block (no cross-block coordinate sharing)

Duplicate Prevention
--------------------

* Implicit symbols are only added if not already defined by user
* User-defined symbols always take precedence over implicit ones
* No errors for shadowing implicit symbols

Constants in Lattice Parameter Validation
==========================================

Constants defined in ``global_constants`` are resolved and validated when used in lattice parameters. This validation occurs in the **ConstantsResolverVisitor** after constants are fully resolved.

Hierarchical Constant Access
----------------------------

The ``lattices`` block can access constants from ``global_constants`` via hierarchical symbol lookup:

.. code-block:: gelb

    global_constants {
        const int N = 64;
        const int D = 2;
        const int Q = 9;
    }
    
    lattices {
        lattice f(D, Q, int, {N, N}, {false, true});  // All constants resolved
    }

Constant Expression Evaluation
------------------------------

The system evaluates arithmetic expressions before validation:

.. code-block:: gelb

    global_constants {
        const int BASE_SIZE = 32;
        const int DOUBLE_SIZE = BASE_SIZE * 2;      // Resolves to 64
        const int INVALID_SIZE = BASE_SIZE - 40;    // Resolves to -8
    }
    
    lattices {
        lattice f(1, 1, int, DOUBLE_SIZE, false);   // Valid: 64 > 0
        lattice g(1, 1, int, INVALID_SIZE, false);  // Error: -8 <= 0
    }

The constant ``INVALID_SIZE`` is resolved to ``-8`` before validation, triggering:
``Error: Grid size -8 is invalid. Grid size must be positive, got -8``

Complex Expression Support
---------------------------

The validation system handles complex constant expressions with proper precedence:

.. code-block:: gelb

    global_constants {
        const int A = 10;
        const int B = 5;
        const int COMPLEX = (A + B) * 2 - A;  // Resolves to: (10+5)*2-10 = 20
    }
    
    lattices {
        lattice f(1, 1, int, COMPLEX, false);  // Valid: COMPLEX = 20
    }

**Supported Operations:**
- Addition (``+``), Subtraction (``-``), Multiplication (``*``), Division (``/``)
- Unary minus (``-EXPR``)
- Parentheses for precedence override

Validation Error Examples
-------------------------

When constants evaluate to invalid values, clear error messages are generated:

.. code-block:: gelb

    global_constants {
        const int BAD_D = 5;        // Invalid dimensionality
        const int BAD_Q = -2;       // Invalid distribution functions
        const int BAD_SIZE = -16;   // Invalid grid size
    }
    
    lattices {
        lattice f(BAD_D, BAD_Q, int, BAD_SIZE, false);
    }

This generates multiple validation errors:
- ``Lattice dimensionality d=5 is invalid. Dimensionality must be between 1 and 3 (inclusive), got 5``
- ``Number of distribution functions q=-2 is invalid. Number of distribution functions must be positive, got -2``
- ``Grid size -16 is invalid. Grid size must be positive, got -16``

Array Shape Validation
----------------------

Constants are also used in array shape validation for multi-dimensional lattices:

.. code-block:: gelb

    global_constants {
        const int Nx = 64;
        const int Ny = 32;
        const int D = 2;
    }
    
    lattices {
        // Valid: d=2 matches 2-element arrays
        lattice f(D, 9, int, {Nx, Ny}, {false, true});
        
        // Error: d=1 but grid_size has 2 elements  
        lattice g(1, 9, int, {Nx, Ny}, false);
    }

The shape mismatch error shows resolved values:
``Grid size has 2 elements but d=1. Grid size must have exactly 1 element to match dimensionality``

Testing
=======

Test Coverage
-------------

**Unit Tests** (``gelb/tests/symbols_table/test_hierarchical_symbol_resolution.py``):
* ``test_symbols_table_parent_lookup()`` - Core hierarchical functionality
* ``test_symbols_table_local_precedence()`` - Shadowing behavior
* ``test_symbols_table_duplicate_prevention()`` - Error handling

**Integration Tests:**
* ``test_lattices_with_global_constants_integration()`` - Cross-block access
* ``test_real_world_integration_ex31_style()`` - Complete program scenarios

**Real-World Examples:**
* ``examples/basic/1d/ex30_constants_in_blocks.gelb`` - Complex constant usage
* ``examples/basic/1d/ex31_simple_constants_test.gelb`` - Simple test case

**Implicit Symbols Tests** (``gelb/tests/test_implicit_symbols.py``):
* ``test_1d_implicit_symbols()`` - Verifies Nx and x for 1D grids
* ``test_2d_implicit_symbols()`` - Verifies Nx, Ny and x, y for 2D grids
* ``test_3d_implicit_symbols()`` - Verifies Nx, Ny, Nz and x, y, z for 3D grids
* ``test_implicit_symbols_no_duplicates()`` - Ensures user symbols take precedence
* ``test_blocks_without_lattice_coordinates()`` - Verifies coordinates only in simulation blocks

Debugging Symbol Resolution
============================

Common Issues
-------------

1. **Symbol not found** - Check if symbol is defined in global_constants or local scope
2. **Wrong symbol value** - Verify if local symbol is shadowing global symbol
3. **Circular references** - Ensure constants don't reference themselves

Debugging Tools
---------------

* Print symbol table contents with ``repr(symbol_table)``
* Check parent table chain: ``symbol_table.parent_table``
* Use AST visualization to see symbol references
* Run with ``--ast-stage symbols`` to see symbol table construction

Debug Output Example
--------------------

.. code-block:: python

    print("Local symbols:", ast.lattices.symbol_defs)
    print("Global symbols:", ast.global_constants.symbol_defs)
    print("Parent link:", ast.lattices.symbol_defs.parent_table is ast.global_constants.symbol_defs)

Best Practices
==============

For Compiler Development
------------------------

* Always use ``contains_local()`` when adding symbols to prevent conflicts
* Use ``get_symbol_definition()`` for resolution (includes parent lookup)
* Maintain parent table references correctly during AST transformations
* Test both positive and negative cases (found/not found symbols)

For Language Design
-------------------

* Keep global_constants as the single source of truth for global symbols
* Avoid complex nested scoping (current implementation is two-level)
* Use descriptive symbol names to minimize shadowing confusion
* Document which blocks can access which symbol scopes

CUDA-Style Programming Model
============================

The implicit coordinate system enables a CUDA-like programming model where:

**Each Lattice Site is a Thread:**
* x, y, z represent the current thread's (lattice site's) coordinates
* Each site executes the same code but operates on different data
* Sites can be processed in parallel (hardware-dependent)

**Implicit Grid Iteration:**
* Grid dimensions (Nx, Ny, Nz) define the problem size
* Runtime system automatically iterates over all lattice sites
* User code focuses on per-site computation without explicit iteration

**Data Locality:**
* Each site primarily accesses its own data: ``f[x,y | :]``
* Neighbor access follows structured patterns
* Memory access patterns are predictable for optimization

This programming model makes GeLB suitable for both CPU and GPU execution while maintaining a clean, mathematical notation for lattice-based algorithms.