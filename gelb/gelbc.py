#!/usr/bin/env python3

import click
import sys

# If we reached this point, we should be able to import GeLB modules
from gelb.utils.misc import load_file
import gelb.utils.config
from gelb.utils.ast_visualization import generate_ast_visualization
from gelb.frontend.stage1_frontend import (
    get_ast,
    validate_ast_root_is_program,
    build_symbols_tables,
    validate_gauges,
    validate_node_classes,
    initial_validation_geometry,
    enforce_rectangular_array_literals,
    # validate_ast,
    resolve_all_constants,
    resolve_ranges,
    prevent_clashes_of_symbol_refs_with_implicits,
    prevent_clashes_of_symbol_defs_with_implicits,
    add_implicit_symbols,
    infer_types,
    promote_types,
    validate_types,
    validate_constant_assignments,
    validate_lattice_consistency
)
from gelb.midware.stage2_midware import (
    validate_midware_input,
    fold_constants,
    validate_division_by_zero
    # Future imports when implemented:
    # eliminate_dead_code,
    # eliminate_common_subexpressions,
    # optimize_lattice_access_patterns,
    # prepare_for_backend
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
    type=click.Choice(['parsing', 'symbols', 'constants', 'ranges', 'types', 'promotions', 'constant_folding', 'midware', 'all']),
    default='promotions',
    help="Which compilation stage to visualize (default: promotions)"
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
    
    # ... validate AST root is Program_N for proper symbol resolution
    validate_ast_root_is_program(ast)

    # ... validate gauge blocks have required output specifications
    validate_gauges(ast)

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
    ast = add_implicit_symbols(ast)

    # ... all array-literals should be rectangular (because we DO NOT support
    # ragged arrays in GeLB)
    # enforce_rectangular_array_literals(ast)

    # ... resolve ALL constants (explicit AND implicit, in ALL scopes)
    ast = resolve_all_constants(ast)
    capture_ast_if_requested(ast, 'constants')

    # ... resolve range bounds (replace None with concrete values)
    ast = resolve_ranges(ast)
    capture_ast_if_requested(ast, 'ranges')

    # ... infer types for all expressions
    ast = infer_types(ast)
    capture_ast_if_requested(ast, 'types')

    # ... apply implicit type promotions
    ast = promote_types(ast)
    capture_ast_if_requested(ast, 'promotions')

    # ... validate type compatibility
    ast = validate_types(ast)

    # ... validate that constants are not assigned to
    ast = validate_constant_assignments(ast)

    # ... validate lattice consistency (all lattices must have same grid properties)
    validate_lattice_consistency(ast)

    # ... validate node-classes
    validate_node_classes(ast)

    # ... initial validation of geometry block (all referenced node-classes
    # were defined in the node-classes block).
    initial_validation_geometry(ast)

    # validate_ast(ast)
    # ast.iterate_over_ast_fields()

    # ... TODO semantic analysis, checks, etc.

    # Stage 2 :: MidWare
    
    # ... validate input is ready for midware processing
    validate_midware_input(ast)
    
    # ... fold constant expressions at compile time
    ast = fold_constants(ast)
    capture_ast_if_requested(ast, 'constant_folding')
    
    # ... check for division by zero after constant folding
    # This must run after constant folding/propagation to catch cases like:
    # - const int ZERO = 0; ... 1 / ZERO (propagation)
    # - const int ZERO = 1 - 1; ... 1 / ZERO (folding + propagation)
    ast = validate_division_by_zero(ast)
    
    # ... TODO: Future midware optimizations (not yet implemented)
    # ast = eliminate_dead_code(ast)
    # capture_ast_if_requested(ast, 'dead_code_elimination')
    #
    # ast = eliminate_common_subexpressions(ast)
    # capture_ast_if_requested(ast, 'common_subexpression_elimination')
    #
    # ast = optimize_lattice_access_patterns(ast)
    # capture_ast_if_requested(ast, 'lattice_access_optimization')
    #
    # ast = prepare_for_backend(ast)
    # capture_ast_if_requested(ast, 'backend_preparation')

    # Stage 3 :: BackEnd
    # ... TODO code-generation (will use 'backend' parameter)
    print(ast)


if __name__ == "__main__":
    cli()