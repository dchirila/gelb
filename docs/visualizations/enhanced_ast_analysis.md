# Enhanced GeLB AST Node Analysis
==================================================

## Field Type Analysis

### ArrayDataType_N
**Inherits from**: Node_N

**Fields**:
- `element_dtype`: Unknown
- `shape`: Unknown

**Description**: Represents all computational data types (scalars and arrays).

**Dependencies**: None

---

### AssignmentStmt_N
**Inherits from**: Stmt_N

**Fields**:
- `lhs`: Unknown
- `rhs`: Unknown

**Description**: Base-class for all GeLB assignment statements.

**Dependencies**: None

---

### BinaryExpr_N
**Inherits from**: Expr_N

**Fields**:
- `left`: Unknown
- `right`: Unknown

**Description**: Base-class for all GeLB binary expressions.

**Dependencies**: None

---

### Block_N
**Inherits from**: Node_N

**Fields**:
- `stmts`: Unknown
- `symbol_defs`: Constant

**Description**: Base-class for larger AST sub-trees.

**Dependencies**: None

---

### ConstantDefinitionStmt_N
**Inherits from**: Stmt_N

**Fields**:
- `data_type`: Unknown
- `name`: Unknown
- `value`: Unknown

**Description**: Represents a constant-definition statement.

**Dependencies**: None

---

### DynamicBlock_N
**Inherits from**: Block_N

**Fields**:
- `name`: Unknown

**Description**: Represents a dynamic-block (one or more per program).

**Dependencies**: None

---

### GaugeBlock_N
**Inherits from**: Block_N

**Fields**:
- `name`: Unknown
- `outputs`: Unknown

**Description**: Represents a gauge-block (one or more per program).

**Dependencies**: None

---

### GeometryBlock_N
**Inherits from**: Block_N

**Fields**: None

**Description**: Represents the block (one per program) of node-painting statements.

**Dependencies**: None

---

### Identifier_N
**Inherits from**: Expr_N

**Fields**:
- `name`: Unknown

**Description**: Represents an identifier.

**Dependencies**: None

---

### InitializerBlock_N
**Inherits from**: Block_N

**Fields**:
- `name`: Unknown

**Description**: Represents an initializer-block (one or more per program).

**Dependencies**: None

---

### LatticeInstaStmt_N
**Inherits from**: Node_N

**Fields**:
- `name`: Unknown
- `d`: Unknown
- `q`: Unknown
- `df_type`: Unknown
- `grid_size`: Unknown
- `periodicity`: Unknown

**Description**: Represents a lattice-instantiation statement.

**Dependencies**: None

---

### List_N
**Inherits from**: Node_N

**Fields**:
- `elements`: List

**Description**: Wrapper for Python lists, with some GeLB-related functionality.

**Dependencies**: None

---

### Literal_N
**Inherits from**: Expr_N

**Fields**:
- `value`: Unknown

**Description**: Base-class for all GeLB literals.

**Dependencies**: None

---

### NodeClassInstaStmt_N
**Inherits from**: Node_N

**Fields**:
- `name`: Unknown
- `initializer`: Unknown
- `dynamic`: Unknown
- `gauge`: Unknown

**Description**: Represents a node-class-instantiation statement.

**Dependencies**: None

---

### Node_N
**Inherits from**: ABC

**Fields**:
- `code_range`: Unknown

**Description**: Base class (for all GeLB AST Node-types)

**Dependencies**: None

---

### Program_N
**Inherits from**: Node_N

**Fields**:
- `simulation_description`: Constant
- `global_constants`: Constant
- `lattices`: Constant
- `initializers`: Constant
- `dynamics`: Constant
- `gauges`: Constant
- `node_classes`: Constant
- `geometry`: Constant
- `symbol_defs`: Constant

**Description**: Represents the root AST node for a GeLB program.

**Dependencies**: None

---

### Range_N
**Inherits from**: Node_N

**Fields**:
- `low`: Unknown
- `high`: Unknown

**Description**: Represents an index-range.

**Dependencies**: None

---

### RectSelOfArrayElems_N
**Inherits from**: RectSel_N

**Fields**:
- `array_name`: Unknown

**Description**: Rectangular selection of array elements.

**Dependencies**: None

---

### RectSelOfLatticeDFs_N
**Inherits from**: RectSel_N

**Fields**:
- `lattice_name`: Unknown

**Description**: Base-class for rectangular selection of lattice IN/OUT DFs.

**Dependencies**: None

---

### RectSel_N
**Inherits from**: Expr_N

**Fields**:
- `element_ranges`: Unknown

**Description**: Base-class for rectangular selections of elements.

**Dependencies**: None

---

### SetSimulationDescriptionStmt_N
**Inherits from**: Stmt_N

**Fields**:
- `description`: Unknown

**Description**: Represents an instruction to set the simulation's description.

**Dependencies**: None

---

### TypePromotionNode_N
**Inherits from**: Expr_N

**Fields**:
- `expr`: Unknown
- `target_type`: Unknown
- `inferred_type`: Unknown

**Description**: Represents an implicit type promotion in the AST.

**Dependencies**: None

---

### UnaryExpr_N
**Inherits from**: Expr_N

**Fields**:
- `value`: Unknown

**Description**: Base-class for all GeLB unary expressions.

**Dependencies**: None

---

### VariableDeclarationStmt_N
**Inherits from**: Stmt_N

**Fields**:
- `data_type`: Unknown
- `name`: Unknown

**Description**: Represents a variable-declaration statement.

**Dependencies**: None

---

## Dependency Summary

Nodes with the most dependencies:

