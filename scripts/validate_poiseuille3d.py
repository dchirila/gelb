#!/usr/bin/env python3
"""
Validate 3D Poiseuille flow simulations against the exact analytical solution.

Gravity-driven channel flow between two parallel no-slip walls (bounce-back).
Periodic in x (flow direction) and z (spanwise), walls at y=0 and y=NY-1.

At steady state the velocity profile is exactly parabolic:
    u_x(y) = G/(2*nu) * y_eff * (H - y_eff)
where y_eff = y - 0.5 and H = NY - 2 (full-way bounce-back walls).

Acoustic scaling: G is scaled as G = 8*nu*u_target/H^2 to keep the peak
velocity (and Mach number) constant across grid sizes.  This isolates the
spatial discretization error and should yield 2nd-order convergence with
Guo forcing + bounce-back.

Uses gelb-run for compilation and execution.

Usage:
    uv run python scripts/validate_poiseuille3d.py [--gpu]
"""

import argparse
import glob
import os
import subprocess
import sys
import tempfile
import numpy as np

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TAU = 0.8
NU = (TAU - 0.5) / 3.0       # 0.1
G_FIXED = 1e-5                 # fixed body force for diffusive scaling

# Grid sizes for convergence study (NY values)
GRID_SIZES = [16, 24, 32, 48, 64]

# Diffusion-time multiplier for steady-state convergence
DIFFUSION_TIMES = 4

EXAMPLES = {
    'bgk': 'examples/lbm/3d/poiseuille_flow_3d_bgk.gelb',
    'mrt': 'examples/lbm/3d/poiseuille_flow_3d_mrt.gelb',
}

BACKEND_MAP = {
    'cpu': 'cpu_fortran_serial',
    'gpu': 'gpu_cuda_cpp',
}

# ---------------------------------------------------------------------------
# Analytical solution
# ---------------------------------------------------------------------------

def analytical_poiseuille(NY, G, nu):
    """Exact Poiseuille velocity profile for full-way bounce-back walls.

    Returns u_exact array of shape (NY,) with u_exact[0] = u_exact[NY-1] = 0
    (wall nodes).
    """
    H = NY - 2   # effective channel height
    y = np.arange(NY)
    y_eff = y - 0.5
    u_exact = np.where((y >= 1) & (y <= NY - 2),
                       G / (2.0 * nu) * y_eff * (H - y_eff), 0.0)
    return u_exact


def l2_error(profile_sim, profile_exact):
    """Relative L2 error of 1D profiles."""
    diff = profile_sim - profile_exact
    norm_exact = np.sqrt(np.sum(profile_exact**2))
    if norm_exact < 1e-15:
        return np.sqrt(np.sum(diff**2))
    return np.sqrt(np.sum(diff**2)) / norm_exact


def l2_error_shape(profile_sim, profile_exact, ny):
    """Relative L2 error after subtracting mean offset on fluid nodes.

    This isolates the parabolic shape error from the constant discrete
    offset inherent in the LBM Poiseuille solution.
    """
    fluid = slice(1, ny - 1)
    offset = np.mean(profile_sim[fluid] - profile_exact[fluid])
    corrected = profile_sim.copy()
    corrected[fluid] -= offset
    return l2_error(corrected, profile_exact)

# ---------------------------------------------------------------------------
# Run via gelb-run
# ---------------------------------------------------------------------------

def _setup_gpu_env(env):
    """Set up environment for GPU compilation via gelb-run.

    Adds nvcc to PATH if not already there; ``gelb-run`` itself
    handles NetCDF-C detection via ``nc-config``.
    """
    import shutil

    if not shutil.which('nvcc'):
        for pattern in ['/usr/local/cuda*/bin',
                        '/opt/cuda*/bin']:
            candidates = sorted(glob.glob(pattern), reverse=True)
            if candidates:
                env['PATH'] = candidates[0] + ':' + env.get('PATH', '')
                break


def run_gelb(gelb_file, backend, work_dir, ny, num_timesteps, g_force):
    """Run a simulation via gelb-run with NY and G overrides."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    gelb_run = os.path.join(project_root, 'scripts', 'gelb-run')
    gelb_abs = os.path.join(project_root, gelb_file)

    cmd = [
        gelb_run,
        '-b', BACKEND_MAP[backend],
        '-n', str(num_timesteps),
        '-w', str(num_timesteps),
        '-D', f'NY={ny}',
        '-D', f'G={g_force:.10e}',
        gelb_abs,
    ]
    env = os.environ.copy()
    if backend == 'gpu':
        _setup_gpu_env(env)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=work_dir,
                            env=env)
    if result.returncode != 0:
        print(f"    FAILED: gelb-run ({backend}, NY={ny})")
        print(f"      {result.stderr.strip()[-200:]}")
        return None

    # Find .nc file
    ncs = glob.glob(os.path.join(work_dir, '*.nc'))
    return ncs[0] if ncs else None


def read_ux_profile(nc_path, ny):
    """Read ux profile along y at x=0, z=0 from NetCDF.

    NetCDF has shape (time, z, y, x) in Python.
    """
    from netCDF4 import Dataset
    ds = Dataset(nc_path, 'r')
    ux = np.asarray(ds.variables['ux'][-1, 0, :, 0])  # (z=0, y, x=0)
    ds.close()
    return ux

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Validate 3D Poiseuille flow against analytical solution")
    parser.add_argument('--gpu', action='store_true',
                        help="Also test GPU (CUDA Fortran) backend")
    args = parser.parse_args()

    backends = ['cpu']
    if args.gpu:
        backends.append('gpu')

    print(f"3D Poiseuille convergence study: TAU={TAU}, NU={NU:.4f}, G={G_FIXED:.1e}")
    print(f"  Diffusive scaling: G fixed, NY varies (2nd-order spatial convergence)")
    print(f"  Steady state: {DIFFUSION_TIMES} diffusion times per grid size")
    print()

    # Collect results: (collision, backend) -> list of (NY, L2, u_max_sim)
    all_results = {}

    for collision in ['bgk', 'mrt']:
        gelb_file = EXAMPLES[collision]

        for backend in backends:
            label = f"{collision.upper()}/{('CPU' if backend == 'cpu' else 'GPU')}"
            print(f"{'='*70}")
            print(f"  {label}")
            print(f"{'='*70}")

            entries = []
            prev_err = None
            prev_ny = None

            for ny in GRID_SIZES:
                H = ny - 2
                G = G_FIXED  # diffusive scaling: fixed G
                T = max(int(DIFFUSION_TIMES * H * H / NU), 5000)
                u_exact = analytical_poiseuille(ny, G, NU)
                u_max_exact = G * H**2 / (8.0 * NU)

                with tempfile.TemporaryDirectory() as tmpdir:
                    nc_path = run_gelb(gelb_file, backend, tmpdir, ny, T, G)
                    if nc_path is None:
                        entries.append((ny, T, None, None, None))
                        continue

                    profile_sim = read_ux_profile(nc_path, ny)

                if np.any(np.isnan(profile_sim)):
                    print(f"    NY={ny:3d}  T={T:6d}  *** NaN ***")
                    entries.append((ny, T, None, None, None))
                    continue

                u_max_sim = np.max(profile_sim)
                err = l2_error(profile_sim, u_exact)
                err_shape = l2_error_shape(profile_sim, u_exact, ny)

                if prev_err is not None and prev_err > 0 and err_shape > 0:
                    order = np.log(prev_err / err_shape) / np.log(ny / prev_ny)
                    print(f"    NY={ny:3d}  T={T:6d}  "
                          f"u_max={u_max_sim:.6e} (exact {u_max_exact:.6e})  "
                          f"L2={err:.4e}  L2_shape={err_shape:.4e}  "
                          f"order={order:.2f}")
                else:
                    print(f"    NY={ny:3d}  T={T:6d}  "
                          f"u_max={u_max_sim:.6e} (exact {u_max_exact:.6e})  "
                          f"L2={err:.4e}  L2_shape={err_shape:.4e}")

                entries.append((ny, T, u_max_sim, err, err_shape))
                prev_err = err_shape
                prev_ny = ny

            all_results[(collision, backend)] = entries
            print()

    # Summary table
    print(f"{'='*70}")
    print(f"  SUMMARY: L2_shape errors (offset-corrected) at steady state")
    print(f"{'='*70}")
    print(f"  {'NY':>4s}  ", end='')
    for collision in ['bgk', 'mrt']:
        for backend in backends:
            bname = 'CPU' if backend == 'cpu' else 'GPU'
            print(f" {collision.upper()}/{bname:>3s}       ", end='')
    print()
    print(f"  {'----':>4s}  ", end='')
    for _ in range(len(backends) * 2):
        print(f" {'----------':>13s}", end='')
    print()

    for i, ny in enumerate(GRID_SIZES):
        print(f"  {ny:4d}  ", end='')
        for collision in ['bgk', 'mrt']:
            for backend in backends:
                entries = all_results.get((collision, backend), [])
                if i < len(entries) and entries[i][4] is not None:
                    print(f" {entries[i][4]:13.4e}", end='')
                else:
                    print(f" {'--':>13s}", end='')
        print()

    # CPU vs GPU comparison
    if args.gpu:
        print(f"\n  CPU vs GPU max difference (across all NY):")
        for collision in ['bgk', 'mrt']:
            cpu_entries = all_results.get((collision, 'cpu'), [])
            gpu_entries = all_results.get((collision, 'gpu'), [])
            diffs = []
            for c, g in zip(cpu_entries, gpu_entries):
                if c[3] is not None and g[3] is not None:
                    diffs.append(abs(c[3] - g[3]))
            if diffs:
                print(f"    {collision.upper()}: max|L2_cpu - L2_gpu| = "
                      f"{max(diffs):.6e}")


if __name__ == '__main__':
    main()
