=====================
GeLB developer manual
=====================

Development Environment
=======================

* Prerequisites:

  - Python 3.12 or higher
  - Git for version control
  - Operating system: Windows, Linux, or macOS
  - Disk space: At least 500MB for the virtual environment and dependencies
  - Internet connection for the initial downloading of dependencies
  - Text editor or IDE with RST support (recommended)
  - Basic knowledge of command-line interfaces
  
  No Java installation is required as ANTLR4 tools are managed through Python packages.

* Set up the development environment:

  .. code-block:: bash

      # On Windows:
      .\scripts\gelb_bootstrap.ps1

      # On Unix/MacOS:
      ./scripts/gelb_bootstrap.sh

* Activate the virtual environment:

  .. code-block:: bash

      # On Windows:
      .\.venv\Scripts\activate

      # On Unix/MacOS:
      source .venv/bin/activate

* Install GeLB locally:

  .. code-block:: bash

      # Basic installation (core dependencies only)
      uv pip install -e .

      # Full installation with development tools
      uv sync --all-extras

  After installation, the ``gelbc`` command-line tool will be available in your environment.
  
  The ``-e`` flag installs the package in "editable" mode, meaning:
  
  * Changes to Python code are immediately reflected without reinstallation
  * However, you must reinstall (``uv pip install -e .``) if you modify:
    
    - ``pyproject.toml`` (dependencies, entry points)
    - Package metadata
    - Non-Python files

* Run the tests:

  .. code-block:: bash

      # Run all tests
      pytest

      # Run specific test file
      uv run pytest gelb/tests/type_inference/test_type_inference_paint_nodes.py

      # Run specific test class
      uv run pytest gelb/tests/type_inference/test_type_inference_paint_nodes.py::TestPaintNodesTypeInference

      # Run specific test method
      uv run pytest gelb/tests/type_inference/test_type_inference_paint_nodes.py::TestPaintNodesTypeInference::test_paint_nodes_with_constant_ranges

      # Alternative: Use -k to match test name pattern
      uv run pytest gelb/tests/type_inference/test_type_inference_paint_nodes.py -k "test_paint_nodes_with_constant_ranges"

      # Common pytest flags:
      # -x  : stop on first failure
      # -v  : verbose output
      # -s  : show print statements
      # -xvs: combine all three flags (recommended for debugging)

* Clean up generated files:

  .. code-block:: bash

      # On Windows:
      .\scripts\cleanup_repo.ps1

      # On Unix/MacOS:
      ./scripts/cleanup_repo.sh

* Regenerate ANTLR4 files:

  .. code-block:: bash

      # On Windows:
      .\scripts\regenerate_antlr.ps1

      # On Unix/MacOS:
      ./scripts/regenerate_antlr.sh

  Note: These scripts require the virtual environment to be set up first.
  They will regenerate all ANTLR4-generated files based on the GeLB grammar.
  The files are also automatically regenerated when running tests.

* Update dependencies:

  .. code-block:: bash

      # Dependencies are managed in pyproject.toml
      # To add a new dependency:
      uv add package-name
      
      # To add a development dependency:
      uv add --dev package-name

* Render RST files to HTML:

  .. code-block:: bash

      rst2html FILE.rst FILE.html


ANTLR4 Labels
=============

This section explains ANTLR4 labels, which are used throughout the GeLB grammar to make the generated parser code more readable and the visitor implementation cleaner.

What are ANTLR4 Labels?
-----------------------

ANTLR4 labels are annotations you can add to grammar rules to give names to rule elements. They make it easier to access specific parts of a parsed rule in your visitor or listener code.

Types of Labels
---------------

1. **Simple Labels (=)**
   
   Used to label a single element in a rule::

       variable_assignment_stmt :
           lhs=identifier OP_ASSIGN rhs=expr SEMICOLON ;

   In the visitor, you can access these as ``ctx.lhs`` and ``ctx.rhs`` instead of ``ctx.identifier()`` and ``ctx.expr()``.

2. **List Labels (+=)**
   
   Used when an element can appear multiple times::

       rect_sel_of_array_elems :
           array_name=identifier BRACKET_OPEN
           ranges+=coords_range (COMMA ranges+=coords_range)*
           BRACKET_CLOSE ;

   The ``+=`` operator collects all matching elements into a list. In the visitor, ``ctx.ranges`` will be a list containing all ``coords_range`` elements.

3. **Alternative Labels (#)**
   
   Used to label alternatives in a rule::

       coords_range : low=expr                  # singleElementRange
                    | low=expr COLON high=expr  # lowhighBoundRange
                    | low=expr COLON            # lowBoundRange
                    |          COLON high=expr  # highBoundRange
                    |          COLON            # allElementsRange
                    ;

   ANTLR generates separate visitor methods for each alternative: ``visitSingleElementRange()``, ``visitLowhighBoundRange()``, etc.

Benefits of Using Labels
------------------------

1. **More Readable Code**: Instead of ``ctx.expr(0)`` and ``ctx.expr(1)``, you can use ``ctx.left`` and ``ctx.right``.

2. **Self-Documenting Grammar**: Labels make the grammar easier to understand.

3. **Type Safety**: With labels, you know exactly what type to expect.

4. **Simplified Visitor Code**: Compare these two approaches:

   Without labels::

       def visitVariable_assignment_stmt(self, ctx):
           lhs = self.visit(ctx.identifier())
           rhs = self.visit(ctx.expr())

   With labels::

       def visitVariable_assignment_stmt(self, ctx):
           lhs = self.visit(ctx.lhs)
           rhs = self.visit(ctx.rhs)

Examples from GeLB Grammar
--------------------------

1. **Assignment Statement**::

       lattice_out_selection_assignment_stmt :
           lhs=rect_sel_of_lattice_out_dfs
           OP_ASSIGN
           rhs=expr
           SEMICOLON ;

2. **Array Selection with List Labels**::

       rect_sel_of_lattice_in_dfs:
           lattice_name=identifier DOT IN
           BRACKET_OPEN
           spatial_ranges+=coords_range (COMMA spatial_ranges+=coords_range)*
           dfs_range=lattice_dfs_range
           BRACKET_CLOSE ;

3. **Expression Alternatives**::

       expr : PAREN_OPEN expr PAREN_CLOSE                # parensExpr
            | left=expr op=(OP_MUL | OP_DIV) right=expr  # infixExpr
            | left=expr OP_AND right=expr                 # logicalAndExpr
            | value=NON_NEGATIVE_INT_LITERAL              # nonNegIntLiteralExpr
            ;

Important Gotchas
-----------------

When using ANTLR4 labels in Python projects, be aware of these potential issues:

1. **Python Keyword Conflicts**: If you use a label name that conflicts with a Python keyword, ANTLR4 automatically adds an underscore suffix to the generated Python code.

   Example::

       // In grammar:
       constant_definition_stmt : CONST type=data_type assignment=variable_assignment_stmt ;
       
       // In Python visitor:
       data_type = self.visit(ctx.type_)  # Note: type_ not type

   Common Python keywords to avoid: ``type``, ``class``, ``def``, ``if``, ``for``, ``while``, ``import``, etc.

2. **Grammar Rule Name Conflicts**: You cannot use a label name that matches an existing grammar rule name.

   Example::

       // This will cause an error:
       constant_definition_stmt : CONST data_type=data_type assignment=variable_assignment_stmt ;
       //                              ^^^^^^^^^ label name conflicts with rule name
       
       // Correct approach:
       constant_definition_stmt : CONST type=data_type assignment=variable_assignment_stmt ;

Best Practices
--------------

1. Use descriptive label names that indicate the role of the element
2. Be consistent with naming across similar rules
3. Use ``+=`` for elements that can repeat
4. Use ``#`` labels for alternatives that need different processing logic
5. Don't overuse labels - only add them where they improve clarity
6. Avoid Python keywords and existing grammar rule names when choosing label names
7. Document any keyword conflicts with comments in both grammar and visitor code

Abstract Syntax Tree (AST)
==========================

Definition: TODO

Despite their name, there is nothing abstract about the trees themselves
(although they can have size-induced complexity, for non-trivial programs).
Instead, the word "abstract" refers to the fact that some of the syntax is
"abstracted-away" (e.g. the AST for a language from the C family would not
include separator keywords, parentheses or the semicolon at the end of each
instruction). This is in contrast with *parse trees* (also known as *concrete
syntax trees*), which contain all of these low-level syntax elements.

"Each node of the tree denotes a construct occurring in the source code."

Benefits of using ASTs (& motivation for using them):

- They make program analysis and program transformation systems easier to
  implement (compared to working directly on the source-code, or on the parse
  trees).

- AST nodes can be enhanced with additional information, which is deduced as the
  AST passes through the different `MidWare` stages within the GeLB compiler
  (something which would be impossible if working directly with the source-code,
  and cumbersome if working with the syntax trees).


Types of Nodes in the GeLB AST
==============================

NOTEs:

- All AST Nodes inherit from the **Node** class, which has:

  - Attributes:

    - start
    - end

    NOTE: {start, end} are positions in the original input-stream, which
    allow us to provide more informative error-messages

  - Methods:

    - TODO

- **Program**

  - simulation_description -> **StringLit**
  - lattices -> **List** (**Lattice** )
  - node_classes -> **List** (**NodeClass**)
  - initializers -> **List** (**Initializer**)
  - dynamics -> **List** (**Dynamic**)
  - gauges -> **List** (**Gauge**)
  - functions -> **List** (**Function**)
  - geometry -> **StructuredGeometry** | **GeneralGeometry**

- **Lattice**
  TODO

- **NodeClass**
  TODO

- **Initializer**
  TODO

- **Dynamic**
  TODO

- **Gauge**
  TODO

- **Function**
  TODO

- **StructuredGeometry**
  TODO

- **Scalar** types

  - **BoolLit**
    TODO

  - **NumIntLit**
    TODO

  - **NumRealLit**
    TODO

  - **StringLit**
    TODO


Range Syntax and Resolution
===========================

GeLB supports flexible range syntax for selecting array elements, lattice sites, and distribution functions. Understanding how ranges work is crucial for compiler development.

Range Syntax
------------

GeLB supports four range patterns:

* ``:`` - All elements (e.g., ``nodes[:] = BULK``)
* ``low:`` - From ``low`` to end (e.g., ``nodes[5:] = BULK``)
* ``:high`` - From start to ``high`` (e.g., ``nodes[:10] = BULK``)
* ``low:high`` - Specific range (e.g., ``nodes[5:10] = BULK``)

Range patterns appear in multiple contexts:

* Geometry: ``nodes[:, :] = BULK`` (2D all nodes)
* Lattice selections: ``f.out[x, y | :]`` (all distribution functions)
* Array access: ``f.E[0, :]`` (all elements in second dimension)

AST Traversal Challenge
-----------------------

The range syntax creates ``Range_N`` AST nodes where missing bounds are represented as ``None``:

* ``:`` creates ``Range_N(low=None, high=None)``
* ``5:`` creates ``Range_N(low=5, high=None)``
* ``:10`` creates ``Range_N(low=None, high=10)``

This caused AST traversal methods to crash when encountering ``None`` values during recursive descent.

Resolution Strategy
-------------------

The issue was resolved with a two-part approach:

**Part 1: Defensive AST Methods**
  Added ``None`` checks to base ``Node_N`` class methods (see ``gelb/gelb_ast/ASTNodes.py``)::

    if child is None:  # Handle None fields
        continue

**Part 2: Range Resolution**
  Implemented ``RangeResolverVisitor`` (see ``gelb/frontend/RangeResolverVisitor.py``) that replaces ``None`` bounds with concrete expressions:

  * ``None`` lower bound → ``0``
  * ``None`` upper bound → ``Nx-1``, ``Ny-1``, or ``Nz-1`` (spatial dimensions)
  * ``None`` upper bound → ``q-1`` (distribution function ranges)

Integration
-----------

Range resolution runs in the compilation pipeline after symbol table construction::

    ast = build_symbols_tables(ast)
    ast = resolve_all_constants(ast)
    ast = resolve_ranges(ast)  # ← Range resolution here
    validate_node_classes(ast)

See ``gelb/gelbc.py`` for the complete pipeline and ``gelb/frontend/stage1_frontend.py`` for the ``resolve_ranges()`` function.

Testing
-------

Comprehensive tests cover various range scenarios in ``gelb/tests/more_frontend_validation/test_range_resolver_visitor.py``. All GeLB examples now compile successfully with proper range resolution.

Symbol Resolution and Hierarchical Lookup
==========================================

GeLB implements a hierarchical symbol resolution system that allows blocks to access symbols from global_constants while maintaining proper scoping rules. Understanding this system is crucial for compiler development and debugging.

Overview
--------

Symbol resolution in GeLB follows a hierarchical model where:

* ``global_constants`` serves as the top-level symbol table
* All other blocks (``lattices``, ``geometry``, ``node_classes``, etc.) have hierarchical access to global constants
* Local symbols always take precedence over global symbols (shadowing)
* Symbol lookup follows the chain: local scope → parent scope → error if not found

Architecture
------------

**SymbolsTable Class** (``gelb/frontend/SymbolsTable.py``)
  The core data structure implementing hierarchical lookup:

  * ``__init__(parent_table=None)`` - Creates table with optional parent reference
  * ``contains(symbol_name)`` - Hierarchical lookup (local first, then parent)
  * ``contains_local(symbol_name)`` - Local-only lookup (prevents infinite recursion)
  * ``get_symbol_definition(symbol_name)`` - Returns SymbolDefinition with hierarchical lookup
  * ``get_symbol_definition_local(symbol_name)`` - Returns SymbolDefinition from local scope only

**SymbolsTablesBuilderVisitor** (``gelb/frontend/SymbolsTablesBuilderVisitor.py``)
  Constructs the hierarchical symbol table structure:

  * Stores ``global_constants`` symbol table as ``self.global_constants_symbol_table``
  * Passes global_constants as parent table to all other blocks
  * Maintains proper scoping by using local-only methods for symbol addition

Symbol Lookup Rules
-------------------

**Lookup Order:**
  1. Check local symbol table first
  2. If not found and parent table exists, check parent recursively
  3. If not found anywhere, raise ``GeLBExSymbolUnknown``

**Conflict Resolution:**
  * Local symbols shadow global symbols (no error)
  * Duplicate symbols in the same scope raise ``GeLBExSymbolExists``
  * Cross-block references are resolved through parent lookup

Example Scenarios
-----------------

**Basic Global Constants Access:**

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

**Local Symbol Shadowing:**

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

**Error Cases:**

.. code-block:: gelb

    global_constants {
        const int KNOWN = 42;
    }

    lattices {
        lattice f(1, UNKNOWN, real);  // Error: UNKNOWN not defined anywhere
    }

Implementation Details
----------------------

**Symbol Storage:**
  * SymbolDefinition objects store: ``name`` (string), ``tag`` (string), ``value`` (AST node)
  * Names are stored as strings, not Identifier_N objects
  * Values contain the complete AST subtree for the symbol definition

**Parent Table Setup:**
  The hierarchical structure is established in ``SymbolsTablesBuilderVisitor.visitProgram_N()``:

  .. code-block:: python

      # Store global constants for use as parent table
      self.global_constants_symbol_table = node.global_constants.symbol_defs

      # Set up parent table for each block type
      if node.lattices:
          node.lattices.symbol_defs = SymbolsTable(self.global_constants_symbol_table)

      if node.geometry:
          node.geometry.symbol_defs = SymbolsTable(self.global_constants_symbol_table)

**Lookup Implementation:**
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
-------------------------------

Symbol resolution occurs early in the compilation pipeline:

.. code-block:: python

    ast = get_ast("gelb_program", input_string)
    validate_ast_root_is_program(ast)      # Ensure proper AST structure
    ast = build_symbols_tables(ast)        # ← Hierarchical setup happens here
    ast = resolve_all_constants(ast)       # Uses symbol resolution
    ast = resolve_ranges(ast)

The hierarchical symbol table structure is essential for later stages that need to resolve symbol references in expressions.

Testing
-------

Comprehensive tests cover the symbol resolution system in:

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

Debugging Symbol Resolution
---------------------------

**Common Issues:**
  1. **Symbol not found** - Check if symbol is defined in global_constants or local scope
  2. **Wrong symbol value** - Verify if local symbol is shadowing global symbol
  3. **Circular references** - Ensure constants don't reference themselves

**Debugging Tools:**
  * Print symbol table contents with ``repr(symbol_table)``
  * Check parent table chain: ``symbol_table.parent_table``
  * Use AST visualization to see symbol references
  * Run with ``--ast-stage symbols`` to see symbol table construction

**Debug Output Example:**

.. code-block:: python

    print("Local symbols:", ast.lattices.symbol_defs)
    print("Global symbols:", ast.global_constants.symbol_defs)
    print("Parent link:", ast.lattices.symbol_defs.parent_table is ast.global_constants.symbol_defs)

Best Practices
--------------

**For Compiler Development:**
  * Always use ``contains_local()`` when adding symbols to prevent conflicts
  * Use ``get_symbol_definition()`` for resolution (includes parent lookup)
  * Maintain parent table references correctly during AST transformations
  * Test both positive and negative cases (found/not found symbols)

**For Language Design:**
  * Keep global_constants as the single source of truth for global symbols
  * Avoid complex nested scoping (current implementation is two-level)
  * Use descriptive symbol names to minimize shadowing confusion
  * Document which blocks can access which symbol scopes

Implicit Symbols and Lattice Coordinates
========================================

GeLB automatically provides implicit symbols that represent grid dimensions and lattice site coordinates. These symbols are essential for lattice-based simulations and work similarly to CUDA thread indices, allowing each lattice site to know its position in the simulation grid.

Overview
--------

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
          // Use dimension constants for boundary detection
          if (x == 0 || x == Nx-1) {
              // Handle boundary conditions
              f.out[x,y | :] = boundary_value;
          }
      }

Implementation Architecture
---------------------------

**ImplicitSymbolsAdderVisitor** (``gelb/frontend/ImplicitSymbolsAdderVisitor.py``)
  The visitor that adds implicit symbols to the AST:

  * ``_extract_grid_dimensions()`` - Analyzes geometry block to determine dimensionality
  * ``_add_dimension_constants()`` - Adds Nx, Ny, Nz to global_constants
  * ``_add_lattice_coordinates()`` - Adds x, y, z to simulation blocks

**Grid Dimension Extraction:**
  .. code-block:: python

      if isinstance(grid_size, IntLiteral_N):
          # 1D case: set_grid_size(32)
          self.grid_dimensions = [grid_size]
          self.dimensionality = 1
      elif isinstance(grid_size, Array1DLiteral_N):
          # Multi-dimensional: set_grid_size({64, 32})
          self.grid_dimensions = grid_size.value.elements
          self.dimensionality = len(grid_size.value.elements)

**Symbol Addition:**
  .. code-block:: python

      # Add dimension constants to global_constants
      for i in range(self.dimensionality):
          dim_name = ['Nx', 'Ny', 'Nz'][i]
          symbol_def = SymbolDefinition(
              name=dim_name,
              tag="implicit dimension constant",
              value=self.grid_dimensions[i]
          )

**Compilation Pipeline Integration:**
  The implicit symbols are added after symbol table construction:

  .. code-block:: python

      ast = build_symbols_tables(ast)
      ast = add_implicit_symbols(ast)        # ← Implicit symbols added here
      ast = resolve_all_constants(ast)

Symbol Scoping Rules
--------------------

**Dimension Constants (Nx, Ny, Nz):**
  * Added to ``global_constants`` symbol table
  * Accessible in all blocks via hierarchical lookup
  * Take precedence: user-defined → implicit → error

**Lattice Coordinates (x, y, z):**
  * Added only to simulation blocks: ``initializer``, ``dynamic``, ``gauge``
  * Not added to structural blocks: ``lattices``, ``node_classes``, ``geometry``
  * Local to each block (no cross-block coordinate sharing)

**Duplicate Prevention:**
  * Implicit symbols are only added if not already defined by user
  * User-defined symbols always take precedence over implicit ones
  * No errors for shadowing implicit symbols

Advanced Usage Patterns
------------------------

**Neighbor Access Patterns:**
  .. code-block:: gelb

      dynamic StreamingStep {
          // Access neighbors using coordinate arithmetic
          // (Note: actual neighbor access syntax may vary)
          
          // Current site
          real center = f.in[x,y | 0];
          
          // Boundary-safe neighbor access would use modulo or conditionals
          if (x > 0) {
              real left = f.in[x-1,y | 0];
          }
      }

**Position-Dependent Initialization:**
  .. code-block:: gelb

      initializer PositionalInit {
          // Initialize based on lattice position
          real distance_from_center = sqrt((x - Nx/2)^2 + (y - Ny/2)^2);
          
          if (distance_from_center < Nx/4) {
              f.out[x,y | :] = equilibrium_distribution(1.0);  // High density
          } else {
              f.out[x,y | :] = equilibrium_distribution(0.1);  // Low density
          }
      }

**Multi-Scale Computations:**
  .. code-block:: gelb

      gauge GlobalAverages(out = {real avg_density;}) {
          // Each site contributes to global average
          // (Note: actual reduction syntax may vary)
          real local_density = f.in[x,y | :].sum();
          avg_density = local_density / (Nx * Ny);  // Normalize by grid size
      }

Testing and Validation
-----------------------

**Test Coverage** (``gelb/tests/test_implicit_symbols.py``):
  * ``test_1d_implicit_symbols()`` - Verifies Nx and x for 1D grids
  * ``test_2d_implicit_symbols()`` - Verifies Nx, Ny and x, y for 2D grids
  * ``test_3d_implicit_symbols()`` - Verifies Nx, Ny, Nz and x, y, z for 3D grids
  * ``test_implicit_symbols_no_duplicates()`` - Ensures user symbols take precedence
  * ``test_blocks_without_lattice_coordinates()`` - Verifies coordinates only in simulation blocks

**Real-World Examples:**
  * ``examples/basic/1d/ex0_int_vec_setto_one.gelb`` - 1D usage of x and Nx
  * ``examples/basic/1d/ex31_simple_constants_test.gelb`` - Constants with implicit symbols
  * All lattice-based examples use implicit coordinates

Debugging Implicit Symbols
---------------------------

**Common Issues:**
  1. **Missing coordinates** - Check if you're in the right block type (initializer/dynamic/gauge)
  2. **Wrong dimensionality** - Verify geometry block's ``set_grid_size()`` call
  3. **Shadowed symbols** - User-defined x, y, z, Nx, Ny, Nz take precedence

**Debug Commands:**
  * View symbol tables: ``gelbc --ast-stage symbols program.gelb``
  * Check grid dimensions in AST visualization
  * Print symbol table contents during development

**Debug Output Example:**
  .. code-block:: python

      # Check if implicit symbols were added
      print("Global constants:", ast.global_constants.symbol_defs)
      print("Initializer symbols:", ast.initializers[0].symbol_defs)
      
      # Verify dimensionality detection
      visitor = ImplicitSymbolsAdderVisitor()
      visitor._extract_grid_dimensions(ast.geometry)
      print("Detected dimensionality:", visitor.dimensionality)

Best Practices
--------------

**For Simulation Development:**
  * Use x, y, z as the primary coordinate variables in simulation blocks
  * Use Nx, Ny, Nz for boundary conditions and grid-size-dependent calculations
  * Avoid shadowing implicit symbols unless you have a specific need
  * Remember that coordinates represent the *current* lattice site being processed

**For Compiler Development:**
  * Always test implicit symbol addition with different grid dimensions
  * Ensure implicit symbols don't interfere with user-defined symbols
  * Verify that symbols are added to the correct block types only
  * Test with both literal and expression-based grid sizes

**Performance Considerations:**
  * Implicit coordinates will be uint64 variables at runtime
  * Grid dimensions are compile-time constants that can be optimized
  * Consider cache efficiency when accessing neighboring lattice sites

CUDA-Style Programming Model
----------------------------

The implicit coordinate system enables a CUDA-like programming model where:

**Each Lattice Site is a Thread:**
  * x, y, z represent the current thread's (lattice site's) coordinates
  * Each site executes the same code but operates on different data
  * Sites can be processed in parallel (hardware-dependent)

**Grid-Stride Loops:**
  * Grid dimensions (Nx, Ny, Nz) define the problem size
  * Runtime system handles iteration over all lattice sites
  * User code focuses on per-site computation

**Data Locality:**
  * Each site primarily accesses its own data: ``f[x,y | :]``
  * Neighbor access follows structured patterns
  * Memory access patterns are predictable for optimization

This programming model makes GeLB suitable for both CPU and GPU execution while maintaining a clean, mathematical notation for lattice-based algorithms.

AST Visualization
=================

GeLB includes a powerful AST visualization feature that generates visual representations of the Abstract Syntax Tree at various compilation stages. This is an essential tool for debugging, understanding compiler transformations, and documenting AST structure.

CLI Integration
---------------

The AST visualization is integrated into the ``gelbc`` compiler with the following options:

* ``--visualize-ast`` - Enable AST visualization
* ``--ast-output FILE`` - Specify output filename (default: ``<input_basename>_ast.<format>``)
* ``--ast-format {png,svg,pdf}`` - Output format (default: png)
* ``--ast-stage {parsing,symbols,constants,ranges,all}`` - Compilation stage to visualize (default: ranges)
* ``--keep-dot`` - Keep intermediate DOT file after generating visualization

Usage Examples
--------------

Generate AST visualization at the default stage (after range resolution)::

    gelbc --visualize-ast example.gelb

Visualize AST at a specific compilation stage::

    gelbc --visualize-ast --ast-stage parsing example.gelb

Generate visualizations for all compilation stages::

    gelbc --visualize-ast --ast-stage all example.gelb

Specify custom output and keep DOT file::

    gelbc --visualize-ast --ast-output my_ast.svg --keep-dot example.gelb

Compilation Stages
------------------

The AST can be visualized at four different compilation stages:

1. **parsing** - Raw AST immediately after parsing, with ``None`` values in range bounds
2. **symbols** - After symbol table construction
3. **constants** - After constant resolution
4. **ranges** - After range resolution (default) - ``None`` bounds replaced with concrete values

When using ``--ast-stage all``, separate files are generated for each stage with names like:

* ``example_ast_stage_parsing.png``
* ``example_ast_stage_symbols.png``
* ``example_ast_stage_constants.png``
* ``example_ast_stage_ranges.png``

Implementation Architecture
---------------------------

The visualization system consists of:

**ASTVisualizationVisitor** (``gelb/frontend/ASTVisualizationVisitor.py``)
  Inherits from ``ASTBaseVisitor`` and traverses the AST to generate Graphviz DOT format. Key features:

  * Generates unique node IDs for graph construction
  * Tracks tree depth for statistics
  * Creates compact, readable node labels
  * Implements color coding for different node types

**Visualization Pipeline** (``gelb/utils/ast_visualization.py``)
  The ``generate_ast_visualization()`` function orchestrates:

  1. DOT format generation via the visitor
  2. Writing DOT content to temporary file
  3. Invoking Graphviz ``dot`` command for rendering
  4. Optional cleanup of intermediate files
  5. Display of AST statistics (node count and max depth)

Visual Design
-------------

**Node Representation**
  Each AST node displays:

  * Node type (with ``_N`` suffix removed for clarity)
  * Key attributes:
    
    - Literal values for ``IntLiteral``, ``StringLiteral``, etc.
    - Identifier names for ``Identifier`` nodes
    - Operators for expression nodes (``+``, ``-``, ``*``, ``/``)
    - Data types for ``ScalarDataType`` nodes (e.g., ``int``, ``float``)
    - Range bounds for ``Range`` nodes (e.g., ``0:Nx-1``)

**Color Coding**
  A compact legend shows the color scheme:

  * **Light Blue** - Program structure (Program, blocks, Geometry)
  * **Light Green** - Literals (String, Int, Real, Bool)
  * **Light Yellow** - Identifiers and references
  * **Orange** - Operators and expressions
  * **Plum** - Statements and control flow
  * **Light Pink** - Ranges and selections
  * **Light Cyan** - Data types
  * **Light Gray** - Other nodes

**Graph Layout**
  * Top-to-bottom tree layout (``rankdir=TB``)
  * Edge labels show relationship names (e.g., ``lhs``, ``rhs``, ``[0]`` for list elements)
  * Compact node sizing with readable fonts

Statistics
----------

Each visualization includes statistics displayed as::

    📊 AST Statistics: 71 nodes, max depth: 8

This helps assess AST complexity and track how transformations affect tree structure.

Dependencies
------------

**Required:**
  * Graphviz must be installed and available in PATH
  * Python subprocess module (standard library)

**Error Handling:**
  * Compilation continues even if visualization fails
  * Clear error messages for missing Graphviz
  * Fallback to DOT file generation if rendering fails

Benefits
--------

**Development Benefits:**
  * Debug AST structure visually
  * Validate AST transformations between stages
  * Understand complex expression trees
  * Generate diagrams for documentation

**Educational Benefits:**
  * See how source code becomes AST
  * Track compiler transformation effects
  * Debug compilation issues visually

**Research Benefits:**
  * Analyze AST complexity metrics
  * Document language constructs visually
  * Compare different program structures
