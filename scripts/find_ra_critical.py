#!/usr/bin/env python3
"""Find the critical Rayleigh number for the Rayleigh-Benard MRT example.

Reproduces the Fortran reference Ra_cr_1 study
(``rb_{2,3}d/runs__Ra_cr_1/Pr_0_71__Ny_41__Gamma_2__MaxMach_0_1/Ra_{1685..1730}``)
using GeLB's CUDA Fortran (or CPU-OpenMP) backend.  For each Ra value,
this script compiles and runs the GeLB example at the Fortran-matching
grid (Gamma ~= 2.0158, Ny=41 fluid rows) via ``scripts/gelb-run``, then
classifies the late-time state of the vertical velocity field as
*decaying*, *growing*, or *inconclusive*.  The critical Rayleigh number
is bracketed between the largest decaying Ra and the smallest growing
Ra and compared to the theoretical value ``Ra_c ~= 1707.76``.

Usage
-----
    uv run python scripts/find_ra_critical.py                # 2D (default)
    uv run python scripts/find_ra_critical.py --dim 3        # 3D
    uv run python scripts/find_ra_critical.py --ra 1685 1700 1715 1730
    uv run python scripts/find_ra_critical.py --num-timesteps 3000000
    uv run python scripts/find_ra_critical.py --backend cpu

The script must be run from the GeLB project root so that
``./scripts/gelb-run`` and the example files resolve correctly.
"""

from __future__ import annotations

import argparse
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # only for the annotations below; rich is optional at runtime
    from rich.panel import Panel
    from rich.table import Table

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Per-dimension configuration.
_DIM_CONFIG = {
    2: dict(
        example_path='examples/lbm/2d/rayleigh_benard_2d_mrt.gelb',
        example_basename='rayleigh_benard_2d_mrt',
        default_ny=43, default_nx=83, default_nz=None,
        # Fortran rb_2d uses simTime=450 -> ~10M steps at NY=43.
        default_num_timesteps=10_000_000,
        default_write_every=20_000,
    ),
    3: dict(
        example_path='examples/lbm/3d/rayleigh_benard_3d_mrt.gelb',
        example_basename='rayleigh_benard_3d_mrt',
        default_ny=43, default_nx=83, default_nz=83,
        # Fortran rb_3d uses simTime=25 -> ~870K steps at NY=43.
        default_num_timesteps=870_000,
        default_write_every=1_740,
    ),
}

# Defaults that apply regardless of dimension.
DEFAULT_NY = 43
DEFAULT_NX = 83

# Detection thresholds on the L_inf norm of uY.  The gauge reports
# ``jy + alpha*G/2 * T`` (the post-first-half-force momentum), so a
# fully-relaxed stable simulation sits at a Ra-independent
# ``max|uY| ~= alpha*G*T_HOT`` "floor" (~= 8.0e-5 at NY=43, MaxMach=0.1)
# coming from the Strang-split bookkeeping.  A decaying run sits
# *at* that floor; a growing run climbs one to two decades above
# it.  The default thresholds are chosen to cleanly separate the
# two for the Fortran-matching ``NY=43`` grid and must be
# re-tuned if you change ``NY`` or ``MAX_MACH``.
DEFAULT_DECAY_THRESHOLD = 2e-4
DEFAULT_GROW_THRESHOLD = 5e-4

# Default Ra sweep: the four Fortran-matching Ra values that
# bracket the theoretical Ra_c ~= 1707.76 to within +/-8, plus wider
# sanity anchors.
DEFAULT_RA_VALUES = [1500.0, 1685.0, 1700.0, 1715.0, 1730.0, 1800.0, 2000.0]

# Default simulation horizon (~= Fortran simTime = 450 at these params).
DEFAULT_NUM_TIMESTEPS = 10_000_000
DEFAULT_WRITE_EVERY = 20_000  # -> 500 time slices per run

DEFAULT_SEED = 42


@dataclass
class RunResult:
    ra: float
    uy_inf_initial: float
    uy_inf_final: float
    classification: str  # 'decaying' / 'growing' / 'inconclusive'
    wall_time_s: float
    nc_path: str


# ---------------------------------------------------------------------------
# Per-Ra row state (mutable, drives the Rich table)
# ---------------------------------------------------------------------------

@dataclass
class RowState:
    """Live status for one Ra value in the sweep table."""
    ra: float
    phase: str = 'queued'       # queued / compiling / running / analyzing / done / error
    records: int = 0
    total_records: int = 0
    elapsed_s: float = 0.0
    wall_s: float = 0.0
    classification: str = ''
    uy_inf_final: float = float('nan')
    error: str = ''


# ---------------------------------------------------------------------------
# Rich TUI
# ---------------------------------------------------------------------------

def _format_time(seconds: float) -> str:
    """Format seconds as H:MM:SS or M:SS."""
    s = int(seconds)
    if s < 3600:
        return f'{s // 60}:{s % 60:02d}'
    return f'{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}'


def _class_style(cls: str) -> str:
    """Rich markup style for a classification label."""
    if cls == 'decaying':
        return '[cyan]decaying[/cyan]'
    if cls == 'growing':
        return '[red]growing[/red]'
    if cls == 'inconclusive':
        return '[yellow]inconclusive[/yellow]'
    return cls


def _build_table(rows: list[RowState], header: str) -> 'Table':
    """Build a Rich Table from the current row states."""
    from rich.table import Table
    from rich.progress_bar import ProgressBar

    t = Table(title=header, title_style='bold', expand=False,
              border_style='dim')
    t.add_column('#', justify='right', style='dim', no_wrap=True, min_width=2)
    t.add_column('Ra', justify='right', no_wrap=True, min_width=6)
    t.add_column('Status', no_wrap=True, min_width=9)
    t.add_column('Progress', no_wrap=True, min_width=22)
    t.add_column('Wall', justify='right', no_wrap=True, min_width=7)
    t.add_column('uY_inf', justify='right', no_wrap=True, min_width=9)
    t.add_column('Class', no_wrap=True, min_width=13)

    for i, r in enumerate(rows, 1):
        # Progress column
        BAR_W = 12
        if r.phase in ('running', 'analyzing') and r.total_records > 0:
            frac = min(r.records / r.total_records, 1.0)
            pct = f'{100 * frac:4.0f}%'
            filled = int(BAR_W * frac)
            bar = '█' * filled + '░' * (BAR_W - filled)
            if frac > 0.01 and frac < 1.0:
                eta = r.elapsed_s / frac * (1 - frac)
                eta_str = f'~{_format_time(eta)}'
            else:
                eta_str = ''
            progress = f'{bar} {pct} {eta_str}'
        elif r.phase == 'done':
            progress = '█' * BAR_W + ' 100%'
        elif r.phase == 'compiling':
            progress = '[dim]compiling…[/dim]'
        elif r.phase == 'error':
            progress = f'[red]{r.error[:26]}[/red]'
        else:
            progress = '[dim]—[/dim]'

        # Status style
        if r.phase == 'running':
            status = '[bold green]running[/bold green]'
        elif r.phase == 'compiling':
            status = '[yellow]compiling[/yellow]'
        elif r.phase == 'analyzing':
            status = '[magenta]analyzing[/magenta]'
        elif r.phase == 'done':
            status = '[dim]done[/dim]'
        elif r.phase == 'error':
            status = '[red]error[/red]'
        else:
            status = '[dim]queued[/dim]'

        # Elapsed
        elapsed = _format_time(r.wall_s) if r.wall_s > 0 else (
            _format_time(r.elapsed_s) if r.elapsed_s > 0 else '')

        # uY and class
        uy_str = f'{r.uy_inf_final:.2e}' if not math.isnan(r.uy_inf_final) else ''
        cls_str = _class_style(r.classification) if r.classification else ''

        t.add_row(str(i), f'{r.ra:g}', status, progress, elapsed,
                  uy_str, cls_str)

    return t


def _build_summary_panel(rows: list[RowState]) -> 'Panel':
    """Build a summary panel with the bracket result (shown after sweep)."""
    from rich.panel import Panel
    from rich.text import Text

    decaying = [r for r in rows if r.classification == 'decaying']
    growing = [r for r in rows if r.classification == 'growing']
    done = [r for r in rows if r.phase == 'done']
    errors = [r for r in rows if r.phase == 'error']

    lines: list[str] = []
    lines.append(f'Completed: {len(done)}/{len(rows)}')
    if errors:
        lines.append(f'Errors: {len(errors)}')

    if decaying and growing:
        lo = max(r.ra for r in decaying)
        hi = min(r.ra for r in growing)
        if lo < hi:
            mid = 0.5 * (lo + hi)
            theoretical = 1707.76
            rel_err = abs(mid - theoretical) / theoretical * 100.0
            lines.append('')
            lines.append(f'Bracket:    Ra_c ∈ ({lo:g}, {hi:g})')
            lines.append(f'Midpoint:   Ra_c ≈ {mid:g}')
            lines.append(f'Theoretical: Ra_c ≈ {theoretical}  (Shan 1997)')
            lines.append(f'Rel. error: {rel_err:.2f}%')
        else:
            lines.append('')
            lines.append(f'⚠ Inverted bracket: decaying up to {lo}, '
                         f'growing from {hi}')
    elif done:
        lines.append('')
        lines.append('⚠ No clean bracket — add more Ra values or '
                     'extend --num-timesteps')

    total_wall = sum(r.wall_s for r in rows if r.wall_s > 0)
    if total_wall > 0:
        lines.append(f'\nTotal wall time: {_format_time(total_wall)}')

    return Panel('\n'.join(lines), title='Ra_c sweep result',
                 border_style='green' if (decaying and growing) else 'yellow')


def _get_nc_record_count(nc_path: str) -> int:
    """Read the current number of time records from a NetCDF file.

    Returns -1 if the file cannot be read (locked, missing, etc.).
    """
    try:
        import netCDF4 as nc
        ds = nc.Dataset(nc_path, 'r')
        try:
            n = len(ds.dimensions['time'])
        finally:
            ds.close()
        return n
    except Exception:
        return -1


def _estimate_records_from_size(nc_path: str,
                                bytes_per_record: float) -> int:
    """Estimate record count from file size when NetCDF read fails."""
    try:
        return int(os.path.getsize(nc_path) / bytes_per_record)
    except OSError:
        return 0


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------

def pick_backend(requested: str) -> str:
    """Map ``--backend {auto,gpu,cpu}`` to a gelb-run backend name.

    ``auto`` always targets the CUDA backend.  If the CUDA toolchain
    is unavailable, gelb-run reports a clear error on the first run
    and the sweep aborts.  Use ``--backend cpu`` to force the
    CPU-OpenMP path.
    """
    if requested == 'cpu':
        return 'cpu_fortran_serial'
    return 'gpu_cuda_cpp'


# ---------------------------------------------------------------------------
# Single-Ra runner
# ---------------------------------------------------------------------------

def run_one(ra: float, backend: str, ny: int, nx: int,
            num_timesteps: int, write_every: int, seed: int,
            out_dir: str, verbose: bool,
            example_path: str, example_basename: str,
            nz: int | None = None,
            extra_defines: list[str] | None = None,
            row: RowState | None = None,
            on_progress: 'Callable[[], None] | None' = None) -> RunResult:
    """Compile + run the example at one Ra value and return timing +
    NetCDF path.  The .nc file lands at ``out_dir/rb_<ra>.nc``.

    If *row* is supplied (Rich TUI mode), the function updates the
    RowState in-place while the simulation runs so that the Live
    display can reflect real-time progress.  *on_progress* is called
    after each poll cycle to trigger a display refresh.
    """
    os.makedirs(out_dir, exist_ok=True)
    dst_nc = os.path.join(out_dir, f'rb_ra_{ra:g}.nc')

    total_records = num_timesteps // write_every + 1

    cmd = [
        './scripts/gelb-run',
        '-b', backend,
        '-n', str(num_timesteps),
        '-w', str(write_every),
        '-s', str(seed),
        '-D', f'NY={ny}',
        '-D', f'NX={nx}',
        '-D', f'RA={ra}',
    ]
    if nz is not None:
        cmd.extend(['-D', f'NZ={nz}'])
    for d in (extra_defines or []):
        cmd.extend(['-D', d])
    cmd.append(example_path)

    if row:
        row.phase = 'compiling'
        row.total_records = total_records

    # Remove any stale NC file at the expected output path -- a leftover
    # from a previous (possibly killed) run will (a) mislead our NC-record
    # polling on the first poll cycle, and (b) trip "NetCDF Permission
    # denied" errors if an orphaned process still holds a write lock on it.
    nc_path = os.path.join(REPO_ROOT, f'{example_basename}.nc')
    if os.path.exists(nc_path):
        try:
            os.remove(nc_path)
        except OSError:
            pass

    t0 = time.monotonic()
    if not row:
        print(f'[Ra={ra:g}] launching gelb-run ({backend}) ...', flush=True)

    # Capture stderr into a temp file (NOT a PIPE). gelb-run pipes a
    # continuous progress bar to stderr via progress_monitor.py; the
    # default 64 KB PIPE buffer fills within seconds of a long run and
    # the child blocks on write(2), causing an apparent hang with no GPU
    # activity. A temp file has no such limit.
    stderr_file = tempfile.TemporaryFile(mode='w+')

    # start_new_session=True puts the child in its own process group, so
    # if we need to kill it on error or ^C we can tear down the entire
    # group (gelb-run -> nvcc -> Fortran binary -> progress_monitor).
    proc = subprocess.Popen(
        cmd, cwd=REPO_ROOT,
        stdout=None if verbose else subprocess.DEVNULL,
        stderr=None if verbose else stderr_file,
        text=True,
        start_new_session=True,
    )

    bytes_per_record: float | None = None
    poll_interval = 1.0

    try:
        while proc.poll() is None:
            elapsed = time.monotonic() - t0
            if row:
                row.elapsed_s = elapsed

            if os.path.exists(nc_path):
                if row and row.phase == 'compiling':
                    row.phase = 'running'

                count = _get_nc_record_count(nc_path)
                if count > 1 and bytes_per_record is None:
                    try:
                        bytes_per_record = os.path.getsize(nc_path) / count
                    except OSError:
                        pass
                if count < 0 and bytes_per_record:
                    count = _estimate_records_from_size(nc_path,
                                                        bytes_per_record)
                if row and count > 0:
                    row.records = count

            if on_progress:
                on_progress()

            time.sleep(poll_interval)
    except BaseException:
        # On ^C or exception, tear down the entire child process group so
        # we don't leave an orphan Fortran binary pinning the GPU + NC file.
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass
        raise

    wall = time.monotonic() - t0
    stderr_file.seek(0)
    stderr_text = stderr_file.read()
    stderr_file.close()

    if proc.returncode != 0:
        if row:
            row.phase = 'error'
            row.error = 'gelb-run failed'
            row.wall_s = wall
        raise RuntimeError(
            f'gelb-run failed at Ra={ra}:\n{stderr_text[-2000:]}'
        )

    # gelb-run writes <basename>.nc into CWD (= REPO_ROOT).
    src_nc = nc_path
    if not os.path.exists(src_nc):
        if row:
            row.phase = 'error'
            row.error = 'NC file missing'
            row.wall_s = wall
        raise RuntimeError(
            f'expected NetCDF output not found at {src_nc} for Ra={ra}'
        )

    if row:
        row.phase = 'analyzing'
        row.records = total_records

    shutil.move(src_nc, dst_nc)

    # Load uY and compute the L_inf-norm time series.
    import netCDF4
    ds = netCDF4.Dataset(dst_nc, 'r')
    uY = np.asarray(ds.variables['uY'][:])
    ds.close()
    # uY has NaNs on wall rows; nanmax collapses all spatial dims.
    spatial_axes = tuple(range(1, uY.ndim))
    uy_series = np.nanmax(np.abs(uY), axis=spatial_axes)

    uy_initial = float(uy_series[0]) if uy_series.size > 0 else float('nan')
    uy_final = float(uy_series[-1]) if uy_series.size > 0 else float('nan')

    if row:
        row.wall_s = wall
        row.uy_inf_final = uy_final

    return RunResult(
        ra=ra, uy_inf_initial=uy_initial, uy_inf_final=uy_final,
        classification='', wall_time_s=wall, nc_path=dst_nc,
    )


def classify(result: RunResult, decay_thr: float, grow_thr: float) -> str:
    """Return one of ``'decaying'`` / ``'growing'`` / ``'inconclusive'``
    based on the final uY_inf amplitude.
    """
    if result.uy_inf_final < decay_thr:
        return 'decaying'
    if result.uy_inf_final > grow_thr:
        return 'growing'
    return 'inconclusive'


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _run_sweep_plain(args, backend, cfg, ny, nx, nz,
                     num_timesteps, write_every, out_dir) -> int:
    """Original plain-text sweep loop (fallback when --no-tui)."""
    example_path = cfg['example_path']
    example_basename = cfg['example_basename']

    print(f'Dimension: {args.dim}D')
    print(f'Backend: {backend}')
    grid_str = f'NY={ny}  NX={nx}'
    if nz is not None:
        grid_str += f'  NZ={nz}'
    print(f'Grid: {grid_str}  '
          f'(fluid rows = {ny - 2}, Γ ≈ {nx / (ny - 2):.4f})')
    print(f'Timesteps per run: {num_timesteps:,} '
          f'(write-every {write_every:,})')
    print(f'Ra values: {[f"{r:g}" for r in args.ra]}')
    print()

    results: list[RunResult] = []
    for ra in args.ra:
        try:
            r = run_one(ra, backend, ny, nx,
                        num_timesteps, write_every,
                        args.seed, out_dir, args.verbose,
                        example_path=example_path,
                        example_basename=example_basename,
                        nz=nz,
                        extra_defines=args.define)
        except Exception as exc:
            print(f'[Ra={ra:g}] ERROR: {exc}', file=sys.stderr)
            continue
        r.classification = classify(r, args.decay_threshold,
                                    args.grow_threshold)
        results.append(r)
        print(f'[Ra={ra:g}] wall={r.wall_time_s:.1f}s  '
              f'uY_inf(0)={r.uy_inf_initial:.2e}  '
              f'uY_inf(end)={r.uy_inf_final:.2e}  '
              f'→ {r.classification}')

    return _print_summary_plain(results)


def _print_summary_plain(results: list[RunResult]) -> int:
    """Print final results table and bracket (plain text)."""
    print()
    print('=' * 72)
    print(f'{"Ra":>10}  {"uY_inf(0)":>12}  {"uY_inf(end)":>12}  '
          f'{"class":>13}  {"wall(s)":>8}')
    print('-' * 72)
    for r in results:
        print(f'{r.ra:>10g}  {r.uy_inf_initial:>12.3e}  '
              f'{r.uy_inf_final:>12.3e}  {r.classification:>13}  '
              f'{r.wall_time_s:>8.1f}')
    print('=' * 72)

    decaying = [r for r in results if r.classification == 'decaying']
    growing = [r for r in results if r.classification == 'growing']
    if decaying and growing:
        lo = max(r.ra for r in decaying)
        hi = min(r.ra for r in growing)
        if lo < hi:
            mid = 0.5 * (lo + hi)
            theoretical = 1707.76
            rel_err = abs(mid - theoretical) / theoretical * 100.0
            print()
            print(f'Bracket: Ra_c ∈ ({lo:g}, {hi:g})')
            print(f'Midpoint estimate:  Ra_c ≈ {mid:g}')
            print(f'Theoretical value:  Ra_c ≈ {theoretical}  '
                  f'(Shan 1997, rigid-rigid walls)')
            print(f'Relative error:     {rel_err:.2f}%')
            return 0
        else:
            print()
            print(f'[warn] inverted bracket: decaying up to {lo}, '
                  f'growing from {hi} — classification is inconsistent.')
            return 1
    else:
        print()
        print('[warn] no clean bracket found. '
              'Add more Ra values or extend --num-timesteps.')
        return 1


def _run_sweep_rich(args, backend, cfg, ny, nx, nz,
                    num_timesteps, write_every, out_dir) -> int:
    """Rich Live TUI sweep loop."""
    from rich.console import Console
    from rich.live import Live
    from rich.console import Group

    example_path = cfg['example_path']
    example_basename = cfg['example_basename']

    console = Console()

    grid_str = f'NY={ny}  NX={nx}'
    if nz is not None:
        grid_str += f'  NZ={nz}'
    header = (f'{args.dim}D Ra_c sweep — {backend}\n'
              f'{grid_str}  (fluid rows={ny-2}, '
              f'Γ≈{nx/(ny-2):.4f})  '
              f'{num_timesteps:,} steps/run')

    rows = [RowState(ra=ra) for ra in args.ra]
    results: list[RunResult] = []

    with Live(_build_table(rows, header), console=console,
              refresh_per_second=2, transient=True) as live:

        def _refresh():
            live.update(_build_table(rows, header))

        for i, ra in enumerate(args.ra):
            row = rows[i]
            try:
                r = run_one(ra, backend, ny, nx,
                            num_timesteps, write_every,
                            args.seed, out_dir, False,
                            example_path=example_path,
                            example_basename=example_basename,
                            nz=nz,
                            extra_defines=args.define,
                            row=row,
                            on_progress=_refresh)
            except Exception as exc:
                row.phase = 'error'
                row.error = str(exc)[:50]
                live.update(_build_table(rows, header))
                continue

            r.classification = classify(r, args.decay_threshold,
                                        args.grow_threshold)
            results.append(r)
            row.phase = 'done'
            row.classification = r.classification
            row.uy_inf_final = r.uy_inf_final
            row.wall_s = r.wall_time_s
            live.update(_build_table(rows, header))

    # Print final static table + summary panel.
    # Mark all rows final for the static render.
    final_table = _build_table(rows, header)
    summary = _build_summary_panel(rows)
    console.print(final_table)
    console.print(summary)

    # Return code
    decaying = [r for r in results if r.classification == 'decaying']
    growing = [r for r in results if r.classification == 'growing']
    if decaying and growing:
        lo = max(r.ra for r in decaying)
        hi = min(r.ra for r in growing)
        return 0 if lo < hi else 1
    return 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dim', type=int, choices=(2, 3), default=2,
                        help='Spatial dimension — 2 (default) or 3')
    parser.add_argument('--ra', type=float, nargs='+', default=DEFAULT_RA_VALUES,
                        help='Ra values to sweep (default: %(default)s)')
    parser.add_argument('--ny', type=int, default=None,
                        help='Grid rows including walls (default: 43)')
    parser.add_argument('--nx', type=int, default=None,
                        help='Grid columns (default: 83)')
    parser.add_argument('--nz', type=int, default=None,
                        help='Grid depth for 3D (default: 83)')
    parser.add_argument('--num-timesteps', type=int, default=None,
                        help='LBM steps per run (default: dim-dependent)')
    parser.add_argument('--write-every', type=int, default=None,
                        help='Gauge output stride (default: dim-dependent)')
    parser.add_argument('--seed', type=int, default=DEFAULT_SEED,
                        help='PRNG seed (default: %(default)s)')
    parser.add_argument('--backend', choices=('auto', 'gpu', 'cpu'),
                        default='auto',
                        help='Backend selector (default: %(default)s)')
    parser.add_argument('--decay-threshold', type=float,
                        default=DEFAULT_DECAY_THRESHOLD,
                        help='uY_inf below this → decaying (default: %(default)s)')
    parser.add_argument('--grow-threshold', type=float,
                        default=DEFAULT_GROW_THRESHOLD,
                        help='uY_inf above this → growing (default: %(default)s)')
    parser.add_argument('--out-dir', default=None,
                        help='Directory for NetCDF outputs '
                             '(default: rb_sweep_results_{dim}d)')
    parser.add_argument('-D', '--define', action='append', default=[],
                        metavar='NAME=VALUE',
                        help='Extra global constant override forwarded '
                             'to gelb-run (repeatable)')
    parser.add_argument('--verbose', action='store_true',
                        help='Stream gelb-run stdout/stderr live')
    parser.add_argument('--no-tui', action='store_true',
                        help='Disable Rich TUI — use plain text output')
    args = parser.parse_args(argv)

    cfg = dict(_DIM_CONFIG[args.dim])
    ny = args.ny or cfg['default_ny']
    nx = args.nx or cfg['default_nx']
    nz = args.nz or cfg['default_nz']  # None for 2D
    num_timesteps = args.num_timesteps or cfg['default_num_timesteps']
    write_every = args.write_every or cfg['default_write_every']
    out_dir_name = args.out_dir or f'rb_sweep_results_{args.dim}d'
    out_dir = os.path.abspath(out_dir_name)
    backend = pick_backend(args.backend)

    use_tui = not args.no_tui and not args.verbose
    if use_tui:
        try:
            import rich  # noqa: F401
        except ImportError:
            use_tui = False

    if use_tui:
        return _run_sweep_rich(args, backend, cfg, ny, nx, nz,
                               num_timesteps, write_every, out_dir)
    else:
        return _run_sweep_plain(args, backend, cfg, ny, nx, nz,
                                num_timesteps, write_every, out_dir)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
