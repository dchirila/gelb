# GeLB AST Node Visualizations

This directory contains comprehensive visualizations and analysis of the GeLB AST (Abstract Syntax Tree) node hierarchy and dependencies.

## Generated Files

### 📊 Main Visualizations

- **`gelb_ast.inheritance.dot/png`** - Inheritance hierarchy graph showing parent-child relationships between AST node classes
- **`gelb_ast.dependencies.dot/png`** - Dependency graph showing which nodes reference other nodes
- **`gelb_ast.detailed.dot/png`** - Detailed structure graph with field information for each node
- **`gelb_ast_overview.png/pdf`** - High-level overview diagram with category statistics

### 📈 Analysis Reports

- **`gelb_ast.statistics.md`** - Comprehensive statistics about the AST structure including:
  - Node counts and categories
  - Inheritance depth analysis
  - Most referenced nodes
  - Detailed node listings by category

- **`enhanced_ast_analysis.md`** - Enhanced analysis with field type information and actual dependencies

### 🐍 Generated Scripts

- **`gelb_ast.diagram.py`** - Executable Python script to generate matplotlib-based overview diagrams

## AST Node Statistics

- **Total AST Nodes**: 61
- **Abstract Base Classes**: 12
- **Concrete Implementations**: 49
- **Maximum Inheritance Depth**: 5
- **Node Categories**: 8

### Node Categories

1. **Abstract Base Classes** (12 nodes) - Base classes like `Node_N`, `Expr_N`, `Stmt_N`
2. **Terminal Nodes** (9 nodes) - Literals and identifiers
3. **Expression Nodes** (16 nodes) - Binary operations, unary operations, etc.
4. **Statement Nodes** (10 nodes) - Assignment statements, declarations, etc.
5. **Block Nodes** (6 nodes) - Program structure blocks
6. **Selection Nodes** (3 nodes) - Array and lattice selections
7. **Data Type Nodes** (2 nodes) - Scalar and array types
8. **Other Nodes** (3 nodes) - Utility nodes like `List_N`, `Range_N`

## Key Insights

### Most Referenced Nodes
The following nodes are referenced most frequently by other nodes, indicating their importance in the AST structure:

1. **Or_N** - Referenced 24 times
2. **Expr_N** - Referenced 20 times (base class for expressions)
3. **Block_N** - Referenced 10 times (base class for blocks)
4. **Literal_N** - Referenced 10 times (base class for literals)

### Inheritance Patterns
- The AST follows a clear hierarchy with `Node_N` as the root
- Most nodes inherit from specialized base classes (`Expr_N`, `Stmt_N`, `Block_N`)
- Terminal nodes (literals) have minimal inheritance depth
- Complex nodes like `Program_N` have many fields (9) reflecting their central role

## Usage

### Viewing the Visualizations

1. **DOT files**: Can be viewed with Graphviz or online DOT viewers
2. **PNG files**: Standard image files viewable in any image viewer
3. **PDF files**: Vector format suitable for high-quality printing

### Regenerating the Visualizations

```bash
# Basic visualization
python scripts/visualize_ast_node_hierarchy.py --output-dir docs/visualizations

# Generate PNG format
python scripts/visualize_ast_node_hierarchy.py --output-dir docs/visualizations --format png

# Enhanced analysis
python scripts/enhanced_ast_analyzer.py
```

### Dependencies

- **Python 3.7+**
- **Graphviz** (for DOT to image conversion)
- **matplotlib** (for Python-generated diagrams)

## Understanding the Visualizations

### Inheritance Graph
- **Blue arrows**: Inheritance relationships (parent → child)
- **Dashed boxes**: Abstract classes
- **Colors**: Represent different node categories
- **Labels**: Show node name and field count

### Dependency Graph  
- **Red arrows**: Dependency relationships (node uses other node)
- **Elliptical nodes**: Concrete AST nodes
- **Limited edges**: Only top dependencies shown to avoid clutter

### Detailed Graph
- **Record shapes**: Show field names and types
- **Solid arrows**: Inheritance relationships
- **Dashed arrows**: Field dependencies
- **Colors**: Category-based coloring

## Applications

These visualizations are useful for:

1. **Compiler Development** - Understanding AST structure when adding new features
2. **Documentation** - Visual reference for the GeLB language design
3. **Debugging** - Identifying problematic node relationships
4. **Optimization** - Finding heavily used nodes that may benefit from optimization
5. **Education** - Teaching compiler design and AST concepts

## Maintenance

The visualizations should be regenerated when:
- New AST node types are added
- Existing nodes are modified
- Field types or relationships change
- Major refactoring of the AST structure occurs

Run the generation scripts as part of the development process to keep visualizations current.