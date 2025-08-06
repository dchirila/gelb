# GeLB AST Node Analysis Report
==================================================

## Overview Statistics
- **Total AST Nodes**: 60
- **Abstract Nodes**: 1
- **Concrete Nodes**: 59
- **Maximum Inheritance Depth**: 5
- **Average Fields per Node**: 0.8

## Node Categories
- **Abstract Base Classes**: 11 nodes
- **Other Nodes**: 3 nodes
- **Statement Nodes**: 10 nodes
- **Block Nodes**: 6 nodes
- **Terminal Nodes**: 9 nodes
- **Selection Nodes**: 3 nodes
- **Data Type Nodes**: 1 nodes
- **Expression Nodes**: 16 nodes

## Most Referenced Nodes
- **Or_N**: referenced 24 times
- **Expr_N**: referenced 20 times
- **Block_N**: referenced 10 times
- **Literal_N**: referenced 10 times
- **Node_N**: referenced 6 times
- **Program_N**: referenced 6 times
- **List_N**: referenced 5 times
- **Range_N**: referenced 4 times
- **Mul_N**: referenced 3 times
- **Equal_N**: referenced 3 times

## Detailed Node Listings
### Abstract Base Classes
- **ArrayLiteral_N** - 0 fields
  - Base-class for Array{1,2,3,4}DLiteral_N.
- **AssignmentStmt_N** - 2 fields
  - Base-class for all GeLB assignment statements.
- **BinaryExpr_N** - 2 fields
  - Base-class for all GeLB binary expressions.
- **Block_N** - 2 fields
  - Base-class for larger AST sub-trees.
- **Expr_N** - 0 fields
  - Base-class for all types of GeLB expression-elements.
- **Literal_N** - 1 fields
  - Base-class for all GeLB literals.
- **Node_N** (abstract) - 1 fields
  - Base class (for all GeLB AST Node-types)
- **RectSelOfLatticeDFs_N** - 1 fields
  - Base-class for rectangular selection of lattice IN/OUT DFs.
- **RectSel_N** - 1 fields
  - Base-class for rectangular selections of elements.
- **Stmt_N** - 0 fields
  - Base-class for all types of GeLB statements.
- **UnaryExpr_N** - 1 fields
  - Base-class for all GeLB unary expressions.

### Other Nodes
- **List_N** - 1 fields
  - Wrapper for Python lists, with some GeLB-related functionality.
- **Program_N** - 9 fields
  - Represents the root AST node for a GeLB program.
- **Range_N** - 2 fields
  - Represents an index-range.

### Statement Nodes
- **ArraySelectionAssignmentStmt_N** - 0 fields
  - Represents an assignment to an array element or slice selection.
- **ConstantDefinitionStmt_N** - 3 fields
  - Represents a constant-definition statement.
- **GeometryBlock_N** - 0 fields
  - Represents the block (one per program) of node-painting statements.
- **LatticeInstaStmt_N** - 6 fields
  - Represents a lattice-instantiation statement.
- **LatticeOutSelectionAssignmentStmt_N** - 0 fields
  - Represents an assignment to a lattice-out (rectangular) selection.
- **NodeClassInstaStmt_N** - 4 fields
  - Represents a node-class-instantiation statement.
- **PaintNodesStmt_N** - 0 fields
  - Represents a node-painting statement (@GeometryBlock).
- **SetSimulationDescriptionStmt_N** - 1 fields
  - Represents an instruction to set the simulation's description.
- **VariableAssignmentStmt_N** - 0 fields
  - Represents a variable-assignment statement.
- **VariableDeclarationStmt_N** - 2 fields
  - Represents a variable-declaration statement.

### Block Nodes
- **DynamicBlock_N** - 1 fields
  - Represents a dynamic-block (one or more per program).
- **GaugeBlock_N** - 2 fields
  - Represents a gauge-block (one or more per program).
- **GlobalConstantsBlock_N** - 0 fields
  - Represents the block of global constants.
- **InitializerBlock_N** - 1 fields
  - Represents an initializer-block (one or more per program).
- **LatticesBlock_N** - 0 fields
  - Represents the block (one per program) of lattice-instantiations.
- **NodeClassesBlock_N** - 0 fields
  - Represents the block (one per program) of node-classes.

### Terminal Nodes
- **Array1DLiteral_N** - 0 fields
  - Represents a 1D array literal.
- **Array2DLiteral_N** - 0 fields
  - Represents a 2D array literal.
- **Array3DLiteral_N** - 0 fields
  - Represents a 3D array literal.
- **Array4DLiteral_N** - 0 fields
  - Represents a 4D array literal.
- **BoolLiteral_N** - 0 fields
  - Represents a boolean literal.
- **Identifier_N** - 1 fields
  - Represents an identifier.
- **IntLiteral_N** - 0 fields
  - Represents an integer literal.
- **RealLiteral_N** - 0 fields
  - Represents a real literal.
- **StringLiteral_N** - 0 fields
  - Represents a string literal.

### Selection Nodes
- **RectSelOfArrayElems_N** - 1 fields
  - Rectangular selection of array elements.
- **RectSelOfLatticeInDFs_N** - 0 fields
  - Rectangular selection of lattice IN DFs.
- **RectSelOfLatticeOutDFs_N** - 0 fields
  - Rectangular selection of lattice OUT DFs.

### Data Type Nodes
- **ArrayDataType_N** - 2 fields
  - Represents all computational data types (scalars and arrays).

### Expression Nodes
- **Add_N** - 0 fields
  - Represents an addition (+) binary expression.
- **And_N** - 0 fields
  - Represents a logical AND (&&) expression.
- **Div_N** - 0 fields
  - Represents a division (/) binary expression.
- **Equal_N** - 0 fields
  - Represents an equality (==) comparison expression.
- **GreaterEqual_N** - 0 fields
  - Represents a greater-than-or-equal (>=) comparison expression.
- **Greater_N** - 0 fields
  - Represents a greater-than (>) comparison expression.
- **LessEqual_N** - 0 fields
  - Represents a less-than-or-equal (<=) comparison expression.
- **Less_N** - 0 fields
  - Represents a less-than (<) comparison expression.
- **Mul_N** - 0 fields
  - Represents a multiplication (*) binary expression.
- **NotEqual_N** - 0 fields
  - Represents a not-equal (!=) comparison expression.
- **NotExpr_N** - 0 fields
  - Represents a logical negation (not) unary expression.
- **Or_N** - 0 fields
  - Represents a logical OR (||) expression.
- **Pow_N** - 0 fields
  - Represents a raise-to-power (^) binary expression.
- **Sub_N** - 0 fields
  - Represents a subtraction (-) binary expression.
- **TypePromotionNode_N** - 3 fields
  - Represents an implicit type promotion in the AST.
- **UnaryMinusExpr_N** - 0 fields
  - Represents an arithmetic negation (-) unary expression.

## Inheritance Hierarchy
**Node_N** (abstract)
  └─ **Block_N**
    └─ **DynamicBlock_N**
    └─ **GaugeBlock_N**
    └─ **GeometryBlock_N**
    └─ **GlobalConstantsBlock_N**
    └─ **InitializerBlock_N**
    └─ **LatticesBlock_N**
    └─ **NodeClassesBlock_N**
  └─ **ArrayDataType_N**
  └─ **Expr_N**
    └─ **BinaryExpr_N**
      └─ **Add_N**
      └─ **And_N**
      └─ **Div_N**
      └─ **Equal_N**
      └─ **GreaterEqual_N**
      └─ **Greater_N**
      └─ **LessEqual_N**
      └─ **Less_N**
      └─ **Mul_N**
      └─ **NotEqual_N**
      └─ **Or_N**
      └─ **Pow_N**
      └─ **Sub_N**
    └─ **Identifier_N**
    └─ **Literal_N**
      └─ **ArrayLiteral_N**
        └─ **Array1DLiteral_N**
        └─ **Array2DLiteral_N**
        └─ **Array3DLiteral_N**
        └─ **Array4DLiteral_N**
      └─ **BoolLiteral_N**
      └─ **IntLiteral_N**
      └─ **RealLiteral_N**
      └─ **StringLiteral_N**
    └─ **RectSel_N**
      └─ **RectSelOfArrayElems_N**
      └─ **RectSelOfLatticeDFs_N**
        └─ **RectSelOfLatticeInDFs_N**
        └─ **RectSelOfLatticeOutDFs_N**
    └─ **TypePromotionNode_N**
    └─ **UnaryExpr_N**
      └─ **NotExpr_N**
      └─ **UnaryMinusExpr_N**
  └─ **LatticeInstaStmt_N**
  └─ **List_N**
  └─ **NodeClassInstaStmt_N**
  └─ **Program_N**
  └─ **Range_N**
  └─ **Stmt_N**
    └─ **AssignmentStmt_N**
      └─ **ArraySelectionAssignmentStmt_N**
      └─ **LatticeOutSelectionAssignmentStmt_N**
      └─ **PaintNodesStmt_N**
      └─ **VariableAssignmentStmt_N**
    └─ **ConstantDefinitionStmt_N**
    └─ **SetSimulationDescriptionStmt_N**
    └─ **VariableDeclarationStmt_N**
