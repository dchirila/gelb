#!/usr/bin/env python3

import click
import json
import os
import re
import sys

from gelb.utils.ast_visualization import generate_ast_visualization
from gelb.compiler_pipeline import (
    PipelineOptions, PipelineProfile, build_backend_context, compile_file,
    resolve_geometry_for_compile)


def _print_identifier_mapping(ast):
    """Print per-scope tables mapping GeLB identifiers to Fortran encodings."""
    from gelb.utils.identifier_mapping import (
        collect_identifier_mapping, format_identifier_mapping
    )
    sections = collect_identifier_mapping(ast)
    click.echo(format_identifier_mapping(sections))


_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


def _strip_ansi(s):
    if s is None:
        return None
    return _ANSI_RE.sub('', s)


def _diag_range(start_line, start_col, end_line, end_col):
    """Build the JSON sub-object for a source-range, in 0-based coords
    with an exclusive end column (VSCode convention)."""
    return {
        'startLine': max(0, start_line - 1),
        'startCol':  max(0, start_col),
        'endLine':   max(0, end_line - 1),
        'endCol':    max(0, end_col),
    }


def _line_range(source_lines, line):
    """JSON range over source line ``line`` (1-based), from its first
    non-blank character to its end: for a warning about a block or a
    declaration, the line that opens it."""
    text = source_lines[line - 1] if 0 < line <= len(source_lines) else ''
    start = len(text) - len(text.lstrip())
    return _diag_range(line, start, line, max(len(text.rstrip()), start + 1))


def _run_diagnostics(input_file, define, show_traceback, no_geometry_lint):
    """Frontend + midware only, no codegen. Collect every
    GeLBException plus any warnings (via config.DIAGNOSTICS_WARNINGS)
    and emit a single JSON document to stdout.

    Exit code: 1 if any error was collected, 0 otherwise (warnings
    alone don't set the exit code). This lets the VSCode extension
    tell whether to block the preview commands.
    """
    import gelb.utils.config as _config
    _config.DIAGNOSTICS_MODE = True
    _config.DIAGNOSTICS_WARNINGS = []
    _config.GELB_FILE_NAME = input_file

    diagnostics = []

    from gelb.utils.error_utils import resolve_error_location
    from gelb.utils.exceptions import GeLBException

    try:
        compile_file(
            input_file,
            PipelineProfile.DIAGNOSTICS,
            PipelineOptions(
                defines=tuple(define),
                require_stencils=True,
                require_geometry=True,
                emit_warnings=True,
                geometry_lint=not no_geometry_lint,
            ),
        )
    except GeLBException as ex:
        diag = {
            'severity': 'error',
            'message': _strip_ansi(getattr(ex, 'error', None))
                       or _strip_ansi(str(ex))
                       or 'GeLB compile error',
            'hint': _strip_ansi(getattr(ex, 'hint', None)),
            'source': 'gelbc',
        }
        loc = resolve_error_location(ex)
        if loc is not None:
            diag['range'] = _diag_range(*loc)
        else:
            diag['range'] = _diag_range(1, 0, 1, 1)
        diagnostics.append(diag)
    except Exception as ex:
        # Any non-GeLB exception is an internal compiler bug; surface
        # it as a single file-level error so the user sees *something*
        # instead of an opaque process exit.
        msg = f"(internal) {type(ex).__name__}: {ex}"
        diagnostics.append({
            'severity': 'error',
            'message': msg,
            'hint': ('This is probably a compiler bug. Please report it'
                     ' with the .gelb file attached.'),
            'source': 'gelbc',
            'range': _diag_range(1, 0, 1, 1),
        })
        if show_traceback:
            import traceback
            traceback.print_exc(file=sys.stderr)

    # Merge collected midware warnings.  Each points at the line of the
    # block or declaration it is about; one that concerns no single
    # place in the source sits at the start of the file.
    with open(input_file, encoding='utf-8', errors='replace') as f:
        source_lines = f.read().splitlines()
    for msg, hint, line in _config.DIAGNOSTICS_WARNINGS:
        diagnostics.append({
            'severity': 'warning',
            'message': _strip_ansi(msg),
            'hint': _strip_ansi(hint),
            'source': 'gelbc',
            'range': (_line_range(source_lines, line) if line
                      else _diag_range(1, 0, 1, 1)),
        })

    json.dump({'diagnostics': diagnostics}, sys.stdout)
    sys.stdout.write('\n')
    sys.stdout.flush()
    exit_code = 1 if any(d['severity'] == 'error' for d in diagnostics) else 0
    _config.DIAGNOSTICS_MODE = False
    _config.DIAGNOSTICS_WARNINGS = []
    sys.exit(exit_code)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
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
    "--backend", "-b",
    type=click.Choice(
        ['cpu_fortran_serial',
         'cpu_highway',
         'gpu_cuda_cpp',
         ]
    ),
    default='cpu_highway',
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
@click.option(
    "--output", "-o",
    type=click.STRING,
    default=None,
    help="Output file for generated code (default: <input_basename>.f90)"
)
@click.option(
    "--num-timesteps", "-n",
    type=click.INT,
    default=1,
    help="Number of simulation time steps (default: 1)"
)
@click.option(
    "--output-mode", "-m",
    type=click.Choice(['netcdf', 'stdout']),
    default='netcdf',
    help=(
        "Gauge output mode: 'netcdf' writes .nc file; 'stdout' prints"
        " to terminal and currently requires --backend cpu_fortran_serial"
    )
)
@click.option(
    "--nc-output",
    type=click.STRING,
    default=None,
    help="NetCDF output filename embedded in generated code (default: <input_basename>.nc)"
)
@click.option(
    "--write-every", "-w",
    type=click.INT,
    default=1,
    help="Write gauge output every N timesteps (default: 1, i.e. every timestep)"
)
@click.option(
    "--stencils",
    is_flag=True,
    help="Print stencil analysis report and exit (no code generation)"
)
@click.option(
    "--seed", "-s",
    type=click.INT,
    default=None,
    help="Fixed PRNG seed for reproducible runs of programs that use "
         "random(). If omitted, the runtime seeds from the system clock."
)
@click.option(
    "-D", "--define",
    multiple=True,
    metavar="NAME=VALUE",
    help="Override a global constant (e.g. -D N=512 -D TAU=0.8)"
)
@click.option(
    "--show-mapping",
    is_flag=True,
    help="Print GeLB → Fortran identifier mapping and exit"
)
@click.option(
    "--cuda-block-size",
    type=click.INT,
    default=None,
    help=(
        "CUDA threads per block (gpu_cuda_cpp only).  When unset,"
        " uses the dimension-and-grid-shape-aware auto-default; when"
        " set, switches to a 1D-along-x layout (N,)/(N,1)/(N,1,1)."
    ),
)
@click.option(
    "--cuda-coarsening",
    type=click.INT,
    default=1,
    help=(
        "Thread coarsening factor for gpu_cuda_cpp (default: 1, no"
        " coarsening).  Each thread handles N cells along the"
        " outer-most spatial axis (y for 2D, z for 3D).  Workload-"
        " and hardware-dependent — gather per-anchor data via"
        " --cuda-coarsening N; the eventual auto-heuristic will pick"
        " defaults based on lattice dim + NC count.  See PMPP 4ed §8.4."
    )
)
@click.option(
    "--cuda-ldg",
    is_flag=True,
    help=(
        "Wrap stencil reads from g_<lname>_storage[g_<ln>_old][...]"
        " in __ldg(&...) for the gpu_cuda_cpp backend.  Routes"
        " reads through the read-only L1 cache (~32 KB per SM on"
        " sm_89).  Modest expected win on memory-bound kernels;"
        " neutral or marginal on cache-friendly ones."
    )
)
@click.option(
    "--cuda-stwt",
    is_flag=True,
    help=(
        "Use __stwt() (write-streaming, no L1 cache fill) for the"
        " gpu_cuda_cpp backend's streaming-step writes to"
        " g_<lname>_storage[g_<ln>_new].  Mirrors cpu_highway's"
        " nontemporal-store path; helps when the next-timestep read"
        " pattern doesn't re-touch the same cells."
    )
)
@click.option(
    "--cuda-tiled",
    is_flag=True,
    help=(
        "Enable PMPP §8.3 shared-memory tiling for the gpu_cuda_cpp"
        " backend's dynamic kernel.  Each block cooperatively loads"
        " its (block + halo) tile of all DFs into shared memory"
        " once per timestep, then stencil reads come from shared."
        "  Current scope: 2D, all-periodic, single dense NC, single"
        " lattice.  Nsight Compute profiling on an sm_89 RTX 4080"
        " Laptop GPU (2026-05-07) shows tiling"
        " is **NEUTRAL on TGV-2D BGK** (kernel is compute-bound at"
        " default: SM Compute 81 %, DRAM 29 %, L2 hit 58 % already"
        " absorbs stencil reuse) and **regresses TGV-3D BGK 1.74×**"
        " (91 KB/block collapses occupancy 64 % → 16 %).  Flag is"
        " kept opt-in for experimentation on hardware with smaller"
        " L2 / different SM topology; default is OFF."
    )
)
@click.option(
    "--cuda-graphs/--no-cuda-graphs",
    default=True,
    help=(
        "Capture the per-iteration halo + dyn + swap kernel"
        " sequence into a ``cudaGraph_t`` once and replay it via"
        " ``cudaGraphLaunch`` each timestep.  gpu_cuda_cpp only."
        "  Reduces driver-side launch overhead from N kernels per"
        " step to one graph dispatch.  **Default ON** as of"
        " 2026-05-08 (+3 % to +66 % Real MLUPS across every 2D"
        " anchor measured in the tuning sweep, no regressions)."
        "  Programs using ``random()`` or with no dynamic NC fall"
        " back to no-graphs automatically with a one-line stderr"
        " note.  Pass ``--no-cuda-graphs`` to opt out."
    )
)
@click.option(
    "--diagnostics-json",
    is_flag=True,
    help=(
        "Run frontend + midware only (no codegen) and emit all collected"
        " errors and warnings as a JSON document on stdout. Exit 0 if there"
        " are no errors, 1 otherwise. Used by the VSCode extension to"
        " populate the Problems panel."
    )
)
@click.option(
    "--no-geometry-lint",
    is_flag=True,
    help=(
        "Disable default geometry-lint warnings. Geometry resolution still"
        " runs when required for diagnostics or backend code generation."
    )
)
@click.option(
    "--no-collinearity-rewrite",
    is_flag=True,
    help=(
        "Accepted for compatibility; the BGK collinearity rewrite"
        " (`x - C*(x - y)` to `(1-C)*x + C*y`) is OFF by default since"
        " it re-associates and has no general error bound (numerical"
        " semantics chapter). It returns under --associative-math in 1.1."
    )
)
@click.option(
    "--strict-fp",
    is_flag=True,
    help=(
        "Strict floating point (user manual, numerical semantics chapter): no fused"
        " multiply-add in GeLB-visible arithmetic or in the runtime"
        " helpers. The generated C++ defines GELB_STRICT_FP before the"
        " runtime header; gelb-run adds -ffp-contract=off (CPU) and"
        " -fmad=false (CUDA). Excludes -F/--fast-math."
    )
)
@click.option(
    "--no-slice-simplify",
    is_flag=True,
    help=(
        "Disable the slice-DF expansion + CSE midware pass."
        " Default: ON. Expands Q-element-array statements (e.g. the BGK feq"
        " polynomial) over each direction i ∈ [0,Q), substitutes literal-"
        "indexed array constants (EX[i], EY[i], W[i], …), applies only the"
        " identities that hold bit for bit (1·x, -1·x, x/1; a zero only"
        " where its sign cannot change) and shares identical ordered"
        " sub-expressions across the Q expressions."
        " Bit-exact against the unexpanded form, signed zeros included."
    )
)
@click.option(
    "--no-scalar-cse",
    is_flag=True,
    help=(
        "Disable the scalar-block CSE midware pass."
        " Default: ON. For each block, shares identical ordered"
        " sub-expressions across consecutive scalar variable assignments"
        " as hoisted temporaries. Bit-exact against the unhoisted form."
    )
)
@click.option(
    "--poison-uninit",
    is_flag=True,
    help=(
        "Debugging aid: fill lattice allocations with NaN instead of"
        " zeros, so any read of a lattice cell that no initializer or"
        " update ever wrote surfaces as NaN in the gauge output instead"
        " of hiding behind a benign zero. Supported by all backends"
        " (the Fortran reference emits an explicit ieee_quiet_nan array"
        " fill). Masked cells are unaffected — they hold zero DFs by"
        " language guarantee — so a correct program produces output"
        " bitwise identical to a normal run; any difference indicates"
        " a read of genuinely undefined lattice memory."
    )
)
@click.option(
    "--storage-layout",
    type=click.Choice(["auto", "soa", "aos", "cbt"]),
    default="auto",
    help=(
        "Lattice storage layout for the cpu_highway backend."
        " 'auto' (default): ISA- and dimension-aware rule fitted to"
        " cross-machine measurements (May 2026). 1D → SoA;"
        " 2D and 3D → CBT on AVX-512 hosts, SoA otherwise"
        " (override the AVX-512 detection via the"
        " GELB_HAS_AVX512 env var when needed)."
        " 'soa': force SoA `[buf][df][...y][x]`."
        " 'aos': force AoS `[buf][...y][x][df]` — per-cell cache"
        " locality but disables across-cell SIMD (scalar inner loop)."
        " 'cbt': cell-block-tiled `[buf][...y][x_tile][df][x_within]`"
        " (x_within = 8 = AVX-512 lane count).  Combines per-cell DF"
        " locality with across-cell SIMD inside each tile."
        " Every layout gives bitwise identical output (numerical"
        " semantics chapter; tested across layouts and thread counts)."
        "  The cpu_fortran_serial backend ignores this flag."
    )
)
def cli(
        t, input_file, backend, visualize_ast, ast_output, ast_format,
        keep_dot, ast_stage, output, num_timesteps, output_mode, nc_output,
        write_every, stencils, seed, define, show_mapping, cuda_block_size,
        cuda_coarsening, cuda_ldg, cuda_stwt, cuda_tiled, cuda_graphs,
        diagnostics_json, no_geometry_lint, no_collinearity_rewrite,
        strict_fp, no_slice_simplify, no_scalar_cse, poison_uninit,
        storage_layout):
    """
    gelbc -- reference compiler (actually: "transpiler") for the GeLB DSL.

    This is the compiler-driver, which reads a "*.gelb" file and passes it
    through the various stages of the compiler.
    """

    if not t:  # disable the traceback by default
        sys.tracebacklimit = 0

    # Diagnostics mode: frontend + midware only, no codegen, errors &
    # warnings are collected and emitted as a single JSON document on
    # stdout. Called by the VSCode extension to populate the Problems
    # panel. See gelb/utils/config.DIAGNOSTICS_MODE docstring.
    if diagnostics_json:
        _run_diagnostics(
            input_file=input_file,
            define=define,
            show_traceback=t,
            no_geometry_lint=no_geometry_lint,
        )
        # _run_diagnostics always calls sys.exit; unreachable:
        return

    # Report the parsed metadata and capture requested AST stages.
    def report_and_capture_ast(ast, stage_name):
        """Report the parsed description and optionally capture the AST."""
        if stage_name == 'parsing' and not (stencils or show_mapping):
            description = ast.simulation_description
            if description is not None:
                click.echo(f"Simulation: {description.value}", err=True)
        if visualize_ast and ast_stage in [stage_name, 'all']:
            generate_ast_visualization(ast, input_file, ast_output, ast_format, keep_dot, stage_name)

    # The report modes return before the backend hand-off, so they
    # resolve the geometry here; normal codegen resolves it after the
    # output-mode check (resolve_geometry_for_compile), and both paths
    # run the same map-based validation.
    require_geometry = bool(stencils or show_mapping)

    compile_result = compile_file(
        input_file,
        PipelineProfile.CODEGEN,
        PipelineOptions(
            defines=tuple(define),
            capture_ast=report_and_capture_ast,
            # The rewrite is off by default, as it re-associates; the
            # flag can only keep it off.
            enable_collinearity_rewrite=False,
            enable_scalar_cse=not no_scalar_cse,
            enable_slice_simplify=not no_slice_simplify,
            require_stencils=True,
            require_geometry=require_geometry,
            emit_warnings=True,
            geometry_lint=not no_geometry_lint,
            strict_fp=strict_fp,
        ),
    )
    ast = compile_result.ast
    stencil_result = compile_result.stencils
    resolved_geometry = compile_result.geometry

    if stencils:
        click.echo(stencil_result.format_report())
        return

    if show_mapping:
        _print_identifier_mapping(ast)
        return

    # Stage 3 :: BackEnd

    if output_mode == 'stdout' and backend != 'cpu_fortran_serial':
        raise click.ClickException(
            "--output-mode stdout is currently implemented only for "
            "the cpu_fortran_serial backend. Use "
            "--backend cpu_fortran_serial, or keep --output-mode netcdf "
            f"with backend {backend}."
        )

    nc_filename = nc_output or \
        os.path.splitext(os.path.basename(input_file))[0] + '.nc'
    resolved_geometry, _ = resolve_geometry_for_compile(
        ast,
        stencil_result,
        emit_warnings=True,
        geometry_lint=not no_geometry_lint,
    )
    backend_context = build_backend_context(
        compile_result,
        geometry=resolved_geometry,
    )

    if backend == 'cpu_fortran_serial':
        from gelb.backends.stage3_backend_cpu_fortran_serial import generate_fortran
        code = generate_fortran(ast, num_timesteps=num_timesteps,
                                output_mode=output_mode,
                                output_filename=nc_filename,
                                write_every=write_every,
                                random_seed=seed,
                                source_file=input_file,
                                backend_context=backend_context,
                                poison_uninit=poison_uninit,
                                strict_fp=strict_fp)

        if output is None:
            output = os.path.splitext(input_file)[0] + '.f90'

        with open(output, 'w') as f:
            f.write(code)
        click.echo(f"Generated: {output}")

    elif backend == 'cpu_highway':
        from gelb.backends.stage3_backend_cpu_highway import generate_cpu_highway
        code = generate_cpu_highway(ast, num_timesteps=num_timesteps,
                                    output_filename=nc_filename,
                                    write_every=write_every,
                                    use_openmp=True,
                                    random_seed=seed,
                                    source_file=input_file,
                                    storage_layout=storage_layout,
                                    backend_context=backend_context,
                                    poison_uninit=poison_uninit,
                                    strict_fp=strict_fp)

        if output is None:
            output = os.path.splitext(input_file)[0] + '.cpp'

        with open(output, 'w') as f:
            f.write(code)
        click.echo(f"Generated: {output}")

    elif backend == 'gpu_cuda_cpp':
        from gelb.backends.stage3_backend_gpu_cuda_cpp import generate_cuda_cpp
        code = generate_cuda_cpp(ast, num_timesteps=num_timesteps,
                                 output_filename=nc_filename,
                                 write_every=write_every,
                                 random_seed=seed,
                                 source_file=input_file,
                                 cuda_block_size=cuda_block_size,
                                 cuda_coarsening=cuda_coarsening,
                                 cuda_ldg=cuda_ldg,
                                 cuda_stwt=cuda_stwt,
                                 cuda_tiled=cuda_tiled,
                                 cuda_graphs=cuda_graphs,
                                 backend_context=backend_context,
                                 poison_uninit=poison_uninit,
                                 strict_fp=strict_fp)

        if output is None:
            output = os.path.splitext(input_file)[0] + '.cu'

        with open(output, 'w') as f:
            f.write(code)
        click.echo(f"Generated: {output}")


if __name__ == "__main__":
    cli()
