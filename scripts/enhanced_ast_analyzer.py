#!/usr/bin/env python3
"""
Enhanced GeLB AST Node Analyzer

This script provides more detailed analysis of AST node relationships by actually
inspecting the __init__ methods and constructor parameters to understand field types.
"""

import ast
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set

class EnhancedASTAnalyzer:
    """Enhanced analyzer that inspects actual field types in AST nodes."""
    
    def __init__(self, ast_nodes_file: Path):
        self.ast_nodes_file = ast_nodes_file
        self.node_info = {}
        self.actual_dependencies = defaultdict(set)
        self.field_types = defaultdict(dict)  # node -> {field: type}
        
    def analyze(self):
        """Perform enhanced analysis with actual field type inspection."""
        print("🔍 Enhanced AST analysis...")
        
        with open(self.ast_nodes_file, 'r') as f:
            content = f.read()
        
        # Parse as AST
        tree = ast.parse(content)
        
        # Extract class information
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                self._analyze_class(node, content)
        
        # Build dependency graph
        self._build_dependency_graph()
        
        # Generate enhanced report
        self._generate_enhanced_report()
    
    def _analyze_class(self, class_node: ast.ClassDef, source_content: str):
        """Analyze a class to extract field types and dependencies."""
        class_name = class_node.name
        
        # Find __init__ method
        init_method = None
        for item in class_node.body:
            if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                init_method = item
                break
        
        if not init_method:
            return
        
        # Extract parameter types from function signature
        param_types = {}
        for arg in init_method.args.args[1:]:  # Skip 'self'
            # Look for type annotations
            if arg.annotation:
                param_types[arg.arg] = ast.unparse(arg.annotation)
        
        # Extract field assignments and their types
        field_info = {}
        for stmt in init_method.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Attribute) and \
                       isinstance(target.value, ast.Name) and target.value.id == 'self':
                        field_name = target.attr
                        
                        # Try to infer type from assignment
                        field_type = self._infer_assignment_type(stmt.value, param_types)
                        field_info[field_name] = field_type
        
        self.node_info[class_name] = {
            'fields': field_info,
            'docstring': ast.get_docstring(class_node) or "",
            'bases': [ast.unparse(base) for base in class_node.bases],
            'line_number': class_node.lineno
        }
        
        self.field_types[class_name] = field_info
    
    def _infer_assignment_type(self, value_node, param_types: Dict[str, str]) -> str:
        """Infer the type of a field assignment."""
        if isinstance(value_node, ast.Name):
            # Direct parameter assignment: self.field = param
            return param_types.get(value_node.id, "Unknown")
        elif isinstance(value_node, ast.List):
            return "List"
        elif isinstance(value_node, ast.Constant):
            if isinstance(value_node.value, str):
                return "str"
            elif isinstance(value_node.value, int):
                return "int"
            elif isinstance(value_node.value, bool):
                return "bool"
            else:
                return "Constant"
        elif isinstance(value_node, ast.Call):
            if isinstance(value_node.func, ast.Name):
                return value_node.func.id + "()"
            else:
                return "Call"
        else:
            return "Expression"
    
    def _build_dependency_graph(self):
        """Build actual dependency graph based on field types."""
        for node_name, info in self.node_info.items():
            for field_name, field_type in info['fields'].items():
                # Look for references to other AST nodes
                for other_node in self.node_info.keys():
                    if other_node != node_name and other_node in field_type:
                        self.actual_dependencies[node_name].add(other_node)
                
                # Also check for List_N containing other nodes
                if "List_N" in field_type:
                    self.actual_dependencies[node_name].add("List_N")
    
    def _generate_enhanced_report(self):
        """Generate an enhanced analysis report."""
        report_path = Path("/home/dchirila/Research/gelb/gelb/docs/visualizations/enhanced_ast_analysis.md")
        
        with open(report_path, 'w') as f:
            f.write("# Enhanced GeLB AST Node Analysis\n")
            f.write("="*50 + "\n\n")
            
            f.write("## Field Type Analysis\n\n")
            
            for node_name, info in sorted(self.node_info.items()):
                f.write(f"### {node_name}\n")
                f.write(f"**Inherits from**: {', '.join(info['bases']) if info['bases'] else 'None'}\n\n")
                
                if info['fields']:
                    f.write("**Fields**:\n")
                    for field_name, field_type in info['fields'].items():
                        f.write(f"- `{field_name}`: {field_type}\n")
                else:
                    f.write("**Fields**: None\n")
                
                if info['docstring']:
                    first_line = info['docstring'].split('\n')[0].strip()
                    f.write(f"\n**Description**: {first_line}\n")
                
                f.write(f"\n**Dependencies**: {', '.join(sorted(self.actual_dependencies[node_name])) if self.actual_dependencies[node_name] else 'None'}\n\n")
                f.write("---\n\n")
            
            # Dependency summary
            f.write("## Dependency Summary\n\n")
            f.write("Nodes with the most dependencies:\n\n")
            
            dep_counts = [(node, len(deps)) for node, deps in self.actual_dependencies.items()]
            dep_counts.sort(key=lambda x: x[1], reverse=True)
            
            for node, count in dep_counts[:10]:
                if count > 0:
                    deps = ', '.join(sorted(self.actual_dependencies[node]))
                    f.write(f"- **{node}** ({count} dependencies): {deps}\n")
        
        print(f"📊 Enhanced report generated: {report_path}")
    
    def generate_detailed_dot_graph(self):
        """Generate a more detailed DOT graph with field information."""
        output_path = Path("/home/dchirila/Research/gelb/gelb/docs/visualizations/gelb_ast.detailed.dot")
        
        with open(output_path, 'w') as f:
            f.write('digraph "GeLB AST Detailed Structure" {\n')
            f.write('    rankdir=TB;\n')
            f.write('    node [shape=record, style=filled];\n')
            f.write('    edge [color=darkblue];\n\n')
            
            # Add nodes with field details
            for node_name, info in self.node_info.items():
                if info['fields']:
                    field_list = '|'.join([f"{name}: {type_}" for name, type_ in info['fields'].items()])
                    label = f"{node_name}|{field_list}"
                else:
                    label = node_name
                
                # Color by category
                if node_name.endswith('Block_N'):
                    color = '#E6F3FF'
                elif node_name.endswith('Stmt_N') or 'Stmt' in node_name:
                    color = '#E6FFE6'
                elif node_name.endswith('Expr_N') or 'Expr' in node_name:
                    color = '#FFFACD'
                elif 'Literal' in node_name:
                    color = '#FFE6E6'
                else:
                    color = '#F5F5F5'
                
                f.write(f'    "{node_name}" [label="{label}", fillcolor="{color}"];\n')
            
            f.write('\n')
            
            # Add inheritance edges
            for node_name, info in self.node_info.items():
                for base in info['bases']:
                    if base in self.node_info:
                        f.write(f'    "{base}" -> "{node_name}" [style=solid, arrowhead=empty];\n')
            
            f.write('\n')
            
            # Add dependency edges
            for node_name, deps in self.actual_dependencies.items():
                for dep in deps:
                    if dep in self.node_info:
                        f.write(f'    "{node_name}" -> "{dep}" [style=dashed, color=red, arrowhead=vee];\n')
            
            f.write('}\n')
        
        print(f"📊 Detailed DOT graph generated: {output_path}")


def main():
    """Main function for enhanced AST analysis."""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    ast_nodes_file = project_root / "gelb" / "gelb_ast" / "ASTNodes.py"
    
    if not ast_nodes_file.exists():
        print(f"❌ Error: Could not find ASTNodes.py at {ast_nodes_file}")
        return
    
    analyzer = EnhancedASTAnalyzer(ast_nodes_file)
    analyzer.analyze()
    analyzer.generate_detailed_dot_graph()
    
    print("✅ Enhanced analysis complete!")


if __name__ == "__main__":
    main()