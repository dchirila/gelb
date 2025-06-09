================
Midware Stage
================

The Midware stage (Stage 2) sits between the Frontend and Backend stages in the GeLB compilation pipeline. It is responsible for AST transformations, optimizations, and preparing the AST for code generation.

Current Implementation
======================

The Midware implements **optimization and transformation passes** on the validated AST from the Frontend. It currently includes constant folding optimization with a modular design for adding more transformations.

Key Components
--------------

* **process_ast(ast)** - Main entry point that accepts and returns the AST
* **validate_midware_input(ast)** - Validates the AST is ready for processing  
* **apply_constant_folding(ast)** - Evaluates constant expressions at compile time
* **apply_optimizations(ast)** - Applies optimization passes (currently constant folding)
* **apply_transformations(ast)** - Placeholder for AST transformations

Current Behavior
----------------

.. code-block:: python

    def process_ast(ast):
        """Process the AST through the midware stage."""
        validate_midware_input(ast)
        
        # Apply constant folding optimization
        ast = apply_constant_folding(ast)
        
        # Apply other optimizations
        ast = apply_optimizations(ast)
        
        # Apply transformations for backend compatibility
        ast = apply_transformations(ast)
        
        return ast

Implemented Optimizations
=========================

Constant Folding
----------------

**Status**: ✅ **IMPLEMENTED**

Constant folding evaluates constant expressions at compile time, replacing them with their computed literal values. This optimization improves performance and enables better static analysis.

**Supported Operations:**

* **Arithmetic**: ``+``, ``-``, ``*``, ``/``, ``^`` (power)
* **Comparison**: ``<``, ``>``, ``<=``, ``>=``, ``==``, ``!=``
* **Logical**: ``&&``, ``||``, ``!``
* **Unary**: ``-`` (negation)
* **Mixed types**: ``int`` + ``real``, with proper type promotion

**Examples:**

.. code-block:: gelb

    // Before constant folding:
    const int A = 2 + 3;           // Expression: Add_N(2, 3)
    const real B = (10.0 - 5.0) / 2.5;  // Nested expressions
    
    // After constant folding:
    const int A = 5;               // Literal: IntLiteral_N(5)
    const real B = 2.0;            // Literal: RealLiteral_N(2.0)

**Broadcasting Support:**

Constant folding fully supports broadcasting operations introduced by the Frontend:

* **BroadcastNode_N**: Scalar expressions within broadcast nodes are folded when possible
* **Type Promotion Integration**: Folding respects type promotion within broadcast operations
* **Efficiency Preservation**: Broadcast nodes preserve their scalar values after folding

.. code-block:: gelb

    // Before constant folding:
    array[real, 5] data;
    data = 2 + 3;  // BroadcastNode_N with Add_N(2, 3) as scalar
    
    // After constant folding:
    array[real, 5] data;
    data = 5;      // BroadcastNode_N with IntLiteral_N(5) as scalar

**Implementation:** ``gelb/midware/ConstantFoldingVisitor.py``

Arithmetic Safety Analysis
---------------------------

**Status**: ✅ **IMPLEMENTED**

Arithmetic safety analysis detects potential runtime errors (like division by zero) at compile time. This analysis has been moved from the Frontend to the Midware stage for more effective error detection after constant folding.

**Benefits of Midware Placement:**

* **Enhanced Detection**: Expressions like ``1 / (5-5)`` are detected after folding to ``1 / 0``
* **Better Error Messages**: Errors are reported on simplified expressions
* **Logical Separation**: Safety analysis runs after optimizations but before code generation

**Implementation:** ``gelb/midware/ArithmeticSafetyVisitor.py``

The ``ArithmeticSafetyVisitor`` analyzes folded expressions for potential arithmetic errors:

.. code-block:: python

    class ArithmeticSafetyVisitor(ASTBaseVisitor, ProgramTraversalMixin):
        """Detects arithmetic safety violations in the AST."""
        
        def visitDiv_N(self, node: Div_N, ast_root_node: Program_N):
            """Check for division by zero."""
            # Visit children first
            node.left = self.visit(node.left, ast_root_node)
            node.right = self.visit(node.right, ast_root_node)
            
            # Check for literal zero in denominator
            if (isinstance(node.right, IntLiteral_N) and node.right.value == 0) or \
               (isinstance(node.right, RealLiteral_N) and node.right.value == 0.0):
                raise GeLBExArithmeticError(f"Division by zero detected", node.code_range)
            
            return node

**Testing Impact:**

- Use ``get_midware_ast()`` for testing division by zero errors
- Use ``get_typed_ast()`` for general frontend testing  
- Use ``get_promoted_ast()`` for testing type validation errors

The ``ConstantFoldingVisitor`` class uses the visitor pattern to traverse the AST and fold constant expressions:

.. code-block:: python

    class ConstantFoldingVisitor(ASTBaseVisitor, ProgramTraversalMixin):
        """Performs constant folding optimizations on the AST."""
        
        def visitAdd_N(self, node: Add_N, ast_root_node: Program_N):
            """Fold addition operations."""
            return self._handle_arithmetic_binary_op(node, ast_root_node, self._evaluate_add)
        
        def visitBroadcastNode_N(self, node: BroadcastNode_N, ast_root_node: Program_N):
            """Fold expressions within broadcast operations."""
            # Fold the scalar expression (preserving broadcast structure)
            node.scalar_expr = self.visit(node.scalar_expr, ast_root_node)
            return node
        
        def _handle_arithmetic_binary_op(self, node, ast_root_node, evaluator):
            # Visit children first (bottom-up processing)
            node.left = self.visit(node.left, ast_root_node)
            node.right = self.visit(node.right, ast_root_node)
            
            # Check if both operands are constant literals
            if self._is_constant_literal(node.left) and self._is_constant_literal(node.right):
                try:
                    result_value = evaluator(node.left, node.right)
                    return self._create_literal_from_value(result_value, node)
                except (ZeroDivisionError, OverflowError, ValueError):
                    # Don't fold if evaluation fails - preserve for validation
                    pass
            
            return node

**Key Features:**

1. **Bottom-up Processing**: Evaluates nested expressions from innermost to outermost
2. **Type Preservation**: Maintains GeLB type semantics (e.g., ``int / int`` → ``real``)
3. **ArrayDataType_N Compatibility**: Preserves universal array type system for folded literals
4. **Error Handling**: Division by zero and overflow errors are caught gracefully
5. **Boolean Handling**: Preserves GeLB's string-based boolean literals (``'true'``/``'false'``)

**ArrayDataType_N Type Preservation:**

The constant folding pass preserves the universal ArrayDataType_N type system:

.. code-block:: python

    def _preserve_inferred_type(self, new_literal, original_node):
        """Preserve ArrayDataType_N type on folded literals."""
        if hasattr(original_node, 'inferred_type'):
            new_literal.inferred_type = original_node.inferred_type
        else:
            self._set_default_array_type(new_literal)

**Typed Literal Creation:**

- ``_create_typed_bool_literal()`` - Creates BoolLiteral_N with ArrayDataType_N("bool", List_N([]))
- ``_create_typed_int_literal()`` - Creates IntLiteral_N with ArrayDataType_N("int", List_N([]))
- ``_create_typed_real_literal()`` - Creates RealLiteral_N with ArrayDataType_N("real", List_N([]))

**Benefits:**

* **Performance**: Eliminates redundant runtime calculations
* **Static Analysis**: Enables division by zero detection on folded expressions
* **Code Size**: Reduces generated code complexity
* **Error Detection**: Catches arithmetic errors at compile time

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
    └── stage2_midware.py      # Main midware implementation

Integration in Compilation Pipeline
===================================

The Midware integrates into the compilation pipeline in ``gelbc.py``:

.. code-block:: python

    # Stage 1: Frontend
    ast = get_ast("gelb_program", source_code)
    ast = build_symbols_tables(ast)
    ast = resolve_all_constants(ast)
    # ... other frontend passes ...
    
    # Stage 2: Midware (currently pass-through)
    ast = process_ast(ast)
    
    # Stage 3: Backend
    code = generate_code(ast, backend_type)

Testing Infrastructure
======================

The Midware has comprehensive test coverage:

**Unit Tests** (``gelb/tests/unit/midware/``):
* ``test_midware_pass_through.py`` - Core functionality tests
* ``test_constant_folding.py`` - Comprehensive constant folding tests
* ``test_constant_folding_simple.py`` - Basic constant folding tests
* ``midware_test_utils.py`` - Shared test utilities

**Integration Tests** (``gelb/tests/integration/test_midware.py``):
* Frontend-to-midware pipeline tests
* Type information preservation tests
* Error handling validation
* Constant folding integration tests

**Test Utilities:**
* ``get_midware_ast()`` - Helper for full frontend + midware pipeline testing
* ``get_promoted_ast()`` - Helper for type inference + promotion only
* ``get_typed_ast()`` - Helper for full frontend pipeline
* ``assert_midware_preserves_structure()`` - Validates AST integrity
* ``assert_constant_folding_preserves_types()`` - Validates ArrayDataType_N preservation

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