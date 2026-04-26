# GeLB AST node visualizations

Two scripts render the AST node hierarchy defined in
`gelb/gelb_ast/ASTNodes.py`.  Their output is written into this
directory and is **not tracked** (see `.gitignore`); regenerate it on
demand.

```bash
# Inheritance / dependency / detailed graphs (DOT), statistics report,
# and a matplotlib overview script:
uv run python scripts/visualize_ast_node_hierarchy.py --output-dir docs/visualizations

# Same, rendering the DOT files to PNG (needs Graphviz on PATH):
uv run python scripts/visualize_ast_node_hierarchy.py --output-dir docs/visualizations --format png

# Field-level analysis with actual dependencies:
uv run python scripts/enhanced_ast_analyzer.py
```

## What gets generated

- `gelb_ast.inheritance.dot` / `.png` — parent-child relationships
  between AST node classes
- `gelb_ast.dependencies.dot` / `.png` — which nodes reference which
- `gelb_ast.detailed.dot` / `.png` — record-shaped graph with field
  names and types
- `gelb_ast.statistics.md` — node counts by category, inheritance
  depth, most-referenced nodes
- `gelb_ast.diagram.py` — standalone matplotlib overview script
- `enhanced_ast_analysis.md` — field-type information and resolved
  dependencies

## Reading the graphs

- Inheritance graph: blue arrows point from parent to child; dashed
  boxes are abstract classes; colours follow the node category.
- Dependency graph: red arrows point from a node to the node types it
  holds in its fields; only the strongest edges are drawn.
- Detailed graph: solid arrows are inheritance, dashed arrows are
  field dependencies.

Regenerate after adding or changing AST node classes; the graphs are
a quick way to check that a new node sits in the intended part of the
hierarchy.
