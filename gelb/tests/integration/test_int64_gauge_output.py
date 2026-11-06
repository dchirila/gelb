"""An ``int`` or ``int64`` gauge output is a 64-bit integer in the
output file, on every backend.

``int`` is ``int64`` (user manual, GeLB in 10 minutes: Types), and its
gauge field is ``int64`` in the file (Hello World: ``gauge``, what the
program outputs).  Values outside the 32-bit range are stored exactly
at every record, and ``-2147483647``, the fill value of a 32-bit NetCDF
integer, reads back as a value, not as missing.  The values are exact,
so the backends must agree bit for bit, and every backend writes each
gauge type with the same NetCDF type.
"""

import os
import pathlib
import subprocess
import sys

import numpy as np
import pytest

from gelb.backends.highway.common import _NETCDF_TYPE_MAP as CPP_TYPES
from gelb.backends.stage3_backend_cpu_fortran_serial import (
    _NETCDF_TYPE_MAP as FORTRAN_TYPES)
from gelb.tests.integration.test_tutorial_regressions import BACKENDS

netCDF4 = pytest.importorskip("netCDF4")

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_GELB_RUN = _ROOT / "scripts" / "gelb-run"

# On a 16 x 4 lattice: two outputs beyond 2^31 from the start, and one
# that leaves the 32-bit range only at t = 2.
BEYOND = """
simulation_description("int and int64 gauge outputs beyond 32 bits");
lattices { lattice f(2, 9, real, {16, 4}, {true, true}); }
initializer Init { f.out[x, y | :] = real(x); }
dynamic Step { f.out[x, y | :] = f.in[x, y | :]; }
gauge G -> (int big_pos, int64 big_neg, int later) {
    big_pos = 3000000000 + y;
    big_neg = -3000000000 - y;
    later = 2147483646 + t;
}
node_classes { node_class BULK(Init, Step, G); }
geometry { nodes[:, :] = BULK; }
"""

# The 32-bit and 64-bit extremes, and NC_INT's default fill value.
EXTREMES = """
simulation_description("int gauge outputs at the 32-bit and 64-bit extremes");
lattices { lattice f(2, 9, real, {16, 4}, {true, true}); }
initializer Init { f.out[x, y | :] = real(x); }
dynamic Step { f.out[x, y | :] = f.in[x, y | :]; }
gauge G -> (int hi, int lo, int fillv, int64 hi64, int64 lo64) {
    hi = 2147483647;
    lo = -2147483647 - 1;
    fillv = -2147483647;
    hi64 = 9223372036854775807;
    lo64 = -9223372036854775807 - 1;
}
node_classes { node_class BULK(Init, Step, G); }
geometry { nodes[:, :] = BULK; }
"""

# An int lattice that holds values beyond 2^31, gauged as they are.
INT_LATTICE = """
simulation_description("an int lattice beyond 32 bits");
lattices { lattice f(2, 9, int, {16, 4}, {true, true}); }
initializer Init { f.out[x, y | :] = 3000000000 + x; }
dynamic Step { f.out[x, y | :] = f.in[x, y | :] + 1; }
gauge G -> (int v) { v = f.in[x, y | 0]; }
node_classes { node_class BULK(Init, Step, G); }
geometry { nodes[:, :] = BULK; }
"""


def _run(directory, backend, source):
    """Run two steps and return {name: (raw values, mask)} per output."""
    directory.mkdir()
    path = directory / "probe.gelb"
    path.write_text(source)
    result = subprocess.run(
        [str(_GELB_RUN), "-b", backend, "-n", "2", "-w", "1", str(path)],
        cwd=directory, env=dict(os.environ, GELB_PYTHON=sys.executable),
        capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stdout + result.stderr
    with netCDF4.Dataset(next(directory.glob("*.nc"))) as nc:
        return {name: (np.asarray(var[:].data), np.ma.getmaskarray(var[:]))
                for name, var in nc.variables.items()
                if name not in ("x", "y", "time")}


def _expected(values):
    """Broadcast a (t, y, x) expression over three records."""
    t, y, x = np.meshgrid(np.arange(3, dtype=np.int64),
                          np.arange(4, dtype=np.int64),
                          np.arange(16, dtype=np.int64), indexing="ij")
    return np.broadcast_to(values(t, y, x), t.shape)


@pytest.mark.parametrize("backend", BACKENDS)
def test_int_outputs_beyond_32_bits(tmp_path, backend):
    data = _run(tmp_path / "run", backend, BEYOND)
    expected = {
        "big_pos": _expected(lambda t, y, x: 3000000000 + y),
        "big_neg": _expected(lambda t, y, x: -3000000000 - y),
        "later": _expected(lambda t, y, x: 2147483646 + t),
    }
    _check(data, expected)


@pytest.mark.parametrize("backend", BACKENDS)
def test_int_outputs_at_the_extremes(tmp_path, backend):
    data = _run(tmp_path / "run", backend, EXTREMES)
    expected = {"hi": _expected(lambda t, y, x: 2147483647),
                "lo": _expected(lambda t, y, x: -2147483648),
                "fillv": _expected(lambda t, y, x: -2147483647),
                "hi64": _expected(lambda t, y, x: 2**63 - 1),
                "lo64": _expected(lambda t, y, x: -2**63)}
    _check(data, expected)


def _check(data, expected):
    assert sorted(data) == sorted(expected)
    for name, (values, mask) in data.items():
        assert values.dtype == np.int64, name
        np.testing.assert_array_equal(values, expected[name], err_msg=name)
        assert not mask.any(), name


@pytest.mark.parametrize("backend", BACKENDS)
def test_an_int_lattice_beyond_32_bits(tmp_path, backend):
    values, mask = _run(tmp_path / "run", backend, INT_LATTICE)["v"]
    assert values.dtype == np.int64
    np.testing.assert_array_equal(
        values, _expected(lambda t, y, x: 3000000000 + x + t))
    assert not mask.any()


def test_gauge_types_match_the_cpp_backends():
    """Every gauge type is written with the NetCDF type the C++
    backends use."""
    for dtype, cpp_type in CPP_TYPES.items():
        assert FORTRAN_TYPES[dtype] == cpp_type.replace("NC_", "NF90_"), dtype
