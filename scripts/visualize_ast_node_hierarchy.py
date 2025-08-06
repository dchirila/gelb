#!/usr/bin/env python3
"""
GeLB AST Node Hierarchy Visualizer

This script analyzes the GeLB AST node definitions and creates visualizations
showing the inheritance hierarchy and dependencies between different node types.

Features:
- Inheritance hierarchy graph
- Dependency analysis (which nodes contain references to other nodes)
- Node categorization by type (abstract base classes, concrete nodes, etc.)
- Statistics and metrics about the AST structure

Usage:
    python scripts/visualize_ast_node_hierarchy.py [--output-dir OUTPUT_DIR] [--format FORMAT]

Dependencies:
    - graphviz (for DOT file generation)
    - matplotlib (for statistics plots)
"""

import ast
import re
import sys
import argparse
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Set, Tuple, Optional
import subprocess

class ASTNodeAnalyzer:
    """Analyzes the GeLB AST node structure and relationships."""
    
    def __init__(self, ast_nodes_file: Path):
        self.ast_nodes_file = ast_nodes_file
        self.node_classes = {}  # name -> class_info
        self.inheritance_tree = defaultdict(list)  # parent -> [children]
        self.dependencies = defaultdict(set)  # node -> {dependencies}
        self.node_categories = defaultdict(list)  # category -> [nodes]
        
    def analyze(self):
        """Perform complete analysis of AST nodes."""
        print("🔍 Analyzing AST node structure...")
        self._parse_ast_file()
        self._build_inheritance_tree()
        self._analyze_dependencies()
        self._categorize_nodes()
        self._compute_statistics()
        
    def _parse_ast_file(self):
        """Parse the ASTNodes.py file to extract class definitions."""
        with open(self.ast_nodes_file, 'r') as f:
            content = f.read()
        
        # Parse the file as Python AST
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_info = self._extract_class_info(node, content)
                self.node_classes[node.name] = class_info
                
    def _extract_class_info(self, class_node: ast.ClassDef, source_content: str) -> dict:
        """Extract detailed information about a class."""
        # Get base classes
        bases = []
        for base in class_node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                # Handle cases like ABC.abstractmethod
                bases.append(ast.unparse(base))
        
        # Get docstring
        docstring = ast.get_docstring(class_node) or ""
        
        # Determine if it's abstract
        is_abstract = any(
            isinstance(decorator, ast.Name) and decorator.id == 'abstractmethod'
            for decorator in getattr(class_node, 'decorator_list', [])
        ) or 'ABC' in bases or '@abstractmethod' in docstring
        
        # Get class attributes/fields from __init__ method
        fields = []
        init_method = None
        for item in class_node.body:
            if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                init_method = item
                break
        
        if init_method:
            fields = self._extract_fields_from_init(init_method)
        
        # Get line number
        line_number = class_node.lineno
        
        return {
            'name': class_node.name,
            'bases': bases,
            'docstring': docstring,
            'is_abstract': is_abstract,
            'fields': fields,
            'line_number': line_number,
            'methods': [item.name for item in class_node.body if isinstance(item, ast.FunctionDef)]
        }
    
    def _extract_fields_from_init(self, init_method: ast.FunctionDef) -> List[str]:
        """Extract field assignments from __init__ method."""
        fields = []
        for stmt in init_method.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Attribute) and \
                       isinstance(target.value, ast.Name) and target.value.id == 'self':
                        fields.append(target.attr)
        return fields
    
    def _build_inheritance_tree(self):
        """Build the inheritance hierarchy."""
        for name, info in self.node_classes.items():
            for base in info['bases']:
                if base in self.node_classes:
                    self.inheritance_tree[base].append(name)
    
    def _analyze_dependencies(self):
        """Analyze which nodes depend on other nodes through field types."""
        for name, info in self.node_classes.items():
            deps = set()
            
            # Look for type hints and field assignments that reference other nodes
            # This is a simplified analysis - in practice, you'd want to look at
            # actual field types more carefully
            for field in info['fields']:
                # Look for common AST node patterns
                for other_name in self.node_classes.keys():
                    if other_name != name and other_name in info['docstring']:
                        deps.add(other_name)
            
            # Also check the docstring for references to other nodes
            docstring = info['docstring'].lower()
            for other_name in self.node_classes.keys():
                if other_name != name and other_name.lower().replace('_n', '') in docstring:
                    deps.add(other_name)
            
            self.dependencies[name] = deps
    
    def _categorize_nodes(self):
        """Categorize nodes by their role and characteristics."""
        for name, info in self.node_classes.items():
            # Abstract base classes
            if info['is_abstract'] or name.endswith('_N') and len(self.inheritance_tree[name]) > 0:
                self.node_categories['Abstract Base Classes'].append(name)
            
            # Terminal nodes (literals, identifiers)
            elif any(term in name.lower() for term in ['literal', 'identifier']):
                self.node_categories['Terminal Nodes'].append(name)
            
            # Statement nodes
            elif 'stmt' in name.lower() or 'statement' in info['docstring'].lower():
                self.node_categories['Statement Nodes'].append(name)
            
            # Expression nodes
            elif name.endswith('Expr_N') or 'expr' in name.lower() or 'expression' in info['docstring'].lower():
                self.node_categories['Expression Nodes'].append(name)
            
            # Block nodes
            elif 'block' in name.lower():
                self.node_categories['Block Nodes'].append(name)
            
            # Selection nodes
            elif 'sel' in name.lower() or 'selection' in info['docstring'].lower():
                self.node_categories['Selection Nodes'].append(name)
            
            # Data type nodes
            elif 'type' in name.lower() or 'Type' in name:
                self.node_categories['Data Type Nodes'].append(name)
            
            # Other nodes
            else:
                self.node_categories['Other Nodes'].append(name)
    
    def _compute_statistics(self):
        """Compute various statistics about the AST structure."""
        self.stats = {
            'total_nodes': len(self.node_classes),
            'abstract_nodes': len([n for n, info in self.node_classes.items() if info['is_abstract']]),
            'concrete_nodes': len([n for n, info in self.node_classes.items() if not info['is_abstract']]),
            'max_inheritance_depth': self._compute_max_depth(),
            'avg_fields_per_node': sum(len(info['fields']) for info in self.node_classes.values()) / len(self.node_classes),
            'most_referenced_nodes': self._find_most_referenced_nodes(),
            'categories': {cat: len(nodes) for cat, nodes in self.node_categories.items()}
        }
    
    def _compute_max_depth(self) -> int:
        """Compute the maximum inheritance depth."""
        def depth(node, visited=None):
            if visited is None:
                visited = set()
            if node in visited:
                return 0  # Avoid cycles
            visited.add(node)
            
            children = self.inheritance_tree.get(node, [])
            if not children:
                return 1
            return 1 + max(depth(child, visited.copy()) for child in children)
        
        return max(depth(node) for node in self.node_classes.keys() if node in self.inheritance_tree)
    
    def _find_most_referenced_nodes(self) -> List[Tuple[str, int]]:
        """Find the most frequently referenced nodes."""
        ref_count = Counter()
        for deps in self.dependencies.values():
            ref_count.update(deps)
        return ref_count.most_common(10)
    
    def generate_inheritance_graph(self, output_file: Path):
        """Generate DOT file for inheritance hierarchy."""
        print(f"📊 Generating inheritance hierarchy graph: {output_file}")
        
        dot_content = []
        dot_content.append('digraph "GeLB AST Inheritance Hierarchy" {')
        dot_content.append('    rankdir=TB;')
        dot_content.append('    node [shape=box, style=filled];')
        dot_content.append('    edge [color=blue, arrowhead=empty];')
        dot_content.append('')
        
        # Define node styles by category
        colors = {
            'Abstract Base Classes': '#FFE6E6',
            'Terminal Nodes': '#E6F3FF', 
            'Statement Nodes': '#E6FFE6',
            'Expression Nodes': '#FFFACD',
            'Block Nodes': '#F0E6FF',
            'Selection Nodes': '#FFE6F3',
            'Data Type Nodes': '#E6FFFF',
            'Other Nodes': '#F5F5F5'
        }
        
        # Add nodes with category-based coloring
        for category, nodes in self.node_categories.items():
            color = colors.get(category, '#F5F5F5')
            for node in nodes:
                info = self.node_classes[node]
                label = f"{node}\\n({len(info['fields'])} fields)"
                if info['is_abstract']:
                    dot_content.append(f'    "{node}" [label="{label}", fillcolor="{color}", style="filled,dashed"];')
                else:
                    dot_content.append(f'    "{node}" [label="{label}", fillcolor="{color}"];')
        
        dot_content.append('')
        
        # Add inheritance edges
        for parent, children in self.inheritance_tree.items():
            for child in children:
                dot_content.append(f'    "{parent}" -> "{child}";')
        
        # Add legend
        dot_content.append('')
        dot_content.append('    subgraph cluster_legend {')
        dot_content.append('        label="Node Categories";')
        dot_content.append('        style=filled;')
        dot_content.append('        fillcolor=white;')
        for i, (category, color) in enumerate(colors.items()):
            dot_content.append(f'        "legend_{i}" [label="{category}", fillcolor="{color}", shape=box];')
        dot_content.append('    }')
        
        dot_content.append('}')
        
        with open(output_file, 'w') as f:
            f.write('\n'.join(dot_content))
    
    def generate_dependency_graph(self, output_file: Path):
        """Generate DOT file for node dependencies."""
        print(f"🔗 Generating dependency graph: {output_file}")
        
        dot_content = []
        dot_content.append('digraph "GeLB AST Node Dependencies" {')
        dot_content.append('    rankdir=LR;')
        dot_content.append('    node [shape=ellipse, style=filled, fillcolor=lightblue];')
        dot_content.append('    edge [color=red, arrowhead=vee];')
        dot_content.append('')
        
        # Add nodes
        for node in self.node_classes.keys():
            dot_content.append(f'    "{node}";')
        
        dot_content.append('')
        
        # Add dependency edges (limit to avoid clutter)
        for node, deps in self.dependencies.items():
            for dep in list(deps)[:5]:  # Limit to top 5 dependencies
                if dep in self.node_classes:
                    dot_content.append(f'    "{node}" -> "{dep}" [label="uses"];')
        
        dot_content.append('}')
        
        with open(output_file, 'w') as f:
            f.write('\n'.join(dot_content))
    
    def generate_statistics_report(self, output_file: Path):
        """Generate a detailed statistics report."""
        print(f"📈 Generating statistics report: {output_file}")
        
        report = []
        report.append("# GeLB AST Node Analysis Report")
        report.append("=" * 50)
        report.append("")
        
        # Overview statistics
        report.append("## Overview Statistics")
        report.append(f"- **Total AST Nodes**: {self.stats['total_nodes']}")
        report.append(f"- **Abstract Nodes**: {self.stats['abstract_nodes']}")
        report.append(f"- **Concrete Nodes**: {self.stats['concrete_nodes']}")
        report.append(f"- **Maximum Inheritance Depth**: {self.stats['max_inheritance_depth']}")
        report.append(f"- **Average Fields per Node**: {self.stats['avg_fields_per_node']:.1f}")
        report.append("")
        
        # Category breakdown
        report.append("## Node Categories")
        for category, count in self.stats['categories'].items():
            report.append(f"- **{category}**: {count} nodes")
        report.append("")
        
        # Most referenced nodes
        report.append("## Most Referenced Nodes")
        for node, count in self.stats['most_referenced_nodes']:
            if count > 0:
                report.append(f"- **{node}**: referenced {count} times")
        report.append("")
        
        # Detailed node listing by category
        report.append("## Detailed Node Listings")
        for category, nodes in self.node_categories.items():
            if nodes:
                report.append(f"### {category}")
                for node in sorted(nodes):
                    info = self.node_classes[node]
                    abstract_marker = " (abstract)" if info['is_abstract'] else ""
                    field_count = len(info['fields'])
                    report.append(f"- **{node}**{abstract_marker} - {field_count} fields")
                    if info['docstring']:
                        # First line of docstring
                        first_line = info['docstring'].split('\n')[0].strip()
                        if first_line:
                            report.append(f"  - {first_line}")
                report.append("")
        
        # Inheritance hierarchy details
        report.append("## Inheritance Hierarchy")
        root_nodes = [node for node in self.node_classes.keys() 
                     if not any(node in children for children in self.inheritance_tree.values())]
        
        def print_hierarchy(node, indent=0):
            lines = []
            prefix = "  " * indent + ("└─ " if indent > 0 else "")
            info = self.node_classes[node]
            abstract_marker = " (abstract)" if info['is_abstract'] else ""
            lines.append(f"{prefix}**{node}**{abstract_marker}")
            
            children = sorted(self.inheritance_tree.get(node, []))
            for child in children:
                lines.extend(print_hierarchy(child, indent + 1))
            return lines
        
        for root in sorted(root_nodes):
            if root in self.inheritance_tree:  # Only show nodes with children
                report.extend(print_hierarchy(root))
                report.append("")
        
        with open(output_file, 'w') as f:
            f.write('\n'.join(report))
    
    def generate_python_class_diagram(self, output_file: Path):
        """Generate a Python script that creates a class diagram using matplotlib."""
        print(f"🐍 Generating Python class diagram script: {output_file}")
        
        script_content = '''#!/usr/bin/env python3
"""
Auto-generated script to create GeLB AST class hierarchy diagram using matplotlib.
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch
import numpy as np

def create_class_diagram():
    """Create a visual class diagram of the GeLB AST hierarchy."""
    fig, ax = plt.subplots(1, 1, figsize=(20, 15))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_aspect('equal')
    
    # Category positions and colors
    categories = {
'''
        
        # Add category data
        for i, (category, nodes) in enumerate(self.node_categories.items()):
            x = (i % 4) * 25 + 10
            y = 80 - (i // 4) * 20
            script_content += f'        "{category}": {{"pos": ({x}, {y}), "nodes": {len(nodes)}, "color": "C{i % 10}"}},\n'
        
        script_content += '''    }
    
    # Draw category boxes
    for category, info in categories.items():
        x, y = info["pos"]
        color = info["color"]
        node_count = info["nodes"]
        
        # Draw box
        box = FancyBboxPatch((x-8, y-3), 16, 6, 
                           boxstyle="round,pad=0.1",
                           facecolor=color, alpha=0.3,
                           edgecolor=color, linewidth=2)
        ax.add_patch(box)
        
        # Add text
        ax.text(x, y+1, category, ha='center', va='center', fontsize=10, fontweight='bold')
        ax.text(x, y-1, f"{node_count} nodes", ha='center', va='center', fontsize=8)
    
    # Add title and labels
    ax.set_title("GeLB AST Node Categories Overview", fontsize=16, fontweight='bold', pad=20)
    ax.set_xlabel("Node Categories Distribution", fontsize=12)
    ax.set_ylabel("Inheritance Hierarchy", fontsize=12)
    
    # Remove axes
    ax.set_xticks([])
    ax.set_yticks([])
    
    # Add statistics text
    stats_text = f"""
    Total Nodes: ''' + str(self.stats['total_nodes']) + '''
    Abstract: ''' + str(self.stats['abstract_nodes']) + '''
    Concrete: ''' + str(self.stats['concrete_nodes']) + '''
    Max Depth: ''' + str(self.stats['max_inheritance_depth']) + '''
    Avg Fields: ''' + f"{self.stats['avg_fields_per_node']:.1f}" + '''
    """
    ax.text(80, 15, stats_text, fontsize=10, bbox=dict(boxstyle="round,pad=0.5", facecolor="lightgray", alpha=0.8))
    
    plt.tight_layout()
    return fig

if __name__ == "__main__":
    fig = create_class_diagram()
    plt.savefig("gelb_ast_overview.png", dpi=300, bbox_inches='tight')
    plt.savefig("gelb_ast_overview.pdf", bbox_inches='tight')
    print("📊 Class diagram saved as gelb_ast_overview.png and gelb_ast_overview.pdf")
    plt.show()
'''
        
        with open(output_file, 'w') as f:
            f.write(script_content)
        
        # Make it executable
        output_file.chmod(0o755)


def main():
    """Main entry point for the AST visualization script."""
    parser = argparse.ArgumentParser(
        description="Generate visualizations of GeLB AST node hierarchy and dependencies"
    )
    parser.add_argument(
        "--output-dir", 
        type=Path, 
        default=Path("ast_visualization_output"),
        help="Output directory for generated files (default: ast_visualization_output)"
    )
    parser.add_argument(
        "--format", 
        choices=["dot", "png", "svg", "pdf"], 
        default="dot",
        help="Output format for graphs (default: dot)"
    )
    
    args = parser.parse_args()
    
    # Ensure output directory exists
    args.output_dir.mkdir(exist_ok=True)
    
    # Find the ASTNodes.py file
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    ast_nodes_file = project_root / "gelb" / "gelb_ast" / "ASTNodes.py"
    
    if not ast_nodes_file.exists():
        print(f"❌ Error: Could not find ASTNodes.py at {ast_nodes_file}")
        sys.exit(1)
    
    print(f"🎯 Analyzing AST nodes from: {ast_nodes_file}")
    print(f"📁 Output directory: {args.output_dir}")
    
    # Analyze the AST structure
    analyzer = ASTNodeAnalyzer(ast_nodes_file)
    analyzer.analyze()
    
    # Generate outputs
    base_path = args.output_dir / "gelb_ast"
    
    # Generate DOT files
    analyzer.generate_inheritance_graph(base_path.with_suffix(".inheritance.dot"))
    analyzer.generate_dependency_graph(base_path.with_suffix(".dependencies.dot"))
    
    # Generate reports
    analyzer.generate_statistics_report(base_path.with_suffix(".statistics.md"))
    analyzer.generate_python_class_diagram(base_path.with_suffix(".diagram.py"))
    
    # Convert DOT files to other formats if requested and graphviz is available
    if args.format != "dot":
        try:
            for dot_file in args.output_dir.glob("*.dot"):
                output_file = dot_file.with_suffix(f".{args.format}")
                subprocess.run(["dot", f"-T{args.format}", str(dot_file), "-o", str(output_file)], 
                             check=True, capture_output=True)
                print(f"✅ Generated {output_file}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("⚠️  Graphviz not found. Install with: apt-get install graphviz (Linux) or brew install graphviz (Mac)")
            print("📄 DOT files generated - you can manually convert them using online tools")
    
    print(f"\n🎉 Analysis complete! Generated files:")
    for file in sorted(args.output_dir.glob("gelb_ast*")):
        print(f"   📄 {file.name}")
    
    print(f"\n📊 Summary:")
    print(f"   • {analyzer.stats['total_nodes']} total AST nodes")
    print(f"   • {analyzer.stats['abstract_nodes']} abstract base classes")
    print(f"   • {analyzer.stats['concrete_nodes']} concrete implementations")
    print(f"   • {len(analyzer.node_categories)} different categories")
    print(f"   • Maximum inheritance depth: {analyzer.stats['max_inheritance_depth']}")


if __name__ == "__main__":
    main()