====================
Backend Code Generation
====================

The backend stage is responsible for translating the validated and optimized AST into executable code for specific target platforms. This section covers the architecture and implementation of code generation backends.

Backend Architecture
====================

Target Platform Abstraction
---------------------------

GeLB backends follow a common architecture pattern that abstracts target platform differences:

**Common Backend Interface:**
- ``generate_code(ast, options)`` - Main entry point
- AST traversal using visitor pattern
- Template-based code emission
- Platform-specific optimizations

**Target Platform Specifics:**
- Language syntax and semantics
- Memory management strategies
- Parallelization models
- Performance optimization opportunities

Current Backend Implementation
=============================

Fortran Backend
--------------

**Location:** ``gelb/backends/stage3_backend_cpu_serial_fortran.py``

**Purpose:** Generates serial Fortran code for CPU execution

**Key Features:**
- Translates GeLB lattice operations to Fortran array operations
- Handles memory allocation and management
- Implements GeLB's block structure as Fortran subroutines
- Provides runtime support for lattice-based computations

**Target Use Cases:**
- Research prototyping and validation
- Single-core performance optimization
- Integration with existing Fortran codebases
- Educational and debugging purposes

Backend Code Generation Process
==============================

1. AST Traversal
---------------

Backends use the visitor pattern to systematically traverse the AST:

.. code-block:: python

    class FortranBackendVisitor(ASTBaseVisitor):
        """Generates Fortran code from GeLB AST."""
        
        def visitProgram_N(self, node, ast_root_node):
            # Generate program structure
            self.emit_program_header()
            self.visit_all_blocks(node)
            self.emit_program_footer()

2. Code Emission
---------------

Code is generated using template-based emission:

.. code-block:: python

    def emit_lattice_declaration(self, lattice_node):
        """Generate Fortran declaration for a lattice."""
        template = "real(kind=8), allocatable :: {name}({dims})"
        return template.format(
            name=lattice_node.name,
            dims=self.format_dimensions(lattice_node)
        )

3. Template System
-----------------

Common code patterns are handled through a template system:

- **Variable declarations** - Type-specific allocation
- **Implicit iteration patterns** - Lattice site traversal
- **Boundary conditions** - Edge case handling
- **I/O operations** - Data input/output formatting

4. Optimization
--------------

Target-specific optimizations are applied:

- **Memory layout optimization** - Efficient array access patterns
- **Lattice iteration optimization** - Minimize memory bandwidth requirements for implicit iterations
- **Instruction scheduling** - Platform-specific performance tuning
- **Compile-time range optimization** - Static loop bounds enable unrolling and vectorization

Compile-Time Range Benefits
---------------------------

GeLB's compile-time range restriction enables powerful backend optimizations:

**Static Loop Generation:**
All array and lattice access patterns have known bounds at compile time, allowing:

- **Loop unrolling** - Known iteration counts enable aggressive unrolling
- **Vectorization** - Static access patterns facilitate SIMD optimizations
- **Memory prefetching** - Predictable access patterns for cache optimization
- **Bounds check elimination** - No runtime overhead for range validation

**Example Backend Optimization:**

.. code-block:: fortran

    ! GeLB: array[real, 64] data; data[16:48] = 0.0;
    ! Fortran backend can generate:
    data(16:48) = 0.0d0  ! Direct array slice assignment
    
    ! Or with loop unrolling:
    !$OMP SIMD
    do i = 16, 48
        data(i) = 0.0d0
    end do

**Memory Access Patterns:**
Compile-time ranges ensure:

- **Contiguous memory access** - Better cache utilization
- **Predictable stride patterns** - Hardware prefetcher optimization
- **No indirect indexing** - Simplified address calculation

Fortran Backend Implementation Details
=====================================

Lattice Translation
------------------

GeLB lattices are translated to Fortran allocatable arrays:

.. code-block:: gelb

    // GeLB source
    lattice f(2, 9, real, {64, 32}, {true, true});

.. code-block:: fortran

    ! Generated Fortran
    real(kind=8), allocatable :: f_in(:,:,:)
    real(kind=8), allocatable :: f_out(:,:,:)
    ! Dimensions: (64, 32, 9)

Block Translation
----------------

GeLB blocks become Fortran subroutines:

.. code-block:: gelb

    // GeLB initializer
    initializer SetDensity {
        f.out[x,y | :] = equilibrium(1.0, 0.0, 0.0);
    }

.. code-block:: fortran

    ! Generated Fortran
    subroutine set_density()
        integer :: x, y, q
        do y = 1, Ny
            do x = 1, Nx
                do q = 1, 9
                    f_out(x, y, q) = equilibrium(1.0d0, 0.0d0, 0.0d0, q)
                end do
            end do
        end do
    end subroutine

Expression Translation
---------------------

GeLB expressions are mapped to Fortran equivalents:

- **Arithmetic operations** → Fortran operators
- **Array selections** → Fortran array indexing
- **Function calls** → Fortran function invocations
- **Type promotions** → Fortran type conversions
- **Broadcasting operations** → Fortran array assignment with scalar values

Broadcasting Translation
-----------------------

**Status**: 🚧 **PENDING IMPLEMENTATION**

GeLB's ``BroadcastNode_N`` enables efficient scalar-to-array assignment translation:

.. code-block:: gelb

    // GeLB source
    array[real, {64, 32}] density;
    density = 1.0;

**Fortran Translation:**

.. code-block:: fortran

    ! Efficient Fortran broadcast
    real(kind=8), allocatable :: density(:,:)
    allocate(density(64, 32))
    density(:,:) = 1.0d0

**C++ Translation:**

.. code-block:: cpp

    // Efficient C++ broadcast using std::fill
    std::vector<std::vector<double>> density(64, std::vector<double>(32));
    for (auto& row : density) {
        std::fill(row.begin(), row.end(), 1.0);
    }

**OpenCL Translation:**

.. code-block:: c

    // GPU kernel for broadcast
    __kernel void broadcast_fill(__global float* density, float value) {
        int idx = get_global_id(0);
        density[idx] = value;
    }

**Key Backend Advantages:**

1. **Fortran**: Native array assignment syntax (``array(:,:) = value``)
2. **C/C++**: Optimized with ``memset`` for numeric types or ``std::fill``
3. **GPU**: Embarrassingly parallel kernel operations
4. **SIMD**: Vector instruction utilization for performance

**Implementation Strategy:**

.. code-block:: python

    def visitBroadcastNode_N(self, node: BroadcastNode_N, ast_root_node):
        """Generate efficient broadcast code for target platform."""
        scalar_code = self.visit(node.scalar_expr, ast_root_node)
        target_type = node.target_array_type
        
        if self.target == "fortran":
            return f"{self.get_array_name()} = {scalar_code}"
        elif self.target == "cpp":
            return self.generate_cpp_fill(scalar_code)
        elif self.target == "opencl":
            return self.generate_gpu_kernel(scalar_code)

**Benefits for Backend Optimization:**

- **No Array Expansion**: Scalar value preserved through entire pipeline
- **Target-Specific**: Each backend can choose optimal implementation
- **Memory Efficient**: Avoids creating temporary arrays
- **Performance**: Leverages platform-specific optimizations

Future Backend Targets
======================

C/C++ Backend
------------

**Target Use Cases:**
- Integration with existing C/C++ simulation frameworks
- Performance-critical applications
- Library development and distribution

**Implementation Considerations:**
- Memory management with malloc/free or smart pointers
- Template-based generic programming
- Integration with numerical libraries (BLAS, LAPACK)

OpenCL Backend
-------------

**Target Use Cases:**
- GPU acceleration for massively parallel lattice operations
- Cross-platform heterogeneous computing
- High-throughput simulation studies

**Implementation Considerations:**
- Kernel-based computation model
- Memory hierarchy optimization (global, local, private memory)
- Work-group organization and synchronization

CUDA Backend
-----------

**Target Use Cases:**
- NVIDIA GPU optimization
- Advanced GPU features (shared memory, warp primitives)
- Maximum single-GPU performance

**Implementation Considerations:**
- CUDA-specific optimization techniques
- Memory coalescing and bank conflict avoidance
- Dynamic parallelism for complex algorithms

OpenMP Backend
-------------

**Target Use Cases:**
- Shared-memory multicore parallelization
- Hybrid CPU-GPU computing
- NUMA-aware optimization

**Implementation Considerations:**
- Thread-level parallelism
- Data locality optimization
- Load balancing strategies

Backend Development Guidelines
=============================

Creating a New Backend
----------------------

1. **Define Target Platform Requirements:**
   - Language syntax and semantics
   - Memory model and management
   - Parallelization capabilities
   - Performance characteristics

2. **Implement Backend Visitor:**

   .. code-block:: python

       class NewTargetBackendVisitor(ASTBaseVisitor):
           """Generates code for new target platform."""
           
           def __init__(self, options):
               self.code_buffer = []
               self.options = options
           
           def visitProgram_N(self, node, ast_root_node):
               # Generate target-specific program structure
               pass

3. **Handle All AST Node Types:**
   - Program structure (blocks, declarations)
   - Expressions (arithmetic, logical, comparisons)
   - Statements (assignments, lattice operations)
   - Literals and identifiers
   - Type promotions (TypePromotionNode_N)
   - Broadcasting operations (BroadcastNode_N)

4. **Implement Code Templates:**
   - Variable declarations
   - Control flow structures
   - Function definitions
   - I/O operations

5. **Add Optimization Passes:**
   - Target-specific optimizations
   - Memory layout optimization
   - Performance tuning

6. **Create Test Suite:**
   - Unit tests for code generation
   - Integration tests with real programs
   - Performance benchmarks

Code Generation Patterns
========================

Memory Management
----------------

Different targets require different memory management strategies:

**Fortran:** Allocatable arrays with automatic management
**C/C++:** Manual memory management or smart pointers
**GPU:** Device memory allocation and transfer
**Distributed:** Communication and synchronization

Parallelization Models
---------------------

**Serial:** Single-threaded execution
**OpenMP:** Shared-memory threads
**GPU:** Massively parallel kernels
**MPI:** Distributed memory processes

Error Handling
-------------

**Compile-time:** Type checking and validation
**Runtime:** Bounds checking and error reporting
**Platform-specific:** Device errors and resource management

Backend Testing
===============

Code Generation Tests
--------------------

Verify correct code generation for all language constructs:

.. code-block:: python

    def test_lattice_generation():
        ast = create_test_lattice_ast()
        code = generate_fortran_code(ast)
        assert "allocatable" in code
        assert "real(kind=8)" in code

Integration Tests
----------------

Test generated code compilation and execution:

.. code-block:: python

    def test_generated_code_compiles():
        gelb_source = load_test_program()
        fortran_code = compile_to_fortran(gelb_source)
        compile_result = compile_fortran(fortran_code)
        assert compile_result.success

Performance Tests
----------------

Benchmark generated code performance:

.. code-block:: python

    def test_performance_benchmark():
        large_program = create_performance_test()
        generated_code = compile_to_target(large_program)
        execution_time = benchmark_execution(generated_code)
        assert execution_time < performance_threshold

Backend Debugging
=================

Code Generation Debugging
-------------------------

1. **Inspect Generated Code:**
   - Print generated code for manual inspection
   - Compare with expected output patterns
   - Verify syntax correctness

2. **Test Individual Node Types:**
   - Generate code for isolated AST nodes
   - Verify correct translation patterns
   - Check edge cases and boundary conditions

3. **Use AST Visualization:**
   - Visualize AST structure before code generation
   - Identify problematic node patterns
   - Trace code generation issues to AST problems

Performance Debugging
---------------------

1. **Profile Generated Code:**
   - Use platform-specific profiling tools
   - Identify performance bottlenecks
   - Optimize critical code paths

2. **Memory Usage Analysis:**
   - Monitor memory allocation patterns
   - Identify memory leaks or excessive usage
   - Optimize data structures and access patterns

3. **Benchmark Comparisons:**
   - Compare with hand-optimized implementations
   - Identify optimization opportunities
   - Validate performance improvements

Best Practices
==============

For Backend Development
----------------------

* **Start with a simple, correct implementation**
* **Add optimizations incrementally**
* **Test thoroughly at each step**
* **Document platform-specific decisions**
* **Maintain clean separation between target platforms**

For Code Generation
-------------------

* **Use template-based emission for consistency**
* **Generate readable code for debugging**
* **Handle edge cases and error conditions**
* **Preserve source location information in comments**
* **Validate generated code syntax**

For Performance
--------------

* **Profile before optimizing**
* **Focus on algorithmic improvements first**
* **Use platform-specific optimization guides**
* **Benchmark against baseline implementations**
* **Document performance characteristics**

The backend architecture provides a flexible foundation for targeting multiple platforms while maintaining code quality, performance, and maintainability across different target environments.