================
Midware Stage
================

The Midware stage (Stage 2) sits between the Frontend and Backend stages in the GeLB compilation pipeline. It is responsible for AST transformations, optimizations, and preparing the AST for code generation.

Current Implementation
======================

The Midware currently implements a **minimal pass-through design** to enable MVP (Minimum Viable Product) development. This allows the backend to be developed immediately while providing a clean insertion point for future transformations.

Key Components
--------------

* **process_ast(ast)** - Main entry point that accepts and returns the AST
* **validate_midware_input(ast)** - Validates the AST is ready for processing
* **apply_optimizations(ast)** - Placeholder for optimization passes
* **apply_transformations(ast)** - Placeholder for AST transformations

Current Behavior
----------------

.. code-block:: python

    def process_ast(ast):
        """Process the AST through the midware stage."""
        if not isinstance(ast, Program_N):
            raise TypeError(
                f"Midware expects a Program_N AST root, but got {type(ast).__name__}. "
                "Ensure the frontend properly validates the AST root."
            )
        
        # For MVP: return the AST unchanged
        return ast

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
* ``midware_test_utils.py`` - Shared test utilities

**Integration Tests** (``gelb/tests/integration/test_midware.py``):
* Frontend-to-midware pipeline tests
* Type information preservation tests
* Error handling validation

**Test Utilities:**
* ``get_midware_processed_ast()`` - Helper for full pipeline testing
* ``assert_midware_preserves_structure()`` - Validates AST integrity
* ``assert_ast_identity_preserved()`` - Ensures pass-through behavior

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

* **Constant Folding** - Evaluate constant expressions at compile time
* **Dead Code Elimination** - Remove unreachable code
* **Common Subexpression Elimination** - Reuse computed values
* **Loop Optimizations** - Optimize lattice iteration patterns

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

Example: Adding Constant Folding
=================================

Here's how to add a constant folding optimization:

1. **Create the Visitor**:

   .. code-block:: python

       # In gelb/midware/constant_folding.py
       class ConstantFoldingVisitor(ASTBaseVisitor):
           """Folds constant expressions at compile time."""
           
           def visitAdd_N(self, node, ast_root_node):
               # Visit children first
               node.left = self.visit(node.left, ast_root_node)
               node.right = self.visit(node.right, ast_root_node)
               
               # Fold if both operands are constants
               if (isinstance(node.left, IntLiteral_N) and 
                   isinstance(node.right, IntLiteral_N)):
                   return IntLiteral_N(
                       code_range=node.code_range,
                       value=node.left.value + node.right.value
                   )
               
               return node

2. **Integrate into Midware**:

   .. code-block:: python

       # In stage2_midware.py
       from gelb.midware.constant_folding import ConstantFoldingVisitor
       
       def apply_optimizations(ast):
           """Apply optimization passes to the AST."""
           # Add constant folding
           folder = ConstantFoldingVisitor()
           ast = folder.visit(ast, ast)
           
           # Future: Add more optimizations here
           return ast

3. **Update process_ast**:

   .. code-block:: python

       def process_ast(ast):
           """Process the AST through the midware stage."""
           validate_midware_input(ast)
           
           # Apply transformations
           ast = apply_transformations(ast)
           
           # Apply optimizations
           ast = apply_optimizations(ast)
           
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

       def test_constant_folding():
           ast = get_typed_ast("const int X = 2 + 3;")
           ast = apply_constant_folding(ast)
           assert ast.global_constants.stmts[0].value.value == 5

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