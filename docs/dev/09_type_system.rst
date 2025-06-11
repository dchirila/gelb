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

**Array Arithmetic Operations**

GeLB supports arithmetic operations on arrays with automatic broadcasting and shape compatibility checking:

.. code-block:: gelb

    // Array + Scalar (Broadcasting)
    f.out[x | :] = f.in[x | :] + 1;        // Broadcasts scalar 1 to array shape
    
    // Array * Scalar (Broadcasting)  
    f.out[x | :] = f.in[x | :] * 0.5;      // Broadcasts scalar 0.5 to array shape
    
    // Array + Array (Element-wise, same shape required)
    f.out[x | :] = f.in[x | :] + g.in[x | :];  // Arrays must have compatible shapes

**Broadcasting Rules:**
- **Scalar + Array** → Scalar is broadcast to match array shape
- **Array + Scalar** → Scalar is broadcast to match array shape  
- **Array + Array** → Arrays must have identical shapes for element-wise operation

**Type Promotion with Arrays:**
Arrays follow the same type promotion rules as scalars for element types:

.. code-block:: gelb

    // Type promotion with broadcasting
    array[int, 3] int_array = {1, 2, 3};
    real scalar = 2.5;
    array[real, 3] result = int_array + scalar;  // → {3.5, 4.5, 5.5}

**Lattice Selection Arithmetic:**
Lattice selections (with the ``|`` separator) return arrays and fully support arithmetic operations:

.. code-block:: gelb

    lattices {
        lattice f(1, 3, int, 32, false);  // 3 distribution functions
    }
    
    dynamic Update {
        // Lattice selection returns array, arithmetic operations work naturally
        f.out[x | :] = f.in[x | :] + 1;           // Add 1 to all DFs
        f.out[x | 0] = f.in[x | 0] * 2;           // Multiply specific DF by 2
        f.out[x | :] = f.in[x | :] + g.in[x | :]; // Element-wise lattice addition
    }

**Validation:**
- Element types must be numeric (``int`` or ``real``) for arithmetic operations
- Shape compatibility is enforced for array-array operations
- Broadcasting is handled automatically by the type promotion system

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

Type Demotion Prevention
------------------------

GeLB strictly enforces the **unidirectional** type promotion hierarchy to prevent precision loss and unexpected behavior. Type "demotion" (conversion in the reverse direction: real → int → bool) is forbidden.

**Prohibited Type Demotions:**

.. code-block:: gelb

    // Scalar assignments
    real temperature = 98.6;
    int count = temperature;        // ERROR: real → int (precision loss)
    
    int level = 42;
    bool flag = level;              // ERROR: int → bool (precision loss)
    
    real value = 3.14159;
    bool status = value;            // ERROR: real → bool (precision loss)

**Scalar-to-Array Broadcasting with Demotion:**

.. code-block:: gelb

    // Array assignments with type demotion
    array[int, 5] integers;
    real pi = 3.14159;
    integers = pi;                  // ERROR: real → int array (precision loss)
    
    array[bool, 3] flags;
    int count = 5;
    flags = count;                  // ERROR: int → bool array (precision loss)

**Lattice Output Assignments:**

.. code-block:: gelb

    lattices {
        lattice f(1, 1, int, 32, false);  // int lattice
    }
    
    initializer Init {
        real value = 3.14;
        f.out[x | 0] = value;       // ERROR: real → int (precision loss)
    }

**Error Messages:**

Type demotion errors provide clear feedback with source context:

.. code-block::

    error: ...
      9      real real_value = 3.14;
     10->    int_array = real_value;
                         ^^                 [Problem] Cannot assign 'real' to array of 'int' - would lose precision
                                            [Hint] Type promotion only allows: bool → int → real. Consider using an explicit cast when available.
     11  }

**Rationale:**

1. **Precision Preservation**: Prevents accidental data loss (3.14 → 3)
2. **Predictable Behavior**: Clear promotion direction eliminates ambiguity
3. **Type Safety**: Catches potential bugs at compile time
4. **Explicit Intent**: Forces developers to use explicit casts for intentional demotions

**Future Support - Explicit Type Casts:**

When intrinsic functions are implemented, explicit casts will enable controlled type demotions:

.. code-block:: gelb

    // Future syntax (not yet implemented)
    real pi = 3.14159;
    int truncated = int_cast(pi);       // Explicit: 3.14159 → 3
    bool is_nonzero = bool_cast(pi);    // Explicit: 3.14159 → true

**Implementation Details:**

Type demotion prevention is enforced in two places:

1. **TypePromotionVisitor**: Validates scalar-to-array broadcasting operations
2. **TypeValidationVisitor**: Validates direct scalar assignments and lattice assignments

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

**2. String Type Restrictions**

Strings are completely isolated from the computational type system and are only allowed in specific metadata contexts:

.. code-block:: gelb

    // ✅ ALLOWED: Only in simulation description
    simulation_description("This is valid");
    
    // ❌ FORBIDDEN: All computational uses
    "hello" + 1              // ERROR: Strings excluded from expressions
    int x = "hello";         // ERROR: No string scalar type exists
    array[string, 2] strs;   // ERROR: No string array type exists
    
**Grammar Enforcement:**
- String literals are explicitly excluded from all expression contexts
- ``array[string, ...]`` declarations are not permitted by the grammar
- String types cannot be used in variable declarations or computational contexts

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

Lattice Parameter Validation
=============================

Lattice parameter validation ensures that lattice instantiations follow GeLB's structural constraints. This validation occurs in the **ConstantsResolverVisitor** after constants are resolved to their final values.

Validation Rules
----------------

**1. Dimensionality Constraints:**
- Must satisfy: ``1 <= d <= 3``
- GeLB supports only 1D, 2D, and 3D lattices

**2. Distribution Function Constraints:**
- Must satisfy: ``q > 0``
- Zero distribution functions are not meaningful for LBM

**3. Grid Size Constraints:**
- All grid size values must be positive: ``grid_size > 0``
- Applies to both scalar grid sizes (1D) and array elements (2D/3D)

**4. Shape Consistency Constraints:**
- For ``d=1``: ``grid_size`` must be scalar, ``periodicity`` must be scalar
- For ``d=2``: ``grid_size`` must be 2-element array, ``periodicity`` must be 2-element array  
- For ``d=3``: ``grid_size`` must be 3-element array, ``periodicity`` must be 3-element array

Constant Expression Support
---------------------------

The validation system handles constants and arithmetic expressions:

**Simple Constants:**

.. code-block:: gelb

    global_constants {
        const int N = 64;
        const int D = 2;
    }
    
    lattices {
        lattice f(D, 9, int, {N, N}, {false, true});  // Valid
    }

**Arithmetic Expression Constants:**

.. code-block:: gelb

    global_constants {
        const int BASE = 16;
        const int SIZE = BASE * 2;     // Evaluates to 32
        const int BAD = BASE - 20;     // Evaluates to -4 
    }
    
    lattices {
        lattice f(1, 1, int, SIZE, false);  // Valid: SIZE = 32
        lattice g(1, 1, int, BAD, false);   // Error: grid size -4 invalid
    }

**Complex Expression Evaluation:**

The system evaluates:
- Addition (``+``), Subtraction (``-``), Multiplication (``*``), Division (``/``)
- Nested expressions: ``(BASE + 10) * 2 - 5``
- Unary minus: ``-N``, ``-(BASE + 5)``

Validation Examples
-------------------

**Common Error Cases:**

.. code-block:: gelb

    global_constants {
        const int D = 5;        // Invalid dimensionality
        const int Q = 0;        // Invalid distribution functions  
        const int N = -32;      // Invalid grid size
    }
    
    lattices {
        lattice f(D, Q, int, N, false);
        // Errors generated:
        // - "Lattice dimensionality d=5 is invalid"
        // - "Number of distribution functions q=0 is invalid" 
        // - "Grid size -32 is invalid"
    }

**Shape Mismatch Examples:**

.. code-block:: gelb

    lattices {
        // Shape mismatch: d=1 but grid_size has 2 elements
        lattice f(1, 1, int, {32, 64}, false);
        // Error: "Grid size has 2 elements but d=1"
        
        // Periodicity mismatch: grid_size is scalar but periodicity is array
        lattice g(1, 1, int, 32, {false, true});
        // Error: "Periodicity has 2 elements but grid_size is scalar"
    }

**Validation Timing:**

This validation occurs in **ConstantsResolverVisitor** rather than **TypeValidationVisitor** because:

1. **Constants must be resolved first**: ``const int N = -32`` needs to be evaluated before validation
2. **Expression evaluation required**: ``BASE - 20`` must be computed to ``-4`` before checking positivity
3. **Shape analysis needs concrete values**: Cannot validate array shapes with unresolved identifiers

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

Assignment Target Validation
============================

GeLB provides enhanced validation for assignment operations with user-friendly error messages that clearly distinguish between array and scalar types.

Validation Rules
----------------

**1. Array-to-Scalar Assignment (Invalid):**

Array values cannot be assigned to scalar variables as this would lose dimensional information:

.. code-block:: gelb

    array[real, {2, 2}] matrix;
    real scalar_var;
    scalar_var = matrix;  // ERROR: Invalid assignment

**Error Message:**

.. code-block::

    error: Cannot assign array[real, {2, 2}] to scalar 'real'
         8      initializer Init {
         9->        scalar_var = matrix;
                                  ~~~~~~^^                    [Problem] Cannot assign array[real, {2, 2}] to scalar 'real'
                                                              [Hint] Scalars cannot hold array values. Use array indexing like 'matrix[0, 1]' to get a single element
        10      }

**2. Scalar-to-Array Assignment (Valid - Broadcasting):**

Scalar values CAN be assigned to array variables through the broadcasting system:

.. code-block:: gelb

    real scalar_val = 3.14;
    array[real, 5] vector;
    vector = scalar_val;  // ✅ Valid: Creates BroadcastNode_N

This assignment is handled by the TypePromotionVisitor which creates a BroadcastNode_N that efficiently broadcasts the scalar value to fill the entire array.

**3. Array Element Selection (Valid):**

Individual array elements can be assigned to scalars:

.. code-block:: gelb

    array[real, {2, 2}] matrix;
    real element;
    element = matrix[0, 1];  // ✅ Valid: Single element access

User-Friendly Type Descriptions
-------------------------------

The validation system provides clear, user-friendly type descriptions in error messages:

**Type Description Function:**

.. code-block:: python

    def _get_user_friendly_type_description(self, data_type):
        """Create user-friendly type description for error messages."""
        if isinstance(data_type, ArrayDataType_N):
            # 0D arrays (scalars)
            if len(data_type.shape.elements) == 0:
                return f"scalar '{data_type.element_dtype}'"
            
            # 1D arrays  
            elif isinstance(data_type.shape, IntLiteral_N):
                return f"array[{data_type.element_dtype}, {data_type.shape.value}]"
            
            # 2D+ arrays
            else:
                shape_str = format_dimensions(data_type.shape)
                return f"array[{data_type.element_dtype}, {{{shape_str}}}]"

**Examples of Type Descriptions:**

* ``ArrayDataType_N("int", List_N([]))`` → ``"scalar 'int'"``
* ``ArrayDataType_N("real", IntLiteral_N(5))`` → ``"array[real, 5]"``
* ``ArrayDataType_N("bool", Array1DLiteral_N([3, 4]))`` → ``"array[bool, {3, 4}]"``

Context-Specific Hints
----------------------

The system provides specific guidance based on the type mismatch:

**Array-to-Scalar Hints:**

.. code-block::

    [Hint] Scalars cannot hold array values. Use array indexing like 'array[0, 1]' to get a single element

**Scalar-to-Array (Note: This is handled by broadcasting):**

Scalar-to-array assignments are automatically handled by the broadcasting system and do not generate errors.

**Array Shape Mismatch Hints:**

.. code-block::

    [Hint] Arrays must have compatible shapes for assignment

Integration with Broadcasting System
------------------------------------

Assignment validation works seamlessly with GeLB's broadcasting system:

**1. Type Promotion First:** If needed, scalar types are promoted (int → real)
**2. Broadcasting Second:** Promoted scalars are wrapped in BroadcastNode_N for array assignment
**3. Validation Last:** Remaining incompatible assignments are caught with clear error messages

**Example Pipeline:**

.. code-block:: gelb

    array[real, 3] data;
    int value = 42;
    data = value;  // int → real promotion → BroadcastNode_N → valid

This becomes:

.. code-block::

    BroadcastNode_N {
        scalar_expr: TypePromotionNode_N {
            expr: IntLiteral_N(42)
            target_type: ArrayDataType_N("real", List_N([]))
        }
        target_array_type: ArrayDataType_N("real", IntLiteral_N(3))
    }

Testing Assignment Validation
-----------------------------

Comprehensive test coverage ensures assignment validation works correctly:

**Test Categories:**

* **Valid assignments:** Scalar-to-scalar, array element access
* **Invalid assignments:** Array-to-scalar with clear error messages  
* **Broadcasting:** Scalar-to-array handled by promotion system
* **Type promotion:** Integration with promotion and validation pipeline
* **Error message quality:** User-friendly descriptions and hints

**Example Test Pattern:**

.. code-block:: python

    def test_array_to_scalar_assignment_rejected(self):
        test_code = minimal_gelb_program_1d(
            initializer_content=\"\"\"
                array[real, {2, 2}] matrix;
                real scalar;
                scalar = matrix;  // Invalid: array to scalar
                f.out[x | 0] = 0;
            \"\"\"
        )
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_fully_validated_ast(test_code)
        
        error = exc_info.value
        assert "Cannot assign array[real, {2, 2}] to scalar 'real'" in str(error.error)
        assert "Use array indexing" in str(error.hint)

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

The type system provides several shared test utilities in ``gelb.tests.test_utils`` to avoid code duplication and ensure consistent testing patterns.

**Available Helper Functions:**

.. code-block:: python

    from gelb.tests.test_utils import (
        get_typed_ast,              # Type inference only
        get_fully_validated_ast,    # Complete validation pipeline  
        minimal_gelb_program_1d     # Program templates
    )

**Pipeline Helper Functions:**

``get_typed_ast(gelb_code)``
    Runs the frontend pipeline up to type inference:
    - Parse → Symbol tables → Constants → Ranges → Type inference
    - Returns AST with ``inferred_type`` attributes on expressions

``get_fully_validated_ast(gelb_code)`` 
    Runs the complete frontend validation pipeline:
    - Type inference → Type promotion → Type validation
    - Returns fully validated AST ready for backend processing
    - **Use this for all type validation tests**

**Usage Examples:**

.. code-block:: python

    def test_type_inference_only():
        """Test just type inference without validation."""
        ast = get_typed_ast("real x = 42;")
        # Check inferred types but no validation applied
        
    def test_full_validation_pipeline():
        """Test complete type validation including error detection."""
        with pytest.raises(GeLBExTypeError):
            get_fully_validated_ast("int x = 3.14;")  # Type demotion error

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
        """Use get_fully_validated_ast for simpler error testing."""
        code = minimal_gelb_program_1d(initializer_content="bool b; b = 1 && 2;")
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_fully_validated_ast(code)  # Complete pipeline in one call
        
        assert "logical AND" in str(exc_info.value)
        assert "expected 'bool'" in str(exc_info.value)
        
    def test_type_demotion_prevention():
        """Test that type demotion is caught."""
        test_code = """
        simulation_description("Test");
        lattices { lattice f(1, 1, int, 32, false); }
        initializer Init { f.out[x | 0] = 3.14; }  // real → int (invalid)
        dynamic Dyn { f.out[x | 0] = 1; }
        gauge Out(out = {int val;}) { val = f.in[x | 0]; }
        node_classes { node_class BULK(Init, Dyn, Out); }
        geometry { nodes[:] = BULK; }
        """
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_fully_validated_ast(test_code)
        
        assert "would lose precision" in str(exc_info.value)

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

**Binary Operand Validation Testing:**

.. code-block:: python

    def test_scalar_array_division_rejected():
        """Test binary operand validation with full pipeline."""
        test_code = """
        simulation_description("Test");
        lattices { lattice f(1, 3, int, 32, false); }
        initializer Init { f.out[x | :] = 1 / f.in[x | :]; }
        dynamic Dyn { f.out[x | 0] = 1; }
        gauge Out(out = {int val;}) { val = f.in[x | 0]; }
        node_classes { node_class BULK(Init, Dyn, Out); }
        geometry { nodes[:] = BULK; }
        """
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_fully_validated_ast(test_code)
        
        error = exc_info.value
        assert "Cannot perform scalar division by array" in str(error.error)
        assert "mathematically ambiguous" in str(error.error)

**Test Function Consolidation**

The ``get_fully_validated_ast`` function was consolidated from 4 duplicate implementations across different test files into a single shared utility. This provides:

- **Consistency**: All validation tests use the same pipeline
- **Maintainability**: Single point of change for validation logic
- **Documentation**: Clear understanding of the complete validation process
- **Efficiency**: Reduces code duplication and maintenance burden

**Best Practices for Type System Testing:**

1. **Use appropriate helper functions**:
   - ``get_typed_ast()`` for type inference-only tests
   - ``get_fully_validated_ast()`` for validation tests that expect errors
   - ``minimal_gelb_program_1d()`` for simple test cases

2. **Import from shared utilities**:
   
   .. code-block:: python
   
       from gelb.tests.test_utils import (
           get_typed_ast,
           get_fully_validated_ast,
           minimal_gelb_program_1d
       )

3. **Follow naming conventions**:
   - Test functions should clearly indicate what they're testing
   - Use descriptive variable names for complex test code
   - Include docstrings explaining the test purpose

4. **Error testing patterns**:
   - Always test both the error type and message content
   - Verify hint/guidance messages for actionable feedback
   - Test edge cases and boundary conditions

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

Required Intrinsic Functions
=============================

GeLB requires a set of intrinsic (built-in) functions to support operations that cannot be safely performed through automatic type promotion. These functions provide explicit, controlled operations that would otherwise be forbidden by the type system.

Type Conversion Functions
-------------------------

**Explicit Type Demotion Casts**

To enable controlled precision loss when required by the algorithm:

.. code-block:: gelb

    // int_cast: Explicit real → int conversion
    int_cast(expr: real) -> int
    // Truncates fractional part: 3.14159 → 3, -2.8 → -2
    
    int truncated = int_cast(3.14159);     // 3
    int negative = int_cast(-2.8);         // -2
    
    // bool_cast: Explicit numeric → bool conversion  
    bool_cast(expr: int|real) -> bool
    // Zero → false, non-zero → true
    
    bool flag1 = bool_cast(0);             // false
    bool flag2 = bool_cast(42);            // true
    bool flag3 = bool_cast(-3.14);         // true
    bool flag4 = bool_cast(0.0);           // false

**Type-Safe Rounding Functions**

For precise control over real → int conversion:

.. code-block:: gelb

    // round: Round to nearest integer
    round(expr: real) -> int
    // Uses "round half to even" (banker's rounding)
    
    int rounded1 = round(3.14159);         // 3
    int rounded2 = round(3.6);             // 4
    int rounded3 = round(2.5);             // 2 (banker's rounding)
    int rounded4 = round(3.5);             // 4 (banker's rounding)
    
    // floor: Round down to nearest integer
    floor(expr: real) -> int
    
    int floored1 = floor(3.9);             // 3
    int floored2 = floor(-2.1);            // -3
    
    // ceil: Round up to nearest integer  
    ceil(expr: real) -> int
    
    int ceiling1 = ceil(3.1);              // 4
    int ceiling2 = ceil(-2.9);             // -2

**Array-Aware Type Conversions**

Support type conversion for arrays while preserving shapes:

.. code-block:: gelb

    // Array type conversions preserve shape
    array[real, 3] reals = {1.1, 2.7, 3.9};
    array[int, 3] truncated = int_cast(reals);    // {1, 2, 3}
    array[int, 3] rounded = round(reals);         // {1, 3, 4}

**Usage Examples**

.. code-block:: gelb

    // Example 1: LBM with integer coordinates
    lattices {
        lattice f(2, 9, real, {64, 64}, {true, true});
    }
    
    initializer Init {
        // Convert real lattice indices to integer array indices
        real x_real = x + 0.5;  // Offset for centering
        int x_index = round(x_real);
        
        // Explicit conversion for algorithm requirements
        real density = calculate_density();
        int density_class = int_cast(density * 10.0);  // Explicit truncation
    }

**Implementation Priority**

1. **High Priority** (Essential for type safety):
   - ``int_cast()`` - Most common demotion operation
   - ``bool_cast()`` - Conditional logic requirements
   
2. **Medium Priority** (Mathematical operations):
   - ``round()`` - Common rounding needs
   - ``floor()`` - Scientific computing algorithms
   - ``ceil()`` - Boundary calculations
   
3. **Future Enhancements**:
   - Array-aware versions of all functions
   - Additional mathematical functions (abs, sqrt, etc.)
   - String conversion functions

**Design Principles**

1. **Explicit Intent**: All type demotions must be explicitly requested
2. **Predictable Behavior**: Functions have well-defined semantics
3. **Array Compatibility**: Functions work with GeLB's universal array type system
4. **Performance**: Intrinsics should enable efficient code generation
5. **Safety**: Clear error messages for invalid operations

**Integration with Type System**

Intrinsic functions integrate seamlessly with GeLB's type system:

- **Input Validation**: Type checker ensures correct argument types
- **Output Types**: Return types are statically determined
- **Array Broadcasting**: Support both scalar and array arguments
- **Error Reporting**: Clear messages for misuse

**Future Extensions**

The intrinsic function system provides a foundation for:

- Mathematical functions (trigonometric, logarithmic)
- Array manipulation functions (reshape, transpose)
- String manipulation functions
- I/O functions for debugging and output

Binary Operand Validation
=========================

GeLB enforces strict validation rules for binary operations involving arrays and scalars to prevent mathematically ambiguous expressions and ensure clear, predictable semantics.

Validation Philosophy
---------------------

**Core Principle**: Mathematical operations should have unambiguous, well-defined semantics that map clearly to efficient backend implementations.

**Problem**: Operations like ``scalar / array`` or ``scalar - array`` are mathematically ambiguous:

.. code-block:: gelb

    // What does this mean?
    real result = 5.0 / {1.0, 2.0, 3.0};
    // 5.0 / each element → {5.0, 2.5, 1.67}? (elementwise)
    // 5.0 / sum → 5.0 / 6.0 = 0.83? (reduction) 
    // 5.0 / product → 5.0 / 6.0 = 0.83? (reduction)
    // 5.0 / norm → 5.0 / 3.74 = 1.34? (reduction)

**Solution**: Restrict operations to mathematically unambiguous patterns and provide clear error messages with guidance.

Allowed Operations
------------------

**1. Scalar-Scalar Operations**

All arithmetic operations are allowed between scalars:

.. code-block:: gelb

    int a = 5;
    int b = 3;
    int result1 = a + b;    // ✅ 8
    int result2 = a - b;    // ✅ 2
    int result3 = a * b;    // ✅ 15
    int result4 = a / b;    // ✅ 1 (integer division)

**2. Array-Scalar Operations (Element-wise)**

Arrays can be combined with scalars for element-wise operations:

.. code-block:: gelb

    lattices {
        lattice f(1, 3, real, 32, false);
    }
    
    initializer Init {
        // All element-wise operations allowed
        f.out[x | :] = f.in[x | :] + 1.0;    // ✅ Add 1.0 to each element
        f.out[x | :] = f.in[x | :] - 2.0;    // ✅ Subtract 2.0 from each element  
        f.out[x | :] = f.in[x | :] * 3.0;    // ✅ Multiply each element by 3.0
        f.out[x | :] = f.in[x | :] / 4.0;    // ✅ Divide each element by 4.0
        f.out[x | :] = f.in[x | :] ^ 2.0;    // ✅ Square each element
    }

**3. Scalar-Array Commutative Operations**

For commutative operations (addition, multiplication), scalar-array is equivalent to array-scalar:

.. code-block:: gelb

    initializer Init {
        // Commutative operations work both ways
        f.out[x | :] = 2.0 + f.in[x | :];    // ✅ Equivalent to f.in[x | :] + 2.0
        f.out[x | :] = 3.0 * f.in[x | :];    // ✅ Equivalent to f.in[x | :] * 3.0
    }

Rejected Operations
-------------------

**1. Scalar-Array Non-Commutative Operations**

Non-commutative operations with scalar on the left are rejected as mathematically ambiguous:

.. code-block:: gelb

    initializer Init {
        f.out[x | :] = 5.0 - f.in[x | :];    // ❌ ERROR: Ambiguous semantics
        f.out[x | :] = 1.0 / f.in[x | :];    // ❌ ERROR: Ambiguous semantics  
        f.out[x | :] = 2.0 ^ f.in[x | :];    // ❌ ERROR: Ambiguous semantics
    }

**Error Messages:**

.. code-block::

    error: Cannot perform scalar subtraction by array: mathematically ambiguous
         7      initializer Init {
         8->        f.out[x | :] = 5.0 - f.in[x | :];
                                   ~~~~~~~~~~~~~~~~~~^^   [Problem] Cannot perform scalar subtraction by array: mathematically ambiguous
                                                           [Hint] Consider: array subtraction scalar for clear element-wise semantics
         9      }

**2. Array-Array Operations**

Currently, array-array operations are not supported as they require complex broadcasting semantics:

.. code-block:: gelb

    lattices {
        lattice f(1, 3, real, 32, false);
        lattice g(1, 3, real, 32, false);
    }
    
    initializer Init {
        // All array-array operations rejected
        f.out[x | :] = f.in[x | :] + g.in[x | :];    // ❌ ERROR: Not supported
        f.out[x | :] = f.in[x | :] - g.in[x | :];    // ❌ ERROR: Not supported
        f.out[x | :] = f.in[x | :] * g.in[x | :];    // ❌ ERROR: Not supported  
        f.out[x | :] = f.in[x | :] / g.in[x | :];    // ❌ ERROR: Not supported
    }

**Error Messages:**

.. code-block::

    error: Cannot perform array addition by array: operation not supported
         8      initializer Init {
         9->        f.out[x | :] = f.in[x | :] + g.in[x | :];
                                    ~~~~~~~~~~~~~~~~~~~~~~~~^^   [Problem] Cannot perform array addition by array: operation not supported
                                                                 [Hint] Use scalar-array operations like: array + scalar
        10      }

Lattice Selection Integration
-----------------------------

**Single Element Selections as Scalars**

Single element lattice selections are treated as scalars, not arrays:

.. code-block:: gelb

    lattices {
        lattice f(1, 1, real, 32, false);  // Single distribution function
    }
    
    initializer Init {
        // f.in[x | 0] is a scalar (single element)
        // So scalar / scalar is allowed
        f.out[x | 0] = 1.0 / f.in[x | 0];   // ✅ Scalar division
    }

**Full Range Selections as Arrays**

Full range selections return arrays and follow array operation rules:

.. code-block:: gelb

    lattices {
        lattice f(1, 3, real, 32, false);  // Three distribution functions
    }
    
    initializer Init {
        // f.in[x | :] is an array of size 3
        f.out[x | :] = f.in[x | :] + 1.0;   // ✅ Array + scalar
        f.out[x | :] = 2.0 + f.in[x | :];   // ✅ Scalar + array (commutative)
        f.out[x | :] = 1.0 / f.in[x | :];   // ❌ ERROR: Scalar / array (ambiguous)
    }

Type Promotion Integration
--------------------------

Binary operand validation works seamlessly with type promotion:

.. code-block:: gelb

    lattices {
        lattice f(1, 3, real, 32, false);
    }
    
    initializer Init {
        // Type promotion: int → real, then array operation
        f.out[x | :] = 1 + f.in[x | :];         // ✅ int promoted to real
        f.out[x | :] = f.in[x | :] * true;      // ✅ bool promoted to real
        
        // Type promotion + validation: still rejects ambiguous operations
        f.out[x | :] = 5 - f.in[x | :];         // ❌ ERROR: Still ambiguous after promotion
    }

Implementation Details
----------------------

**Validation Location**: Binary operand validation occurs in ``TypeValidationVisitor._validate_arithmetic_op``

**Validation Logic**:

.. code-block:: python

    def _validate_arithmetic_op(self, left_type, right_type, op_name, node):
        left_is_scalar = self._is_scalar_array(left_type)
        right_is_scalar = self._is_scalar_array(right_type)
        
        # Allow scalar op array only for commutative operations
        if left_is_scalar and not right_is_scalar:
            if op_name in ['addition', 'multiplication']:
                return True  # Commutative: scalar + array, scalar * array
            elif op_name in ['subtraction', 'division', 'exponentiation']:
                raise GeLBExTypeError(
                    node,
                    f"Cannot perform scalar {op_name} by array: mathematically ambiguous",
                    f"Consider: array {op_name} scalar for clear element-wise semantics"
                )
        
        # Reject all array op array operations
        elif not left_is_scalar and not right_is_scalar:
            raise GeLBExTypeError(
                node,
                f"Cannot perform array {op_name} by array: operation not supported",
                f"Use scalar-array operations like: array {op_name} scalar"
            )

**Operation Classification**:

- **Commutative**: addition (``+``), multiplication (``*``)
- **Non-Commutative**: subtraction (``-``), division (``/``), exponentiation (``^``)

**Error Message Design**:

1. **Clear Problem Description**: Exactly what operation is problematic
2. **Rationale**: Why it's problematic ("mathematically ambiguous")  
3. **Actionable Hint**: How to fix it ("Consider: array operation scalar")

Rationale and Benefits
----------------------

**1. Predictable Semantics**

Clear rules eliminate guesswork about operation meaning:

.. code-block:: gelb

    // Clear: element-wise addition
    array + scalar  // Each element + scalar
    
    // Clear: commutative equivalence  
    scalar + array  // Same as array + scalar
    
    // Ambiguous: rejected
    scalar / array  // What does this mean?

**2. Backend Optimization**

Restricted operations enable efficient code generation:

- **Array + Scalar**: Simple broadcast implementation
- **Scalar + Array**: Rewrite as Array + Scalar
- **Array × Array**: Avoided complexity of shape broadcasting

**3. Error Prevention**

Catches likely programming errors at compile time:

.. code-block:: gelb

    // Likely intended: array - scalar
    velocity[x | :] = velocity[x | :] - damping;    // ✅ Clear
    
    // Likely error: scalar - array  
    velocity[x | :] = damping - velocity[x | :];    // ❌ Caught at compile time

**4. Future Extensibility**

Clear foundation for adding array-array operations with well-defined broadcasting rules:

.. code-block:: gelb

    // Future: with proper broadcasting semantics
    result[x | :] = array1[x | :] + array2[x | :];  // Compatible shapes required

Testing Coverage
----------------

Binary operand validation includes comprehensive test coverage:

**Test Files**:
- ``test_binary_operand_validation.py`` - Core validation logic
- ``test_array_scalar_operations.py`` - Extended operation patterns

**Test Categories**:

1. **Allowed Operations**: Verify valid patterns work correctly
2. **Rejected Operations**: Ensure invalid patterns are caught
3. **Error Message Quality**: Validate helpful error messages
4. **Type Integration**: Test with type promotion
5. **Lattice Integration**: Test with lattice selections
6. **Edge Cases**: Single elements, mixed types, complex expressions

**Example Test Structure**:

.. code-block:: python

    @pytest.mark.parametrize("expr,op_name", [
        ("f.in[x | :] + g.in[x | :]", "addition"),
        ("f.in[x | :] - g.in[x | :]", "subtraction"), 
        ("f.in[x | :] * g.in[x | :]", "multiplication"),
        ("f.in[x | :] / g.in[x | :]", "division"),
    ])
    def test_all_array_array_operations_rejected(self, expr, op_name):
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_fully_validated_ast(test_code)
        
        error = exc_info.value
        assert f"Cannot perform array {op_name} by array" in str(error.error)

Future Extensions
-----------------

**Array-Array Operations**

Future versions may support array-array operations with broadcasting:

.. code-block:: gelb

    // Future: shape-compatible array operations
    array[real, 3] + array[real, 3]     // Element-wise, same shape
    array[real, {2,3}] + array[real, 3]  // Broadcasting: {2,3} + {1,3}

**Advanced Mathematical Operations**

Specialized operations for scientific computing:

.. code-block:: gelb

    // Future: reduction operations
    real sum = reduce_sum(array);        // Unambiguous reduction
    real dot = dot_product(array1, array2);  // Explicit dot product
    
    // Future: element-wise functions  
    array[real, 3] squared = square(array);   // Clear element-wise operation

**Validation Configuration**

Allow customization of validation strictness:

.. code-block:: gelb

    // Future: configuration options
    #pragma gelb strict_arrays on       // Current behavior
    #pragma gelb allow_ambiguous off    // Reject ambiguous operations