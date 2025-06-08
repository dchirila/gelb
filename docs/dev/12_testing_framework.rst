====================
Testing Framework
====================

GeLB has a comprehensive testing framework designed to ensure compiler correctness, maintainability, and reliability. Understanding the testing infrastructure is essential for contributing to the project.

Test Organization
=================

The test suite is organized hierarchically in ``gelb/tests/``:

**Unit Tests** (``gelb/tests/unit/``):
- Test individual components in isolation
- Focus on specific functionality
- Fast execution and minimal dependencies

**Integration Tests** (``gelb/tests/integration/``):
- Test component interactions
- End-to-end compilation pipelines
- Cross-stage functionality validation

**Test Utilities** (``gelb/tests/test_utils.py``):
- Shared test infrastructure
- Common test patterns and helpers
- Consistent test data generation

Test Categories
===============

AST Building Tests
-----------------

**Location:** ``gelb/tests/unit/ast_building/``

**Purpose:** Verify parse tree to AST conversion

**Key Test Files:**
- ``test_build_ast_expressions.py`` - Expression AST building
- ``test_build_ast_array_literals.py`` - Array literal handling
- ``test_build_ast_constant_definition_stmt.py`` - Constant definitions
- And many more for each AST node type

Parsing Tests
------------

**Location:** ``gelb/tests/unit/parsing/``

**Purpose:** Verify ANTLR4 grammar and parsing correctness

**Key Test Files:**
- ``test_parse_expressions.py`` - Expression parsing
- ``test_parse_array_literals.py`` - Array syntax parsing
- ``test_parse_global_constants_block.py`` - Block structure parsing

Type System Tests
----------------

**Location:** ``gelb/tests/unit/type_inference/``, ``gelb/tests/unit/type_promotion/``, ``gelb/tests/unit/type_validation/``

**Purpose:** Comprehensive type system validation

**Key Areas:**
- Universal ArrayDataType_N type system testing
- Scalar-as-array representation validation
- Type inference for all expression types
- Type promotion rule verification with broadcasting
- Shape preservation in operations
- Mixed scalar/array operation testing
- Lattice selection type inference
- Type validation error detection
- Edge cases and boundary conditions

**Array Type System Tests:**

.. code-block::

    gelb/tests/unit/type_inference/
    ├── test_array_type_system_comprehensive.py     # 19 scalar-as-array tests
    ├── test_shape_preservation_comprehensive.py    # 15 shape preservation tests
    ├── test_lattice_selection_type_inference.py    # 12 lattice selection tests
    ├── test_mixed_scalar_array_operations.py       # 12 mixed operation tests
    └── test_constant_folding_array_types.py        # 4 constant folding tests

Symbol Resolution Tests
----------------------

**Location:** ``gelb/tests/unit/symbols/``

**Purpose:** Symbol table and resolution testing

**Key Features:**
- Hierarchical symbol lookup
- Implicit symbol generation
- Symbol conflict detection
- Cross-block symbol access

Validation Tests
---------------

**Location:** ``gelb/tests/unit/validation/``

**Purpose:** Semantic validation and constraint checking

**Coverage:**
- Constant assignment validation
- Range resolution testing
- AST structure validation
- Language constraint enforcement

Test Utilities and Best Practices
=================================

Shared Test Infrastructure
-------------------------

**Critical Utilities in test_utils.py:**

.. code-block:: python

    # ✅ CORRECT - Use shared utilities
    from gelb.tests.test_utils import (
        get_typed_ast,           # For full frontend pipeline tests
        get_promoted_ast,        # For type inference + promotion only
        get_midware_ast,         # For frontend + midware pipeline tests
        get_validated_ast,       # For symbol table tests  
        get_resolved_ast,        # For constant/range resolution tests
        minimal_gelb_program_1d, # For 1D program templates
        minimal_gelb_program_2d, # For 2D program templates
        minimal_gelb_program_3d, # For 3D program templates
        assert_symbol_unknown_error,  # For exception testing
    )

**Program Templates:**

.. code-block:: python

    # Flexible test program generation
    test_code = minimal_gelb_program_1d(
        global_constants_content="const int N = 32;",
        initializer_content="real x; x = 1 + 2.5;"
    )

**Exception Testing Utilities:**

.. code-block:: python

    # Consistent error testing
    assert_symbol_unknown_error(test_string, "expected_symbol")
    assert_type_error(test_code, "expected_error_fragment")

Testing Anti-Patterns to Avoid
-----------------------------

**❌ NEVER duplicate these patterns:**

.. code-block:: python

    # ❌ WRONG - Don't create duplicate helper functions
    def get_typed_ast(gelb_code):  # Already exists in test_utils
    def minimal_gelb_program(...): # Already exists in test_utils

    # ❌ WRONG - Don't duplicate imports
    from gelb.frontend.stage1_frontend import (
        get_ast, build_symbols_tables, resolve_all_constants, 
        resolve_ranges, add_implicit_symbols, infer_types
    )

**❌ NEVER write excessive individual test functions:**

.. code-block:: python

    # ❌ WRONG - Excessive duplication
    def test_global_constants_block_invalid1(): # x
    def test_global_constants_block_invalid2(): # y  
    def test_global_constants_block_invalid3(): # z
    # ... 34 more nearly identical functions

**✅ CORRECT - Use parameterized tests:**

.. code-block:: python

    @pytest.mark.parametrize("symbol", get_coordinate_symbols() + get_dimension_symbols())
    def test_invalid_symbols_in_block(self, symbol):
        test_string = f"global_constants {{ const int X = {symbol}; }}"
        assert_symbol_not_allowed_error(test_string, "global_constants_block")

Effective Testing Patterns
==========================

Parameterized Testing
--------------------

Use parameterized tests for systematic coverage:

.. code-block:: python

    @pytest.mark.parametrize("data_type,expected", [
        ("int", ScalarDataType_N("int")),
        ("real", ScalarDataType_N("real")),
        ("bool", ScalarDataType_N("bool")),
    ])
    def test_scalar_data_type(self, data_type, expected):
        result = parse_data_type(data_type)
        assert_ast_equals(result, expected)

Integration Testing
------------------

Test complete pipelines with realistic scenarios:

.. code-block:: python

    def test_complete_type_pipeline():
        source_code = minimal_gelb_program_1d(
            initializer_content="real x; x = 1 + 2.5;"
        )
        
        # Should complete without errors
        ast = get_typed_ast(source_code)  # Full frontend pipeline
        
        # Verify final state
        assign_stmt = find_assignment_statement(ast)
        assert isinstance(assign_stmt.rhs, TypePromotionNode_N)
        assert isinstance(assign_stmt.rhs.target_type, ArrayDataType_N)
        assert assign_stmt.rhs.target_type.scalar_dtype == "real"
        assert len(assign_stmt.rhs.target_type.shape.elements) == 0  # 0D array

Error Testing
------------

Systematically test error conditions:

.. code-block:: python

    def test_type_validation_errors():
        error_cases = [
            ("bool b; b = 1 && 2;", "logical AND"),
            ("int x; x = 3.14;", "Cannot assign 'real' to 'int'"),
            ("bool b; b = !42;", "logical NOT"),
        ]
        
        for source, expected_error in error_cases:
            test_code = minimal_gelb_program_1d(initializer_content=source)
            with pytest.raises(GeLBExTypeError) as exc_info:
                get_typed_ast(test_code)  # Full frontend pipeline includes validation
            assert expected_error in str(exc_info.value)

**Testing Array Type System:**

.. code-block:: python

    def test_scalar_as_array_representation():
        """Test that scalar literals have ArrayDataType_N with 0D shape."""
        code = minimal_gelb_program_1d(initializer_content="int x; x = 42;")
        ast = get_typed_ast(code)
        
        # Find the assignment statement
        assign_stmt = ast.initializers[0].stmts.elements[1]
        rhs = assign_stmt.rhs
        
        # Check ArrayDataType_N with 0D shape
        assert isinstance(rhs.inferred_type, ArrayDataType_N)
        assert rhs.inferred_type.scalar_dtype == "int"
        assert isinstance(rhs.inferred_type.shape, List_N)
        assert len(rhs.inferred_type.shape.elements) == 0
    
    def test_shape_preservation_in_operations():
        """Test that array shapes are preserved in arithmetic operations."""
        code = minimal_gelb_program_1d(
            global_constants_content="const array[int, 3] vec = {1, 2, 3};",
            initializer_content="array[int, 3] result; result = vec + 5;"
        )
        ast = get_typed_ast(code)
        
        # Find assignment and check result type
        assign_stmt = ast.initializers[0].stmts.elements[1]
        add_expr = assign_stmt.rhs
        
        # Should preserve array shape from vec
        assert isinstance(add_expr.inferred_type, ArrayDataType_N)
        assert isinstance(add_expr.inferred_type.shape, IntLiteral_N)
        assert add_expr.inferred_type.shape.value == 3

    def test_lattice_selection_type_inference():
        """Test lattice selection type inference with ArrayDataType_N."""
        code = minimal_gelb_program_2d(
            lattices_content="lattice f(d=2, q=9, df_type=real);",
            initializer_content="real scalar; scalar = f.in[x,y|0];"
        )
        ast = get_typed_ast(code)
        
        # Find assignment and check lattice selection type
        assign_stmt = ast.initializers[0].stmts.elements[1]
        lattice_sel = assign_stmt.rhs
        
        # Single DF selection should return 0D array (scalar)
        assert isinstance(lattice_sel.inferred_type, ArrayDataType_N)
        assert lattice_sel.inferred_type.scalar_dtype == "real"
        assert len(lattice_sel.inferred_type.shape.elements) == 0  # 0D

Test Development Workflow
=========================

Writing New Tests
----------------

1. **Identify Test Scope:**
   - What functionality needs testing?
   - Which test category is appropriate?
   - Are there existing similar tests?

2. **Use Existing Utilities:**
   - Check ``test_utils.py`` for relevant helpers
   - Use program templates instead of hardcoded strings
   - Leverage existing assertion utilities

3. **Follow Naming Conventions:**
   - Descriptive test method names
   - Consistent file organization
   - Clear test class organization

4. **Ensure Comprehensive Coverage:**
   - Test positive cases (should work)
   - Test negative cases (should fail)
   - Test edge cases and boundaries

Running Tests
============

Test Execution Commands
-----------------------

.. code-block:: bash

    # Run all tests
    uv run pytest

    # Run specific test file
    uv run pytest gelb/tests/unit/type_inference/test_type_inference_literals.py

    # Run specific test class
    uv run pytest gelb/tests/unit/type_inference/test_type_inference_literals.py::TestLiteralTypeInference

    # Run specific test method
    uv run pytest gelb/tests/unit/type_inference/test_type_inference_literals.py::TestLiteralTypeInference::test_int_literal_type

    # Use pattern matching
    uv run pytest -k "test_type_inference"

    # Useful pytest flags
    uv run pytest -v        # Verbose output
    uv run pytest -s        # Show print statements
    uv run pytest -x        # Stop on first failure
    uv run pytest --tb=short # Shorter tracebacks
    uv run pytest -xvs      # Combination of useful flags

Test Categories by Purpose
=========================

Regression Tests
---------------

Prevent previously fixed bugs from reoccurring:

.. code-block:: python

    def test_range_resolution_none_handling():
        """Regression test for issue #123: None range bounds crash."""
        source = minimal_gelb_program_2d(
            geometry_content="nodes[:,:] = BULK;"
        )
        # Should not crash
        ast = get_resolved_ast(source)

Performance Tests
----------------

Ensure compilation performance remains acceptable:

.. code-block:: python

    def test_large_program_compilation_time():
        """Ensure large programs compile within reasonable time."""
        large_program = generate_large_test_program(1000)
        
        start_time = time.time()
        ast = compile_frontend(large_program)
        compilation_time = time.time() - start_time
        
        assert compilation_time < 10.0  # seconds

Compatibility Tests
------------------

Ensure backward compatibility:

.. code-block:: python

    def test_example_programs_compile():
        """Ensure all example programs still compile."""
        example_files = glob.glob("examples/**/*.gelb", recursive=True)
        
        for example_file in example_files:
            with open(example_file, 'r') as f:
                source_code = f.read()
            
            # Should compile without errors
            try:
                ast = compile_frontend(source_code)
            except Exception as e:
                pytest.fail(f"Example {example_file} failed to compile: {e}")

Test Data Management
===================

Test Program Generation
----------------------

Use utilities for consistent test data:

.. code-block:: python

    # Generate test programs with specific features
    def create_type_promotion_test(lhs_type, rhs_expr):
        return minimal_gelb_program_1d(
            initializer_content=f"{lhs_type} x; x = {rhs_expr};"
        )
    
    # Create test cases systematically
    type_promotion_cases = [
        ("real", "1"),      # int → real
        ("real", "true"),   # bool → real
        ("int", "false"),   # bool → int
    ]

Test File Organization
---------------------

Organize tests logically:

.. code-block::

    gelb/tests/
    ├── test_utils.py              # Shared utilities
    ├── unit/                      # Unit tests
    │   ├── ast_building/          # AST construction tests
    │   ├── parsing/               # Grammar and parsing tests
    │   ├── type_inference/        # Type system tests
    │   ├── symbols/               # Symbol resolution tests
    │   └── validation/            # Semantic validation tests
    └── integration/               # Integration tests
        ├── test_frontend.py       # Frontend pipeline tests
        ├── test_midware.py        # Midware tests
        └── test_backend_*.py      # Backend-specific tests

Continuous Integration
=====================

Automated Testing
----------------

The test suite is designed for CI/CD integration:

- **Fast execution** - Unit tests complete quickly
- **Reliable results** - Deterministic test outcomes
- **Clear reporting** - Informative test failure messages
- **Comprehensive coverage** - All major functionality tested

Test Quality Metrics
--------------------

Monitor test effectiveness:

- **Code coverage** - Ensure all code paths are tested
- **Test execution time** - Keep test suite fast
- **Test failure analysis** - Understand and fix flaky tests
- **Test maintenance** - Keep tests up to date with code changes

Type System Debugging
====================

Debugging Array Type Issues
---------------------------

When debugging the universal ArrayDataType_N system, use these patterns:

.. code-block:: python

    def test_debug_array_type_issue():
        problematic_code = minimal_gelb_program_1d(
            initializer_content="int x; x = 42 + 3.14;"
        )
        
        # Use appropriate pipeline helper for debugging
        
        # For type inference only:
        ast = get_promoted_ast(problematic_code)
        print("After promotion:", ast.some_expr.inferred_type)
        
        # For full frontend pipeline:
        ast = get_typed_ast(problematic_code)
        print("After full frontend:", ast.some_expr.inferred_type)
        
        # For midware testing (includes constant folding):
        ast = get_midware_ast(problematic_code)
        print("After midware:", type(ast.some_expr))
        
        # Check ArrayDataType_N properties
        if isinstance(ast.some_expr.inferred_type, ArrayDataType_N):
            shape = ast.some_expr.inferred_type.shape
            if isinstance(shape, List_N):
                print(f"Scalar (0D): {len(shape.elements) == 0}")
            elif isinstance(shape, IntLiteral_N):
                print(f"1D array size: {shape.value}")
            elif isinstance(shape, Array1DLiteral_N):
                print(f"Multi-D shape: {[elem.value for elem in shape.value.elements]}")

**Pipeline Helper Selection:**

- **get_promoted_ast()** - For testing type promotion only
- **get_typed_ast()** - For full frontend pipeline (includes validation)
- **get_midware_ast()** - For frontend + midware (includes constant folding)

**Common Array Type Debugging Checks:**

.. code-block:: python

    def debug_array_type_properties(expr_type):
        """Helper function to inspect ArrayDataType_N properties."""
        if not isinstance(expr_type, ArrayDataType_N):
            print(f"Not ArrayDataType_N: {type(expr_type)}")
            return
        
        print(f"Scalar type: {expr_type.scalar_dtype}")
        
        shape = expr_type.shape
        if isinstance(shape, List_N):
            if len(shape.elements) == 0:
                print("Type: 0D array (scalar)")
            else:
                print(f"Type: {len(shape.elements)}D array with shape elements")
        elif isinstance(shape, IntLiteral_N):
            print(f"Type: 1D array of size {shape.value}")
        elif isinstance(shape, Array1DLiteral_N):
            dims = [elem.value for elem in shape.value.elements]
            print(f"Type: {len(dims)}D array with shape {dims}")

Best Practices Summary
=====================

**DO:**
- Use shared test utilities consistently
- Write parameterized tests for systematic coverage
- Test both positive and negative cases
- Use descriptive test names and documentation
- Keep tests focused and independent
- Maintain test data systematically
- Test ArrayDataType_N properties for all expressions
- Verify shape preservation in array operations
- Use appropriate pipeline helpers (get_typed_ast, get_promoted_ast, get_midware_ast)

**DON'T:**
- Duplicate test utility functions
- Write excessive numbers of similar test methods
- Hardcode test data when templates are available
- Ignore test failures or mark them as expected
- Create interdependent tests
- Skip edge case testing
- Assume ScalarDataType_N for numeric types (use ArrayDataType_N)
- Forget to test shape preservation in operations
- Mix pipeline stages in tests without clear purpose

The GeLB testing framework provides a solid foundation for maintaining compiler quality while enabling confident refactoring and feature development.