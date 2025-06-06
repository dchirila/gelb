==================
Visitor Pattern Design
==================

GeLB uses the Visitor pattern extensively for AST traversal and transformation. Understanding the design decisions behind our visitor implementation is crucial for compiler development.

Design Philosophy
=================

The GeLB compiler uses a **dynamic dispatch visitor pattern** rather than the traditional abstract visitor pattern. This design choice was made deliberately to provide flexibility and reduce boilerplate code.

Traditional Abstract Visitor Pattern
------------------------------------

* Requires abstract methods for every possible node type
* Forces all visitors to implement every visit method
* Results in many empty/pass-through implementations
* Makes adding new node types cumbersome (must update base class)

GeLB's Dynamic Dispatch Pattern
-------------------------------

* Base class (``ASTBaseVisitor``) provides only the dispatch mechanism
* Visitors implement only the methods they need
* Missing methods are caught at runtime with clear error messages
* Adding new node types requires no base class changes

Implementation Details
======================

The ``ASTBaseVisitor`` class provides a single ``visit()`` method that:

1. Extracts the node's class name (e.g., ``Program_N``)
2. Constructs the method name (e.g., ``visitProgram_N``)
3. Uses ``getattr()`` to find and call the method dynamically
4. Raises ``GeLBExMissingASTVisitationMethod`` if method not found

Example implementation:

.. code-block:: python

    class ASTBaseVisitor:
        def visit(self, node, ast_root_node):
            ast_node_type_name = type(node).__name__
            visitation_method_name = f"visit{ast_node_type_name}"
            if hasattr(self, visitation_method_name):
                visitation_method = getattr(self, visitation_method_name)
                return visitation_method(node, ast_root_node)
            else:
                raise GeLBExMissingASTVisitationMethod(...)

Writing New Visitors
====================

Creating a Basic Visitor
------------------------

1. **Inherit from ASTBaseVisitor:**

   .. code-block:: python

       from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor

       class MyNewVisitor(ASTBaseVisitor):
           """Description of what this visitor does."""

2. **Implement only needed visit methods:**

   .. code-block:: python

       def visitProgram_N(self, node, ast_root_node):
           # Process program node
           # Visit children as needed
           for initializer in node.initializers:
               self.visit(initializer, ast_root_node)
           return node

       def visitIdentifier_N(self, node, ast_root_node):
           # Process identifier
           return node

3. **Use mixins for common functionality:**

   .. code-block:: python

       from gelb.frontend.visitor_mixins import ProgramTraversalMixin

       class MyNewVisitor(ASTBaseVisitor, ProgramTraversalMixin):
           # Now you have access to program traversal utilities

Available Visitor Mixins
------------------------

**ProgramTraversalMixin**
Provides utilities for systematic program traversal:

* ``traverse_program_blocks()`` - Visit all blocks in order
* ``_store_global_constants()`` - Hook for accessing global constants
* ``_before_block_visit()`` - Hook called before visiting each block
* ``_after_block_visit()`` - Hook called after visiting each block

**SymbolTableUtilityMixin**
Provides symbol table manipulation utilities:

* Symbol lookup methods
* Symbol definition helpers
* Scope management utilities

Example: Focused Visitor
========================

Here's an example of a visitor that only cares about constant definitions:

.. code-block:: python

    class ConstantCollectorVisitor(ASTBaseVisitor):
        """Collects all constant definitions in the program."""
        
        def __init__(self):
            self.constants = []
        
        def visitProgram_N(self, node, ast_root_node):
            # Only visit global constants block
            if node.global_constants:
                self.visit(node.global_constants, ast_root_node)
            return node
        
        def visitGlobalConstantsBlock_N(self, node, ast_root_node):
            # Visit all statements in the block
            for stmt in node.stmts:
                self.visit(stmt, ast_root_node)
            return node
        
        def visitConstantDefinitionStmt_N(self, node, ast_root_node):
            # Collect the constant
            self.constants.append({
                'name': node.name,
                'type': node.data_type,
                'value': node.value
            })
            return node

This visitor only implements 3 methods instead of 40+, making it much cleaner and easier to understand.

Visitor Categories
==================

GeLB visitors fall into several categories based on their purpose:

AST Building Visitors
--------------------

**ASTBuilderVisitor**
* Converts ANTLR4 parse trees to GeLB AST nodes
* Handles all grammar rules
* Eliminates parsing artifacts
* Preserves source location information

Analysis Visitors
-----------------

**SymbolsTablesBuilderVisitor**
* Constructs hierarchical symbol tables
* Establishes parent-child relationships between scopes
* Populates symbol definitions

**TypeInferenceVisitor**
* Adds ``inferred_type`` attributes to expression nodes
* Implements basic type inference rules
* Handles implicit symbols and symbol table lookups

**Various Validation Visitors**
* Check semantic constraints
* Validate type compatibility
* Ensure proper language usage

Transformation Visitors
-----------------------

**TypePromotionVisitor**
* Inserts ``TypePromotionNode_N`` for implicit conversions
* Implements type promotion hierarchy
* Prepares AST for type validation

**RangeResolverVisitor**
* Resolves ``None`` bounds in range expressions
* Converts ``:`` to concrete bounds like ``0:Nx-1``
* Enables backend code generation

**ConstantsResolverVisitor**
* Evaluates constant expressions at compile time
* Replaces constant references with their values
* Enables optimizations and static analysis

Utility Visitors
-----------------

**ASTVisualizationVisitor**
* Generates DOT format for graphical AST visualization
* Provides debugging and documentation support
* Handles all node types automatically

Best Practices
==============

DO
---

* **Implement only the visit methods you actually need**
* **Use descriptive names and docstrings for your visitor class**
* **Leverage existing mixins for common functionality**
* **Call ``self.visit()`` to recursively process child nodes**
* **Return the node (potentially modified) from visit methods**
* **Handle ``None`` values gracefully in child nodes**
* **Use the ``ast_root_node`` parameter for global context**

DON'T
-----

* **Implement empty visit methods just to avoid errors**
* **Access node internals directly when traversal is needed**
* **Forget to pass ``ast_root_node`` through recursive calls**
* **Assume all nodes have all fields (use ``hasattr()`` checks)**
* **Modify AST structure without understanding the implications**
* **Ignore error handling and edge cases**

Common Visitor Patterns
=======================

Information Collection
----------------------

.. code-block:: python

    class InformationCollector(ASTBaseVisitor):
        def __init__(self):
            self.collected_info = []
        
        def visitTargetNode_N(self, node, ast_root_node):
            self.collected_info.append(extract_info(node))
            return node

AST Transformation
------------------

.. code-block:: python

    class ASTTransformer(ASTBaseVisitor):
        def visitTargetNode_N(self, node, ast_root_node):
            # Transform children first
            node.child = self.visit(node.child, ast_root_node)
            
            # Apply transformation
            if should_transform(node):
                return create_new_node(node)
            return node

Validation and Analysis
-----------------------

.. code-block:: python

    class ValidationVisitor(ASTBaseVisitor):
        def visitTargetNode_N(self, node, ast_root_node):
            # Visit children first
            self.visit(node.child, ast_root_node)
            
            # Validate this node
            if not is_valid(node):
                raise ValidationError(f"Invalid node: {node}")
            
            return node

Comparison with Existing Visitors
=================================

Most GeLB visitors follow the focused pattern effectively:

* **TypeInferenceVisitor**: ~20 methods for type-related nodes
* **ConstantAssignmentValidationVisitor**: ~35 methods but many are simple pass-throughs
* **SymbolsTablesBuilderVisitor**: ~15 methods focused on symbol definitions
* **RangeResolverVisitor**: ~10 methods for range-related nodes

Some visitors like ``ConstantAssignmentValidationVisitor`` implement more methods than strictly necessary for traversal completeness, but this is still more maintainable than forcing all visitors to implement all methods.

Performance Considerations
==========================

The dynamic dispatch approach has minimal performance impact:

* ``getattr()`` lookups are fast in Python
* Method resolution happens once per node visit
* The flexibility gained outweighs any micro-optimization concerns
* Real performance bottlenecks will be in code generation, not AST traversal

Future Extensibility
====================

This design makes the compiler easily extensible:

* New AST node types can be added without touching ``ASTBaseVisitor``
* New visitors can be created without implementing unnecessary methods
* Visitors can be composed using mixins for shared functionality
* The pattern scales well as the language grows

Error Handling
==============

**Missing Visit Methods**
When a visitor encounters a node type it doesn't handle:

.. code-block:: python

    raise GeLBExMissingASTVisitationMethod(
        f"Visitor {self.__class__.__name__} is missing method: {visitation_method_name}"
    )

**Debugging Missing Methods**
* Error messages include the exact method name needed
* Stack traces show where the unhandled node was encountered
* Easy to add the missing method and continue development

**Graceful Degradation**
Some visitors provide default behaviors:

.. code-block:: python

    def generic_visit(self, node, ast_root_node):
        """Default behavior for unhandled node types."""
        # Visit all children by default
        for child in node.children:
            if child is not None:
                self.visit(child, ast_root_node)
        return node

Testing Visitors
================

**Unit Testing Individual Methods**

.. code-block:: python

    def test_visit_constant_definition():
        visitor = MyVisitor()
        node = create_test_constant_node()
        result = visitor.visitConstantDefinitionStmt_N(node, mock_ast_root)
        assert_expected_behavior(result)

**Integration Testing Full Traversal**

.. code-block:: python

    def test_full_program_traversal():
        visitor = MyVisitor()
        program_ast = parse_test_program()
        result = visitor.visit(program_ast, program_ast)
        assert_visitor_completed_successfully(result)

**Error Case Testing**

.. code-block:: python

    def test_missing_visit_method():
        visitor = IncompleteVisitor()
        node = create_unhandled_node_type()
        with pytest.raises(GeLBExMissingASTVisitationMethod):
            visitor.visit(node, mock_ast_root)