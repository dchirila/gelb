#!/usr/bin/env python3
"""
AST visualization utilities for GeLB compiler.

This module provides functionality to generate visual representations
of the Abstract Syntax Tree (AST) at various compilation stages.
"""

from pathlib import Path
import subprocess


def _get_numbered_stage_name(stage_name):
    """
    Convert stage name to numbered stage name for better ordering.
    
    Args:
        stage_name (str): Original stage name
        
    Returns:
        str: Numbered stage name for file ordering
    """
    stage_mapping = {
        'parsing': '1_1_parsing',
        'symbols': '1_2_symbols',
        'constants': '1_3_constants',
        'ranges': '1_4_ranges',
        'types': '1_5_types',
        'promotions': '1_6_promotions',
        'constant_folding': '2_1_constant_folding',
        # Future midware stages:
        'dead_code_elimination': '2_2_dead_code_elimination',
        'common_subexpression_elimination': '2_3_common_subexpression_elimination',
        'lattice_access_optimization': '2_4_lattice_access_optimization',
        'backend_preparation': '2_5_backend_preparation',
        # Future backend stages can be added as:
        # 'backend': '3_1_backend',
        # 'optimization': '3_2_optimization',
    }
    
    return stage_mapping.get(stage_name, stage_name)


def generate_ast_visualization(ast, input_file, ast_output, ast_format, keep_dot=False, stage_name=None):
    """
    Generate AST visualization using Graphviz.
    
    Args:
        ast: The AST root node to visualize
        input_file: Original input file path (for default output naming)
        ast_output: User-specified output file (or None for auto-naming)
        ast_format: Output format ('png', 'svg', 'pdf')
        keep_dot: Whether to keep the intermediate DOT file
        stage_name: Name of the compilation stage (for output naming)
    """
    try:
        # Import visualization functionality
        from gelb.debugging.ASTVisualizationVisitor import ASTVisualizationVisitor
        
        # Determine output file name
        if ast_output is None:
            input_path = Path(input_file)
            if stage_name:
                numbered_stage = _get_numbered_stage_name(stage_name)
                ast_output = f"{input_path.stem}_{numbered_stage}.{ast_format}"
            else:
                ast_output = f"{input_path.stem}_ast.{ast_format}"
        
        # Ensure output has correct extension
        output_path = Path(ast_output)
        if output_path.suffix != f".{ast_format}":
            output_path = output_path.with_suffix(f".{ast_format}")
        
        stage_info = f" (stage: {stage_name})" if stage_name else ""
        print(f"Generating AST visualization{stage_info}: {output_path}")
        
        # Create visualization visitor and generate DOT format
        visitor = ASTVisualizationVisitor()
        dot_content = visitor.generate_dot(ast)
        
        # Get statistics
        node_count, max_depth = visitor.get_statistics()
        
        # Write DOT file (temporary)
        dot_file = output_path.with_suffix('.dot')
        with open(dot_file, 'w') as f:
            f.write(dot_content)
        
        # Use Graphviz to render the image
        cmd = [
            'dot',
            f'-T{ast_format}',
            str(dot_file),
            '-o', str(output_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ AST visualization saved to: {output_path}")
            print(f"📊 AST Statistics: {node_count} nodes, max depth: {max_depth}")
            # Clean up temporary DOT file unless asked to keep it
            if keep_dot:
                print(f"📄 DOT file saved at: {dot_file}")
            else:
                dot_file.unlink()
        else:
            print(f"❌ Graphviz error: {result.stderr}")
            print(f"DOT file saved at: {dot_file}")
            
    except ImportError:
        print("❌ AST visualization module not available (ASTVisualizationVisitor missing from debugging module)")
    except FileNotFoundError:
        print("❌ Graphviz 'dot' command not found. Please install Graphviz and ensure it's in your PATH.")
    except Exception as e:
        print(f"❌ Error generating AST visualization: {e}")