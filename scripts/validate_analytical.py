#!/usr/bin/env python3
"""
Analytical validation of GeLB-generated LBM simulations.

Runs Poiseuille flow and Taylor-Green vortex decay at multiple grid
resolutions, computes L2 error norms against known analytical solutions,
and produces convergence plots for the SoftwareX paper.

Usage (from the gelb/ project root):
    uv run python scripts/validate_analytical.py
    uv run python scripts/validate_analytical.py --cases poiseuille
    uv run python scripts/validate_analytical.py --cases taylor_green_bgk
    uv run python scripts/validate_analytical.py -o validation.png
    uv run python scripts/validate_analytical.py --backend cpu_highway

    # Ra_cr sweeps (not included in default -- expensive)
    uv run python scripts/validate_analytical.py --cases ra_critical_2d
    uv run python scripts/validate_analytical.py --cases ra_critical_3d
    uv run python scripts/validate_analytical.py --cases ra_critical_2d ra_critical_3d

Requires: matplotlib, netCDF4, numpy, and the toolchain for the
selected backend: nvcc + NetCDF-C (gpu_cuda_cpp, default),
g++ + OpenMP + NetCDF-C (cpu_highway), or gfortran +
NetCDF-Fortran (cpu_fortran_serial).
"""

import argparse
import os
import subprocess

import matplotlib.pyplot as plt
import numpy as np


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
EXAMPLES_2D = os.path.join(PROJECT_ROOT, 'examples', 'lbm', '2d')
EXAMPLES_3D = os.path.join(PROJECT_ROOT, 'examples', 'lbm', '3d')


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description='GeLB analytical validation')
    p.add_argument('-o', '--output', default='validation_convergence.png',
                   help='Output image path (default: validation_convergence.png)')
    all_cases = ['poiseuille', 'poiseuille_zouhe', 'poiseuille_3d',
                  'couette_bgk', 'couette_mrt',
                  'couette_bgk_zouhe', 'couette_mrt_zouhe',
                  'taylor_green_bgk', 'taylor_green_mrt',
                  'ra_critical_2d', 'ra_critical_3d']
    # Default: convergence cases only (Ra_cr sweeps are expensive)
    default_cases = [c for c in all_cases if not c.startswith('ra_')]
    p.add_argument('--cases', nargs='+',
                   default=default_cases,
                   choices=all_cases,
                   help='Which cases to run (default: convergence cases; '
                        'add ra_critical_2d/ra_critical_3d for Ra_cr sweeps)')
    p.add_argument('--backend', default='gpu_cuda_cpp',
                   choices=['gpu_cuda_cpp', 'cpu_highway',
                            'cpu_fortran_serial'],
                   help='Compiler backend (default: gpu_cuda_cpp). '
                        'cpu_highway is the OpenMP-parallel CPU choice '
                        'for machines without an NVIDIA GPU.')
    p.add_argument('--resolutions', nargs='+', type=int, default=None,
                   help='Override the default resolution sweep '
                        '(e.g. --resolutions 16 32 64 128).  '
                        'When omitted, each case uses its built-in default.')
    return p.parse_args()


# ---------------------------------------------------------------------------
# Simulation runner (delegates to gelb-run)
# ---------------------------------------------------------------------------

def run_example(gelb_path, num_timesteps, write_every, backend,
                defines=None, seed=None, timeout=3600):
    """Run a ``.gelb`` example via ``gelb-run`` with optional ``-D``
    overrides and return the last-timestep fields as a dict, or
    ``None`` on failure.
    """
    cmd = ['./scripts/gelb-run', '-b', backend]
    cmd.extend(['-n', str(num_timesteps), '-w', str(write_every)])
    if seed is not None:
        cmd.extend(['-s', str(seed)])
    for k, v in (defines or {}).items():
        cmd.extend(['-D', f'{k}={v}'])
    cmd.append(gelb_path)

    rc = subprocess.run(
        cmd, capture_output=True, text=True,
        timeout=timeout, cwd=PROJECT_ROOT)
    if rc.returncode != 0:
        stderr = rc.stderr[:500] if rc.stderr else ''
        print(f'  gelb-run failed: {stderr}')
        return None

    # gelb-run writes <stem>.nc into cwd (= PROJECT_ROOT)
    stem = os.path.splitext(os.path.basename(gelb_path))[0]
    nc_path = os.path.join(PROJECT_ROOT, f'{stem}.nc')
    if not os.path.exists(nc_path):
        print('  NetCDF output not found')
        return None

    import netCDF4 as netcdf
    ds = netcdf.Dataset(nc_path)
    result = {
        'ux': np.asarray(ds.variables['ux'][-1]),
        'uy': np.asarray(ds.variables['uy'][-1]),
        'rho': np.asarray(ds.variables['rho'][-1]),
    }
    ds.close()
    os.remove(nc_path)
    return result


def _run_rb_one(gelb_path, ra, ny, nx, nz, num_timesteps, write_every,
                backend, seed=42, row=None, on_progress=None):
    """Run one Rayleigh-Benard simulation at a given Ra and return
    the final max|uY| (L-infinity norm over the fluid interior),
    or ``None`` on failure.

    If *row* is supplied (Rich TUI mode), updates it in-place during
    the run.  *on_progress* is called after each poll cycle.
    """
    import time as _time

    defines = {'RA': ra, 'NY': ny, 'NX': nx}
    if nz is not None:
        defines['NZ'] = nz

    cmd = [
        './scripts/gelb-run',
        '-b', backend,
        '-n', str(num_timesteps),
        '-w', str(write_every),
        '-s', str(seed),
    ]
    for k, v in defines.items():
        cmd.extend(['-D', f'{k}={v}'])
    cmd.append(gelb_path)

    total_records = num_timesteps // write_every + 1
    if row:
        row['phase'] = 'compiling'
        row['total_records'] = total_records

    t0 = _time.monotonic()

    if not row:
        print(f'    Ra={ra:g}: running {num_timesteps:,} steps ...',
              end='', flush=True)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        cwd=PROJECT_ROOT,
    )

    stem = os.path.splitext(os.path.basename(gelb_path))[0]
    nc_path = os.path.join(PROJECT_ROOT, f'{stem}.nc')
    bytes_per_record = None

    while proc.poll() is None:
        elapsed = _time.monotonic() - t0
        if row:
            row['elapsed_s'] = elapsed

        if os.path.exists(nc_path):
            if row and row['phase'] == 'compiling':
                row['phase'] = 'running'
            try:
                sz = os.path.getsize(nc_path)
                if bytes_per_record and sz > 0:
                    est = int(sz / bytes_per_record)
                    if row:
                        row['records'] = min(est, total_records)
                elif sz > 0 and not bytes_per_record:
                    # Try to calibrate from NC record count
                    try:
                        import netCDF4 as _nc
                        _ds = _nc.Dataset(nc_path, 'r')
                        cnt = len(_ds.dimensions['time'])
                        _ds.close()
                        if cnt > 1:
                            bytes_per_record = sz / cnt
                            if row:
                                row['records'] = cnt
                    except Exception:
                        pass
            except OSError:
                pass

        if on_progress:
            on_progress()
        _time.sleep(1.0)

    wall = _time.monotonic() - t0
    if proc.stderr:
        proc.stderr.read()
        proc.stderr.close()

    if proc.returncode != 0:
        if row:
            row['phase'] = 'error'
            row['wall_s'] = wall
        elif not row:
            print(' FAILED')
        return None

    if not os.path.exists(nc_path):
        if row:
            row['phase'] = 'error'
            row['wall_s'] = wall
        elif not row:
            print(' no output')
        return None

    if row:
        row['phase'] = 'analyzing'
        row['records'] = total_records

    import netCDF4 as netcdf
    ds = netcdf.Dataset(nc_path)
    uY = np.asarray(ds.variables['uY'][:])
    ds.close()
    os.remove(nc_path)

    uy_inf_final = float(np.nanmax(np.abs(uY[-1]), axis=None))

    if row:
        row['wall_s'] = wall
        row['uy_inf'] = uy_inf_final
    else:
        print(f' uY_inf={uy_inf_final:.3e} ({wall:.0f}s)')

    return uy_inf_final


# ---------------------------------------------------------------------------
# Poiseuille flow validation
# ---------------------------------------------------------------------------

# Parameters matching the example defaults (poiseuille_flow_2d_mrt.gelb).
# The example derives G from NY_BASE and G_BASE internally, so only -D NY=
# is needed per resolution.
_POISEUILLE_TAU = 0.54
_POISEUILLE_G_BASE = 0.00001
_POISEUILLE_NY_BASE = 32


def poiseuille_analytical(ny, tau, g):
    """Compute analytical Poiseuille profile for fluid nodes."""
    nu = (tau - 0.5) / 3.0
    H = ny - 2  # effective channel height (half-way BB)
    y_fluid = np.arange(1, ny - 1)
    y_eff = y_fluid - 0.5  # distance from bottom wall at y=0.5
    u_ana = g / (2 * nu) * y_eff * (H - y_eff)
    return y_fluid, u_ana


def run_poiseuille(backend):
    """Run Poiseuille flow at multiple resolutions and return errors."""
    gelb_path = os.path.join(EXAMPLES_2D, 'poiseuille_flow_2d_mrt.gelb')
    tau = _POISEUILLE_TAU
    nu = (tau - 0.5) / 3.0

    resolutions = [16, 32, 64, 128, 256]
    errors = []

    print(f'Poiseuille flow (MRT): TAU={tau}, nu={nu:.6f}')
    print(f'{"NY":>6s}  {"timesteps":>10s}  {"u_max_sim":>12s}  '
          f'{"u_max_ana":>12s}  {"L2 error":>12s}')

    for ny in resolutions:
        H = ny - 2
        t_diff = int(H * H / nu)
        n_steps = max(5 * t_diff, 10000)

        # G auto-scales inside the .gelb -- replicate the formula here
        # only for the analytical comparison.
        g_scaled = (_POISEUILLE_G_BASE
                    * (_POISEUILLE_NY_BASE - 2)**2 / (ny - 2)**2)

        result = run_example(gelb_path, n_steps, n_steps, backend,
                             defines={'NY': ny})
        if result is None:
            print(f'{ny:6d}  {"FAILED":>10s}')
            errors.append(np.nan)
            continue

        ux_sim = result['ux'][1:ny-1, 2]
        _, u_ana = poiseuille_analytical(ny, tau, g_scaled)

        l2 = np.sqrt(np.sum((ux_sim - u_ana)**2) / np.sum(u_ana**2))
        errors.append(l2)

        print(f'{ny:6d}  {n_steps:10d}  {np.max(ux_sim):12.6e}  '
              f'{np.max(u_ana):12.6e}  {l2:12.4e}')

    return resolutions, errors, 'Poiseuille (MRT)'


def poiseuille_analytical_zouhe(ny, tau, g):
    """Analytical Poiseuille profile with Zou-He walls (pinned at nodes)."""
    nu = (tau - 0.5) / 3.0
    H = ny - 1  # walls at y=0 and y=NY-1 -- exact node positions
    y_all = np.arange(ny)
    u_ana = g / (2 * nu) * y_all * (H - y_all)
    return y_all, u_ana


def run_poiseuille_zouhe(backend, resolutions=None):
    """Run Poiseuille flow with Zou-He BCs at multiple resolutions."""
    gelb_path = os.path.join(EXAMPLES_2D, 'poiseuille_flow_2d_mrt_zouhe.gelb')
    tau = _POISEUILLE_TAU
    nu = (tau - 0.5) / 3.0

    if resolutions is None:
        resolutions = [16, 32, 64, 128, 256]
    errors = []

    print(f'\nPoiseuille (MRT + Zou-He): TAU={tau}, nu={nu:.6f}')
    print(f'{"NY":>6s}  {"timesteps":>10s}  {"u_max_sim":>12s}  '
          f'{"u_max_ana":>12s}  {"L2 error":>12s}')

    for ny in resolutions:
        H = ny - 1
        t_diff = int(H * H / nu)
        n_steps = max(5 * t_diff, 10000)

        # The example doesn't auto-scale G (no NY_BASE indirection like
        # the bounce-back variant); pass scaled G via -D so peak velocity
        # stays bounded across resolutions.
        g_scaled = (_POISEUILLE_G_BASE
                    * (_POISEUILLE_NY_BASE - 1)**2 / (ny - 1)**2)

        result = run_example(gelb_path, n_steps, n_steps, backend,
                             defines={'NY': ny, 'G': g_scaled})
        if result is None:
            print(f'{ny:6d}  {"FAILED":>10s}')
            errors.append(np.nan)
            continue

        # Sample all nodes (Zou-He pins walls at y=0 and y=NY-1; u=0 there).
        ux_sim = result['ux'][:, 2]
        _, u_ana = poiseuille_analytical_zouhe(ny, tau, g_scaled)

        l2 = np.sqrt(np.sum((ux_sim - u_ana)**2) / np.sum(u_ana**2))
        errors.append(l2)

        print(f'{ny:6d}  {n_steps:10d}  {np.max(ux_sim):12.6e}  '
              f'{np.max(u_ana):12.6e}  {l2:12.4e}')

    return resolutions, errors, 'Poiseuille (MRT + Zou-He)'


# ---------------------------------------------------------------------------
# 3D Poiseuille flow validation
# ---------------------------------------------------------------------------

# Parameters matching poiseuille_flow_3d_mrt.gelb defaults; its walls
# and forcing are described in the example header.
_POISEUILLE_3D_TAU = 0.54
_POISEUILLE_3D_G_BASE = 0.00001
_POISEUILLE_3D_NY_BASE = 32


def run_poiseuille_3d(backend):
    """Run 3D Poiseuille flow at multiple resolutions and return errors."""
    gelb_path = os.path.join(EXAMPLES_3D, 'poiseuille_flow_3d_mrt.gelb')
    tau = _POISEUILLE_3D_TAU
    nu = (tau - 0.5) / 3.0

    # 3D is much heavier -- use smaller grids
    resolutions = [16, 32, 64, 128]
    errors = []

    print(f'\nPoiseuille 3D (MRT): TAU={tau}, nu={nu:.6f}')
    print(f'{"NY":>6s}  {"timesteps":>10s}  {"u_max_sim":>12s}  '
          f'{"u_max_ana":>12s}  {"L2 error":>12s}')

    for ny in resolutions:
        H = ny - 2
        t_diff = int(H * H / nu)
        n_steps = max(5 * t_diff, 10000)

        g_scaled = (_POISEUILLE_3D_G_BASE
                    * (_POISEUILLE_3D_NY_BASE - 2)**2 / (ny - 2)**2)

        result = run_example(gelb_path, n_steps, n_steps, backend,
                             defines={'NY': ny})
        if result is None:
            print(f'{ny:6d}  {"FAILED":>10s}')
            errors.append(np.nan)
            continue

        # Profile at mid-z, any x column -- should be uniform
        nz = result['ux'].shape[0]  # netCDF4 in Python: (z, y, x)
        ux_sim = result['ux'][nz // 2, 1:ny-1, 2]
        _, u_ana = poiseuille_analytical(ny, tau, g_scaled)

        l2 = np.sqrt(np.sum((ux_sim - u_ana)**2) / np.sum(u_ana**2))
        errors.append(l2)

        print(f'{ny:6d}  {n_steps:10d}  {np.max(ux_sim):12.6e}  '
              f'{np.max(u_ana):12.6e}  {l2:12.4e}')

    return resolutions, errors, 'Poiseuille 3D (MRT)'


# ---------------------------------------------------------------------------
# Couette flow validation
# ---------------------------------------------------------------------------

_COUETTE_TAU = 0.54
_COUETTE_U_WALL = 0.01


def couette_analytical(ny, u_wall):
    """Compute analytical Couette profile for fluid nodes."""
    H = ny - 2  # effective channel height (half-way BB)
    y_fluid = np.arange(1, ny - 1)
    y_eff = y_fluid - 0.5  # distance from bottom wall at y=0.5
    u_ana = u_wall * y_eff / H
    return y_fluid, u_ana


def run_couette(backend, variant='bgk'):
    """Run Couette flow at multiple resolutions and return errors."""
    if variant == 'mrt':
        filename = 'couette_flow_2d_mrt.gelb'
        label = 'Couette (MRT)'
    else:
        filename = 'couette_flow_2d_bgk.gelb'
        label = 'Couette (BGK)'

    gelb_path = os.path.join(EXAMPLES_2D, filename)
    tau = _COUETTE_TAU
    u_wall = _COUETTE_U_WALL
    nu = (tau - 0.5) / 3.0

    resolutions = [16, 32, 64, 128, 256]
    errors = []

    print(f'\n{label}: TAU={tau}, U_WALL={u_wall}, nu={nu:.6f}')
    print(f'{"NY":>6s}  {"timesteps":>10s}  {"u_top_sim":>12s}  '
          f'{"u_top_ana":>12s}  {"L2 error":>12s}')

    for ny in resolutions:
        H = ny - 2
        t_diff = int(H * H / nu)
        n_steps = max(5 * t_diff, 10000)

        result = run_example(gelb_path, n_steps, n_steps, backend,
                             defines={'NY': ny})
        if result is None:
            print(f'{ny:6d}  {"FAILED":>10s}')
            errors.append(np.nan)
            continue

        ux_sim = result['ux'][1:ny-1, 2]
        _, u_ana = couette_analytical(ny, u_wall)

        l2 = np.sqrt(np.sum((ux_sim - u_ana)**2) / np.sum(u_ana**2))
        errors.append(l2)

        print(f'{ny:6d}  {n_steps:10d}  {ux_sim[-1]:12.6e}  '
              f'{u_ana[-1]:12.6e}  {l2:12.4e}')

    return resolutions, errors, label


def couette_analytical_zouhe(ny, u_wall):
    """Analytical Couette profile with Zou-He walls (pinned at nodes)."""
    H = ny - 1  # walls at y=0 and y=NY-1 -- exact node positions
    y_all = np.arange(ny)
    u_ana = u_wall * y_all / H
    return y_all, u_ana


def run_couette_zouhe(backend, variant='bgk', resolutions=None):
    """Run Couette flow with Zou-He BCs at multiple resolutions."""
    if variant == 'mrt':
        filename = 'couette_flow_2d_mrt_zouhe.gelb'
        label = 'Couette (MRT + Zou-He)'
    else:
        filename = 'couette_flow_2d_bgk_zouhe.gelb'
        label = 'Couette (BGK + Zou-He)'

    gelb_path = os.path.join(EXAMPLES_2D, filename)
    tau = _COUETTE_TAU
    u_wall = _COUETTE_U_WALL
    nu = (tau - 0.5) / 3.0

    if resolutions is None:
        resolutions = [16, 32, 64, 128, 256]
    errors = []

    print(f'\n{label}: TAU={tau}, U_WALL={u_wall}, nu={nu:.6f}')
    print(f'{"NY":>6s}  {"timesteps":>10s}  {"u_top_sim":>12s}  '
          f'{"u_top_ana":>12s}  {"L2 error":>12s}')

    for ny in resolutions:
        H = ny - 1
        t_diff = int(H * H / nu)
        n_steps = max(5 * t_diff, 10000)

        result = run_example(gelb_path, n_steps, n_steps, backend,
                             defines={'NY': ny})
        if result is None:
            print(f'{ny:6d}  {"FAILED":>10s}')
            errors.append(np.nan)
            continue

        # Sample all nodes (Zou-He pins walls at y=0 and y=NY-1).
        ux_sim = result['ux'][:, 2]
        _, u_ana = couette_analytical_zouhe(ny, u_wall)

        l2 = np.sqrt(np.sum((ux_sim - u_ana)**2) / np.sum(u_ana**2))
        errors.append(l2)

        print(f'{ny:6d}  {n_steps:10d}  {ux_sim[-1]:12.6e}  '
              f'{u_ana[-1]:12.6e}  {l2:12.4e}')

    return resolutions, errors, label


# ---------------------------------------------------------------------------
# Taylor-Green vortex decay validation
# ---------------------------------------------------------------------------

# BGK: NU = 1/6, U_MAX = 0.04
# MRT: NU = 1/30, U_MAX = 0.04
_TG_PARAMS = {
    'bgk': {'nu': 1.0 / 6.0, 'u_max': 0.04,
             'file': 'taylor_green_vortex_2d_bgk.gelb'},
    'mrt': {'nu': 1.0 / 30.0, 'u_max': 0.04,
             'file': 'taylor_green_vortex_2d_mrt.gelb'},
}


def taylor_green_analytical(n, nu, u_max, t):
    """Compute analytical Taylor-Green velocity field at time t."""
    K = 2.0 * np.pi / n
    decay = np.exp(-2.0 * nu * K * K * t)
    x = np.arange(n) + 0.5  # cell centers
    y = np.arange(n) + 0.5
    X, Y = np.meshgrid(x, y)  # Y varies along axis 0 (rows)
    ux_ana = -u_max * np.cos(K * X) * np.sin(K * Y) * decay
    uy_ana = u_max * np.sin(K * X) * np.cos(K * Y) * decay
    return ux_ana, uy_ana


def run_taylor_green(backend, variant='bgk'):
    """Run Taylor-Green vortex at multiple resolutions and return errors."""
    params = _TG_PARAMS[variant]
    nu = params['nu']
    u_max = params['u_max']
    gelb_path = os.path.join(EXAMPLES_2D, params['file'])
    label = f'Taylor-Green ({variant.upper()})'

    resolutions = [16, 32, 64, 128, 256, 512, 1024]
    errors = []

    print(f'\n{label}: NU={nu:.6f}, U_MAX={u_max}')
    print(f'{"N":>6s}  {"timesteps":>10s}  {"t_eval":>10s}  '
          f'{"max|ux|_sim":>12s}  {"max|ux|_ana":>12s}  {"L2 error":>12s}')

    for n in resolutions:
        K = 2.0 * np.pi / n
        t_decay = 1.0 / (2.0 * nu * K * K)
        t_eval = int(t_decay)
        n_steps = t_eval

        result = run_example(gelb_path, n_steps, n_steps, backend,
                             defines={'N': n})
        if result is None:
            print(f'{n:6d}  {"FAILED":>10s}')
            errors.append(np.nan)
            continue

        ux_sim = result['ux']
        uy_sim = result['uy']
        ux_ana, uy_ana = taylor_green_analytical(n, nu, u_max, t_eval)

        diff_sq = (ux_sim - ux_ana)**2 + (uy_sim - uy_ana)**2
        ref_sq = ux_ana**2 + uy_ana**2
        l2 = np.sqrt(np.sum(diff_sq) / np.sum(ref_sq))
        errors.append(l2)

        print(f'{n:6d}  {n_steps:10d}  {t_eval:10d}  '
              f'{np.max(np.abs(ux_sim)):12.6e}  '
              f'{np.max(np.abs(ux_ana)):12.6e}  {l2:12.4e}')

    return resolutions, errors, label


# ---------------------------------------------------------------------------
# Critical Rayleigh number (Ra_cr,1) validation
# ---------------------------------------------------------------------------

# Detection thresholds for the uY L-infinity norm.  At the
# Fortran-matching grid (NY=43, Ma=0.1) the Strang-split gauge
# floor is ~8e-5; decaying runs sit at that floor and growing
# runs climb one to two decades above it.
_RA_CR_DECAY_THR = 2e-4
_RA_CR_GROW_THR = 5e-4
_RA_CR_THEORETICAL = 1707.76


def _classify(uy_inf, decay_thr=_RA_CR_DECAY_THR,
              grow_thr=_RA_CR_GROW_THR):
    if uy_inf is None or np.isnan(uy_inf):
        return 'error'
    if uy_inf < decay_thr:
        return 'decaying'
    if uy_inf > grow_thr:
        return 'growing'
    return 'inconclusive'


def _format_time(seconds):
    """Format seconds as H:MM:SS or M:SS."""
    s = int(seconds)
    if s < 3600:
        return f'{s // 60}:{s % 60:02d}'
    return f'{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}'


def _class_style(cls):
    """Rich markup for a classification label."""
    if cls == 'decaying':
        return '[cyan]decaying[/cyan]'
    if cls == 'growing':
        return '[red]growing[/red]'
    if cls == 'inconclusive':
        return '[yellow]inconclusive[/yellow]'
    if cls == 'error':
        return '[red bold]error[/red bold]'
    return cls


def _build_ra_table(rows, header):
    """Build a Rich Table for the Ra_cr sweep."""
    import math
    from rich.table import Table

    t = Table(title=header, title_style='bold', expand=False,
              border_style='dim')
    t.add_column('#', justify='right', style='dim', no_wrap=True)
    t.add_column('Ra', justify='right', no_wrap=True)
    t.add_column('Status', no_wrap=True)
    t.add_column('Progress', no_wrap=True, min_width=22)
    t.add_column('Wall', justify='right', no_wrap=True)
    t.add_column('uY_inf', justify='right', no_wrap=True)
    t.add_column('Class', no_wrap=True)

    BAR_W = 12
    for i, r in enumerate(rows, 1):
        phase = r['phase']

        # Progress
        if phase in ('running', 'analyzing') and r['total_records'] > 0:
            frac = min(r['records'] / r['total_records'], 1.0)
            filled = int(BAR_W * frac)
            bar = '\u2588' * filled + '\u2591' * (BAR_W - filled)
            pct = f'{100 * frac:4.0f}%'
            if 0.01 < frac < 1.0:
                eta = r['elapsed_s'] / frac * (1 - frac)
                eta_str = f'~{_format_time(eta)}'
            else:
                eta_str = ''
            progress = f'{bar} {pct} {eta_str}'
        elif phase == 'done':
            progress = '\u2588' * BAR_W + ' 100%'
        elif phase == 'compiling':
            progress = '[dim]compiling...[/dim]'
        elif phase == 'error':
            progress = '[red]failed[/red]'
        else:
            progress = '[dim]\u2014[/dim]'

        # Status style
        if phase == 'running':
            status = '[bold green]running[/bold green]'
        elif phase == 'compiling':
            status = '[yellow]compiling[/yellow]'
        elif phase == 'analyzing':
            status = '[magenta]analyzing[/magenta]'
        elif phase == 'done':
            status = '[dim]done[/dim]'
        elif phase == 'error':
            status = '[red]error[/red]'
        else:
            status = '[dim]queued[/dim]'

        wall = _format_time(r['wall_s']) if r['wall_s'] > 0 else (
            _format_time(r['elapsed_s']) if r['elapsed_s'] > 0 else '')
        uy_str = f'{r["uy_inf"]:.2e}' if not math.isnan(r['uy_inf']) else ''
        cls_str = _class_style(r['classification']) if r['classification'] else ''

        t.add_row(str(i), f'{r["ra"]:g}', status, progress, wall,
                  uy_str, cls_str)
    return t


def _build_ra_summary(rows):
    """Build a Rich summary panel with bracket result."""
    from rich.panel import Panel

    results = [(r['ra'], r['uy_inf'], r['classification']) for r in rows]
    decaying = [r for r in results if r[2] == 'decaying']
    growing = [r for r in results if r[2] == 'growing']
    done = [r for r in rows if r['phase'] == 'done']
    errors = [r for r in rows if r['phase'] == 'error']

    lines = [f'Completed: {len(done)}/{len(rows)}']
    if errors:
        lines.append(f'Errors: {len(errors)}')

    if decaying and growing:
        lo = max(r[0] for r in decaying)
        hi = min(r[0] for r in growing)
        if lo < hi:
            mid = 0.5 * (lo + hi)
            rel_err = abs(mid - _RA_CR_THEORETICAL) / _RA_CR_THEORETICAL
            lines += ['', f'Bracket:     Ra_c \u2208 ({lo:g}, {hi:g})',
                       f'Midpoint:    Ra_c \u2248 {mid:g}',
                       f'Theoretical: Ra_c \u2248 {_RA_CR_THEORETICAL}',
                       f'Rel. error:  {rel_err:.2%}']
        else:
            lines += ['', f'\u26a0 Inverted bracket: decaying up to {lo}, '
                          f'growing from {hi}']
    elif done:
        lines += ['', '\u26a0 No clean bracket \u2014 '
                      'add more Ra values or extend timesteps']

    total_wall = sum(r['wall_s'] for r in rows if r['wall_s'] > 0)
    if total_wall > 0:
        lines.append(f'\nTotal wall time: {_format_time(total_wall)}')

    style = 'green' if (decaying and growing) else 'yellow'
    return Panel('\n'.join(lines), title='Ra_c sweep result',
                 border_style=style)


def _run_ra_cr_sweep(gelb_path, ra_values, ny, nx, nz,
                     num_timesteps, write_every, backend, label):
    """Run a Ra_cr sweep with Rich TUI (or plain-text fallback)."""
    rows = []
    for ra in ra_values:
        rows.append({
            'ra': ra, 'phase': 'queued', 'records': 0,
            'total_records': 0, 'elapsed_s': 0.0, 'wall_s': 0.0,
            'uy_inf': float('nan'), 'classification': '',
        })

    grid_str = f'NY={ny}  NX={nx}'
    if nz is not None:
        grid_str += f'  NZ={nz}'
    header = (f'{label}\n{grid_str}  '
              f'(fluid rows={ny-2})  {num_timesteps:,} steps/run')

    # Try Rich TUI
    use_rich = True
    try:
        from rich.console import Console
        from rich.live import Live
    except ImportError:
        use_rich = False

    if use_rich:
        console = Console()
        with Live(_build_ra_table(rows, header), console=console,
                  refresh_per_second=2, transient=True) as live:
            def _refresh():
                live.update(_build_ra_table(rows, header))

            for i, ra in enumerate(ra_values):
                row = rows[i]
                uy_inf = _run_rb_one(
                    gelb_path, ra, ny, nx, nz,
                    num_timesteps, write_every, backend,
                    row=row, on_progress=_refresh)
                cls = _classify(uy_inf)
                row['phase'] = 'done' if uy_inf is not None else 'error'
                row['classification'] = cls
                if uy_inf is not None:
                    row['uy_inf'] = uy_inf
                live.update(_build_ra_table(rows, header))

        console.print(_build_ra_table(rows, header))
        console.print(_build_ra_summary(rows))
    else:
        # Plain-text fallback
        print(header)
        print()
        for i, ra in enumerate(ra_values):
            row = rows[i]
            uy_inf = _run_rb_one(
                gelb_path, ra, ny, nx, nz,
                num_timesteps, write_every, backend)
            cls = _classify(uy_inf)
            row['phase'] = 'done' if uy_inf is not None else 'error'
            row['classification'] = cls
            if uy_inf is not None:
                row['uy_inf'] = uy_inf
                row['wall_s'] = 0  # not tracked in plain mode

        # Print plain table
        print()
        print(f'  {"Ra":>8s}  {"uY_inf":>12s}  {"class":>13s}')
        print(f'  {"-"*38}')
        for r in rows:
            uy_s = f'{r["uy_inf"]:.3e}' if r['classification'] != 'error' else 'N/A'
            print(f'  {r["ra"]:8g}  {uy_s:>12s}  {r["classification"]:>13s}')

    return rows


def run_ra_critical_2d(backend):
    """Sweep Ra values for the 2D Rayleigh-Benard MRT example and
    bracket the critical Rayleigh number."""
    return _run_ra_cr_sweep(
        gelb_path=os.path.join(EXAMPLES_2D, 'rayleigh_benard_2d_mrt.gelb'),
        ra_values=[1500.0, 1685.0, 1700.0, 1715.0, 1730.0, 1800.0, 2000.0],
        ny=43, nx=83, nz=None,
        num_timesteps=10_000_000,
        write_every=20_000,
        backend=backend,
        label='Ra_cr,1 sweep \u2014 2D MRT',
    )


def run_ra_critical_3d(backend):
    """Sweep Ra values for the 3D Rayleigh-Benard MRT example and
    bracket the critical Rayleigh number.

    Uses the BGK-equivalent-rates variant at a coarser grid (NY=22)
    to keep run times practical (~76 min per Ra on GPU at 10M steps).
    """
    return _run_ra_cr_sweep(
        gelb_path=os.path.join(EXAMPLES_3D, 'rayleigh_benard_3d_mrt.gelb'),
        ra_values=[1500.0, 1700.0, 1730.0, 1800.0, 1850.0, 1900.0, 2000.0],
        ny=22, nx=44, nz=44,
        num_timesteps=10_000_000,
        write_every=10_000,
        backend=backend,
        label='Ra_cr,1 sweep \u2014 3D MRT (BGK rates, NY=22)',
    )


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_convergence(all_results, output_path):
    """Plot L2 error vs grid size for all cases."""
    fig, ax = plt.subplots(figsize=(7, 5))

    colors = {'Poiseuille (MRT)': '#2980b9',
              'Poiseuille 3D (MRT)': '#1a5276',
              'Couette (BGK)': '#8e44ad',
              'Couette (MRT)': '#f39c12',
              'Taylor-Green (BGK)': '#e74c3c',
              'Taylor-Green (MRT)': '#27ae60'}
    markers = {'Poiseuille (MRT)': 'o',
               'Poiseuille 3D (MRT)': 'p',
               'Couette (BGK)': '^',
               'Couette (MRT)': 'v',
               'Taylor-Green (BGK)': 's',
               'Taylor-Green (MRT)': 'D'}

    for resolutions, errors, label in all_results:
        valid = [(r, e) for r, e in zip(resolutions, errors)
                 if not np.isnan(e)]
        if len(valid) < 2:
            continue
        rs, es = zip(*valid)
        color = colors.get(label, '#333333')
        marker = markers.get(label, 'o')
        ax.loglog(rs, es, f'-{marker}', color=color, label=label,
                  markersize=8, linewidth=2)

        # Compute convergence rate from last two points
        if len(rs) >= 2:
            rate = np.log(es[-2] / es[-1]) / np.log(rs[-1] / rs[-2])
            ax.annotate(f'slope = {rate:.2f}',
                        xy=(rs[-1], es[-1]),
                        xytext=(15, 10), textcoords='offset points',
                        fontsize=9, color=color)

    # Reference slopes
    r_ref = np.array([resolutions[0], resolutions[-1]])
    e1 = errors[0] if not np.isnan(errors[0]) else 0.1
    ax.loglog(r_ref, e1 * (r_ref[0] / r_ref)**1,
              '--', color='gray', alpha=0.4, linewidth=1)
    ax.loglog(r_ref, e1 * (r_ref[0] / r_ref)**2,
              ':', color='gray', alpha=0.4, linewidth=1)
    ax.text(r_ref[-1] * 1.05, e1 * (r_ref[0] / r_ref[-1])**1,
            '1st order', fontsize=8, color='gray', va='center')
    ax.text(r_ref[-1] * 1.05, e1 * (r_ref[0] / r_ref[-1])**2,
            '2nd order', fontsize=8, color='gray', va='center')

    ax.set_xlabel('Grid size (N)', fontsize=12)
    ax.set_ylabel('L2 relative error', fontsize=12)
    ax.set_title('GeLB Analytical Validation — Grid Convergence', fontsize=13)
    ax.legend(fontsize=10, framealpha=0.9)
    ax.grid(True, which='both', alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f'\nConvergence plot saved to {output_path}')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    backend = args.backend
    print(f'Backend: {backend}')
    print()

    all_results = []

    if 'poiseuille' in args.cases:
        result = run_poiseuille(backend)
        all_results.append(result)

    if 'poiseuille_zouhe' in args.cases:
        result = run_poiseuille_zouhe(backend, resolutions=args.resolutions)
        all_results.append(result)

    if 'poiseuille_3d' in args.cases:
        result = run_poiseuille_3d(backend)
        all_results.append(result)

    if 'couette_bgk' in args.cases:
        result = run_couette(backend, variant='bgk')
        all_results.append(result)

    if 'couette_mrt' in args.cases:
        result = run_couette(backend, variant='mrt')
        all_results.append(result)

    if 'couette_bgk_zouhe' in args.cases:
        result = run_couette_zouhe(backend, variant='bgk',
                                   resolutions=args.resolutions)
        all_results.append(result)

    if 'couette_mrt_zouhe' in args.cases:
        result = run_couette_zouhe(backend, variant='mrt',
                                   resolutions=args.resolutions)
        all_results.append(result)

    if 'taylor_green_bgk' in args.cases:
        result = run_taylor_green(backend, variant='bgk')
        all_results.append(result)

    if 'taylor_green_mrt' in args.cases:
        result = run_taylor_green(backend, variant='mrt')
        all_results.append(result)

    if all_results:
        plot_convergence(all_results, args.output)

    # Ra_cr sweeps (separate from convergence plot)
    if 'ra_critical_2d' in args.cases:
        print('\n' + '=' * 60)
        run_ra_critical_2d(backend)

    if 'ra_critical_3d' in args.cases:
        print('\n' + '=' * 60)
        run_ra_critical_3d(backend)


if __name__ == '__main__':
    main()
