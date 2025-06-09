============================
Appendix: Design Decisions
============================

This appendix captures important design decisions made during the development of the GeLB language and compiler. Understanding these decisions helps contributors and users comprehend why certain features work the way they do.

Many of these decisions represent changes from the original GeLB specification in the PhD thesis. For historical context and rationale, see the relevant sections below.

Language Design Decisions
=========================

Block Structure and Scope
--------------------------

**Constants in the lattices block**

**Decision**: Constants are NOT allowed directly in the ``lattices`` block.

**Rationale**: This maintains a clear separation of concerns:
- The ``lattices`` block is exclusively for lattice declarations (instantiations)
- Each block type has a single, well-defined purpose
- This makes the code structure clearer and more predictable

**Where to define constants instead**:
- **Global constants**: In the ``global_constants`` block (accessible throughout the program)
- **Local constants**: Inside ``initializer``, ``dynamic``, or ``gauge`` blocks (scoped to that block)

**Example**:

.. code-block:: gelb

    // Correct: Global constant
    global_constants {
        const real D = 2.0;
    }

    lattices {
        lattice f(d=D, q=9, df_type=real64);  // Can use global constant D
    }

    // Incorrect: Would cause a parser error
    lattices {
        const real D = 2.0;  // NOT ALLOWED - constants cannot be defined here
        lattice f(d=D, q=9, df_type=real64);
    }

Array Syntax
------------

**Square brackets vs angle brackets**

**Decision**: Array types use square brackets ``array[type, shape]`` instead of angle brackets ``array<type, shape>``.

**Rationale**: 
- The angle bracket syntax conflicted with the less-than operator ``<`` when comparison operators were added to the language
- Square brackets are more commonly used for array declarations in other languages
- This makes the parser unambiguous

**Example**:

.. code-block:: gelb

    // Current syntax (with square brackets)
    const array[real, {3, 3}] identity = {{1, 0, 0}, {0, 1, 0}, {0, 0, 1}};

    // Old syntax from PhD thesis (would conflict with < operator)
    // const array<real, {3, 3}> identity = {{1, 0, 0}, {0, 1, 0}, {0, 0, 1}};

String Literals
---------------

**Strings not allowed in expressions**

**Decision**: String literals (``STRING_LITERAL``) are intentionally excluded from expressions.

**Rationale**:
- Keeps the language simpler and more focused on numerical computations
- Strings are only needed in specific contexts (like simulation descriptions)
- Avoids complexity of string operations, concatenation, etc.

**Where strings can be used**:
- Only in the ``simulation_description`` statement

**Example**:

.. code-block:: gelb

    // Correct: String used in simulation_description
    simulation_description("2D Taylor-Green vortex simulation");

    // Not supported: Strings cannot be used in expressions or assignments
    // description = "some text";  // Would cause parser error

Numeric Literals
----------------

**Non-negative literals only**

**Decision**: The lexer only recognizes non-negative integer and real literals. Negative numbers are created using the unary minus operator.

**Rationale**:
- **Avoids lexer ambiguity**: In expressions like ``x-3``, it's clear this is ``x minus 3``, not ``x followed by -3``
- **Standard practice**: Used by C, Java, Python, and most other languages
- **Simpler lexer**: No need for complex lookahead rules
- **Consistent operator handling**: Unary minus works the same as other unary operators

**Implementation**:
- Lexer tokens: ``NON_NEGATIVE_REAL_LITERAL`` and ``NON_NEGATIVE_INT_LITERAL``
- Parser handles negation through ``unaryExpr`` rule
- ``-3.14`` is parsed as ``(UnaryMinusExpr (RealLiteral 3.14))``

**Examples**:

.. code-block:: gelb

    // These are all valid:
    x = 3.14;        // Positive literal
    y = -3.14;       // Unary minus applied to positive literal
    z = x - 3.14;    // Binary minus (subtraction)
    w = -(a + b);    // Unary minus applied to expression

    // AST representation:
    // -3.14 becomes: (UnaryMinusExpr (RealLiteral 3.14))
    // x-3.14 becomes: (Sub (Identifier x) (RealLiteral 3.14))

Assignment Statements
--------------------

**Array selection assignments**

**Decision**: Array selection assignments (e.g., ``my_array[0] = 42;``) are fully implemented.

**Rationale**:
- Provides complete array manipulation capabilities
- Consistent with other assignment statement types
- Essential for flexible array initialization and updates

**Current assignment types**:
- ``variable_assignment_stmt`` - for scalar variables
- ``lattice_out_selection_assignment_stmt`` - for lattice output selections
- ``array_selection_assignment_stmt`` - for array element selections

File and Program Naming
------------------------

**GeLB vs GD naming**

**Decision**: Use "GeLB" consistently throughout, not "GD" (GeLB Description).

**Rationale**:
- No reason to burden users with two acronyms
- The ``.gd`` file extension is already taken by other programming languages
- Simplifies documentation and reduces confusion

**Result**: 
- Files are called "GeLB programs" stored in "GeLB files" with ``.gelb`` extension
- All mentions of "GD" have been replaced with "GeLB"

**Simulation name from filename**

**Decision**: The ``simulation_name`` statement is no longer required.

**Rationale**:
- The filename is used as the simulation name automatically
- Reduces boilerplate code
- Makes the language more consistent
- One less thing for users to worry about

Version Management
------------------

**No gelb_version statement**

**Decision**: Programs no longer need to include a ``gelb_version`` statement.

**Rationale**:
- No plans to remove features from the language (backward compatibility)
- Forcing users to type this is pointless
- Simplifies the compiler
- Users have one less thing to worry about

**Future consideration**: Warn users if they're using an older compiler version that might not support newer features.

Geometry and Node Selection
---------------------------

**Rectangular selections only**

**Decision**: In the ``geometry`` block, only rectangular node-selections are allowed using the ``nodes`` statement.

**Rationale**:
- The ``node`` statement is not needed (it's just a special case of ``nodes``)
- The ``read_geometry_from_file`` statement needs more testing
- Keeps the initial implementation simpler

**Note**: ``nodes`` is equivalent to ``node_range`` from the thesis.

**Multiple initializers per node-class**

**Decision**: Allow more than one ``initializer`` for each node-class.

**Rationale**:
- Avoids imposing unnecessary constraints on users
- More flexible than the thesis version (which allowed only one)

**Lattice size and periodicity location (Major revision)**

**Original Design Decision (PhD thesis)**: Size and periodicity were to be specified in the ``geometry`` block using ``set_grid_size`` and ``set_grid_periodicity`` statements.

**Current Implementation (temporary)**: Following the PhD thesis approach with ``set_grid_size`` and ``set_grid_periodicity`` in the geometry block.

**Final Design Decision (to be implemented)**: Size and periodicity will be specified during lattice instantiation (in ``lattices`` block), not in ``geometry`` block.

**New Syntax**:

.. code-block:: gelb

    lattices {
      // 1D example
      lattice f(1,        // d: dimensionality
                1,        // q: number of discrete velocities  
                int,      // df_type: distribution function type
                32,       // grid_size: can be int or array {Nx} for 1D
                false     // periodicity: can be bool or array {periodic_x} for 1D
      );
      
      // 2D example
      lattice g(2, 9, real, {64, 32}, {true, false});
      
      // 3D example  
      lattice h(3, 27, real, {64, 64, 32}, {true, true, false});
    }

    geometry {
      // Simplified - only assigns node classes
      nodes[:] = BULK;     // 1D
      nodes[:,:] = BULK;   // 2D
      nodes[:,:,:] = BULK; // 3D
    }

**Rationale for the change**:
- **Logical cohesion**: Grid size and periodicity are inherent properties of the lattice structure, not the geometry
- **Self-contained lattice definitions**: All lattice properties (dimensions, velocities, data types, size, periodicity) in one place
- **Better separation of concerns**: Geometry block focuses solely on node class assignment
- **Cleaner dependency flow**: Nx, Ny, Nz are derived from lattice definitions, not geometry
- **Consistency**: Aligns with the principle that each block has a single, well-defined purpose

**Migration notes**:
- This is a breaking change from the current implementation
- All existing GeLB programs will need to be updated
- The compiler will need significant refactoring (grammar, AST, visitors)
- For GeLB v1, all lattices must have identical grid_size and periodicity

Syntax Conventions
------------------

**Parentheses for specifications**

**Decision**: ``gauge`` out-specs and ``function`` in/out-specs use parentheses instead of square brackets.

**Rationale**:
- Brings syntax closer to other programming languages
- More familiar to programmers

**Const keyword syntax**

**Decision**: Use ``const`` keyword prefix instead of ``_const`` suffix for constants.

**Rationale**:
- More natural syntax for programmers familiar with C-like languages
- Cleaner and more readable

**Examples**:

.. code-block:: gelb

    // Current syntax
    const real pi = 3.14;
    const array[int, {2, 2}] I = {{1, 0}, {0, 1}};

    // Old thesis syntax
    // real_const pi = 3.14;

Naming Conventions
------------------

**Block naming consistency**

**Current state**: Some blocks use ``_block`` suffix (e.g., ``global_constants_block``, ``lattices_block``) while others don't (e.g., ``initializer``, ``dynamic``, ``gauge``).

**Note**: This inconsistency exists for historical reasons and may be addressed in future versions for better consistency.

**Block order flexibility**

**Decision**: Allow users to specify blocks in any order they like.

**Rationale**:
- More flexible for users
- Different problems might have different natural orderings
- The compiler can handle any order

**Implementation note**: See GeLB.g4 line 7 comment.

Expression Evaluation
---------------------

**Operator precedence**

**Decision**: Follow standard operator precedence from mainstream programming languages.

**Precedence order** (highest to lowest):
1. Parentheses, literals, identifiers, array/lattice selections
2. Power (``^``) - right associative
3. Unary operators (``+``, ``-``, ``!``)
4. Multiplication/Division (``*``, ``/``)
5. Addition/Subtraction (``+``, ``-``)
6. Comparison (``<``, ``>``, ``<=``, ``>=``)
7. Equality (``==``, ``!=``)
8. Logical AND (``&&``)
9. Logical OR (``||``)

**Rationale**:
- Matches conventions from C/C++, Python, Java, and FORTRAN
- Follows standard mathematical precedence
- Minimizes surprises for users coming from other languages
- No need to memorize GeLB-specific rules

**Examples**:

.. code-block:: gelb

    // Mathematical precedence
    2 + 3 * 4        // = 14 (not 20)
    2 ^ 3 ^ 2        // = 512 (right associative: 2^(3^2) = 2^9)

    // Comparison before logical
    x > 5 && y < 10  // = (x > 5) && (y < 10)

    // AND before OR
    a || b && c      // = a || (b && c)

    // Unary has high precedence
    -x ^ 2           // = -(x^2), not (-x)^2
    !a && b          // = (!a) && b

Compiler Implementation Decisions
=================================

Visitor Pattern Design
----------------------

**Dynamic dispatch vs abstract visitor**

**Decision**: Use dynamic dispatch visitor pattern instead of traditional abstract visitor pattern.

**Rationale**:
- Visitors only implement methods they need
- Adding new AST node types doesn't require base class changes
- Reduces boilerplate code significantly
- Clear runtime error messages for missing methods

AST Node Design
---------------

**Code range tracking**

**Decision**: All AST nodes maintain source location information.

**Rationale**:
- Enables precise error reporting with line/column numbers
- Supports IDE integration features
- Essential for debugging and development tools

**Type information storage**

**Decision**: Add ``inferred_type`` attributes to expression nodes during compilation.

**Rationale**:
- Enables later compilation stages to access type information
- Supports type-aware optimizations
- Required for backend code generation

Symbol Resolution Strategy
--------------------------

**Hierarchical symbol tables**

**Decision**: Use two-level hierarchical symbol resolution (global_constants + local scopes).

**Rationale**:
- Simple but sufficient for current language features
- Clear scoping rules for users
- Efficient implementation
- Easy to extend if more complex scoping is needed

Type System Architecture
------------------------

**Three-phase type processing**

**Decision**: Separate type inference, promotion, and validation into distinct phases.

**Rationale**:
- Clear separation of concerns
- Each phase can focus on its specific task
- Easier to debug and maintain
- Enables independent testing of each phase

**Explicit promotion nodes**

**Decision**: Insert ``TypePromotionNode_N`` in AST for implicit conversions.

**Rationale**:
- Makes type conversions explicit in the AST
- Enables backend to generate appropriate conversion code
- Simplifies type validation logic
- Provides clear audit trail for promotions

Error Handling Philosophy
-------------------------

**Early error detection**

**Decision**: Catch errors as early as possible in the compilation pipeline.

**Rationale**:
- Better user experience with fast feedback
- Easier to provide precise error locations
- Prevents cascading errors in later stages

**Clear error messages**

**Decision**: Provide actionable error messages with hints.

**Rationale**:
- Improves user productivity
- Reduces support burden
- Makes the language more approachable

Range Resolution Strategy
-------------------------

**Two-part range handling**

**Decision**: Use defensive AST methods + explicit range resolution visitor.

**Rationale**:
- Handles ``None`` values safely during AST traversal
- Converts abstract ranges to concrete bounds
- Enables backend code generation
- Maintains flexibility for future range extensions

Future Features and Roadmap
============================

Coordinate Access in Geometry Blocks
------------------------------------

**Future Feature**: Allow using lattice coordinates (x, y, z) in geometry block expressions.

This would enable coordinate-based node painting patterns, e.g.:

.. code-block:: gelb

    nodes[:, y < 5] = WALL;           // Bottom wall
    nodes[x > Nx - 10, :] = OUTLET;   // Right outlet region
    nodes[x == 0, y == 0] = CORNER;   // Special corner treatment

**Current limitation**: x, y, z are only available in initializer, dynamic, and gauge blocks.

**Implementation considerations**:
- Would need to add implicit coordinate symbols to geometry block's symbol table
- Must ensure coordinates are properly bounded by grid dimensions
- Could enable more complex geometry specifications without external tools

Input / Output (I/O) Features
------------------------------

**Future Feature**: Test & enable compression for HDF5 / NetCDF files.

This can significantly improve the daily "quality of life" of users by:
- Reducing file sizes for large simulation datasets
- Faster file transfer and storage

**Implementation needs**:
- Test with different compression methods & levels
- Ensure files can be written & read on all platforms
- Verify compression does not slow down simulations significantly

Advanced Language Features
---------------------------

**Explicit Type Casting** (Future):

.. code-block:: gelb

    int n = int(3.14);     // Explicit cast with truncation
    bool b = bool(5);      // Explicit cast (non-zero → true)

**Function Blocks** (Future):
- Support more than one {in & out}-spec
- Enable user-defined pure functions

**Enhanced Geometry** (Future):
- Re-introduce ``read_geometry_from_file`` statement
- Extend ``nodes`` statement for arbitrary conditions based on coordinates
- Enable specification of spheres, cylinders, etc. within GeLB files

Compiler Architecture Evolution
-------------------------------

**Midware Transformations**:
- Constant folding and optimization passes
- AST normalization and simplification
- Backend-specific lowering transformations

**Additional Backends**:
- C/C++ code generation
- GPU OpenCL support
- OpenMP parallel execution
- CUDA backend for NVIDIA GPUs

**Enhanced Tooling**:
- Language server protocol (LSP) support
- Advanced debugging capabilities
- Performance profiling and optimization hints

Migration and Compatibility
===========================

Breaking Changes Management
---------------------------

**Philosophy**: Minimize breaking changes, but don't let backward compatibility prevent important improvements.

**Process for Breaking Changes**:
1. Document the change clearly
2. Provide migration tools where possible
3. Update all examples and documentation
4. Consider deprecation warnings before removal

**Major Breaking Changes Planned**:
- Moving lattice size/periodicity to lattices block
- Potential grammar improvements for clarity

Versioning Strategy
-------------------

**Semantic Versioning**: Following semver principles:
- Major version for breaking changes
- Minor version for new features
- Patch version for bug fixes

**Compiler Version Checking**: Future consideration to warn about version mismatches.

Legacy Support
--------------

**PhD Thesis Compatibility**: While the language has evolved significantly from the PhD thesis version, the core concepts remain stable.

**Documentation of Changes**: This appendix serves as the authoritative record of changes and their rationale.

Deviations from PhD Thesis
===========================

Compile-Time Range Validation
-----------------------------

**Decision**: Restrict range expressions to compile-time evaluable forms only.

**PhD Thesis Design**: Allowed arbitrary expressions in array ranges, including runtime variables and complex computations.

**Current Implementation**: Range expressions must be:
- Literals (e.g., ``5``, ``3.14``)
- Compile-time constants (e.g., ``N``, ``SIZE``)
- Grid dimensions (e.g., ``Nx``, ``Ny``, ``Nz``)
- Simple arithmetic combinations of the above

**Rationale for Change**:
- **Superior optimization**: Enables loop unrolling, memory layout optimizations, and vectorization
- **Clearer semantics**: Users know exactly what expressions are valid in ranges
- **Simplified backend**: Eliminates need for runtime range evaluation infrastructure
- **Better error messages**: Can validate ranges at compile time with precise diagnostics

**Language Advantage**: This restriction is promoted as a key advantage of GeLB over languages that allow arbitrary runtime range expressions, enabling superior compile-time optimization and clearer code semantics.

**Examples**:

.. code-block:: gelb

    // Valid: compile-time evaluable
    array[real, N] vec1;                    // Global constant
    nodes[0:5, :] = BULK;                  // Literal bounds
    f.out[x, y | 0:q-1] = expression;      // Constant arithmetic

    // Invalid: runtime evaluation required
    // array[real, size] vec2;             // Runtime variable
    // nodes[start:end, :] = BULK;         // Runtime bounds

Scalar-to-Array Broadcasting
----------------------------

**Decision**: Automatically promote scalars to arrays when needed through broadcast operations.

**PhD Thesis Design**: Required explicit array literal syntax for all array assignments.

**Current Implementation**: Assignments like ``array_var = scalar_value;`` automatically create broadcast nodes while preserving the original scalar for backend optimization.

**Rationale for Change**:
- **Improved usability**: Eliminates verbose array literal syntax for simple cases
- **Backend efficiency**: ``BroadcastNode_N`` preserves scalar values for runtime broadcasting
- **Consistent type system**: Scalars are treated as 0D arrays uniformly

**Examples**:

.. code-block:: gelb

    // Current syntax (automatic broadcasting)
    array[int, 3] vec = 1;              // Broadcasts 1 to {1, 1, 1}
    array[real, {2, 2}] mat = 0.0;      // Broadcasts 0.0 to {{0.0, 0.0}, {0.0, 0.0}}

    // PhD thesis syntax (required explicit literals)
    // array[int, 3] vec = {1, 1, 1};
    // array[real, {2, 2}] mat = {{0.0, 0.0}, {0.0, 0.0}};

Variable Declaration with Initialization
----------------------------------------

**Decision**: Support single-statement variable declaration and initialization.

**PhD Thesis Design**: Required separate declaration and assignment statements.

**Current Implementation**: Both syntaxes are supported:
- ``type var;`` followed by ``var = value;`` (original)
- ``type var = value;`` (new single-statement syntax)

**Rationale for Addition**:
- **Improved readability**: Reduces visual noise and line count
- **Familiar syntax**: Matches conventions from C, C++, Java, and other languages
- **Backward compatibility**: Original syntax remains fully supported

**Examples**:

.. code-block:: gelb

    // New syntax (single statement)
    real value = 3.14;
    int count = 42;
    array[real, 3] vec = {1.0, 2.0, 3.0};

    // Original syntax (still supported)
    real value;
    value = 3.14;

Array Range Selection Shape Reduction
-------------------------------------

**Decision**: Implement complete dimensional analysis for array slice operations.

**PhD Thesis Design**: Array selections were conceptual without full shape inference.

**Current Implementation**: Array selections with ranges properly calculate resulting dimensions:
- Single element selections reduce dimensionality
- Range selections preserve dimensions with calculated sizes
- Mixed selections handled correctly

**Rationale for Enhancement**:
- **Complete type system**: Enables full static analysis of array operations
- **Backend optimization**: Allows efficient memory layout planning
- **Better error detection**: Catches dimension mismatches at compile time

**Examples**:

.. code-block:: gelb

    array[int, {5, 3}] matrix;
    
    // Shape reductions
    matrix[2, :]        // Results in array[int, 3] (1D)
    matrix[:, 1]        // Results in array[int, 5] (1D)
    matrix[1:3, :]      // Results in array[int, {2, 3}] (2D)
    matrix[2, 1]        // Results in int (scalar)

**Documentation of Changes**: This appendix serves as the authoritative record of changes and their rationale.

---

*This document will be updated as new design decisions are made or existing ones are clarified.*