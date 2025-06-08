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

DataType_N (Abstract Base Class)
---------------------------------

Base class for all GeLB data types:
- Contains: ``scalar_dtype`` (string: "int", "real", "bool", "string")

Universal ArrayDataType_N System
---------------------------------

**Core Design Philosophy:**
GeLB uses a universal type system where **all types are represented as ArrayDataType_N**, treating scalars as 0-dimensional arrays. This provides uniform type handling throughout the compiler and enables powerful array-aware optimizations.

**ArrayDataType_N (Primary Type)**

Represents all numeric and boolean types as arrays:
- Contains: ``scalar_dtype`` (element type) and ``shape`` (dimensions)
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

**ScalarDataType_N (Declaration Context)**

Used for scalar type declarations and metadata:
- Variable declarations: ``int x;``, ``real y;``, ``bool b;``
- Lattice df_type specifications: ``lattice f(d=2, q=9, df_type=int)``
- Gauge output type declarations: ``out = {int state;}``
- String literals: ``"hello"`` *(only expression context)*

Note: While declarations use ``ScalarDataType_N``, the type inference system converts these to ``ArrayDataType_N`` for expressions and computations.

Expression Type Inference
=========================

Literals
--------

All literals extend Literal_N which extends Expr_N:

- **IntLiteral_N** → inferred type: ArrayDataType_N("int", List_N([]))
- **RealLiteral_N** → inferred type: ArrayDataType_N("real", List_N([]))
- **BoolLiteral_N** → inferred type: ArrayDataType_N("bool", List_N([]))
- **StringLiteral_N** → inferred type: ScalarDataType_N("string") *(exception)*
- **Array1DLiteral_N** → inferred type: ArrayDataType_N(element_type, IntLiteral_N(size))
- **Array2DLiteral_N** → inferred type: ArrayDataType_N(element_type, Array1DLiteral_N(dimensions))
- **Array3DLiteral_N** → inferred type: ArrayDataType_N(element_type, Array1DLiteral_N(dimensions))
- **Array4DLiteral_N** → inferred type: ArrayDataType_N(element_type, Array1DLiteral_N(dimensions))

**Key Implementation Methods:**

.. code-block:: python

    def _create_scalar_array_type(self, code_range, scalar_dtype):
        """Create a 0-dimensional array type representing a scalar."""
        empty_shape = List_N(code_range)
        return ArrayDataType_N(code_range, scalar_dtype, empty_shape)

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

The ``string`` type does not participate in promotions:

.. code-block:: gelb

    "hello" + 1    // ERROR: No promotion between string and numeric types

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

Promotion Contexts
------------------

The visitor handles promotion in these contexts:

1. **Arithmetic Binary Operations** - Both operands promoted to common type
2. **Comparison Operations** - Both operands promoted to common type
3. **Assignment Statements** - RHS promoted to LHS type
4. **Constant Definitions** - Value promoted to declared type
5. **Array Literals** - All elements promoted to common type

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

Error Reporting
===============

The type system provides clear error messages:

.. code-block::

    ERROR: Cannot implicitly convert 'real' to 'int' in assignment
      int x = 3.14;
              ^^^^
      Hint: Explicit casting will be supported in future versions

    ERROR: Logical operator '&&' requires 'bool' operands
      bool result = x && y;
                    ^    ^
      Found: 'int' && 'int'
      Hint: Use comparison operators to create boolean expressions

GeLBExTypeError Exception
-------------------------

Type errors are reported using ``GeLBExTypeError`` which includes:
- Source location information
- Clear error description
- Helpful hints for resolution

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

**Type Validation Tests** (``gelb/tests/unit/type_validation/``):
- Valid operations after promotion
- Invalid logical operations (int && int)
- Invalid assignments (real → int)
- Type mismatch detection

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
        assert assign_stmt.rhs.target_type.scalar_dtype == "real"
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
        assert rhs.inferred_type.scalar_dtype == "int"
        
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