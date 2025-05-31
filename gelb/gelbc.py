#!/usr/bin/env python3

import click
import sys
import os
from pathlib import Path

# If we reached this point, we should be able to import GeLB modules
from gelb.utils.misc import load_file
import gelb.utils.config
from gelb.frontend.stage1_frontend import (
    get_ast,
    build_symbols_tables,
    validate_node_classes,
    initial_validation_geometry,
    enforce_rectangular_array_literals,
    # validate_ast,
    resolve_all_constants,
    resolve_ranges,
    prevent_clashes_of_symbol_refs_with_implicits,
    prevent_clashes_of_symbol_defs_with_implicits,
    add_implicit_symbols
)


@click.command()
@click.option(
    "-t",
    is_flag=True,
    help="Display traceback (for debugging the compiler itself)"
)
@click.argument(
    "input_file",
    # not using click.Path(), s.t. we can show nicer error-message
    type=click.STRING,
    nargs=1
)
@click.option(
    "--backend",
    type=click.Choice(
        ['cpu_fortran_serial',
         # Future backends:
         # 'cpu_cpp_serial',
         # 'cpu_cpp_parallel_openmp',
         # 'gpu_cpp_parallel_opencl',
         ]
    ),
    default='cpu_fortran_serial',
    help="Which backend to use for code-generation"
)
@click.option(
    "--visualize-ast",
    is_flag=True,
    help="Generate AST visualization as an image file"
)
@click.option(
    "--ast-output",
    type=click.STRING,
    help="Output file for AST visualization (default: <input_basename>_ast.png)"
)
@click.option(
    "--ast-format",
    type=click.Choice(['png', 'svg', 'pdf']),
    default='png',
    help="Output format for AST visualization"
)
@click.option(
    "--keep-dot",
    is_flag=True,
    help="Keep the intermediate DOT file after generating visualization"
)
def cli(t, input_file, backend, visualize_ast, ast_output, ast_format, keep_dot):
    """
    gelbc -- reference compiler (actually: "transpiler") for the GeLB DSL.

    This is the compiler-driver, which reads a "*.gelb" file and passes it
    through the various stages of the compiler.
    """

    if not t:  # disable the traceback by default
        sys.tracebacklimit = 0

    # Stage 1 :: FrontEnd

    # ... save file-name as global variable
    gelb.utils.config.GELB_FILE_NAME = input_file
    src_raw = load_file(input_file)

    # ... get the initial AST
    ast = get_ast("gelb_program", src_raw)

    # ... [validation] prevent clashes of symbol refs with implicits
    # NOTE: it is OK to reference automatic {x, y, z} variables
    # @{initializer,dynamic,gauge} blocks, but NOT OK to reference them
    # @{global_constants,lattices,node_classes,geometry} blocks
    prevent_clashes_of_symbol_refs_with_implicits(ast)

    # ... build the symbols table
    ast = build_symbols_tables(ast)

    # ... [validation] prevent clashes of user-defined symbols with the
    # - implicit constants {Nx , Ny , Nz}
    # - implicit variables {x, y, z}
    prevent_clashes_of_symbol_defs_with_implicits(ast)

    # ... add symbols for implicit constants & variable (where they are needed)
    # ast = add_implicit_symbols(ast)

    # ... all array-literals should be rectangular (because we DO NOT support
    # ragged arrays in GeLB)
    # enforce_rectangular_array_literals(ast)

    # ... resolve ALL constants (explicit AND implicit, in ALL scopes)
    ast = resolve_all_constants(ast)

    # ... resolve range bounds (replace None with concrete values)
    ast = resolve_ranges(ast)

    # ... validate node-classes
    validate_node_classes(ast)

    # ... initial validation of geometry block (all referenced node-classes
    # were defined in the node-classes block).
    initial_validation_geometry(ast)

    # validate_ast(ast)
    # ast.iterate_over_ast_fields()

    # ... TODO semantic analysis, checks, etc.

    # Stage 2 :: MidWare
    # ... TODO More checks & AST transformations

    # Stage 3 :: BackEnd
    # ... TODO code-generation
    print(ast)
    
    # AST Visualization (if requested)
    if visualize_ast:
        generate_ast_visualization(ast, input_file, ast_output, ast_format, keep_dot)


def generate_ast_visualization(ast, input_file, ast_output, ast_format, keep_dot=False):
    """
    Generate AST visualization using Graphviz.
    
    Args:
        ast: The AST root node to visualize
        input_file: Original input file path (for default output naming)
        ast_output: User-specified output file (or None for auto-naming)
        ast_format: Output format ('png', 'svg', 'pdf')
        keep_dot: Whether to keep the intermediate DOT file
    """
    try:
        # Import visualization functionality (will be implemented in Step 2)
        from gelb.frontend.ASTVisualizationVisitor import ASTVisualizationVisitor
        
        # Determine output file name
        if ast_output is None:
            input_path = Path(input_file)
            ast_output = f"{input_path.stem}_ast.{ast_format}"
        
        # Ensure output has correct extension
        output_path = Path(ast_output)
        if output_path.suffix != f".{ast_format}":
            output_path = output_path.with_suffix(f".{ast_format}")
        
        print(f"Generating AST visualization: {output_path}")
        
        # Create visualization visitor and generate DOT format
        visitor = ASTVisualizationVisitor()
        dot_content = visitor.generate_dot(ast)
        
        # Write DOT file (temporary)
        dot_file = output_path.with_suffix('.dot')
        with open(dot_file, 'w') as f:
            f.write(dot_content)
        
        # Use Graphviz to render the image
        import subprocess
        cmd = [
            'dot',
            f'-T{ast_format}',
            str(dot_file),
            '-o', str(output_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ AST visualization saved to: {output_path}")
            # Clean up temporary DOT file unless asked to keep it
            if keep_dot:
                print(f"📄 DOT file saved at: {dot_file}")
            else:
                dot_file.unlink()
        else:
            print(f"❌ Graphviz error: {result.stderr}")
            print(f"DOT file saved at: {dot_file}")
            
    except ImportError:
        print("❌ AST visualization not yet implemented (ASTVisualizationVisitor missing)")
    except FileNotFoundError:
        print("❌ Graphviz 'dot' command not found. Please install Graphviz and ensure it's in your PATH.")
    except Exception as e:
        print(f"❌ Error generating AST visualization: {e}")


if __name__ == "__main__":
    cli()