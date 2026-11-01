"""The native compiler never fuses on its own, also under a flag override.

A default build keeps contraction off (user manual, Numerical semantics,
"Build modes"); ``gelb-run`` puts ``-ffp-contract=off`` in front of
``GELB_CXXFLAGS`` and ``GELB_FFLAGS``, so an override that does not
mention contraction (an ``-O2`` build, the default plus ``-g``) still
rounds every multiply and addition once, and only an explicit
``-ffp-contract=fast`` of the user's own fuses. The probe is
``sqrt(a*a - b*b)`` with ``a == b``: unfused it is exactly 0, fused the
difference is one rounding error, negative in about half of the cells,
whose square root is NaN.
"""
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from gelb.tests.integration._toolchain import (
    requires_compiler, requires_cpp_highway_compiler)

netCDF4 = pytest.importorskip('netCDF4')

ROOT = Path(__file__).resolve().parents[3]

PROBE = """
simulation_description("contraction probe: sqrt(a*a - b*b) with a == b");
global_constants { const int N = 16; }
lattices { lattice f(2, 2, real, {N, N}, {true, true}); }
initializer Init {
    f.out[x, y | 0] = 0.1 + 0.0137 * x + 0.00731 * y;
    f.out[x, y | 1] = 0.1 + 0.0137 * x + 0.00731 * y;
}
dynamic Step {
    f.out[x, y | 0] = f.in[x, y | 0];
    f.out[x, y | 1] = f.in[x, y | 1];
}
gauge G -> (real r) {
    real a = f.in[x, y | 0];
    real b = f.in[x, y | 1];
    r = sqrt(a * a - b * b);
}
node_classes { node_class BULK(Init, Step, G); }
geometry { nodes[:, :] = BULK; }
"""

BACKENDS = [pytest.param('cpu_highway', marks=requires_cpp_highway_compiler),
            pytest.param('cpu_fortran_serial', marks=requires_compiler)]
OVERRIDE = {   # an ordinary override that says nothing about contraction
    'cpu_highway': ('GELB_CXXFLAGS', '-std=c++17 -O2 -march=native'),
    'cpu_fortran_serial': ('GELB_FFLAGS', '-O2 -march=native -ffree-line-length-none'),
}


def _host_has_fma():
    """Contraction needs a fused multiply-add instruction to fuse into."""
    cpuinfo = Path('/proc/cpuinfo')
    if not cpuinfo.exists():
        return True     # arm64 and macOS: always
    return ' fma ' in cpuinfo.read_text() or ' asimd ' in cpuinfo.read_text()


def nan_count(tmp_path, backend, variable, flags):
    path = tmp_path / 'probe.gelb'
    path.write_text(PROBE)
    result = subprocess.run(
        [str(ROOT / 'scripts/gelb-run'), '-b', backend, '-n', '1', str(path)],
        cwd=tmp_path, env=dict(os.environ, GELB_PYTHON=sys.executable, **{variable: flags}),
        capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stdout + result.stderr
    with netCDF4.Dataset(tmp_path / 'probe.nc') as nc:
        return int(np.isnan(np.asarray(nc.variables['r'][:])).sum())


@pytest.mark.parametrize('backend', BACKENDS)
def test_an_override_without_a_contraction_flag_keeps_it_off(tmp_path, backend):
    variable, flags = OVERRIDE[backend]
    assert nan_count(tmp_path, backend, variable, flags) == 0


@pytest.mark.parametrize('backend', BACKENDS)
def test_an_explicit_fast_contraction_still_wins(tmp_path, backend):
    variable, flags = OVERRIDE[backend]
    if not _host_has_fma():
        pytest.skip('no fused multiply-add on this host')
    assert nan_count(tmp_path, backend, variable, flags + ' -ffp-contract=fast') > 0
