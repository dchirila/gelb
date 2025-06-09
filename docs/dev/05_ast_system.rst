==============
AST System
==============

The Abstract Syntax Tree (AST) is the central data structure in the GeLB compiler, representing parsed programs in a form suitable for analysis and transformation.

What is an AST?
===============

Despite their name, there is nothing abstract about the trees themselves (although they can have size-induced complexity, for non-trivial programs). Instead, the word "abstract" refers to the fact that some of the syntax is "abstracted-away" (e.g. the AST for a language from the C family would not include separator keywords, parentheses or the semicolon at the end of each instruction). This is in contrast with *parse trees* (also known as *concrete syntax trees*), which contain all of these low-level syntax elements.

"Each node of the tree denotes a construct occurring in the source code."

Benefits of using ASTs
----------------------

* They make program analysis and program transformation systems easier to implement (compared to working directly on the source-code, or on the parse trees).

* AST nodes can be enhanced with additional information, which is deduced as the AST passes through the different stages within the GeLB compiler (something which would be impossible if working directly with the source-code, and cumbersome if working with the syntax trees).

AST Node Hierarchy
==================

All AST Nodes inherit from the **Node_N** base class, which provides:

**Attributes:**
* ``code_range`` - Source location information for error reporting

**Methods:**
* Navigation and traversal methods
* Generic AST manipulation utilities

Major Node Categories
=====================

Program Structure
-----------------

**Program_N**
  Root node representing a complete GeLB program:
  
  * ``simulation_description`` → **StringLiteral_N**
  * ``global_constants`` → **GlobalConstantsBlock_N**
  * ``lattices`` → **LatticesBlock_N**
  * ``node_classes`` → **NodeClassesBlock_N**
  * ``initializers`` → **List** of **InitializerBlock_N**
  * ``dynamics`` → **List** of **DynamicBlock_N**
  * ``gauges`` → **List** of **GaugeBlock_N**
  * ``geometry`` → **GeometryBlock_N**

Block Types
-----------

**GlobalConstantsBlock_N**
  Contains constant definitions accessible throughout the program

**LatticesBlock_N**
  Contains lattice instantiation statements

**InitializerBlock_N**
  Contains statements that write initial values to lattices

**DynamicBlock_N**
  Contains statements that update lattice values (read and write operations)

**GaugeBlock_N**
  Contains statements that read values from lattices for output

**GeometryBlock_N**
  Contains statements that assign node classes to lattice sites

**NodeClassesBlock_N**
  Contains node class definitions

Expression Nodes
-----------------

All expression nodes inherit from **Expr_N** and include an ``inferred_type`` attribute added during type inference.

**Literal Expressions:**
* **IntLiteral_N** - Integer constants
* **RealLiteral_N** - Real number constants  
* **BoolLiteral_N** - Boolean constants (true/false)
* **StringLiteral_N** - String constants
* **Array1DLiteral_N, Array2DLiteral_N, Array3DLiteral_N, Array4DLiteral_N** - Array literals

**Binary Expressions:**
All inherit from **BinaryExpr_N** with ``left`` and ``right`` operands:

*Arithmetic:*
* **Add_N** (+), **Sub_N** (-), **Mul_N** (*), **Div_N** (/), **Pow_N** (^)

*Comparison:*
* **Less_N** (<), **Greater_N** (>), **LessEqual_N** (<=), **GreaterEqual_N** (>=)
* **Equal_N** (==), **NotEqual_N** (!=)

*Logical:*
* **And_N** (&&), **Or_N** (||)

**Unary Expressions:**
All inherit from **UnaryExpr_N** with a ``value`` operand:
* **NotExpr_N** (!) - Logical negation
* **UnaryMinusExpr_N** (-) - Arithmetic negation

**Other Expression Types:**
* **Identifier_N** - Variable and constant references
* **RectSelOfLatticeInDFs_N** - Lattice input selections
* **RectSelOfLatticeOutDFs_N** - Lattice output selections  
* **RectSelOfArrayElems_N** - Array element selections with shape reduction
* **TypePromotionNode_N** - Implicit type conversions (inserted by TypePromotionVisitor)
* **BroadcastNode_N** - Scalar-to-array broadcasting operations (inserted by TypePromotionVisitor)

Statement Nodes
----------------

**Assignment Statements:**
All inherit from **AssignmentStmt_N** with ``lhs`` and ``rhs`` components:
* **VariableAssignmentStmt_N** - Scalar variable assignments
* **LatticeOutSelectionAssignmentStmt_N** - Lattice output assignments
* **ArraySelectionAssignmentStmt_N** - Array element assignments

**Declaration Statements:**
* **VariableDeclarationStmt_N** - Variable declarations (with optional initialization)
* **ConstantDefinitionStmt_N** - Constant definitions
* **LatticeInstaStmt_N** - Lattice instantiations

**Other Statements:**
* **PaintNodesStmt_N** - Node class assignments in geometry
* **SetSimulationDescriptionStmt_N** - Simulation metadata

Data Type Nodes
----------------

**ArrayDataType_N**
  Represents all computational types (scalars and arrays)
  
  * ``element_dtype`` - Base type name (int, real, bool)
  * ``shape`` - Dimension specification (empty List_N for scalars)

Utility Nodes
--------------

**Range_N**
  Represents range expressions (e.g., ``5:10``, ``:``, ``5:``)
  
  * ``low`` - Lower bound expression (can be None)
  * ``high`` - Upper bound expression (can be None)

**List_N**
  Generic container for ordered collections of AST nodes
  
  * ``elements`` - List of child nodes

**BroadcastNode_N**
  Represents scalar-to-array broadcasting operations in the AST
  
  * ``scalar_expr`` - The scalar expression to broadcast
  * ``target_array_type`` - The target array type with shape information
  * ``inferred_type`` - Set to target_array_type during creation
  
  **Purpose:**
  BroadcastNode_N enables efficient scalar-to-array assignment (e.g., ``array = scalar``) by preserving the scalar value in the AST rather than expanding it to a full array. This allows backends to generate optimized code using target language features like Fortran's ``array(:) = value``, C's ``memset``, or NumPy's ``np.full()``.
  
  **Creation:**
  Created automatically by TypePromotionVisitor when detecting scalar-to-array assignment patterns. The visitor handles type promotion first (if needed), then wraps the result in a broadcast operation.
  
  **Example:**
  
  .. code-block:: gelb
  
      array[real, 5] data;
      data = 42;  // int promoted to real, then broadcast to array shape
  
  **AST Representation:**
  
  .. code-block::
  
      BroadcastNode_N {
        scalar_expr: TypePromotionNode_N {
          expr: IntLiteral_N(42)
          target_type: ArrayDataType_N("real", List_N([]))
        }
        target_array_type: ArrayDataType_N("real", IntLiteral_N(5))
        inferred_type: ArrayDataType_N("real", IntLiteral_N(5))
      }

**RectSelOfArrayElems_N**
  Represents array element selections with automatic shape reduction
  
  * ``array_name`` - The identifier for the array being accessed
  * ``element_ranges`` - List of Range_N nodes specifying indices/ranges
  * ``inferred_type`` - Result type after shape reduction (added by TypeInferenceVisitor)
  
  **Shape Reduction:**
  The TypeInferenceVisitor calculates the resulting array type based on the selection patterns:
  
  * **Single Element Selection**: ``array[2, 3]`` → scalar (0D array)
  * **Mixed Selection**: ``array[2, :]`` → 1D array 
  * **Range Selection**: ``array[1:3, 2:5]`` → 2D array with reduced dimensions
  
  **AST Preservation:**
  Critical design principle: Original range information is completely preserved for backend code generation while adding computed type information.

**TypePromotionNode_N**
  Represents implicit type conversions inserted by the TypePromotionVisitor
  
  * ``expr`` - The original expression being promoted
  * ``target_type`` - The ArrayDataType_N representing the target type
  * ``inferred_type`` - Set to target_type during creation
  
  **Purpose:**
  TypePromotionNode_N makes implicit type conversions explicit in the AST, enabling backends to generate appropriate conversion code and providing a clear audit trail of all type promotions that occur during compilation.
  
  **Creation:**
  Created automatically by TypePromotionVisitor when implicit type conversion is needed (e.g., int → real in mixed arithmetic operations, assignments to differently-typed variables).
  
  **Example:**
  
  .. code-block:: gelb
  
      real x;
      x = 42;  // int literal promoted to real
  
  **AST Representation:**
  
  .. code-block::
  
      TypePromotionNode_N {
        expr: IntLiteral_N(42)
        target_type: ArrayDataType_N("real", List_N([]))
        inferred_type: ArrayDataType_N("real", List_N([]))
      }

**VariableDeclarationStmt_N**
  Represents variable declarations with optional initialization
  
  * ``data_type`` - The declared type of the variable
  * ``name`` - The variable identifier
  * ``initial_value`` - Optional initialization expression
  
  **Usage:**
  Supports both separate and combined declaration/initialization:
  
  .. code-block:: gelb
  
      // Separate declaration and assignment
      real x;
      x = 3.14;
      
      // Combined declaration with initialization
      real x = 3.14;
  
  **AST Integration:**
  When ``initial_value`` is present, the declaration and initialization are processed together by frontend visitors, ensuring proper type inference and validation.
  
  **Example:**
  
  .. code-block:: gelb
  
      array[real, {5, 7}] matrix;
      slice = matrix[3, 1:4];  // 1D array of size 3
  
  **AST Representation:**
  
  .. code-block::
  
      RectSelOfArrayElems_N {
        array_name: Identifier_N("matrix")
        element_ranges: List_N([
          Range_N(IntLiteral_N(3), IntLiteral_N(3)),    // Single element
          Range_N(IntLiteral_N(1), IntLiteral_N(4))     // Range selection
        ])
        inferred_type: ArrayDataType_N("real", IntLiteral_N(3))  // ← Added by TypeInferenceVisitor
      }
  
  **Backend Benefits:**
  * Original ranges preserved for optimal code generation
  * Symbolic expressions like ``Ny-1`` maintained exactly
  * Type information available for further compilation stages
  * Error detection for invalid index counts

Code Range Tracking
====================

Every AST node maintains source location information through the ``code_range`` attribute. This enables:

* **Precise error reporting** with line and column numbers
* **IDE integration** for syntax highlighting and navigation
* **Debugging support** for mapping compiled code back to source

The ``CodeRange`` class provides:
* Start and end positions in the source file
* Methods for combining and comparing ranges
* Integration with error reporting systems

AST Manipulation Best Practices
===============================

**Creating New Nodes**
Always provide proper ``code_range`` information:

.. code-block:: python

    new_node = IntLiteral_N(
        code_range=original_node.code_range,
        value=42
    )

**Traversing the AST**
Use the visitor pattern for systematic traversal:

.. code-block:: python

    class MyVisitor(ASTBaseVisitor):
        def visitAdd_N(self, node, ast_root):
            # Process addition nodes
            left_result = self.visit(node.left, ast_root)
            right_result = self.visit(node.right, ast_root)
            return process_addition(left_result, right_result)

**Modifying the AST**
Preserve invariants when making changes:
* Maintain parent-child relationships
* Update type information if modifying expressions
* Preserve or update code range information
* Ensure symbol table consistency

**Type Information**
Many AST nodes have type information attached:
* ``inferred_type`` attribute on expression nodes
* Added by ``TypeInferenceVisitor``
* Used by subsequent compilation stages

AST Validation
==============

The AST system includes several validation mechanisms:

**Structural Validation**
* Ensure required child nodes are present
* Verify proper node type relationships
* Check for malformed tree structures

**Semantic Validation**  
* Type compatibility checking
* Symbol resolution validation
* Scope and visibility rules

**Consistency Validation**
* Symbol table coherence
* Type annotation consistency
* Range resolution completeness

Working with AST Attributes
============================

**Adding New Attributes**
When extending AST nodes with new information:

1. **Add to node constructor** - Include in ``__init__`` method
2. **Update equality methods** - Modify ``__eq__`` if needed
3. **Update visitor methods** - Handle new attributes in relevant visitors
4. **Update tests** - Add test coverage for new attributes

**Common Attribute Patterns**
* ``inferred_type`` - Type information (expressions)
* ``symbol_defs`` - Symbol table references (blocks)
* ``resolved_value`` - Compile-time constant values
* ``target_type`` - Type promotion information
* ``scalar_expr`` - Scalar expression in broadcast operations
* ``target_array_type`` - Target array type for broadcasting

AST Debugging and Inspection
=============================

**AST Visualization**
Use the built-in visualization tools:

.. code-block:: bash

    gelbc --visualize-ast --ast-stage all program.gelb

**Manual Inspection**
Useful debugging methods:

.. code-block:: python

    # Print AST structure
    print(repr(ast_node))
    
    # Check node types
    isinstance(node, Add_N)
    
    # Inspect attributes
    print(f"Type: {node.inferred_type}")
    print(f"Location: {node.code_range}")

**Common Debugging Scenarios**
* **Missing type information** - Check if TypeInferenceVisitor ran
* **Symbol resolution failures** - Inspect symbol table contents
* **Unexpected node types** - Verify AST building is correct
* **Invalid transformations** - Check AST invariants are maintained