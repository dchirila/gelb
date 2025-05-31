#!/usr/bin/env python3

import click
import sys

# If we reached this point, we should be able to import GeLB modules
from gelb.utils.misc import load_file
import gelb.utils.config
from gelb.utils.ast_visualization import generate_ast_visualization
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
@click.option(
    "--ast-stage",
    type=click.Choice(['parsing', 'symbols', 'constants', 'ranges', 'all']),
    default='ranges',
    help="Which compilation stage to visualize (default: ranges)"
)
def cli(t, input_file, backend, visualize_ast, ast_output, ast_format, keep_dot, ast_stage):
    """
    gelbc -- reference compiler (actually: "transpiler") for the GeLB DSL.

    This is the compiler-driver, which reads a "*.gelb" file and passes it
    through the various stages of the compiler.
    """

    if not t:  # disable the traceback by default
        sys.tracebacklimit = 0
    
    # Helper function to capture AST at various stages
    def capture_ast_if_requested(ast, stage_name):
        """Capture AST visualization if requested for this stage."""
        if visualize_ast and ast_stage in [stage_name, 'all']:
            generate_ast_visualization(ast, input_file, ast_output, ast_format, keep_dot, stage_name)

    # Stage 1 :: FrontEnd

    # ... save file-name as global variable
    gelb.utils.config.GELB_FILE_NAME = input_file
    src_raw = load_file(input_file)

    # ... get the initial AST
    ast = get_ast("gelb_program", src_raw)
    capture_ast_if_requested(ast, 'parsing')

    # ... [validation] prevent clashes of symbol refs with implicits
    # NOTE: it is OK to reference automatic {x, y, z} variables
    # @{initializer,dynamic,gauge} blocks, but NOT OK to reference them
    # @{global_constants,lattices,node_classes,geometry} blocks
    prevent_clashes_of_symbol_refs_with_implicits(ast)

    # ... build the symbols table
    ast = build_symbols_tables(ast)
    capture_ast_if_requested(ast, 'symbols')

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
    capture_ast_if_requested(ast, 'constants')

    # ... resolve range bounds (replace None with concrete values)
    ast = resolve_ranges(ast)
    capture_ast_if_requested(ast, 'ranges')

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


if __name__ == "__main__":
    cli()