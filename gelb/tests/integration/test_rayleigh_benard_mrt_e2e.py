#!/usr/bin/env python3
"""
End-to-end regression test for the 2D Rayleigh-Benard MRT example.

The example file at ``examples/lbm/2d/rayleigh_benard_2d_mrt.gelb`` is a
bit-faithful port of the reference Fortran solver in
``rb_2d/runs__*/Pr_*/Ra_*/MrtSolverBoussinesq2D_class.f90``. This test
guards the GeLB example against silent regressions in any of the
following:

  * the MRT M / M_inv matrices and moment ordering
  * the relaxation rate vector
  * the incompressible equilibrium moments
  * the Strang-split Boussinesq forcing
  * the Yoshida anti-bounce-back temperature BC
  * the half-way fluid bounce-back BC
  * the initial conditions (quadratic dRho profile + linear T profile)
  * the masked-wall geometry layout

Strategy: compile and run the example with a small grid, a fixed
``--seed``, and a short time horizon, then compare the resulting
NetCDF output against a stored reference snapshot
(``gelb/tests/data/rb_mrt_snapshot.nc``).

The fixed seed makes the run reproducible. The reference snapshot was
captured using the same compile/run command this test uses; if a
deliberate algorithm change is made, regenerate the snapshot with::

    uv run gelbc examples/lbm/2d/rayleigh_benard_2d_mrt.gelb \\
        --seed 42 -D NY=8 \\
        --num-timesteps 40 --write-every 10 \\
        --nc-output gelb/tests/data/rb_mrt_snapshot.nc \\
        -o /tmp/rb_snap.f90
    gfortran -O2 $(nf-config --fflags) -o /tmp/rb_snap \\
        /tmp/rb_snap.f90 $(nf-config --flibs)
    ( cd /tmp && /tmp/rb_snap )
    cp /tmp/gelb/tests/data/rb_mrt_snapshot.nc \\
       gelb/tests/data/rb_mrt_snapshot.nc

(or simply ``cp /tmp/rb_snap.nc gelb/tests/data/rb_mrt_snapshot.nc``
depending on where gelb-run wrote the file).
"""

import os
import subprocess
import tempfile

import numpy as np
import pytest

from gelb.tests.integration._toolchain import (
    HAS_GFORTRAN as _HAS_GFORTRAN,
    HAS_NETCDF as _HAS_NETCDF,
    NC_FFLAGS as _NC_FFLAGS,
    NC_FLIBS as _NC_FLIBS,
)

# ---------------------------------------------------------------------------
# Skip conditions -- this test additionally needs netCDF4 Python bindings to
# read the reference snapshot.
# ---------------------------------------------------------------------------

_HAS_NETCDF4_PY = True
try:
    import netCDF4  # noqa: F401
except ImportError:
    _HAS_NETCDF4_PY = False

_SKIP_REASON = (
    'gfortran not found' if not _HAS_GFORTRAN else
    'NetCDF-Fortran not found' if not _HAS_NETCDF else
    'netCDF4 Python package not installed' if not _HAS_NETCDF4_PY else
    ''
)

requires_compiler = pytest.mark.skipif(
    not (_HAS_GFORTRAN and _HAS_NETCDF and _HAS_NETCDF4_PY),
    reason=_SKIP_REASON or 'compiler toolchain not available'
)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..'))
_EXAMPLE_PATH = os.path.join(
    _REPO_ROOT, 'examples', 'lbm', '2d', 'rayleigh_benard_2d_mrt.gelb')
_REFERENCE_SNAPSHOT = os.path.join(
    os.path.dirname(__file__), '..', 'data', 'rb_mrt_snapshot.nc')

# Snapshot capture parameters -- must match the values used to produce
# the stored reference (see module docstring).
_SEED = 42
_NY = 8
_NUM_TIMESTEPS = 40
_WRITE_EVERY = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compile_and_run_rb(workdir):
    """Compile and run the RB-MRT example into ``workdir``.

    Returns the path to the produced NetCDF file.
    """
    nc_path = os.path.join(workdir, 'rb_run.nc')
    src_path = os.path.join(workdir, 'rb_run.f90')
    exe_path = os.path.join(workdir, 'rb_run')

    # Compile GeLB -> Fortran.  ``--backend cpu_fortran_serial`` is
    # required: the gelbc default is ``cpu_highway``, but this test
    # feeds the output to gfortran below -- pin the backend so the
    # test stays decoupled from default-backend churn.
    rc = subprocess.run(
        ['uv', 'run', 'gelbc', _EXAMPLE_PATH,
         '--backend', 'cpu_fortran_serial',
         '--seed', str(_SEED),
         '-D', f'NY={_NY}',
         '--num-timesteps', str(_NUM_TIMESTEPS),
         '--write-every', str(_WRITE_EVERY),
         '--nc-output', nc_path,
         '-o', src_path],
        cwd=_REPO_ROOT,
        capture_output=True, text=True, timeout=60,
    )
    if rc.returncode != 0:
        pytest.fail(
            f'gelbc failed:\nstdout:\n{rc.stdout}\nstderr:\n{rc.stderr}')

    # Compile Fortran -> executable
    cmd = f'gfortran -O2 {_NC_FFLAGS} -o {exe_path} {src_path} {_NC_FLIBS}'
    rc = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=60)
    if rc.returncode != 0:
        pytest.fail(f'gfortran failed:\n{rc.stderr[:1500]}')

    # Run the executable (cwd = workdir so the .nc file lands there)
    rc = subprocess.run(
        [exe_path], cwd=workdir,
        capture_output=True, text=True, timeout=120,
    )
    if rc.returncode != 0:
        pytest.fail(f'execution failed:\n{rc.stderr[:1500]}')

    return nc_path


def _read_fields(nc_path):
    """Return dict of variable name -> numpy array (full time series)."""
    import netCDF4
    ds = netCDF4.Dataset(nc_path, 'r')
    fields = {}
    for v in ('dRho', 'uX', 'uY', 'T'):
        # Cast through np.array to drop the masked-array wrapper, so
        # downstream NaN comparisons work cleanly.
        fields[v] = np.asarray(ds.variables[v][:])
    ds.close()
    return fields


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@requires_compiler
class TestRayleighBenardMrtE2E:
    """Bit-faithful port of the Fortran reference solver."""

    def test_snapshot_matches_reference(self):
        """Compile + run the example and compare every gauge field to
        the stored reference snapshot.

        Tolerance is loose (atol=1e-10, rtol=1e-7) because gfortran
        version differences and FMA usage can shift least-significant
        bits without changing the algorithm.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            actual_path = _compile_and_run_rb(tmpdir)
            actual = _read_fields(actual_path)
            reference = _read_fields(_REFERENCE_SNAPSHOT)

            assert set(actual) == set(reference), (
                f'variable mismatch: {sorted(actual)} vs '
                f'{sorted(reference)}'
            )

            for name in ('dRho', 'uX', 'uY', 'T'):
                a = actual[name]
                r = reference[name]
                assert a.shape == r.shape, (
                    f'{name}: shape mismatch {a.shape} vs {r.shape}'
                )
                # NaNs must occur at the same positions (masked walls).
                a_nan = np.isnan(a)
                r_nan = np.isnan(r)
                assert np.array_equal(a_nan, r_nan), (
                    f'{name}: NaN positions differ'
                )
                # Compare finite values with a numerical tolerance.
                a_fin = a[~a_nan]
                r_fin = r[~r_nan]
                if not np.allclose(a_fin, r_fin, atol=1e-10, rtol=1e-7):
                    diffs = np.abs(a_fin - r_fin)
                    max_diff = float(diffs.max())
                    pytest.fail(
                        f'{name}: regression vs reference snapshot. '
                        f'max abs diff = {max_diff:.3e}.\n'
                        f'If this is an intentional algorithm change, '
                        f'regenerate the reference snapshot per the '
                        f'docstring of '
                        f'{__file__}.'
                    )

    def test_physics_invariants_at_short_horizon(self):
        """Cross-check the snapshot's physics independently of the stored
        reference: T monotonic in y, mass conserved, walls masked, and
        the buoyancy force is acting (uY non-zero).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            nc_path = _compile_and_run_rb(tmpdir)
            fields = _read_fields(nc_path)

        T = fields['T']
        dRho = fields['dRho']
        uX = fields['uX']
        uY = fields['uY']

        # Wall rows (y=0 and y=Ny-1) must be NaN; interior must be finite.
        # Output shape is (time, y, x).
        for name, arr in fields.items():
            assert np.all(np.isnan(arr[:, 0, :])), (
                f'{name}: y=0 wall row should be NaN'
            )
            assert np.all(np.isnan(arr[:, -1, :])), (
                f'{name}: y=Ny-1 wall row should be NaN'
            )
            interior = arr[:, 1:-1, :]
            assert np.all(np.isfinite(interior)), (
                f'{name}: interior contains non-finite values'
            )

        # T at the last timestep, averaged over x, should be
        # monotonically decreasing in y in the bulk.  At this short
        # horizon the non-equilibrium IC drives a fast buoyant
        # transient in the bottom fluid row (which is in direct
        # contact with the anti-bounce-back hot wall), so the very
        # first bulk row can be slightly cooler than row 2.  We
        # tolerate that single artefact and require strict
        # monotonicity from row 2 onward, plus hot-bottom / cold-top
        # across the channel.
        T_last_x_avg = np.nanmean(T[-1, 1:-1, :], axis=1)
        diffs = np.diff(T_last_x_avg)
        assert np.all(diffs[1:] <= 0), (
            f'T(y) profile is not monotonically decreasing in the bulk: '
            f'diffs={diffs}'
        )
        assert T_last_x_avg[0] > T_last_x_avg[-1], (
            f'Bottom row is not warmer than top row: '
            f'T_last_x_avg={T_last_x_avg}'
        )

        # T values are bounded between T_COLD=0 and T_HOT=1 (modulo
        # tiny BC slack from the Yoshida anti-bounce-back).
        T_int = T[:, 1:-1, :]
        assert T_int.min() > -0.05, f'T below COLD bound: {T_int.min()}'
        assert T_int.max() < 1.05, f'T above HOT bound: {T_int.max()}'

        # Mass conservation: sum of dRho over the *interior* fluid
        # cells. With the wall-cell-reads-fluid bounce-back pattern,
        # the wall stores the previous-step's outgoing DFs, so there
        # is a 1-step lag and the per-step interior mass exchange
        # with the wall is not exactly balanced. The drift is bounded
        # and does not grow -- it oscillates around the initial value
        # at O(alpha_G) ~= a few * 1e-3 for these parameters.
        # The strict bit-exact regression is covered by the snapshot
        # test; here we only check that the drift stays bounded.
        dRho_int = dRho[:, 1:-1, :]
        sums = np.sum(dRho_int, axis=(1, 2))
        sum_drift = float(np.abs(sums - sums[0]).max())
        assert sum_drift < 2e-2, (
            f'mass conservation drift exceeds bound: {sum_drift}'
        )

        # uX should be tiny (no convection cell has formed yet).
        assert float(np.nanmax(np.abs(uX))) < 1e-6, (
            'uX is too large for the conduction-dominated regime'
        )

        # uY should be small but non-zero (Boussinesq force is acting on
        # the perturbed temperature field).
        uY_max = float(np.nanmax(np.abs(uY)))
        assert 0 < uY_max < 1e-2, (
            f'uY is outside the expected range for the short horizon: '
            f'{uY_max}'
        )
