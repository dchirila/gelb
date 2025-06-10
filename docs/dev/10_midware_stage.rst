================
Midware Stage
================

The Midware stage (Stage 2) sits between the Frontend and Backend stages in the GeLB compilation pipeline. It is responsible for AST transformations, optimizations, and safety validations on the fully-processed AST from the Frontend.

Current Implementation
======================

The Midware implements **modular optimization and validation passes** on the validated AST from the Frontend. Each pass is implemented as an individual function that can be called explicitly from the compiler driver.

Key Components
--------------

* **validate_midware_input(ast)** - Validates the AST is ready for processing
* **fold_constants(ast)** - Evaluates constant expressions at compile time  
* **validate_division_by_zero(ast)** - Detects division by zero after constant folding
* **Future functions** - Dead code elimination, common subexpression elimination, etc.

Current Pipeline
----------------

The midware stage processes AST through these steps:

.. code-block:: python

    # In gelbc.py main compilation pipeline:
    
    # Stage 2: Midware
    validate_midware_input(ast)
    ast = fold_constants(ast) 
    ast = validate_division_by_zero(ast)
    
    # Future midware passes:
    # ast = eliminate_dead_code(ast)
    # ast = eliminate_common_subexpressions(ast)
    # ast = optimize_lattice_access_patterns(ast)

Implemented Optimizations
=========================

Constant Folding
----------------

**Status**: ✅ **IMPLEMENTED**

Constant folding evaluates constant expressions at compile time, replacing them with their computed literal values. It also implements **constant propagation** by replacing constant identifiers with their literal values.

**Supported Operations:**

* **Arithmetic**: ``+``, ``-``, ``*``, ``/``, ``^`` (power)
* **Comparison**: ``<``, ``>``, ``<=``, ``>=``, ``==``, ``!=``
* **Logical**: ``&&``, ``||``, ``!``
* **Unary**: ``-`` (negation), ``!`` (logical not)
* **Mixed types**: ``int`` + ``real``, with proper type promotion
* **Constant Propagation**: Replaces constant identifiers with their values

**Examples:**

.. code-block:: gelb

    // Before constant folding and propagation:
    const int A = 2 + 3;           // Expression folding
    const int ZERO = 5 - 5;        // Expression folding
    f.out[x | 0] = 1 / ZERO;       // Constant propagation
    
    // After constant folding and propagation:
    const int A = 5;               // Folded to literal
    const int ZERO = 0;            // Folded to literal  
    f.out[x | 0] = 1 / 0;          // ZERO propagated to 0

**Key Features:**

* **Bottom-up Processing**: Evaluates nested expressions from innermost to outermost
* **Type Preservation**: Maintains ArrayDataType_N type information on folded literals
* **Constant Propagation**: Replaces constant identifiers with their literal values
* **Error Safety**: Gracefully handles arithmetic errors (division by zero preserved for validation)

**Implementation:** ``gelb/midware/ConstantFoldingVisitor.py``

Division by Zero Validation
---------------------------

**Status**: ✅ **IMPLEMENTED**

Division by zero validation detects compile-time division by zero errors after constant folding and propagation. This validation runs in the Midware stage to catch all compile-time detectable cases.

**Why Run After Constant Folding:**

* **Enhanced Detection**: Catches ``const int ZERO = 1 - 1; ... 1 / ZERO`` after folding
* **Complete Coverage**: Detects direct literals, constants, and expression results
* **Stage Separation**: Maintains clean separation between optimization and validation

**Detected Cases:**

* **Direct literals**: ``1 / 0``, ``5.0 / 0.0``
* **Constant propagation**: ``const int ZERO = 0; ... 1 / ZERO``
* **Expression folding**: ``const int ZERO = 5 - 5; ... 1 / ZERO``
* **Complex expressions**: ``const int ZERO = (3 + 2) - (4 + 1); ... 1 / ZERO``

**Implementation:** ``gelb/midware/DivisionByZeroValidator.py``

The ``DivisionByZeroValidator`` analyzes the AST after constant folding:

.. code-block:: python

    class DivisionByZeroValidator(ASTBaseVisitor, ProgramTraversalMixin):
        """Validates that there are no division by zero operations in the AST."""
        
        def visitDiv_N(self, node: Div_N, ast_root_node: Program_N):
            """Check division for zero divisor."""
            # Visit children first
            self.visit(node.left, ast_root_node)
            self.visit(node.right, ast_root_node)
            
            # Check for literal zero (after constant folding/propagation)
            divisor = node.right
            if isinstance(divisor, IntLiteral_N) and divisor.value == 0:
                raise GeLBExTypeError(
                    divisor,
                    "Division by zero: cannot divide by zero",
                    "Remove the division by zero or use a non-zero divisor"
                )
            
            if isinstance(divisor, RealLiteral_N) and divisor.value == 0.0:
                raise GeLBExTypeError(divisor, ...)
            
            return node

**Error Messages:**

Uses ``GeLBExTypeError`` to provide source context with arrows pointing to the problematic code:

.. code-block::

         ...
       6  
       7  initializer Init {
       8->    f.out[x | 0] = 1 / 0;
                                 ^^                         [Problem] Division by zero: cannot divide by zero
                                                            [Hint] Remove the division by zero or use a non-zero divisor
       9  }
      10  
          ...

**Benefits:**

* **Performance**: Eliminates redundant runtime calculations
* **Static Analysis**: Enables division by zero detection on folded expressions  
* **Code Size**: Reduces generated code complexity
* **Error Detection**: Catches arithmetic errors at compile time
* **Type Safety**: Preserves ArrayDataType_N type information throughout optimization

Architecture and Design
=======================

The Midware follows these design principles:

1. **Type Safety** - Validates input is a Program_N AST node
2. **Clear Error Messages** - Provides actionable error messages for debugging
3. **Extensibility** - Structured to easily add transformations later
4. **Separation of Concerns** - Each transformation type has its own function

Module Structure
----------------

.. code-block:: text

    gelb/midware/
    ├── __init__.py
    ├── stage2_midware.py           # Main midware functions  
    ├── ConstantFoldingVisitor.py   # Constant folding and propagation
    └── DivisionByZeroValidator.py  # Division by zero validation

Integration in Compilation Pipeline
===================================

The Midware integrates into the compilation pipeline in ``gelbc.py``:

.. code-block:: python

    # Stage 1: Frontend
    ast = get_ast("gelb_program", source_code)
    ast = build_symbols_tables(ast)
    ast = resolve_all_constants(ast)
    ast = infer_types(ast)
    ast = promote_types(ast)
    ast = validate_types(ast)
    # ... other frontend passes ...
    
    # Stage 2: Midware
    validate_midware_input(ast)
    ast = fold_constants(ast)
    ast = validate_division_by_zero(ast)
    
    # Stage 3: Backend
    print(ast)  # TODO: actual code generation

Testing Infrastructure
======================

The Midware has comprehensive test coverage with 16 unit tests and 2 integration tests:

**Unit Tests** (``gelb/tests/unit/midware/``):
* ``test_midware_pass_through.py`` - Core functionality tests  
* ``test_constant_folding.py`` - Comprehensive constant folding tests
* ``test_constant_folding_simple.py`` - Basic constant folding tests
* ``test_division_by_zero_validation.py`` - **16 division by zero detection tests**
* ``midware_test_utils.py`` - Shared test utilities

**Division by Zero Test Coverage:**
* Direct literal division (``1 / 0``, ``1.5 / 0.0``)
* Constant propagation (``const int ZERO = 0; ... 1 / ZERO``)
* Expression folding (``const int ZERO = 5 - 5; ... 1 / ZERO``)
* Complex expressions (``const int ZERO = (3 + 2) - (4 + 1)``)
* Multiple blocks (global_constants, initializer, dynamic)
* Valid divisions (ensure false positives are avoided)
* Edge cases (negative zero, type promotion, very small numbers)

**Integration Tests** (``gelb/tests/integration/test_midware.py``):
* Frontend-to-midware pipeline tests
* Type information preservation tests
* Error handling validation
* **Division by zero detection integration** - 2 additional tests

**Test Utilities:**
* ``get_typed_ast()`` - Helper for full frontend pipeline testing
* ``minimal_gelb_program_1d()`` - Program template for isolated testing
* Standard exception testing patterns with ``pytest.raises(GeLBExTypeError)``

Future Transformations
======================

The Midware is designed to support these future transformations:

1. AST Normalization
-------------------

* Expand compact notations to explicit forms
* Normalize coordinate ranges (e.g., ``:-5`` → ``:Nx-5``)
* Standardize lattice access patterns

2. Optimization Passes
---------------------

* **Dead Code Elimination** - Remove unreachable code
* **Common Subexpression Elimination** - Reuse computed values
* **Lattice Access Optimizations** - Optimize implicit iteration patterns
* **Constant Propagation** - Propagate constant values across statements

3. Validation Passes
--------------------

* Verify all lattices have same dimensionality (GeLB v1 restriction)
* Check lattice access bounds
* Validate dataflow patterns

4. Backend Preparation
---------------------

* Lower high-level constructs to backend-friendly forms
* Prepare data structures for efficient code generation
* Add backend-specific annotations

Implementation Guidelines
=========================

When adding new transformations to the Midware:

1. **Create a New Function** for each transformation type:

   .. code-block:: python

       def normalize_ranges(ast):
           """Normalize all range expressions in the AST."""
           visitor = RangeNormalizationVisitor()
           return visitor.visit(ast, ast)

2. **Use the Visitor Pattern** for AST traversal:

   .. code-block:: python

       class OptimizationVisitor(ASTBaseVisitor):
           """Visitor for optimization passes."""
           
           def visitAdd_N(self, node, ast_root_node):
               # Constant folding example
               if (isinstance(node.left, IntLiteral_N) and 
                   isinstance(node.right, IntLiteral_N)):
                   return IntLiteral_N(
                       code_range=node.code_range,
                       value=node.left.value + node.right.value
                   )
               return node

3. **Maintain AST Integrity**:
   * Preserve all required AST attributes
   * Update type information when modifying expressions
   * Maintain symbol table references

4. **Add Comprehensive Tests**:
   * Unit tests for individual transformations
   * Integration tests for transformation pipelines
   * Edge case and error handling tests

Example: Adding New Transformations
===================================

Here's how to add a new optimization or transformation:

1. **Create the Visitor**:

   .. code-block:: python

       # In gelb/midware/dead_code_elimination.py
       class DeadCodeEliminationVisitor(ASTBaseVisitor):
           """Removes unreachable code and unused definitions from the AST."""
           
           def visitGlobalConstantsBlock_N(self, node, ast_root_node):
               # Visit all statements first
               for i, stmt in enumerate(node.stmts):
                   node.stmts[i] = self.visit(stmt, ast_root_node)
               
               # Remove unused constant definitions
               used_constants = self._find_used_constants(ast_root_node)
               node.stmts = [stmt for stmt in node.stmts 
                           if stmt.name.name in used_constants]
               
               return node
           
           def _find_used_constants(self, ast_root_node):
               """Find all constants that are actually referenced."""
               # Implementation would traverse the AST to find references
               # This is a simplified example
               pass

2. **Integrate into Midware**:

   .. code-block:: python

       # In stage2_midware.py
       from gelb.midware.dead_code_elimination import DeadCodeEliminationVisitor
       
       def apply_optimizations(ast):
           """Apply optimization passes to the AST."""
           # Apply constant folding first
           ast = apply_constant_folding(ast)
           
           # Apply dead code elimination
           eliminator = DeadCodeEliminationVisitor()
           ast = eliminator.visit(ast, ast)
           
           return ast

Performance Considerations
=========================

When implementing Midware transformations:

* **Single Pass vs Multiple Passes**: Consider combining related transformations
* **AST Copying**: Avoid unnecessary AST copies for performance
* **Visitor Efficiency**: Minimize redundant tree traversals
* **Memory Usage**: Be mindful of memory when transforming large ASTs

Debugging Midware Transformations
=================================

Debugging Tools
---------------

1. **AST Visualization**: Use ``--visualize-ast`` to see transformations:

   .. code-block:: bash

       gelbc --visualize-ast --ast-stage all program.gelb

2. **Logging**: Add debug logging to transformations:

   .. code-block:: python

       import logging
       logger = logging.getLogger(__name__)
       
       def apply_optimization(node):
           logger.debug(f"Optimizing {type(node).__name__}")
           # ... optimization logic ...

3. **Test Individual Transformations**: Test each transformation in isolation:

   .. code-block:: python

       def test_dead_code_elimination():
           source = """
           global_constants {
               const int UNUSED = 42;
               const int USED = 10;
           }
           dynamic Test {
               f.out[x | 0] = USED;
           }
           """
           ast = get_typed_ast(source)
           ast = apply_dead_code_elimination(ast)
           # Should eliminate UNUSED constant

Best Practices
==============

DO
---

* Keep transformations focused and single-purpose
* Document what each transformation does and why
* Preserve AST invariants and type information
* Test edge cases and error conditions
* Consider transformation order dependencies

DON'T
-----

* Modify the AST in ways that break later stages
* Combine unrelated transformations
* Forget to update type information
* Assume transformation order doesn't matter

The Midware stage provides a clean, extensible architecture for AST transformations while currently implementing a minimal pass-through design that enables rapid MVP development. As the compiler matures, transformations can be added incrementally without disrupting the compilation pipeline.