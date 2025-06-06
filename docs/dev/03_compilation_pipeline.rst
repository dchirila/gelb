========================
Compilation Pipeline
========================

The GeLB compiler uses a three-stage compilation pipeline that transforms GeLB source code into optimized target language code. Understanding this pipeline is essential for compiler development and debugging.

Pipeline Overview
=================

The compilation pipeline consists of three main stages:

1. **Stage 1: Frontend** - Parsing, analysis, and validation
2. **Stage 2: Midware** - Transformations and optimizations
3. **Stage 3: Backend** - Code generation

Each stage has well-defined inputs, outputs, and responsibilities, making the compiler modular and extensible.

Stage 1: Frontend
=================

**Input:** GeLB source code (text)  
**Output:** Fully analyzed and validated AST

The frontend is responsible for converting source code into a structured representation and performing all semantic analysis.

Frontend Sub-stages
-------------------

The frontend runs multiple passes over the AST in a specific order:

1. **Parsing** - ANTLR4 generates parse tree from source code
2. **AST Building** - Convert parse tree to GeLB AST nodes
3. **Initial Validation** - Check basic AST structure
4. **Symbol Tables** - Build hierarchical symbol tables
5. **Implicit Symbols** - Add coordinate and dimension symbols
6. **Constants Resolution** - Resolve constant expressions
7. **Range Resolution** - Convert ``:`` to concrete bounds
8. **Type Inference** - Add type information to expressions
9. **Type Promotion** - Insert implicit conversion nodes
10. **Type Validation** - Verify type compatibility
11. **Final Validation** - Semantic checks and constraints

Frontend Implementation
-----------------------

The frontend is orchestrated by ``gelb/frontend/stage1_frontend.py``:

.. code-block:: python

    def compile_frontend(source_code):
        # Parse source code to AST
        ast = get_ast("gelb_program", source_code)
        
        # Validate basic structure
        validate_ast_root_is_program(ast)
        
        # Build symbol infrastructure
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        
        # Resolve constants and ranges
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        
        # Type analysis
        ast = infer_types(ast)
        ast = promote_types(ast)
        ast = validate_types(ast)
        
        # Final validation
        validate_node_classes(ast)
        
        return ast

Key Frontend Components
-----------------------

**ANTLR4 Generated Code** (``gelb/antlr_part/generated_code/``):
- Lexer and parser generated from ``GeLB.g4``
- Provides parse tree representation
- Handles syntax errors and basic parsing

**AST Builder** (``gelb/frontend/ASTBuilderVisitor.py``):
- Converts ANTLR4 parse tree to GeLB AST
- Eliminates parsing artifacts (parentheses, separators)
- Preserves source location information

**Symbol Resolution** (``gelb/frontend/SymbolsTablesBuilderVisitor.py``):
- Creates hierarchical symbol tables
- Establishes global_constants as parent scope
- Handles symbol definition and lookup

**Type System** (``gelb/frontend/Type*Visitor.py``):
- Infers types for all expressions
- Applies implicit type promotions
- Validates type compatibility

Stage 2: Midware
================

**Input:** Validated AST from frontend  
**Output:** Optimized and transformed AST

The midware performs AST transformations and optimizations to prepare for code generation.

Current Midware Implementation
------------------------------

The midware currently implements a **minimal pass-through design** for MVP development:

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

Future Midware Capabilities
---------------------------

The midware is designed to support these transformations:

**AST Normalization:**
- Expand compact notations to explicit forms
- Normalize coordinate ranges
- Standardize lattice access patterns

**Optimization Passes:**
- Constant folding and expression simplification
- Dead code elimination
- Common subexpression elimination
- Lattice access pattern optimizations

**Backend Preparation:**
- Lower high-level constructs to backend-friendly forms
- Add target-specific annotations
- Prepare data structures for code generation

Stage 3: Backend
================

**Input:** Transformed AST from midware  
**Output:** Target language source code

The backend generates executable code for specific target platforms.

Current Backend Implementation
------------------------------

**Fortran Backend** (``gelb/backends/stage3_backend_cpu_serial_fortran.py``):
- Generates serial Fortran code for CPU execution
- Translates GeLB constructs to Fortran equivalents
- Handles lattice operations and memory management

Backend Architecture
--------------------

Backends follow a common pattern:

1. **AST Traversal** - Visit all relevant AST nodes
2. **Code Emission** - Generate target language statements
3. **Template System** - Use code templates for common patterns
4. **Optimization** - Apply target-specific optimizations

Future Backends
---------------

Planned backend implementations:

- **C/C++ Backend** - For integration with existing C++ codebases
- **OpenCL Backend** - For GPU acceleration
- **CUDA Backend** - For NVIDIA GPU optimization
- **OpenMP Backend** - For shared-memory parallelization

Pipeline Integration
====================

Main Compiler Driver
--------------------

The complete pipeline is orchestrated by ``gelb/gelbc.py``:

.. code-block:: python

    def compile_program(source_file, backend_type="fortran"):
        # Read source code
        with open(source_file, 'r') as f:
            source_code = f.read()
        
        # Stage 1: Frontend
        ast = compile_frontend(source_code)
        
        # Stage 2: Midware
        ast = process_ast(ast)
        
        # Stage 3: Backend
        generated_code = generate_code(ast, backend_type)
        
        return generated_code

Error Handling Across Stages
-----------------------------

Each stage implements comprehensive error handling:

**Frontend Errors:**
- Syntax errors from ANTLR4 parser
- Symbol resolution errors
- Type checking errors
- Semantic validation errors

**Midware Errors:**
- Transformation failures
- Optimization constraint violations
- AST consistency errors

**Backend Errors:**
- Code generation failures
- Target platform limitations
- Resource constraint violations

Data Flow Between Stages
=========================

AST Enhancement
---------------

The AST is progressively enhanced as it moves through the pipeline:

**After Parsing:**
- Basic AST structure with parse tree artifacts removed
- Source location information preserved

**After Frontend:**
- Symbol tables attached to block nodes
- Type information on all expression nodes
- Implicit promotion nodes inserted
- All constants resolved to literal values
- Ranges converted to concrete bounds

**After Midware:**
- Optimizations applied
- High-level constructs lowered
- Backend annotations added

**After Backend:**
- Target language code generated
- Platform-specific optimizations applied

Debugging the Pipeline
======================

Pipeline Visualization
----------------------

Use AST visualization to see transformations:

.. code-block:: bash

    # See AST at different stages
    gelbc --visualize-ast --ast-stage parsing program.gelb
    gelbc --visualize-ast --ast-stage symbols program.gelb
    gelbc --visualize-ast --ast-stage constants program.gelb
    gelbc --visualize-ast --ast-stage ranges program.gelb

    # Compare all stages
    gelbc --visualize-ast --ast-stage all program.gelb

Stage-by-Stage Debugging
-------------------------

Debug individual stages by running them in isolation:

.. code-block:: python

    # Debug frontend only
    try:
        ast = compile_frontend(source_code)
        print("Frontend completed successfully")
    except Exception as e:
        print(f"Frontend error: {e}")
    
    # Debug midware with known good AST
    try:
        transformed_ast = process_ast(validated_ast)
        print("Midware completed successfully")
    except Exception as e:
        print(f"Midware error: {e}")

Common Pipeline Issues
----------------------

**Frontend Issues:**
- Parsing errors from malformed syntax
- Symbol resolution failures
- Type checking errors
- Missing implicit symbols

**Midware Issues:**
- AST transformation errors
- Optimization failures
- Type information loss

**Backend Issues:**
- Unsupported language constructs
- Target platform limitations
- Code generation template errors

Performance Considerations
=========================

Pipeline Efficiency
-------------------

The pipeline is designed for reasonable compile-time performance:

- **Single-pass design** where possible
- **Minimal AST copying** between stages
- **Lazy evaluation** for expensive operations
- **Parallel processing** opportunities in the future

Memory Management
-----------------

- AST nodes are reference-counted
- Symbol tables share references to avoid duplication
- Large constant values are stored once and referenced

Profiling Compilation
---------------------

Monitor compilation performance:

.. code-block:: python

    import time

    start_time = time.time()
    ast = compile_frontend(source_code)
    frontend_time = time.time() - start_time
    
    start_time = time.time() 
    ast = process_ast(ast)
    midware_time = time.time() - start_time
    
    print(f"Frontend: {frontend_time:.3f}s")
    print(f"Midware: {midware_time:.3f}s")

Extending the Pipeline
======================

Adding Frontend Passes
-----------------------

To add a new frontend validation or transformation:

1. **Create visitor class** inheriting from ``ASTBaseVisitor``
2. **Add to frontend pipeline** in ``stage1_frontend.py``
3. **Update tests** to cover new functionality
4. **Document the new pass** and its purpose

Adding Midware Transformations
-------------------------------

To add new midware optimizations:

1. **Implement transformation visitor**
2. **Add to midware pipeline** in ``stage2_midware.py``
3. **Ensure AST integrity** is maintained
4. **Test before and after** transformation states

Adding New Backends
--------------------

To support a new target platform:

1. **Create backend module** in ``gelb/backends/``
2. **Implement code generation** for all AST node types
3. **Add backend selection** logic to compiler driver
4. **Test generated code** executes correctly

Pipeline Testing
================

Integration Tests
-----------------

Test the complete pipeline with real programs:

.. code-block:: python

    def test_complete_pipeline():
        source_code = load_test_program()
        
        # Should not raise any exceptions
        generated_code = compile_program(source_code)
        
        # Verify generated code structure
        assert_valid_target_code(generated_code)

Stage-Specific Tests
--------------------

Test each stage independently:

.. code-block:: python

    def test_frontend_stage():
        ast = compile_frontend(test_source)
        assert isinstance(ast, Program_N)
        assert ast.global_constants is not None
        
    def test_midware_stage():
        validated_ast = get_validated_test_ast()
        transformed_ast = process_ast(validated_ast)
        assert_ast_integrity(transformed_ast)

Error Path Testing
------------------

Verify error handling in each stage:

.. code-block:: python

    def test_frontend_error_handling():
        with pytest.raises(GeLBParsingError):
            compile_frontend("invalid syntax")
            
    def test_type_error_reporting():
        with pytest.raises(GeLBExTypeError):
            compile_frontend("bool x = 1 && 2;")

The three-stage pipeline provides a clean, modular architecture that enables systematic development, testing, and debugging of the GeLB compiler while maintaining clear separation of concerns between parsing, optimization, and code generation.