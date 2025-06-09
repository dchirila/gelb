====================
Frontend Pipeline
====================

The frontend pipeline consists of multiple visitors that systematically process the AST to build symbol tables, resolve references, infer types, and validate the program. Understanding the complete visitor catalog and their execution order is crucial for compiler development.

Visitor Execution Order
=======================

The frontend visitors must run in a specific order due to dependencies between passes:

1. **ASTBuilderVisitor** - Convert parse tree to AST
2. **SymbolsTablesBuilderVisitor** - Build symbol tables
3. **ImplicitSymbolsAdderVisitor** - Add coordinates (x,y,z) and dimensions (Nx,Ny,Nz)
4. **ConstantsResolverVisitor** - Resolve constant expressions
5. **RangeResolverVisitor** - Convert ``:`` to concrete bounds
6. **TypeInferenceVisitor** - Add type information to expressions
7. **TypePromotionVisitor** - Insert implicit conversion nodes
8. **TypeValidationVisitor** - Validate type compatibility
9. **Various Validation Visitors** - Final semantic checks

Complete Visitor Catalog
========================

AST Building Visitors
--------------------

**ASTBuilderVisitor**

*Purpose:* Converts ANTLR4 parse trees to GeLB AST nodes

*Key Features:*
- Eliminates parsing artifacts (parentheses, separators, keywords)
- Preserves source location information in ``code_range`` attributes
- Handles all grammar rules systematically
- Creates proper AST node hierarchy

*Dependencies:* None (operates on parse trees)

*Location:* ``gelb/frontend/ASTBuilderVisitor.py``

Symbol Resolution Visitors
--------------------------

**SymbolsTablesBuilderVisitor**

*Purpose:* Constructs hierarchical symbol tables for proper scoping

*Key Features:*
- Creates symbol tables for each block
- Establishes parent-child relationships (global_constants as parent)
- Handles symbol definitions and scope management
- Prevents symbol redefinition within same scope

*Dependencies:* Valid AST structure

*Location:* ``gelb/frontend/SymbolsTablesBuilderVisitor.py``

**ImplicitSymbolsAdderVisitor**

*Purpose:* Adds implicit coordinate and dimension symbols

*Key Features:*
- Extracts grid dimensionality from geometry block
- Adds Nx, Ny, Nz to global_constants symbol table
- Adds x, y, z to simulation blocks (initializer, dynamic, gauge)
- Ensures user-defined symbols take precedence

*Dependencies:* Symbol tables built, geometry block analyzed

*Location:* ``gelb/frontend/ImplicitSymbolsAdderVisitor.py``

Constant and Range Resolution Visitors
-------------------------------------

**ConstantsResolverVisitor**

*Purpose:* Resolves constant expressions to their literal values

*Key Features:*
- Evaluates constant arithmetic at compile time
- Replaces constant references with resolved values
- Handles nested constant expressions
- Enables backend optimizations

*Dependencies:* Symbol tables with constant definitions

*Location:* ``gelb/frontend/ConstantsResolverVisitor.py``

**RangeResolverVisitor**

*Purpose:* Converts abstract ranges to concrete bounds

*Key Features:*
- Resolves ``:`` to ``0:N-1`` patterns
- Handles partial ranges (``5:``, ``:10``)
- Uses grid dimensions for lattice selection bounds
- Enables backend array indexing

*Dependencies:* Constants resolved, implicit symbols available

*Location:* ``gelb/frontend/RangeResolverVisitor.py``

Type System Visitors
-------------------

**TypeInferenceVisitor**

*Purpose:* Adds ``inferred_type`` attributes to all expressions

*Key Features:*
- Infers types for literals, identifiers, and operations
- Performs symbol table lookups for variable types
- Handles array types and lattice selection types
- Provides foundation for type promotion and validation

*Dependencies:* Symbol tables built, constants resolved

*Location:* ``gelb/frontend/TypeInferenceVisitor.py``

**TypePromotionVisitor**

*Purpose:* Inserts ``TypePromotionNode_N`` for implicit conversions and ``BroadcastNode_N`` for scalar-to-array assignments

*Key Features:*
- Implements type promotion hierarchy (bool → int → real)
- Handles arithmetic, comparison, and assignment promotions
- Creates broadcast nodes for scalar-to-array assignments (e.g., ``array = scalar``)
- Integrates type promotion with broadcasting for efficient code generation
- Makes implicit conversions explicit in AST
- Prepares AST for type validation

*Broadcasting Implementation:*
- Detects scalar-to-array assignment patterns
- Applies type promotion first (if needed), then broadcasting
- Preserves scalar values for backend optimization
- Supports all array dimensions (1D, 2D, 3D, 4D)

*Dependencies:* Type inference completed

*Location:* ``gelb/frontend/TypePromotionVisitor.py``

**TypeValidationVisitor**

*Purpose:* Validates type compatibility after promotions and broadcasting

*Key Features:*
- Enforces type rules for all operations
- Validates assignment compatibility
- Ensures logical operations use bool types only
- Validates broadcast operations (always valid since created by TypePromotionVisitor)
- Recursively validates scalar expressions within broadcast nodes
- Provides clear error messages with source locations

*Broadcasting Validation:*
- ``BroadcastNode_N`` operations are considered always valid
- Validates the inner scalar expression recursively
- Ensures type consistency between scalar and target array element type

*Dependencies:* Type promotion and broadcasting applied

*Location:* ``gelb/frontend/TypeValidationVisitor.py``

Validation Visitors
-------------------

**ASTInitialValidationVisitor**

*Purpose:* Performs basic AST structure validation

*Key Features:*
- Validates required program components
- Checks block structure integrity
- Ensures proper AST node relationships

*Dependencies:* Valid AST structure

*Location:* ``gelb/frontend/ASTInitialValidationVisitor.py``

**ConstantAssignmentValidationVisitor**

*Purpose:* Validates proper constant usage and assignment rules

*Key Features:*
- Ensures constants are not reassigned
- Validates constant initialization
- Checks constant scope rules

*Dependencies:* Symbol tables and type information

*Location:* ``gelb/frontend/ConstantAssignmentValidationVisitor.py``

**ArithmeticValidationVisitor**

*Purpose:* Validates arithmetic expression constraints

*Key Features:*
- Checks division by zero at compile time
- Validates numeric operation requirements
- Ensures proper operand types

*Dependencies:* Type validation completed

*Location:* ``gelb/frontend/ArithmeticValidationVisitor.py``

**NodeClassesValidationVisitor**

*Purpose:* Validates node class definitions and usage

*Key Features:*
- Ensures all referenced blocks exist
- Validates node class instantiation
- Checks geometry block consistency

*Dependencies:* Complete symbol resolution

*Location:* ``gelb/frontend/NodeClassesValidationVisitor.py``

**GeometryInitialValidationVisitor**

*Purpose:* Validates geometry block structure and constraints

*Key Features:*
- Checks grid size specifications
- Validates node painting statements
- Ensures geometry consistency

*Dependencies:* Symbol tables and ranges resolved

*Location:* ``gelb/frontend/GeometryInitialValidationVisitor.py**

**LatticeConsistencyValidator**

*Purpose:* Validates lattice definitions and usage consistency

*Key Features:*
- Ensures lattice parameters are consistent
- Validates lattice access patterns
- Checks dimensional compatibility

*Dependencies:* Type system completed

*Location:* ``gelb/frontend/LatticeConsistencyValidator.py``

**RectangularArraysEnforcerVisitor**

*Purpose:* Ensures array literals have rectangular structure

*Key Features:*
- Validates multi-dimensional array shapes
- Enforces consistent array dimensions
- Checks array literal well-formedness

*Dependencies:* Type inference

*Location:* ``gelb/frontend/RectangularArraysEnforcerVisitor.py``

Clash Prevention Visitors
-------------------------

**ImplicitsDefsClashPreventerVisitor**

*Purpose:* Prevents conflicts between implicit and explicit symbol definitions

*Key Features:*
- Checks for user-defined symbols that clash with implicit ones
- Warns about potential confusion
- Ensures proper symbol precedence

*Dependencies:* Symbol tables built

*Location:* ``gelb/frontend/ImplicitsDefsClashPreventerVisitor.py``

**ImplicitsRefsClashPreventerVisitor**

*Purpose:* Prevents conflicts in implicit symbol references

*Key Features:*
- Validates implicit symbol usage
- Prevents ambiguous references
- Ensures clear symbol resolution

*Dependencies:* Implicit symbols added

*Location:* ``gelb/frontend/ImplicitsRefsClashPreventerVisitor.py``

Utility Visitors
----------------

**ASTVisualizationVisitor**

*Purpose:* Generates graphical representations of the AST

*Key Features:*
- Creates DOT format for Graphviz visualization
- Handles all AST node types automatically
- Provides debugging and documentation support
- Tracks AST statistics (node count, depth)

*Dependencies:* Any valid AST

*Location:* ``gelb/frontend/ASTVisualizationVisitor.py``

Frontend Pipeline Implementation
===============================

Main Frontend Function
----------------------

The frontend pipeline is orchestrated in ``gelb/frontend/stage1_frontend.py``:

.. code-block:: python

    def compile_frontend(source_code):
        """Complete frontend compilation pipeline."""
        
        # 1. Parse to AST
        ast = get_ast("gelb_program", source_code)
        validate_ast_root_is_program(ast)
        
        # 2. Build symbol infrastructure  
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        
        # 3. Resolve constants and ranges
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        
        # 4. Type analysis
        ast = infer_types(ast)
        ast = promote_types(ast)
        ast = validate_types(ast)
        
        # 5. Final validation
        validate_node_classes(ast)
        
        return ast

Individual Pipeline Functions
----------------------------

Each major step is implemented as a separate function:

.. code-block:: python

    def build_symbols_tables(ast):
        """Build hierarchical symbol tables."""
        visitor = SymbolsTablesBuilderVisitor()
        return visitor.visit(ast, ast)
    
    def add_implicit_symbols(ast):
        """Add coordinate and dimension symbols."""
        visitor = ImplicitSymbolsAdderVisitor()
        return visitor.visit(ast, ast)
    
    def resolve_all_constants(ast):
        """Resolve constant expressions."""
        visitor = ConstantsResolverVisitor()
        return visitor.visit(ast, ast)
    
    def infer_types(ast):
        """Add type information to expressions."""
        visitor = TypeInferenceVisitor()
        return visitor.visit(ast, ast)

Adding New Frontend Passes
==========================

To add a new frontend visitor:

1. **Create Visitor Class**

.. code-block:: python

    class NewValidationVisitor(ASTBaseVisitor):
        """Description of what this visitor validates."""
        
        def visitTargetNode_N(self, node, ast_root_node):
            # Implement validation logic
            if not is_valid(node):
                raise GeLBValidationError("Validation failed")
            return node

2. **Add to Pipeline**

.. code-block:: python

    def validate_new_feature(ast):
        """Apply new validation pass."""
        visitor = NewValidationVisitor()
        return visitor.visit(ast, ast)

3. **Integrate in Frontend**

Add the call to ``compile_frontend()`` at the appropriate stage.

4. **Add Tests**

Create comprehensive tests for the new validation logic.

Dependencies Between Visitors
=============================

Understanding visitor dependencies is crucial for pipeline maintenance:

**Symbol Dependencies:**
- ``ImplicitSymbolsAdderVisitor`` depends on ``SymbolsTablesBuilderVisitor``
- ``ConstantsResolverVisitor`` depends on symbol tables
- Type visitors depend on symbol resolution

**Type Dependencies:**
- ``TypePromotionVisitor`` depends on ``TypeInferenceVisitor``
- ``TypeValidationVisitor`` depends on ``TypePromotionVisitor``
- Most validation visitors depend on type information

**Resolution Dependencies:**
- ``RangeResolverVisitor`` depends on constants being resolved
- Validation visitors typically depend on ranges being resolved

Frontend Error Handling
=======================

Each visitor can throw specific exception types:

**Symbol Errors:**
- ``GeLBExSymbolUnknown`` - Undefined symbol reference
- ``GeLBExSymbolExists`` - Duplicate symbol definition

**Type Errors:**
- ``GeLBExTypeError`` - Type checking failures
- Type promotion incompatibilities

**Validation Errors:**
- ``GeLBValidationError`` - Semantic constraint violations
- ``GeLBParsingError`` - Syntax and parsing issues

Frontend Testing Strategy
=========================

**Unit Tests:**
Test individual visitors in isolation with controlled AST inputs.

**Integration Tests:**
Test visitor combinations and pipeline segments.

**End-to-End Tests:**
Test complete frontend pipeline with real GeLB programs.

**Test Utilities:**
Use shared utilities like ``get_typed_ast()`` and ``minimal_gelb_program_*()`` for consistent testing.

The frontend pipeline's systematic approach ensures that each compilation phase builds upon the previous ones, creating a robust foundation for the subsequent midware and backend stages.