===============
Type System
===============

GeLB implements a comprehensive type system with automatic type inference, promotion, and validation. Understanding this system is crucial for adding new language features and debugging type-related issues.

Type System Overview
====================

GeLB's type system is designed with these principles:

1. **Static Type Checking** - All types resolved at compile time
2. **Type Inference** - Minimize explicit type annotations
3. **Automatic Promotion** - Implicit conversions where safe
4. **Clear Error Messages** - Actionable feedback for type errors

Type Hierarchy
==============

The type promotion hierarchy in GeLB is:

.. code-block::

    bool → int → real

This means:
- ``bool`` can be promoted to ``int`` (false → 0, true → 1)
- ``int`` can be promoted to ``real`` (exact conversion)
- ``bool`` can be promoted to ``real`` (via int)

Data Type AST Nodes
===================

Universal ArrayDataType_N System
---------------------------------

**Core Design Philosophy:**
GeLB uses a universal type system where **all types are represented as ArrayDataType_N**, treating scalars as 0-dimensional arrays. This provides uniform type handling throughout the compiler and enables powerful array-aware optimizations.

**ArrayDataType_N (Primary Type)**

Represents all numeric and boolean types as arrays:
- Contains: ``element_dtype`` (element type) and ``shape`` (dimensions)
- **Scalars**: 0-dimensional arrays with empty shape ``List_N([])``
- **1D Arrays**: Shape is ``IntLiteral_N`` (array size)
- **2D+ Arrays**: Shape is ``Array1DLiteral_N`` (dimension list)

Examples:

.. code-block:: python

    # Integer literal "42" has type:
    ArrayDataType_N(code_range, "int", List_N([]))  # 0-dimensional
    
    # Array literal "{1, 2, 3}" has type:
    ArrayDataType_N(code_range, "int", IntLiteral_N(3))  # 1-dimensional
    
    # 2D array "{{1, 2}, {3, 4}}" has type:
    ArrayDataType_N(code_range, "int", Array1DLiteral_N([2, 2]))  # 2-dimensional

**StringType_N (Metadata Only)**

Used exclusively for non-computational metadata contexts:
- Simulation descriptions: ``simulation_description("text");``

**Important**: Strings are NOT part of the computational type system and cannot be used in:
- Expressions or computations
- Variable/constant declarations  
- Type promotion or validation
- Array/scalar type relationships

StringType_N is completely independent from the computational type system (ArrayDataType_N).

Expression Type Inference
=========================

Literals
--------

All literals extend Literal_N which extends Expr_N:

- **IntLiteral_N** → inferred type: ArrayDataType_N("int", List_N([]))
- **RealLiteral_N** → inferred type: ArrayDataType_N("real", List_N([]))
- **BoolLiteral_N** → inferred type: ArrayDataType_N("bool", List_N([]))
- **StringLiteral_N** → StringType_N *(metadata only, not part of computational type system)*
- **Array1DLiteral_N** → inferred type: ArrayDataType_N(element_type, IntLiteral_N(size))
- **Array2DLiteral_N** → inferred type: ArrayDataType_N(element_type, Array1DLiteral_N(dimensions))
- **Array3DLiteral_N** → inferred type: ArrayDataType_N(element_type, Array1DLiteral_N(dimensions))
- **Array4DLiteral_N** → inferred type: ArrayDataType_N(element_type, Array1DLiteral_N(dimensions))

**Key Implementation Methods:**

.. code-block:: python

    def _create_scalar_array_type(self, code_range, element_dtype):
        """Create a 0-dimensional array type representing a scalar."""
        empty_shape = List_N(code_range)
        return ArrayDataType_N(code_range, element_dtype, empty_shape)

Binary Expressions
-------------------

All binary expressions extend BinaryExpr_N which extends Expr_N:

**Arithmetic Operations:**
- **Add_N** (+) → type promotion rules + broadcasting apply
- **Sub_N** (-) → type promotion rules + broadcasting apply
- **Mul_N** (*) → type promotion rules + broadcasting apply
- **Div_N** (/) → type promotion rules + broadcasting apply
- **Pow_N** (^) → type promotion rules + broadcasting apply

**Comparison Operations:**
- **Less_N** (<) → always returns ArrayDataType_N("bool", ...)
- **Greater_N** (>) → always returns ArrayDataType_N("bool", ...)
- **LessEqual_N** (<=) → always returns ArrayDataType_N("bool", ...)
- **GreaterEqual_N** (>=) → always returns ArrayDataType_N("bool", ...)
- **Equal_N** (==) → always returns ArrayDataType_N("bool", ...)
- **NotEqual_N** (!=) → always returns ArrayDataType_N("bool", ...)

**Logical Operations:**
- **And_N** (&&) → requires ArrayDataType_N("bool", ...) operands
- **Or_N** (||) → requires ArrayDataType_N("bool", ...) operands

**Broadcasting Rules:**

For mixed scalar/array operations:

- **Scalar + Array → Array**: Result preserves array shape
- **Array + Scalar → Array**: Result preserves array shape  
- **Type Promotion**: Applies to scalar types while preserving shapes

Example:

.. code-block:: gelb

    const array[int, 3] vec = {1, 2, 3};
    const int scalar = 5;
    const array[int, 3] result = scalar + vec;  // Broadcasting: scalar → array shape

**Scalar-to-Array Assignment Broadcasting:**

When assigning a scalar to an array variable, the scalar is broadcast to fill the entire array:

- **Scalar → Array Assignment**: Creates BroadcastNode_N in AST
- **Type Promotion + Broadcasting**: Type promotion occurs first, then broadcasting
- **Backend Optimization**: Allows efficient target-specific code generation

Examples:

.. code-block:: gelb

    array[real, 5] data;
    data = 3.14;        // Direct broadcast: real scalar → real array
    
    array[real, {2, 3}] matrix;
    matrix = 42;        // Type promotion + broadcast: int → real → broadcast
    
    array[bool, 8] flags;
    flags = true;       // Direct broadcast: bool scalar → bool array

**Key Implementation Methods:**

.. code-block:: python

    def _get_shape_if_array(self, expr_type):
        """Normalize shape to List_N format for broadcasting."""
        # Handles IntLiteral_N, Array1DLiteral_N, and List_N shapes
    
    def _denormalize_shape(self, normalized_shape, code_range):
        """Convert normalized List_N back to proper shape format."""
        # 0D → List_N, 1D → IntLiteral_N, 2D+ → Array1DLiteral_N

Unary Expressions
-----------------

All unary expressions extend UnaryExpr_N which extends Expr_N:
- **NotExpr_N** (!) → requires ArrayDataType_N("bool", ...) operand, preserves shape
- **UnaryMinusExpr_N** (-) → preserves operand type and shape

Other Expression Types
----------------------

- **Identifier_N** → ArrayDataType_N from symbol table lookup
- **RectSelOfLatticeInDFs_N** → ArrayDataType_N from lattice definition with proper shape
- **RectSelOfLatticeOutDFs_N** → ArrayDataType_N from lattice definition with proper shape
- **RectSelOfArrayElems_N** → ArrayDataType_N with scalar shape (0D) for element access

**Lattice Selection Integration:**

Lattice selections integrate seamlessly with the array type system:

- **Full DF selection** ``f.in[x|:]`` returns ArrayDataType_N(df_type, IntLiteral_N(q))
- **Single DF selection** ``f.in[x|0]`` returns ArrayDataType_N(df_type, List_N([]))
- **Mixed operations** with lattice selections follow broadcasting rules

Type Promotion System
=====================

Type Promotion Rules by Context
-------------------------------

**1. Binary Arithmetic Operations (+, -, *, /, ^)**

For binary arithmetic operations, both operands are promoted to a common type:

.. code-block:: gelb

    // Examples:
    1 + 2.5      // int + real → real(1) + 2.5 → 3.5 (real)
    true + 5     // bool + int → int(true) + 5 → 1 + 5 → 6 (int)
    false * 3.14 // bool * real → real(false) * 3.14 → 0.0 * 3.14 → 0.0 (real)

**Algorithm:**
1. If either operand is ``real`` → promote both to ``real``
2. Else if either operand is ``int`` → promote both to ``int``
3. Else both are ``bool`` → promote both to ``int``

**2. Comparison Operations (<, >, <=, >=, ==, !=)**

For comparison operations, both operands are promoted to a common type before comparison:

.. code-block:: gelb

    1 < 2.5      // int < real → real(1) < 2.5 → true (bool)
    true == 1    // bool == int → int(true) == 1 → 1 == 1 → true (bool)
    0 != false   // int != bool → 0 != int(false) → 0 != 0 → false (bool)

**Algorithm:**
- Same as arithmetic operations for finding common type
- Result is always ``bool``

**3. Assignment Operations**

For assignments, the RHS is promoted to the LHS type if compatible:

.. code-block:: gelb

    real x = 5;        // int → real(5) → 5.0
    int n = true;      // bool → int(true) → 1
    real y = false;    // bool → real(false) → 0.0

    // Invalid (no demotion):
    int n = 3.14;     // ERROR: Cannot demote real to int
    bool b = 5;       // ERROR: Cannot demote int to bool

**4. Array Literals**

All elements in an array literal are promoted to a common type:

.. code-block:: gelb

    array[real, 3] data = {1, 2.5, 3};     // → {1.0, 2.5, 3.0}
    array[int, 3] nums = {false, true, 2}; // → {0, 1, 2}

Special Cases
-------------

**1. Logical Operations (&&, ||, !)**

Logical operations do NOT perform type promotion:

.. code-block:: gelb

    true && false   // OK: bool && bool
    1 && 2         // ERROR: int && int not allowed
    !0             // ERROR: !int not allowed

**2. String Type**

Strings are NOT part of the computational type system and cannot be used in expressions:

.. code-block:: gelb

    "hello" + 1    // ERROR: Strings cannot be used in computational expressions
    int x = "hello";  // ERROR: Strings cannot be used in variable declarations

**3. Array Types**

Array types follow the universal ArrayDataType_N system:

.. code-block:: gelb

    array[int, 3] a = {1, 2, 3};
    array[real, 3] b = a;  // ERROR: No array-to-array promotion
    real x = a;            // ERROR: No array-to-scalar promotion
    
    // But scalars (0D arrays) can be promoted:
    real y = 5;            // int literal (0D) promoted to real (0D)
    array[real, 3] c = {1, 2.5, 3};  // Mixed elements promoted to common type

TypePromotionNode_N
-------------------

The compiler inserts ``TypePromotionNode_N`` in the AST wherever implicit promotion occurs:

.. code-block::

    // Source: 1 + 2.5
    // AST after type inference:
    Add_N {
      left: IntLiteral_N(1)
      right: RealLiteral_N(2.5)
    }

    // AST after type promotion:
    Add_N {
      left: TypePromotionNode_N {
        expr: IntLiteral_N(1)
        target_type: ArrayDataType_N("real", List_N([]))
      }
      right: RealLiteral_N(2.5)
    }

BroadcastNode_N  
---------------

The compiler inserts ``BroadcastNode_N`` in the AST for scalar-to-array assignment operations:

.. code-block::

    // Source: array[real, 5] data; data = 42;
    // AST after type inference:
    VariableAssignmentStmt_N {
      lhs: Identifier_N("data") 
      rhs: IntLiteral_N(42)
    }

    // AST after type promotion:
    VariableAssignmentStmt_N {
      lhs: Identifier_N("data")
      rhs: BroadcastNode_N {
        scalar_expr: TypePromotionNode_N {
          expr: IntLiteral_N(42)
          target_type: ArrayDataType_N("real", List_N([]))
        }
        target_array_type: ArrayDataType_N("real", IntLiteral_N(5))
        inferred_type: ArrayDataType_N("real", IntLiteral_N(5))
      }
    }

**Key Design Principles:**

1. **Efficiency**: Preserves scalar value rather than expanding to full array
2. **Backend Optimization**: Enables target-specific optimized code generation
3. **Type Safety**: Integrates with type promotion system for safe conversions
4. **Compiler Pipeline**: Works seamlessly with existing type inference and validation

TypePromotionVisitor Implementation
===================================

The **TypePromotionVisitor** class handles implicit type promotions by inserting TypePromotionNode_N where needed:

Key Methods
-----------

``_can_promote(from_type, to_type)``
  Check if a type can be promoted to another type

``_get_common_type(type1, type2)``
  Find the common type that both types can be promoted to

``_needs_promotion(expr_type, target_type)``
  Check if an expression needs promotion to a target type

``_create_promotion(expr, target_type_name)``
  Create a TypePromotionNode_N wrapping the expression

``_is_scalar_array(array_type)``
  Check if a type represents a scalar (0-dimensional array)

``_create_broadcast(scalar_expr, target_array_type)``
  Create a BroadcastNode_N for scalar-to-array assignment

Promotion Contexts
------------------

The visitor handles promotion in these contexts:

1. **Arithmetic Binary Operations** - Both operands promoted to common type
2. **Comparison Operations** - Both operands promoted to common type
3. **Assignment Statements** - RHS promoted to LHS type, with broadcasting for scalar→array
4. **Constant Definitions** - Value promoted to declared type
5. **Array Literals** - All elements promoted to common type

**Broadcasting in Assignment Statements:**

When the TypePromotionVisitor encounters a scalar-to-array assignment:

1. **Type Promotion First**: Scalar is promoted to the array's element type if needed
2. **Broadcasting Second**: Promoted scalar is wrapped in BroadcastNode_N
3. **Preserves Efficiency**: Scalar value is not expanded in the frontend
4. **Backend Flexibility**: Allows backends to choose optimal implementation strategy

.. code-block:: python

    def _handle_assignment(self, node, ast_root_node):
        lhs_type = node.lhs.inferred_type
        rhs_type = node.rhs.inferred_type
        
        lhs_is_scalar = self._is_scalar_array(lhs_type)
        rhs_is_scalar = self._is_scalar_array(rhs_type)
        
        if not lhs_is_scalar and rhs_is_scalar:
            # Scalar-to-array broadcasting case
            node.rhs = self._create_broadcast(node.rhs, lhs_type)
        elif lhs_is_scalar and rhs_is_scalar:
            # Regular scalar assignment with promotion
            if self._needs_promotion(rhs_type, lhs_type):
                node.rhs = self._create_promotion(node.rhs, lhs_type.element_dtype)

Type Validation System
======================

The **TypeValidationVisitor** validates type compatibility after promotions have been applied.

Validation Rules
----------------

**1. Arithmetic Operations (+, -, *, /, ^):**
- After promotion: both operands must be same numeric type
- Result type = operand type

**2. Comparison Operations (<, >, <=, >=, ==, !=):**
- After promotion: both operands must be same type
- Result type = bool

**3. Logical Operations (&&, ||):**
- Both operands must be bool (no promotion)
- Result type = bool

**4. Unary Minus (-):**
- Operand must be numeric (int or real)
- Result type = operand type

**5. Logical NOT (!):**
- Operand must be bool
- Result type = bool

Assignment Validation
---------------------

**1. Variable Assignment:**
- RHS type must be promotable to LHS declared type

**2. Constant Definition:**
- Value type must be promotable to declared type

**3. Lattice Selection Assignment:**
- RHS type must match lattice df_type (after promotion)

**4. Array Selection Assignment:**
- RHS type must match array element type (after promotion)

**5. Broadcast Operations:**
- BroadcastNode_N operations are always valid (created by TypePromotionVisitor)
- Scalar expression within broadcast is validated recursively

TypeValidationVisitor Implementation
====================================

Key Methods
-----------

``_validate_arithmetic_op(left_type, right_type, op_name, node)``
  Validate arithmetic operation compatibility

``_validate_comparison_op(left_type, right_type, op_name, node)``
  Validate comparison operation compatibility

``_validate_logical_op(left_type, right_type, op_name, node)``
  Validate logical operation compatibility

``_validate_assignment(lhs_type, rhs_type, node)``
  Validate assignment compatibility

``visitBroadcastNode_N(node, ast_root_node)``
  Validate broadcast operations (always valid, validates scalar expression)

Error Reporting
===============

The type system provides enhanced error messages using ``GeLBExTypeError`` with source context:

**Type Errors with Source Context:**

.. code-block::

         ...
       6  
       7  initializer Init {
       8->    f.out[x | 0] = scalar_var[x];
                             ~~~~~~~~~~^^                    [Problem] Cannot index scalar 'scalar_var' with 1 indices
                                                             [Hint] 'scalar_var' is a scalar value and cannot be indexed. Only arrays can be indexed with []
       9  }
      10  
          ...

         ...
       6  
       7  initializer Init {
       8->    f.out[x | 0] = undefined_var;
                             ~~~~~~~~~~~~~^^                 [Problem] You mention undefined_var. However, you did not define it.
                                                             [Hint] Define undefined_var.
       9  }
      10  
          ...

    Error: Division by zero: cannot divide by zero
           ...
       6  
       7  initializer Init {
       8->    f.out[x | 0] = 1 / 0;
                                 ^^                         [Problem] Division by zero: cannot divide by zero
                                                            [Hint] Remove the division by zero or use a non-zero divisor
       9  }
      10  
          ...

**User-Friendly Terminology:**

GeLB presents user-friendly terminology while maintaining internal consistency:

- **External**: "scalar" (user-friendly term)
- **Internal**: "0-dimensional array" (implementation detail)
- **Error Messages**: Use "scalar" to match user mental model
- **Type System**: Uses ArrayDataType_N universally

**Improved Error Messages:**

* **Source Context**: Shows exact source location with arrows
* **Clear Descriptions**: "Cannot index scalar" vs technical array dimensions
* **Actionable Hints**: Specific guidance for fixing the issue
* **Consistent Terminology**: Uses language concepts familiar to users

Array Range Selection Shape Reduction
======================================

The type inference system includes sophisticated shape reduction for array range selections. When an array is accessed with range specifications, the resulting type's shape is calculated based on which dimensions are selected as single elements versus ranges.

Shape Reduction Rules
---------------------

**1. Single Element Selection:**
- Removes that dimension from the result shape
- ``array[2, 3, 4]`` on ``array[real, {10, 20, 30}]`` → ``array[real, ()]`` (scalar)

**2. Range Selection:**
- Preserves that dimension with the range size
- ``array[:, 1:3, 5]`` on ``array[real, {10, 20, 30}]`` → ``array[real, {10, 3}]``

**3. Full Range Selection (``:``):**
- Preserves that dimension with its original size
- ``array[2, :, :]`` on ``array[real, {10, 20, 30}]`` → ``array[real, {20, 30}]``

Implementation Details
----------------------

The **TypeInferenceVisitor** implements shape reduction in the ``visitRectSelOfArrayElems_N`` method:

**Step 1: Validate Index Count**

.. code-block:: python

    # Check for too many indices before proceeding
    if len(node.element_ranges.elements) > len(original_dimensions):
        raise GeLBException(
            f"Too many indices: array has {len(original_dimensions)} dimensions but {len(node.element_ranges.elements)} indices provided",
            f"at {node.code_range}"
        )

**Step 2: Classify Range Types**

Each range is classified as:
- **Single Element**: ``[3]`` or ``[3:3]`` → dimension removed
- **Partial Range**: ``[1:4]`` → dimension size = ``4 - 1 + 1 = 4``
- **Full Range**: ``[:]`` → dimension size = original size
- **Open-ended Range**: ``[5:]`` → dimension size = ``original_size - 5``

**Step 3: Calculate Resulting Dimensions**

.. code-block:: python

    for i, range_elem in enumerate(element_ranges.elements):
        dimension_size = original_dimensions[i]
        range_type, new_size = self._classify_range_selection(range_elem, dimension_size, ast_root_node, original_dimensions)
        
        if range_type != "single_element":
            # Keep this dimension with the new size
            resulting_dimensions.append(new_size)
        # For single_element, dimension is removed

**Step 4: Construct Result Type**

The final array type is constructed with the reduced shape:
- **0 dimensions** → ``array[element_type, ()]`` (scalar)
- **1 dimension** → ``array[element_type, size]``
- **2+ dimensions** → ``array[element_type, {size1, size2, ...}]``

Symbolic Expression Handling
-----------------------------

The shape reduction system handles symbolic expressions in range bounds:

**Symbolic Dimensions:**
- ``Nx``, ``Ny``, ``Nz`` resolve to lattice grid dimensions
- User-defined constants resolve to their values
- Complex expressions like ``Ny-1`` are evaluated

**Resolution Priority:**
1. **Array Context**: For expressions in array ranges, ``Nx``/``Ny``/``Nz`` refer to the array's dimensions
2. **Symbol Table**: Look up user-defined constants
3. **Lattice Grid**: Extract from lattice instantiation statements
4. **Fallback**: Default values for undefined symbols

**Example:**

.. code-block:: gelb

    array[real, {Nx, Ny}] matrix;
    array[real, Ny-1] slice;
    slice = matrix[3, 1:Ny-1];  // Creates array[real, {Ny-2}]

Compile-Time Range Validation
-----------------------------

GeLB enforces compile-time evaluable range expressions, enabling superior optimization and clearer semantics.

**Restriction**: Range expressions must be compile-time evaluable:

.. code-block:: gelb

    // Valid: compile-time evaluable
    array[real, N] vec1;                    // Global constant
    nodes[0:5, :] = BULK;                  // Literal bounds
    f.out[x, y | 0:q-1] = expression;      // Constant arithmetic
    matrix[1:Nx-1, 2:Ny] = data;           // Grid dimensions

    // Invalid: runtime evaluation required
    // array[real, size] vec2;             // Runtime variable
    // nodes[start:end, :] = BULK;         // Runtime bounds
    // matrix[i:j, :] = data;              // Loop variables

**Allowed Range Expressions:**

1. **Literals**: ``5``, ``3.14``, ``0``
2. **Compile-time constants**: User-defined constants from ``global_constants`` block
3. **Grid dimensions**: ``Nx``, ``Ny``, ``Nz`` from lattice definitions
4. **Simple arithmetic**: ``N-1``, ``q+1``, ``Nx/2`` using compile-time values

**Target Application Patterns:**

Lattice Boltzmann Method simulations typically use static access patterns that work perfectly with compile-time ranges:

.. code-block:: gelb

    // Full distribution function access
    f.out[x,y|:] = f.in[x,y|:];
    
    // Specific distribution function access
    rho = f.in[x,y|0] + f.in[x,y|1];
    
    // Boundary conditions with grid dimensions
    inlet[0,1:Ny-2] = INLET;
    boundary[:,:] = WALL;
    
    // Neighbor access patterns
    f.out[x,y|0] = f.in[x+1,y|0];
    
    // Range selections with constants
    const int HALF = Nx/2;
    center_region[HALF-5:HALF+5, :] = data;

**Validation Process:**

The **TypeInferenceVisitor** validates range expressions using ``_validate_compile_time_evaluable``:

.. code-block:: python

    def _validate_compile_time_evaluable(self, expr, context="range expression"):
        """Ensure expression can be evaluated at compile time."""
        if expr is None:
            return True  # None is valid (open-ended ranges)
        elif isinstance(expr, (IntLiteral_N, RealLiteral_N, BoolLiteral_N)):
            return True  # Literals are always compile-time
        elif isinstance(expr, Identifier_N):
            if self._is_compile_time_constant(expr.name):
                return True
            else:
                raise GeLBExTypeError(
                    expr,
                    f"Expression in {context} must be compile-time evaluable",
                    f"Variable '{expr.name}' is not allowed here. Only compile-time constants..."
                )
        elif isinstance(expr, (Add_N, Sub_N, Mul_N, Div_N)):
            # Recursively validate arithmetic expressions
            self._validate_compile_time_evaluable(expr.left, context)
            self._validate_compile_time_evaluable(expr.right, context)
            return True
        else:
            raise GeLBExTypeError(
                expr,
                f"Expression in {context} must be compile-time evaluable",
                f"This expression type is not allowed in {context}"
            )

**Optimization Benefits:**

1. **Loop Unrolling**: Backends can unroll loops with known iteration counts
2. **Memory Layout**: Optimal memory allocation and access patterns
3. **Vectorization**: Enable SIMD optimizations with fixed-size operations
4. **Bounds Checking**: Eliminate runtime bounds checks where possible
5. **Code Generation**: Generate target-specific optimized indexing code

Range Bound Evaluation
----------------------

The system evaluates range bounds to determine selection sizes:

.. code-block:: python

    def _evaluate_range_bound(self, expr, ast_root_node, array_dimensions=None):
        if isinstance(expr, IntLiteral_N):
            return expr.value
        elif isinstance(expr, Identifier_N):
            return self._resolve_symbolic_dimension(expr.name, ast_root_node, array_dimensions)
        elif isinstance(expr, Sub_N):
            # Handle expressions like "Nx-1"
            left_val = self._evaluate_range_bound(expr.left, ast_root_node, array_dimensions)
            right_val = self._evaluate_range_bound(expr.right, ast_root_node, array_dimensions)
            return left_val - right_val

AST Structure Preservation
---------------------------

**Critical Design Principle**: The shape reduction process only adds the ``inferred_type`` attribute to ``RectSelOfArrayElems_N`` nodes. The original range information is completely preserved for backend code generation.

**Original Ranges Maintained:**
- ``element_ranges`` list contains original ``Range_N`` nodes
- Symbolic expressions like ``Sub (Identifier Ny) (IntLiteral 1)`` are preserved
- Range bounds (``low``, ``high``) remain unchanged
- Open-ended ranges keep ``high = None``

**Backend Benefits:**
- Can generate optimal indexing code using original expressions
- Preserves symbolic expressions for target language optimization
- Maintains exact range specifications for bounds checking

**Example AST Preservation:**

.. code-block::

    // GeLB Code:
    a[2, 0:2] = b[3, 5:Ny-1];
    
    // AST Structure (preserved):
    LHS: RectSelOfArrayElems
      element_ranges: [Range(2,2), Range(0,2)]
      inferred_type: array[real, {3}]    // ← Added by type inference
    
    RHS: RectSelOfArrayElems  
      element_ranges: [Range(3,3), Range(5, Sub(Identifier(Ny), IntLiteral(1)))]
      inferred_type: array[real, {Ny-6}]  // ← Added by type inference

Error Detection
---------------

The shape reduction system provides comprehensive error detection:

**1. Too Many Indices:**

.. code-block::

    array[int, {2, 3}] matrix;
    elem = matrix[0, 1, 2];  // ERROR: Too many indices: array has 2 dimensions but 3 indices provided

**2. Negative Range Sizes:**
- Handled gracefully with fallback behavior
- ``array[4:2]`` → size defaults to 1

**3. Out-of-Bounds Access:**
- Range bounds are validated against array dimensions
- Symbolic bounds are evaluated where possible

Testing Coverage
----------------

The shape reduction feature includes comprehensive unit tests:

- **12 test cases** covering all reduction scenarios
- **Single element selections** (2D → scalar)
- **Mixed selections** (2D → 1D)
- **Partial and open-ended ranges**
- **Multi-dimensional reductions**
- **Error cases and edge cases**
- **Symbolic expression evaluation**

GeLBExTypeError Exception
-------------------------

Type errors are reported using ``GeLBExTypeError`` which provides enhanced error reporting:

- **Source Location**: Exact line and column information from ``code_range``
- **Visual Context**: Shows source code with arrows pointing to problematic expressions
- **User-Friendly Messages**: Uses terminology familiar to users ("scalar" vs "0-dimensional array")
- **Actionable Hints**: Specific guidance for resolving the error
- **Consistent Interface**: Used throughout Frontend, Midware, and validation stages

**Key Features:**

.. code-block:: python

    raise GeLBExTypeError(
        node,  # AST node with code_range information
        "Cannot index scalar 'var_name' with 1 indices",  # Clear error
        "Only arrays can be indexed with []. Use 'var_name' directly."  # Hint
    )

This produces user-friendly error messages with source context and actionable guidance.

Type System Integration
======================

Compilation Pipeline
--------------------

Type processing occurs in this order:

1. **Type Inference** - Add ``inferred_type`` attributes
2. **Type Promotion** - Insert ``TypePromotionNode_N`` where needed
3. **Type Validation** - Verify all operations are type-safe

Pipeline Integration:

.. code-block:: python

    ast = get_ast("gelb_program", source_code)
    # ... symbol resolution, constants, ranges ...
    ast = infer_types(ast)          # Type inference
    ast = promote_types(ast)        # Type promotion
    ast = validate_types(ast)       # Type validation

Testing the Type System
=======================

Test Categories
---------------

**Type Promotion Tests** (``gelb/tests/unit/type_promotion/``):
- Arithmetic promotion (int + real → real)
- Comparison promotion (bool < int → int < int)
- Assignment promotion (real x = 5 → real x = real(5))
- Array literal promotion
- Nested expression promotion
- Broadcasting tests (scalar → array assignment)
- Broadcasting with type promotion (int → real → broadcast)

**Type Validation Tests** (``gelb/tests/unit/type_validation/``):
- Valid operations after promotion
- Invalid logical operations (int && int)
- Invalid assignments (real → int)
- Type mismatch detection
- Broadcasting validation (BroadcastNode_N always valid)
- Scalar expression validation within broadcasts

**Midware Tests** (``gelb/tests/unit/midware/``):
- Constant folding within broadcast nodes
- Broadcast preservation during optimization
- Type promotion integration with constant folding
- Broadcast with complex scalar expressions

Test Utilities
--------------

.. code-block:: python

    from gelb.tests.test_utils import get_typed_ast, minimal_gelb_program_1d

    def test_type_promotion():
        ast = get_typed_ast("real x; x = 1 + 2.5;")
        # ast now has types inferred and promotions applied

Common Testing Patterns
-----------------------

**Testing Valid Promotions:**

.. code-block:: python

    def test_int_to_real_promotion():
        code = minimal_gelb_program_1d(initializer_content="real x; x = 42;")
        ast = get_typed_ast(code)
        ast = promote_types(ast)
        
        # Check that RHS is wrapped in TypePromotionNode_N
        assign_stmt = ast.initializers[0].stmts.elements[1]
        assert isinstance(assign_stmt.rhs, TypePromotionNode_N)
        assert isinstance(assign_stmt.rhs.target_type, ArrayDataType_N)
        assert assign_stmt.rhs.target_type.element_dtype == "real"
        assert len(assign_stmt.rhs.target_type.shape.elements) == 0  # 0D array

**Testing Type Errors:**

.. code-block:: python

    def test_invalid_logical_operation():
        code = minimal_gelb_program_1d(initializer_content="bool b; b = 1 && 2;")
        ast = get_typed_ast(code)
        ast = promote_types(ast)
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            validate_types(ast)
        
        assert "logical AND" in str(exc_info.value)
        assert "expected 'bool'" in str(exc_info.value)

**Testing Array Type System:**

.. code-block:: python

    def test_scalar_as_array_type():
        """Test that scalar literals have ArrayDataType_N with 0D shape."""
        code = minimal_gelb_program_1d(initializer_content="int x; x = 42;")
        ast = get_typed_ast(code)
        
        # Find the assignment statement
        assign_stmt = ast.initializers[0].stmts.elements[1]
        rhs = assign_stmt.rhs
        
        # Check ArrayDataType_N
        assert isinstance(rhs.inferred_type, ArrayDataType_N)
        assert rhs.inferred_type.element_dtype == "int"
        
        # Check 0D shape
        shape = rhs.inferred_type.shape
        assert isinstance(shape, List_N)
        assert len(shape.elements) == 0  # 0D scalar

Extending the Type System
=========================

Adding New Types
----------------

To add a new scalar type (e.g., ``complex``):

1. **Update promotion hierarchy** in TypePromotionVisitor
2. **Add validation rules** in TypeValidationVisitor  
3. **Update type inference** for new literal types
4. **Add test coverage** for new type interactions

Adding New Operations
---------------------

To add a new operation (e.g., modulo ``%``):

1. **Add AST node** (e.g., ``Mod_N``)
2. **Update grammar** with new operator
3. **Add type inference** rules
4. **Add promotion** handling  
5. **Add validation** rules
6. **Update backend** code generation

Type System Debugging
=====================

Common Issues
-------------

1. **Missing type information** - Check if TypeInferenceVisitor ran
2. **Unexpected promotions** - Verify promotion hierarchy rules
3. **Type validation failures** - Check if promotions were applied correctly
4. **Symbol type errors** - Verify symbol table contains type information

Debugging Tools
---------------

**AST Visualization:**

.. code-block:: bash

    gelbc --visualize-ast --ast-stage all program.gelb

**Type Information Inspection:**

.. code-block:: python

    # Check inferred types
    print(f"Expression type: {expr_node.inferred_type}")
    
    # Check for promotions
    if isinstance(node, TypePromotionNode_N):
        print(f"Promoted from {node.expr.inferred_type} to {node.target_type}")

**Test-Driven Debugging:**

.. code-block:: python

    def test_debug_type_issue():
        ast = get_typed_ast(problematic_code)
        
        # Check each stage
        print("After type inference:", ast.some_expr.inferred_type)
        
        ast = promote_types(ast)
        print("After promotion:", type(ast.some_expr))
        
        # This should not raise
        ast = validate_types(ast)

Best Practices
==============

For Type System Development
---------------------------

* **Test edge cases thoroughly** - Type systems have many corner cases
* **Provide clear error messages** - Include source location and hints
* **Maintain promotion transitivity** - If A→B and B→C, then A→C
* **Document type rules clearly** - Make promotion hierarchy explicit
* **Preserve type information** - Don't lose types during transformations
* **Handle universal ArrayDataType_N** - All numeric types are 0D arrays
* **Implement broadcasting correctly** - Scalar/array operations preserve array shapes
* **Test shape preservation** - Ensure array shapes are maintained through operations

For Language Users
------------------

* **Use explicit types when unclear** - Help the type checker
* **Understand promotion rules** - Know when conversions happen
* **Watch for logical operations** - They don't promote automatically
* **Test boundary conditions** - Mixed-type expressions can be tricky