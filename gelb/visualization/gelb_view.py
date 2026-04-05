"""
gelb-view -- Visualization tool for GeLB simulation output.

Subcommand structure:
  gelb-view data <file.nc> [options]   -- visualize simulation output (default)
  gelb-view algo <file.gelb> [options] -- visualize algorithm stencils

When invoked without a subcommand and without --no-gui, launches the
interactive GUI.  Pass --no-gui or -o to use headless matplotlib.
"""

import sys
import click

from gelb.visualization.data_viewer import (
    GeLBDataset,
    plot_1d,
    plot_2d,
    plot_3d,
)
from gelb.visualization.algo_viewer import compile_to_stencils, plot_stencils


def _launch_gui(files=None):
    """Launch the PySide6 GUI, with optional files pre-loaded."""
    try:
        from gelb.visualization.gui.app import launch_gui
    except ImportError:
        # Note on the quotes: zsh globs unquoted `[...]`, so
        # `pip install gelb[gui]` fails with "no matches found".
        # Single-quoting keeps the command runnable in every shell.
        click.echo(
            'GUI requires PySide6. Install it with one of:\n'
            '  uv sync --all-extras              # if you use uv\n'
            "  pip install 'gelb[gui]'            # note the quotes "
            '(zsh globs the brackets without them)',
            err=True,
        )
        sys.exit(1)
    launch_gui(files)


class DefaultGroup(click.Group):
    """Click group that auto-routes filename arguments to the right subcommand.

    Routing rules:
      - ``foo.gelb``  -> ``source`` subcommand
      - ``foo.nc``    -> ``data`` subcommand (also any other extension)
    """

    def parse_args(self, ctx, args):
        if args and args[0] not in self.commands:
            first = args[0]
            if first.endswith('.gelb'):
                args = ['source'] + args
            else:
                args = ['data'] + args
        return super().parse_args(ctx, args)


@click.group(cls=DefaultGroup, invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """GeLB visualization tool."""
    if ctx.invoked_subcommand is None:
        # No arguments at all -> launch empty GUI
        _launch_gui()


@cli.command()
@click.argument('ncfile', type=click.Path(exists=True))
@click.option('--var', '-v', multiple=True,
              help='Variable(s) to plot (default: all)')
@click.option('--timestep', '-t', type=int, default=-1,
              help='Timestep to visualize (default: last)')
@click.option('--animate', is_flag=True,
              help='Create animation (2D/3D only)')
@click.option('--slice-axis', type=click.Choice(['x', 'y', 'z']),
              default='z', help='Axis for 3D slicing')
@click.option('--slice-index', type=int, default=None,
              help='Index along slice axis (default: midplane)')
@click.option('--output', '-o', type=click.STRING, default=None,
              help='Save plot to file instead of displaying')
@click.option('--no-gui', is_flag=True,
              help='Use headless matplotlib (no interactive GUI)')
@click.option('--list-vars', is_flag=True,
              help='List available variables and exit')
def data(ncfile, var, timestep, animate, slice_axis, slice_index,
         output, no_gui, list_vars):
    """Visualize simulation output from a NetCDF file."""
    # Text-only queries: always headless
    if list_vars:
        with GeLBDataset(ncfile) as dataset:
            click.echo(dataset.summary())
        return

    # Headless mode: save to file or use matplotlib's plt.show()
    if output or no_gui:
        with GeLBDataset(ncfile) as dataset:
            variables = list(var) if var else None

            if dataset.ndim == 1:
                plot_1d(dataset, variables, output)
            elif dataset.ndim == 2:
                plot_2d(dataset, variables, timestep, output, animate)
            elif dataset.ndim == 3:
                plot_3d(dataset, variables, timestep, slice_axis,
                        slice_index, output)
            else:
                click.echo(
                    f"Unsupported dimensionality: {dataset.ndim}D", err=True)
                sys.exit(1)
        return

    # Default: launch GUI with file pre-loaded
    _launch_gui([ncfile])


@cli.command()
@click.argument('gelbfile', type=click.Path(exists=True))
@click.option('--block', '-b', multiple=True,
              help='Block(s) to show (default: all)')
@click.option('--output', '-o', type=click.STRING, default=None,
              help='Save plot to file instead of displaying')
@click.option('--no-gui', is_flag=True,
              help='Use headless matplotlib (no interactive GUI)')
def algo(gelbfile, block, output, no_gui):
    """Visualize algorithm stencils from a .gelb source file."""
    stencils = compile_to_stencils(gelbfile)
    block_names = list(block) if block else None

    # Headless mode (or when GUI is not yet implemented)
    if output or no_gui:
        plot_stencils(stencils, block_names, output)
        return

    # Try to launch interactive GUI
    try:
        from gelb.visualization.gui.algo_window import launch_algo_gui
        launch_algo_gui(stencils, block_names)
    except ImportError:
        # Fall back to headless matplotlib
        plot_stencils(stencils, block_names)


@cli.command()
@click.argument('gelbfile', type=click.Path(exists=True))
@click.option('--output', '-o', type=click.STRING, default=None,
              help='Save plot to file instead of displaying')
@click.option('--no-gui', is_flag=True,
              help='Use headless matplotlib (no interactive GUI)')
@click.option('--stats', is_flag=True,
              help='Print geometry stats (text table) and exit')
@click.option('--text', 'text_mode', is_flag=True,
              help='Print geometry as ASCII grid and exit')
@click.option('--export-npy', type=click.STRING, default=None,
              help='Export nc_map as .npy + sidecar .json metadata')
@click.option('--no-auto-zoom', is_flag=True,
              help='Disable auto-zoom inset for sparse 2D features')
@click.option('--lint', is_flag=True,
              help='Run geometry-lint warnings and exit')
def geo(gelbfile, output, no_gui, stats, text_mode, export_npy,
        no_auto_zoom, lint):
    """Visualize geometry (node-class layout) from a .gelb source file."""
    from gelb.visualization.geo_viewer import (
        compile_to_geometry, plot_geometry,
        format_geometry_stats, format_geometry_ascii,
        export_geometry_npy,
    )
    geo_data = compile_to_geometry(gelbfile)

    if lint:
        from gelb.midware.geometry_lint import all_geometry_warnings
        from gelb.utils.output_to_terminal import warning_with_hint_to_term
        warnings = all_geometry_warnings(geo_data)
        if not warnings:
            click.echo("No geometry-lint warnings.")
            return
        for msg, hint, line in warnings:
            warning_with_hint_to_term(msg, hint, line)
        return
    if stats:
        click.echo(format_geometry_stats(geo_data))
        return
    if text_mode:
        click.echo(format_geometry_ascii(geo_data))
        return
    if export_npy:
        export_geometry_npy(geo_data, export_npy)
        click.echo(f"Saved nc_map to {export_npy} (+ sidecar .json)")
        return

    plot_geometry(geo_data, output=output, auto_zoom=not no_auto_zoom)


@cli.command()
@click.argument('gelbfile', type=click.Path(exists=True))
@click.option('--output', '-o', type=click.STRING, default=None,
              help='Save plot to file')
@click.option('--show', type=click.Choice(['geo', 'algo', 'both', 'combined']),
              default='both',
              help='Which view to render (default: both)')
@click.option('--cell', type=click.STRING, default=None,
              help='For combined mode: cell coordinate as "x,y"')
@click.option('--block', type=click.STRING, default=None,
              help='For combined mode: dynamic block name to use')
@click.option('--export-json', type=click.STRING, default=None,
              help='Export geometry+stencils as a single JSON document')
@click.option('--stats', is_flag=True,
              help='Print geometry stats and exit')
@click.option('--text', 'text_mode', is_flag=True,
              help='Print geometry as ASCII grid and exit')
@click.option('--lint', is_flag=True,
              help='Run geometry-lint warnings and exit')
def source(gelbfile, output, show, cell, block, export_json,
           stats, text_mode, lint):
    """Visualize compile-time program analysis (geometry + stencils)."""
    from gelb.visualization.source_viewer import (
        plot_program_analysis, export_program_analysis_json,
    )
    from gelb.midware.program_analysis import compile_to_program_analysis

    analysis = compile_to_program_analysis(gelbfile)

    if export_json:
        export_program_analysis_json(analysis, export_json)
        click.echo(f"Wrote {export_json}")
        return
    if lint:
        from gelb.midware.geometry_lint import all_geometry_warnings
        from gelb.utils.output_to_terminal import warning_with_hint_to_term
        warnings = all_geometry_warnings(
            analysis.geometry, analysis.stencils)
        if not warnings:
            click.echo("No geometry-lint warnings.")
            return
        for msg, hint, line in warnings:
            warning_with_hint_to_term(msg, hint, line)
        return
    if stats:
        from gelb.visualization.geo_viewer import format_geometry_stats
        click.echo(format_geometry_stats(analysis.geometry))
        return
    if text_mode:
        from gelb.visualization.geo_viewer import format_geometry_ascii
        click.echo(format_geometry_ascii(analysis.geometry))
        return

    parsed_cell = None
    if cell:
        parts = cell.split(',')
        if len(parts) != 2:
            raise click.UsageError("--cell expects 'x,y' (two ints)")
        parsed_cell = (int(parts[0]), int(parts[1]))

    plot_program_analysis(analysis, output=output, mode=show,
                          cell=parsed_cell, block=block)


if __name__ == "__main__":
    cli()
