========================
Extending the Compiler
========================

This section provides guidance for adding new features to the GeLB compiler, from language constructs to backend targets. Understanding the extension process is crucial for contributors.

Adding New Language Features
============================

The process of adding a new language feature involves several coordinated changes across the compilation pipeline:

1. Grammar Modification
----------------------

**Update the ANTLR4 Grammar** (``gelb/antlr_part/grammars/GeLB.g4``):

.. code-block:: antlr

    // Example: Adding a new statement type
    stmt : variable_assignment_stmt
         | constant_definition_stmt
         | new_feature_stmt          // New statement type
         | ...
         ;
    
    new_feature_stmt :
        NEW_KEYWORD lhs=expr OP_ASSIGN rhs=expr SEMICOLON ;

**Regenerate Parser Code:**

.. code-block:: bash

    ./scripts/regenerate_antlr.sh

2. AST Node Definition
---------------------

**Add New AST Node** (``gelb/gelb_ast/ASTNodes.py``):

.. code-block:: python

    class NewFeatureStmt_N(Stmt_N):
        """AST node for the new feature statement."""
        
        def __init__(self, code_range, lhs, rhs):
            super().__init__(code_range)
            self.lhs = lhs
            self.rhs = rhs
        
        def __eq__(self, other):
            return (isinstance(other, NewFeatureStmt_N) and
                    self.lhs == other.lhs and
                    self.rhs == other.rhs)

3. AST Builder Support
---------------------

**Update ASTBuilderVisitor** (``gelb/frontend/ASTBuilderVisitor.py``):

.. code-block:: python

    def visitNew_feature_stmt(self, ctx):
        """Convert parse tree to AST node."""
        code_range = self.get_code_range(ctx)
        lhs = self.visit(ctx.lhs)
        rhs = self.visit(ctx.rhs)
        return NewFeatureStmt_N(code_range, lhs, rhs)

4. Visitor Support
-----------------

**Update All Relevant Visitors:**

Each visitor that processes statements needs to handle the new node type:

.. code-block:: python

    # TypeInferenceVisitor
    def visitNewFeatureStmt_N(self, node, ast_root_node):
        # Add type inference logic
        self.visit(node.lhs, ast_root_node)
        self.visit(node.rhs, ast_root_node)
        return node
    
    # TypeValidationVisitor
    def visitNewFeatureStmt_N(self, node, ast_root_node):
        # Add validation logic
        self.visit(node.lhs, ast_root_node)
        self.visit(node.rhs, ast_root_node)
        # Validate feature-specific constraints
        return node

5. Backend Support
-----------------

**Update Backend Code Generation:**

.. code-block:: python

    # Fortran Backend
    def visitNewFeatureStmt_N(self, node, ast_root_node):
        """Generate Fortran code for new feature."""
        lhs_code = self.visit(node.lhs, ast_root_node)
        rhs_code = self.visit(node.rhs, ast_root_node)
        return f"! New feature: {lhs_code} = {rhs_code}"

6. Testing
---------

**Add Comprehensive Tests:**

.. code-block:: python

    # Parsing tests
    def test_parse_new_feature():
        source = "new_keyword x = 42;"
        result = parse_statement(source)
        assert isinstance(result, NewFeatureStmt_N)
    
    # AST building tests
    def test_build_new_feature_ast():
        parse_tree = parse_new_feature_statement()
        ast_node = ast_builder.visit(parse_tree)
        assert isinstance(ast_node, NewFeatureStmt_N)
    
    # Integration tests
    def test_new_feature_compilation():
        program = minimal_gelb_program_1d(
            initializer_content="new_keyword x = 42;"
        )
        ast = compile_frontend(program)
        # Should compile without errors

Feature Development Workflow
============================

Planning Phase
-------------

1. **Define Feature Scope:**
   - What problem does the feature solve?
   - How does it fit into the language design?
   - What are the interactions with existing features?

2. **Design Syntax:**
   - Choose clear, consistent syntax
   - Consider parsing complexity
   - Avoid conflicts with existing constructs

3. **Plan Implementation:**
   - Identify required AST nodes
   - Determine visitor modifications needed
   - Plan backend support requirements

Implementation Phase
-------------------

1. **Start with Grammar:**
   - Add grammar rules first
   - Test parsing with simple examples
   - Ensure no parsing conflicts

2. **Add AST Support:**
   - Create AST node definitions
   - Implement AST builder support
   - Test AST construction

3. **Frontend Integration:**
   - Add visitor support systematically
   - Implement semantic analysis
   - Add type system support if needed

4. **Backend Support:**
   - Implement code generation
   - Test generated code compilation
   - Verify runtime behavior

5. **Testing and Documentation:**
   - Add comprehensive test coverage
   - Update documentation
   - Create usage examples

Adding New Operators
====================

Adding a new operator requires special consideration for precedence and associativity:

1. Grammar Updates
-----------------

**Define Operator Precedence** (``GeLB.g4``):

.. code-block:: antlr

    expr : expr op=(OP_NEW_OP) expr     # newOpExpr
         | expr op=(OP_MUL | OP_DIV) expr  # infixExpr
         | ...
         ;

**Add Lexer Rule:**

.. code-block:: antlr

    OP_NEW_OP : '%%' ;  // Example: modulo operator

2. AST Node and Visitor Support
------------------------------

.. code-block:: python

    class NewOp_N(BinaryExpr_N):
        """AST node for new operator."""
        pass

    # Add to all relevant visitors
    def visitNewOp_N(self, node, ast_root_node):
        # Handle new operator in type inference, validation, etc.
        pass

3. Type System Integration
-------------------------

Define type rules for the new operator:

.. code-block:: python

    # TypeInferenceVisitor
    def visitNewOp_N(self, node, ast_root_node):
        # Define result type based on operand types
        left_type = node.left.inferred_type
        right_type = node.right.inferred_type
        
        # Example: modulo returns same type as operands
        if are_both_integers(left_type, right_type):
            node.inferred_type = ArrayDataType_N("int", List_N())
        else:
            raise GeLBExTypeError("Modulo requires integer operands")

Adding New Block Types
=====================

New block types require extensive integration across the compiler:

1. Grammar Definition
--------------------

.. code-block:: antlr

    program : simulation_description_stmt
            | global_constants_block
            | new_block_type  // Add new block
            | ...
            ;
    
    new_block_type :
        NEW_BLOCK IDENTIFIER BRACE_OPEN
        new_block_stmts
        BRACE_CLOSE ;

2. AST Integration
-----------------

.. code-block:: python

    class NewBlockType_N(Block_N):
        """New block type AST node."""
        
        def __init__(self, code_range, name, stmts):
            super().__init__(code_range)
            self.name = name
            self.stmts = stmts

3. Symbol Table Integration
--------------------------

Consider whether the new block needs its own symbol table:

.. code-block:: python

    # SymbolsTablesBuilderVisitor
    def visitNewBlockType_N(self, node, ast_root_node):
        # Create symbol table if needed
        node.symbol_defs = SymbolsTable(self.global_constants_symbol_table)
        
        # Process block contents
        for stmt in node.stmts:
            self.visit(stmt, ast_root_node)

Adding New Data Types
====================

Adding new data types requires careful integration with the type system:

1. Type Definition
-----------------

.. code-block:: python

    class ComplexDataType_N(Node_N):
        """Complex number data type."""
        
        def __init__(self, code_range):
            super().__init__(code_range)
            self.element_dtype = "complex"

2. Type System Updates
---------------------

**Update Type Promotion Hierarchy:**

.. code-block:: python

    # TypePromotionVisitor
    def _build_promotion_hierarchy(self):
        return {
            'bool': 0,
            'int': 1,
            'real': 2,
            'complex': 3,  # New type
        }

**Add Validation Rules:**

.. code-block:: python

    # TypeValidationVisitor
    def _build_validation_rules(self):
        return {
            'arithmetic': {'int', 'real', 'complex'},  # Include new type
            'comparison': {'int', 'real', 'bool', 'string'},
            'logical': {'bool'},
        }

3. Literal Support
-----------------

If the new type has literals, add parsing and AST support:

.. code-block:: antlr

    // Grammar for complex literals
    COMPLEX_LITERAL : REAL_PART 'i' ;

.. code-block:: python

    class ComplexLiteral_N(Literal_N):
        """Complex number literal."""
        
        def __init__(self, code_range, real_part, imag_part):
            super().__init__(code_range)
            self.real_part = real_part
            self.imag_part = imag_part

Adding New Backends
===================

Adding support for a new target platform:

1. Backend Module Creation
-------------------------

**Create Backend File** (``gelb/backends/stage3_backend_<target>.py``):

.. code-block:: python

    class NewTargetBackendVisitor(ASTBaseVisitor):
        """Code generator for new target platform."""
        
        def __init__(self, options):
            self.code_buffer = []
            self.options = options
        
        def visitProgram_N(self, node, ast_root_node):
            # Generate target-specific program structure
            self.emit_program_header()
            for block in node.get_all_blocks():
                self.visit(block, ast_root_node)
            self.emit_program_footer()
            return '\n'.join(self.code_buffer)

2. Code Generation Templates
---------------------------

Create templates for common patterns:

.. code-block:: python

    def emit_variable_declaration(self, name, data_type):
        """Generate variable declaration for target."""
        if data_type == "int":
            return f"int {name};"
        elif data_type == "real":
            return f"double {name};"
        # ... other types

3. Backend Integration
---------------------

**Add to Compiler Driver** (``gelbc.py``):

.. code-block:: python

    def generate_code(ast, backend_type):
        """Generate code for specified backend."""
        if backend_type == "fortran":
            return generate_fortran_code(ast)
        elif backend_type == "new_target":
            return generate_new_target_code(ast)
        else:
            raise ValueError(f"Unknown backend: {backend_type}")

Testing New Features
===================

Comprehensive Testing Strategy
-----------------------------

1. **Unit Tests:** Test individual components in isolation
2. **Integration Tests:** Test feature interactions
3. **End-to-End Tests:** Test complete compilation pipeline
4. **Regression Tests:** Ensure existing functionality still works

**Test Organization:**

.. code-block:: python

    # Unit tests for new feature
    class TestNewFeature:
        def test_parsing(self):
            """Test grammar parsing."""
            pass
        
        def test_ast_building(self):
            """Test AST construction."""
            pass
        
        def test_type_inference(self):
            """Test type system integration."""
            pass
        
        def test_code_generation(self):
            """Test backend support."""
            pass

Backward Compatibility
=====================

Maintaining Compatibility
------------------------

1. **Deprecation Process:**
   - Mark old features as deprecated
   - Provide migration guidance
   - Support old syntax for transition period

2. **Version Management:**
   - Document breaking changes clearly
   - Use semantic versioning
   - Provide upgrade tools where possible

3. **Testing Legacy Support:**
   - Maintain tests for deprecated features
   - Test existing examples continue to work
   - Verify migration paths work correctly

Documentation Requirements
=========================

For New Features
---------------

1. **Language Reference:** Update syntax documentation
2. **Examples:** Provide usage examples
3. **Migration Guide:** If replacing existing features
4. **Implementation Notes:** Document design decisions

For Contributors
---------------

1. **Extension Guide:** This document
2. **Architecture Changes:** Document new patterns
3. **Testing Guide:** New testing requirements
4. **Code Review:** Ensure quality standards

Best Practices for Extension
===========================

Development Guidelines
---------------------

* **Start Small:** Implement minimal viable version first
* **Test Early:** Add tests as you implement
* **Document Design:** Record design decisions
* **Consider Impact:** Think about interactions with existing features
* **Follow Patterns:** Use established code patterns and conventions

Code Quality
-----------

* **Consistent Style:** Follow existing code formatting
* **Clear Naming:** Use descriptive names for new constructs
* **Error Handling:** Provide clear error messages
* **Performance:** Consider compilation and runtime performance
* **Maintainability:** Write code that's easy to understand and modify

Review Process
-------------

* **Self Review:** Test thoroughly before submission
* **Code Review:** Get feedback from other developers
* **Integration Testing:** Verify with existing codebase
* **Documentation Review:** Ensure documentation is complete
* **User Testing:** Get feedback from potential users

The extension process requires careful coordination across multiple compiler components, but following these guidelines ensures that new features integrate cleanly with the existing system while maintaining code quality and backward compatibility.