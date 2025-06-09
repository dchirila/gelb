==================
Debugging Tools
==================

GeLB provides comprehensive debugging tools to help developers understand compilation issues, visualize AST structures, and troubleshoot type system problems.

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
    - Data types for ``ArrayDataType`` nodes (e.g., ``int``, ``real``)
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

Range Syntax Resolution Debugging
=================================

GeLB supports flexible range syntax for selecting array elements, lattice sites, and distribution functions. The range resolution system can be debugged when issues arise.

Range Syntax Patterns
---------------------

GeLB supports four range patterns:

* ``:`` - All elements (e.g., ``nodes[:] = BULK``)
* ``low:`` - From ``low`` to end (e.g., ``nodes[5:] = BULK``)
* ``:high`` - From start to ``high`` (e.g., ``nodes[:10] = BULK``)
* ``low:high`` - Specific range (e.g., ``nodes[5:10] = BULK``)

AST Representation Challenge
---------------------------

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

Debugging Range Issues
---------------------

**Common Range Problems:**
1. **Missing grid dimensions** - Nx, Ny, Nz not available
2. **Wrong dimensionality** - 2D ranges used in 1D context
3. **Bounds checking** - Range exceeds array dimensions

**Debug Techniques:**
1. **Visualize before/after range resolution**::

    gelbc --visualize-ast --ast-stage parsing program.gelb
    gelbc --visualize-ast --ast-stage ranges program.gelb

2. **Check implicit symbols**::
    
    # Verify Nx, Ny, Nz are added to global_constants
    print(ast.global_constants.symbol_defs)

3. **Inspect range nodes directly**::

    def debug_ranges(ast):
        class RangeDebugger(ASTBaseVisitor):
            def visitRange_N(self, node, ast_root):
                print(f"Range: low={node.low}, high={node.high}")
                return node
        
        debugger = RangeDebugger()
        debugger.visit(ast, ast)

Symbol Table Debugging
======================

Symbol resolution issues can be debugged using several techniques:

Symbol Table Inspection
-----------------------

**Print Symbol Tables:**

.. code-block:: python

    def debug_symbols(ast):
        print("Global constants:", ast.global_constants.symbol_defs)
        print("Lattices symbols:", ast.lattices.symbol_defs if ast.lattices else None)
        
        # Check parent relationships
        if ast.lattices and ast.lattices.symbol_defs:
            print("Parent link:", ast.lattices.symbol_defs.parent_table)

**Symbol Lookup Testing:**

.. code-block:: python

    def test_symbol_lookup(symbol_table, symbol_name):
        print(f"Looking up '{symbol_name}':")
        print(f"  Local: {symbol_table.contains_local(symbol_name)}")
        print(f"  Hierarchical: {symbol_table.contains(symbol_name)}")
        
        if symbol_table.contains(symbol_name):
            symbol_def = symbol_table.get_symbol_definition(symbol_name)
            print(f"  Definition: {symbol_def}")

**Common Symbol Issues:**
1. **Symbol not found** - Check if defined in appropriate scope
2. **Wrong symbol value** - Verify shadowing relationships
3. **Circular references** - Ensure constants don't reference themselves

Type System Debugging
=====================

Type-related issues can be complex to debug due to the multi-phase type processing.

Type Information Inspection
---------------------------

**Check Inferred Types:**

.. code-block:: python

    def debug_types(ast):
        class TypeDebugger(ASTBaseVisitor):
            def visitExpr_N(self, node, ast_root):
                if hasattr(node, 'inferred_type'):
                    print(f"{type(node).__name__}: {node.inferred_type}")
                return node
        
        debugger = TypeDebugger()
        debugger.visit(ast, ast)

**Check Type Promotions:**

.. code-block:: python

    def debug_promotions(ast):
        class PromotionDebugger(ASTBaseVisitor):
            def visitTypePromotionNode_N(self, node, ast_root):
                print(f"Promoted {node.expr.inferred_type} → {node.target_type}")
                return node
        
        debugger = PromotionDebugger()
        debugger.visit(ast, ast)

**Stage-by-Stage Type Debugging:**

.. code-block:: python

    def debug_type_pipeline(source_code):
        # After type inference
        ast = get_typed_ast(source_code)
        print("After inference:", expr.inferred_type)
        
        # After promotion
        ast = promote_types(ast)
        print("After promotion:", type(expr))
        
        # After validation (should not raise)
        ast = validate_types(ast)
        print("Validation passed")

Compilation Pipeline Debugging
==============================

Debug the complete compilation pipeline systematically:

Pipeline Stage Isolation
------------------------

**Test Each Stage Individually:**

.. code-block:: python

    def debug_pipeline_stages(source_code):
        try:
            # Stage 1: Frontend
            ast = compile_frontend(source_code)
            print("✓ Frontend completed")
        except Exception as e:
            print(f"✗ Frontend failed: {e}")
            return
        
        try:
            # Stage 2: Midware
            ast = process_ast(ast)
            print("✓ Midware completed")
        except Exception as e:
            print(f"✗ Midware failed: {e}")
            return
        
        try:
            # Stage 3: Backend
            code = generate_code(ast, "fortran")
            print("✓ Backend completed")
        except Exception as e:
            print(f"✗ Backend failed: {e}")

**Compare AST at Different Stages:**

.. code-block:: bash

    # Generate visualization at each stage
    gelbc --visualize-ast --ast-stage all program.gelb
    
    # Compare the generated images to see transformations

Error Message Enhancement
========================

When debugging, enhance error messages with additional context:

**Custom Exception Handling:**

.. code-block:: python

    def enhanced_compile(source_code):
        try:
            return compile_frontend(source_code)
        except GeLBExTypeError as e:
            print(f"Type Error at {e.code_range}:")
            print(f"  Message: {e.message}")
            print(f"  Context: {e.context}")
            raise
        except GeLBExSymbolUnknown as e:
            print(f"Symbol Error: {e.symbol_name} not found")
            print(f"  Available symbols: {get_available_symbols()}")
            raise

**Add Debug Information to AST Nodes:**

.. code-block:: python

    def add_debug_info(node, info):
        """Add debug information to AST nodes."""
        if not hasattr(node, '_debug_info'):
            node._debug_info = []
        node._debug_info.append(info)

Performance Debugging
=====================

Debug compilation performance issues:

**Profile Compilation Time:**

.. code-block:: python

    import time
    import cProfile

    def profile_compilation(source_code):
        profiler = cProfile.Profile()
        profiler.enable()
        
        ast = compile_frontend(source_code)
        
        profiler.disable()
        profiler.print_stats(sort='cumulative')

**Memory Usage Monitoring:**

.. code-block:: python

    import tracemalloc

    def monitor_memory(source_code):
        tracemalloc.start()
        
        ast = compile_frontend(source_code)
        
        current, peak = tracemalloc.get_traced_memory()
        print(f"Current memory: {current / 1024 / 1024:.1f} MB")
        print(f"Peak memory: {peak / 1024 / 1024:.1f} MB")
        
        tracemalloc.stop()

Best Practices for Debugging
============================

**Systematic Approach:**
1. Isolate the problem to a specific compilation stage
2. Create minimal test cases that reproduce the issue
3. Use visualization tools to understand AST structure
4. Add targeted debug output at suspected problem points
5. Test fixes with comprehensive test cases

**Debug-Friendly Development:**
* Add debug output to new visitors and transformations
* Use descriptive variable names and comments
* Implement comprehensive error handling
* Create debug utilities for common debugging tasks

**Tool Integration:**
* Use AST visualization regularly during development
* Set up automated testing with debug output
* Create debug configurations for common scenarios
* Document debugging procedures for complex systems

These debugging tools provide comprehensive support for understanding and troubleshooting the GeLB compilation process, from basic syntax issues to complex type system interactions.