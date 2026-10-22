#!/usr/bin/env python3
"""
Validate 3D Taylor-Green Vortex simulations against analytical solution.

Compares CPU (gfortran) and GPU (nvcc/CUDA) backends for both BGK
and MRT collision operators.  Reports L2 errors in ux, uy, uz at the
final timestep against the exact decaying solution.

Uses gelb-run for compilation and execution (handles compiler detection,
NetCDF library resolution, etc.).

Usage:
    uv run python scripts/validate_tgv3d.py [--gpu]

Without --gpu, only the CPU backend is tested.
With --gpu, both CPU and GPU backends are run and compared.
"""

import argparse
import os
import subprocess
import sys
import tempfile
import numpy as np

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

N = 32
NU_BGK = 1.0 / 6.0
NU_MRT = 1.0 / 30.0
U_MAX = 0.04
NUM_TIMESTEPS = 200
WRITE_EVERY = 200   # Only write initial + final

EXAMPLES = {
    'bgk': 'examples/lbm/3d/taylor_green_vortex_3d_bgk.gelb',
    'mrt': 'examples/lbm/3d/taylor_green_vortex_3d_mrt.gelb',
}

NU_MAP = {'bgk': NU_BGK, 'mrt': NU_MRT}

BACKEND_MAP = {
    'cpu': 'cpu_fortran_serial',
    'gpu': 'gpu_cuda_cpp',
}

# ---------------------------------------------------------------------------
# Analytical solution
# ---------------------------------------------------------------------------

def analytical_tgv3d(N, nu, U_max, t):
    """Compute exact 3D Taylor-Green velocity field at time t."""
    K = 2.0 * np.pi / N
    c = np.arange(N) + 0.5
    x, y, z = np.meshgrid(c, c, c, indexing='ij')

    decay = np.exp(-3.0 * nu * K**2 * t)
    ux =  U_max * np.cos(K * x) * np.sin(K * y) * np.cos(K * z) * decay
    uy = -U_max * np.sin(K * x) * np.cos(K * y) * np.cos(K * z) * decay
    uz = np.zeros_like(ux)
    return ux, uy, uz


def l2_error(sim, exact):
    """Relative L2 error: ||sim - exact||_2 / ||exact||_2."""
    diff = sim - exact
    norm_exact = np.sqrt(np.sum(exact**2))
    if norm_exact < 1e-15:
        return np.sqrt(np.sum(diff**2))
    return np.sqrt(np.sum(diff**2)) / norm_exact

# ---------------------------------------------------------------------------
# Run via gelb-run
# ---------------------------------------------------------------------------

def _setup_gpu_env(env):
    """Set up environment for GPU compilation via gelb-run.

    Adds nvcc to PATH if not already there (searching common
    install locations); ``gelb-run`` itself handles NetCDF-C
    detection via ``nc-config``.
    """
    import glob
    import shutil

    if not shutil.which('nvcc'):
        for pattern in ['/usr/local/cuda*/bin',
                        '/opt/cuda*/bin']:
            candidates = sorted(glob.glob(pattern), reverse=True)
            if candidates:
                env['PATH'] = candidates[0] + ':' + env.get('PATH', '')
                break


def run_gelb(gelb_file, backend, work_dir):
    """Run a simulation via gelb-run, producing .nc in work_dir.

    gelb-run writes the .nc file to cwd, so we run it from work_dir
    using an absolute path to the script and the .gelb file.
    """
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    gelb_run = os.path.join(project_root, 'scripts', 'gelb-run')
    gelb_abs = os.path.join(project_root, gelb_file)
    basename = os.path.splitext(os.path.basename(gelb_file))[0]
    expected_nc = os.path.join(work_dir, f'{basename}.nc')

    cmd = [
        gelb_run,
        '-b', BACKEND_MAP[backend],
        '-n', str(NUM_TIMESTEPS),
        '-w', str(WRITE_EVERY),
        '-v',
        gelb_abs,
    ]
    env = os.environ.copy()
    if backend == 'gpu':
        _setup_gpu_env(env)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=work_dir,
                            env=env)
    if result.returncode != 0:
        print(f"  FAILED: gelb-run ({backend})")
        print(f"    stderr: {result.stderr.strip()}")
        sys.exit(1)

    # Print MLUPS report
    for line in (result.stdout + result.stderr).splitlines():
        if 'MLUPS' in line or 'Wall time' in line or 'GPU' in line or '===' in line:
            print(f"    {line.strip()}")

    return expected_nc


def read_final_timestep(nc_path):
    """Read final-timestep velocity fields from NetCDF.

    Returns (ux, uy, uz) arrays of shape (N, N, N).
    NetCDF has (time, z, y, x) -- transpose to (x, y, z).
    """
    from netCDF4 import Dataset
    ds = Dataset(nc_path, 'r')
    ux = np.asarray(ds.variables['ux'][-1, :, :, :]).transpose(2, 1, 0)
    uy = np.asarray(ds.variables['uy'][-1, :, :, :]).transpose(2, 1, 0)
    uz = np.asarray(ds.variables['uz'][-1, :, :, :]).transpose(2, 1, 0)
    ds.close()
    return ux, uy, uz

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Validate 3D TGV against analytical solution")
    parser.add_argument('--gpu', action='store_true',
                        help="Also test the GPU backend (gpu_cuda_cpp)")
    args = parser.parse_args()

    backends = ['cpu']
    if args.gpu:
        backends.append('gpu')

    results = {}

    for collision in ['bgk', 'mrt']:
        gelb_file = EXAMPLES[collision]
        nu = NU_MAP[collision]

        ux_exact, uy_exact, uz_exact = analytical_tgv3d(
            N, nu, U_MAX, NUM_TIMESTEPS)

        for backend in backends:
            label = f"{collision.upper()} / {'CPU' if backend == 'cpu' else 'GPU'}"
            print(f"\n{'='*60}")
            print(f"  {label}")
            print(f"{'='*60}")
            print(f"  Running {NUM_TIMESTEPS} timesteps on {N}^3 grid...")

            with tempfile.TemporaryDirectory() as tmpdir:
                nc_path = run_gelb(gelb_file, backend, tmpdir)

                if not os.path.exists(nc_path):
                    print(f"  ERROR: NetCDF output not found at {nc_path}")
                    # Try to find it
                    import glob
                    ncs = glob.glob(os.path.join(tmpdir, '*.nc'))
                    if ncs:
                        nc_path = ncs[0]
                        print(f"  Found: {nc_path}")
                    else:
                        print(f"  No .nc files in {tmpdir}")
                        sys.exit(1)

                ux_sim, uy_sim, uz_sim = read_final_timestep(nc_path)

                err_ux = l2_error(ux_sim, ux_exact)
                err_uy = l2_error(uy_sim, uy_exact)
                err_uz = np.sqrt(np.mean(uz_sim**2))

                results[(collision, backend)] = {
                    'err_ux': err_ux, 'err_uy': err_uy, 'err_uz': err_uz,
                }

                print(f"  Results:")
                print(f"    |ux|_max  sim={np.max(np.abs(ux_sim)):.8e}  "
                      f"exact={np.max(np.abs(ux_exact)):.8e}")
                print(f"    L2(ux)  = {err_ux:.6e}")
                print(f"    L2(uy)  = {err_uy:.6e}")
                print(f"    RMS(uz) = {err_uz:.6e}  (should be ~0)")

    # Summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY: Relative L2 errors at t={NUM_TIMESTEPS}")
    print(f"{'='*60}")
    print(f"  {'Collision':<10} {'Backend':<8} {'L2(ux)':<14} {'L2(uy)':<14} {'RMS(uz)':<14}")
    print(f"  {'-'*10} {'-'*8} {'-'*14} {'-'*14} {'-'*14}")
    for (collision, backend), r in sorted(results.items()):
        bname = 'CPU' if backend == 'cpu' else 'GPU'
        print(f"  {collision.upper():<10} {bname:<8} "
              f"{r['err_ux']:<14.6e} {r['err_uy']:<14.6e} {r['err_uz']:<14.6e}")

    if args.gpu:
        print(f"\n  CPU vs GPU difference:")
        for collision in ['bgk', 'mrt']:
            cpu = results.get((collision, 'cpu'))
            gpu = results.get((collision, 'gpu'))
            if cpu and gpu:
                diff = abs(cpu['err_ux'] - gpu['err_ux'])
                print(f"    {collision.upper()}: |L2_cpu - L2_gpu| = {diff:.6e}")


if __name__ == '__main__':
    main()
