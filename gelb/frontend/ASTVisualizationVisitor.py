#!/usr/bin/env python3

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.gelb_ast.ASTNodes import Node_N, List_N


class ASTVisualizationVisitor(ASTBaseVisitor):
    """
    AST visitor that generates Graphviz DOT format for visualizing the AST structure.
    
    Creates compact, color-coded nodes showing essential information while maintaining
    readability for large ASTs.
    """
    
    def __init__(self):
        super().__init__()
        self.nodes = []  # List of (node_id, label, color) tuples
        self.edges = []  # List of (parent_id, child_id, edge_label) tuples
        self.node_counter = 0
        self.node_to_id = {}  # Map AST nodes to unique IDs
        self.depth_map = {}  # Map node IDs to their depth in the tree
        self.max_depth = 0
        
    def generate_dot(self, ast_root):
        """
        Generate Graphviz DOT format string for the given AST.
        
        Args:
            ast_root: Root node of the AST to visualize
            
        Returns:
            str: DOT format representation of the AST
        """
        # Reset state
        self.nodes = []
        self.edges = []
        self.node_counter = 0
        self.node_to_id = {}
        self.depth_map = {}
        self.max_depth = 0
        
        # Visit the AST and build graph structure
        self._visit_with_depth(ast_root, 0)
        
        # Generate DOT format
        return self._generate_dot_string()
    
    def _get_node_id(self, node):
        """Get or create a unique ID for an AST node."""
        if id(node) not in self.node_to_id:
            self.node_to_id[id(node)] = f"node_{self.node_counter}"
            self.node_counter += 1
        return self.node_to_id[id(node)]
    
    def _get_simple_node_repr(self, node):
        """Get a simple string representation of a node for compact display."""
        if node is None:
            return "None"
        
        node_type = type(node).__name__
        
        # For literals, just return the value
        if hasattr(node, 'value') and node.value is not None:
            return str(node.value)
        
        # For identifiers, return the name
        elif hasattr(node, 'name') and node.name is not None:
            return str(node.name)
        
        # For binary operators, show in infix notation
        elif node_type in ['Add_N', 'Sub_N', 'Mul_N', 'Div_N']:
            if hasattr(node, 'left') and hasattr(node, 'right'):
                left_repr = self._get_simple_node_repr(node.left)
                right_repr = self._get_simple_node_repr(node.right)
                op_map = {'Add_N': '+', 'Sub_N': '-', 'Mul_N': '*', 'Div_N': '/'}
                op = op_map.get(node_type, '?')
                return f"{left_repr}{op}{right_repr}"
        
        # For other nodes, just return the type
        return node_type.replace('_N', '')
    
    def _get_node_color(self, node):
        """Determine the color for a node based on its type."""
        node_type = type(node).__name__
        
        # Program structure - Blue
        if any(x in node_type for x in ['Program', 'Block', 'Geometry']):
            return 'lightblue'
        
        # Literals - Green
        elif any(x in node_type for x in ['Literal', 'BoolLiteral', 'IntLiteral', 'RealLiteral', 'StringLiteral']):
            return 'lightgreen'
        
        # Identifiers and references - Yellow
        elif any(x in node_type for x in ['Identifier', 'Reference']):
            return 'lightyellow'
        
        # Operators and expressions - Orange
        elif any(x in node_type for x in ['Add', 'Sub', 'Mul', 'Div', 'Pow', 'Equal', 'Less', 'Greater', 'And', 'Or', 'Not']):
            return 'orange'
        
        # Statements and control flow - Purple
        elif any(x in node_type for x in ['Stmt', 'Assignment', 'Declaration']):
            return 'plum'
        
        # Ranges and selections - Pink
        elif any(x in node_type for x in ['Range', 'Selection', 'RectSel']):
            return 'lightpink'
        
        # Data types - Cyan
        elif any(x in node_type for x in ['DataType', 'ScalarDataType', 'ArrayDataType']):
            return 'lightcyan'
        
        # Default - Light gray
        else:
            return 'lightgray'
    
    def _format_node_label(self, node):
        """Create a compact, readable label for a node."""
        node_type = type(node).__name__
        
        # Remove '_N' suffix for cleaner display
        if node_type.endswith('_N'):
            display_type = node_type[:-2]
        else:
            display_type = node_type
        
        # Add specific information based on node type
        if hasattr(node, 'value') and node.value is not None:
            # Literal nodes
            value_str = str(node.value)
            # Only truncate for StringLiteral nodes (simulation descriptions)
            if display_type == 'StringLiteral' and len(value_str) > 20:
                value_str = value_str[:17] + "..."
            # Escape quotes and backslashes for DOT format
            value_str = value_str.replace('\\', '\\\\').replace('"', '\\"')
            return f"{display_type}\\n{value_str}"
        
        elif hasattr(node, 'name') and node.name is not None:
            # Identifier nodes - never truncate these
            name_str = str(node.name)
            return f"{display_type}\\n{name_str}"
        
        elif hasattr(node, 'low') and hasattr(node, 'high'):
            # Range nodes - show bounds info
            # Recursively get simple string representation of bounds
            low_str = self._get_simple_node_repr(node.low) if node.low else "None"
            high_str = self._get_simple_node_repr(node.high) if node.high else "None"
            return f"{display_type}\\n{low_str}:{high_str}"
        
        elif hasattr(node, 'operator'):
            # Operator nodes
            return f"{display_type}\\n{node.operator}"
        
        else:
            # Generic nodes - just show type
            return display_type
    
    def _add_node(self, node):
        """Add a node to the visualization (only if not already added)."""
        node_id = self._get_node_id(node)
        
        # Check if node was already added
        for existing_id, _, _ in self.nodes:
            if existing_id == node_id:
                return node_id
        
        # Add new node
        label = self._format_node_label(node)
        color = self._get_node_color(node)
        self.nodes.append((node_id, label, color))
        return node_id
    
    def _add_edge(self, parent_node, child_node, edge_label=""):
        """Add an edge between two nodes."""
        parent_id = self._get_node_id(parent_node)
        child_id = self._get_node_id(child_node)
        self.edges.append((parent_id, child_id, edge_label))
    
    def _generate_dot_string(self):
        """Generate the final DOT format string."""
        lines = [
            "digraph AST {",
            "    // Graph settings",
            "    rankdir=TB;",
            "    node [shape=box, fontname=\"Arial\", fontsize=10];",
            "    edge [fontname=\"Arial\", fontsize=8];",
            "",
            "    // Node definitions"
        ]
        
        # Add all nodes
        for node_id, label, color in self.nodes:
            lines.append(f'    {node_id} [label="{label}" fillcolor={color} style=filled];')
        
        lines.append("")
        lines.append("    // Edge definitions")
        
        # Add all edges
        for parent_id, child_id, edge_label in self.edges:
            if edge_label:
                lines.append(f'    {parent_id} -> {child_id} [label="{edge_label}"];')
            else:
                lines.append(f'    {parent_id} -> {child_id};')
        
        # Add legend
        lines.extend([
            "",
            "    // Legend",
            "    subgraph cluster_legend {",
            "        label=\"Color Legend\";",
            "        style=filled;",
            "        fillcolor=white;",
            "        node [shape=box, width=2.0, height=0.3, fontsize=9];",
            "        ",
            "        legend1 [label=\"Program Structure\" fillcolor=lightblue style=filled];",
            "        legend2 [label=\"Literals\" fillcolor=lightgreen style=filled];",
            "        legend3 [label=\"Identifiers/References\" fillcolor=lightyellow style=filled];",
            "        legend4 [label=\"Operators\" fillcolor=orange style=filled];",
            "        legend5 [label=\"Statements\" fillcolor=plum style=filled];",
            "        legend6 [label=\"Ranges/Selections\" fillcolor=lightpink style=filled];",
            "        legend7 [label=\"Data Types\" fillcolor=lightcyan style=filled];",
            "        legend8 [label=\"Other\" fillcolor=lightgray style=filled];",
            "        ",
            "        // Invisible edges to control legend layout (single column)",
            "        edge [style=invis];",
            "        legend1 -> legend2 -> legend3 -> legend4 -> legend5 -> legend6 -> legend7 -> legend8;",
            "    }",
        ])
        
        lines.append("}")
        return "\n".join(lines)
    
    def _visit_with_depth(self, node, depth):
        """
        Visit a node and its children, tracking depth for statistics.
        """
        if node is None:
            return
        
        # Add this node to the visualization
        node_id = self._add_node(node)
        self.depth_map[node_id] = depth
        self.max_depth = max(self.max_depth, depth)
        
        # Handle List_N nodes specially
        if isinstance(node, List_N):
            for i, element in enumerate(node.elements):
                if element is not None:
                    child_id = self._add_node(element)
                    self._add_edge(node, element, f"[{i}]")
                    self._visit_with_depth(element, depth + 1)
        else:
            # Visit all children of this node
            for child_name in node.get_children_names():
                child = getattr(node, child_name, None)
                if child is not None:
                    if isinstance(child, Node_N):
                        child_id = self._add_node(child)
                        self._add_edge(node, child, child_name)
                        self._visit_with_depth(child, depth + 1)
                    elif isinstance(child, list):
                        # Handle lists of AST nodes
                        for i, list_item in enumerate(child):
                            if isinstance(list_item, Node_N):
                                child_id = self._add_node(list_item)
                                self._add_edge(node, list_item, f"{child_name}[{i}]")
                                self._visit_with_depth(list_item, depth + 1)
    
    def visit(self, node, ast_root_node):
        """
        Legacy visit method for compatibility with base class.
        """
        self._visit_with_depth(node, 0)
        return node
    
    def get_statistics(self):
        """
        Get statistics about the AST.
        
        Returns:
            tuple: (node_count, max_depth)
        """
        return len(self.nodes), self.max_depth