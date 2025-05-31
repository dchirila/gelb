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
        
        # Visit the AST and build graph structure
        self.visit(ast_root, ast_root)
        
        # Generate DOT format
        return self._generate_dot_string()
    
    def _get_node_id(self, node):
        """Get or create a unique ID for an AST node."""
        if id(node) not in self.node_to_id:
            self.node_to_id[id(node)] = f"node_{self.node_counter}"
            self.node_counter += 1
        return self.node_to_id[id(node)]
    
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
            low_str = "None" if node.low is None else "..."
            high_str = "None" if node.high is None else "..."
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
        
        lines.append("}")
        return "\n".join(lines)
    
    def visit(self, node, ast_root_node):
        """
        Visit a node and its children, building the visualization graph.
        """
        if node is None:
            return
        
        # Add this node to the visualization
        self._add_node(node)
        
        # Handle List_N nodes specially
        if isinstance(node, List_N):
            for i, element in enumerate(node.elements):
                if element is not None:
                    self._add_node(element)
                    self._add_edge(node, element, f"[{i}]")
                    self.visit(element, ast_root_node)
        else:
            # Visit all children of this node
            for child_name in node.get_children_names():
                child = getattr(node, child_name, None)
                if child is not None:
                    if isinstance(child, Node_N):
                        self._add_node(child)
                        self._add_edge(node, child, child_name)
                        self.visit(child, ast_root_node)
                    elif isinstance(child, list):
                        # Handle lists of AST nodes
                        for i, list_item in enumerate(child):
                            if isinstance(list_item, Node_N):
                                self._add_node(list_item)
                                self._add_edge(node, list_item, f"{child_name}[{i}]")
                                self.visit(list_item, ast_root_node)
        
        return node