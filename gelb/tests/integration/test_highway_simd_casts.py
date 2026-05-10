"""cpu_highway: integer arithmetic on the spatial x, assigned to a real
lattice, inside a SIMD body.  In the vector body x is already a double
vector (``gelb_xv``), so ``100 + x`` must not be wrapped in
``static_cast<double>(...)``, which does not compile for a vector."""

import os
import pathlib
import subprocess
import sys

import pytest

from gelb.gelbc import cli as gelbc_cli
from gelb.tests.integration._toolchain import requires_cpp_highway_compiler

netCDF4 = pytest.importorskip("netCDF4")

_REPO = pathlib.Path(__file__).resolve().parents[3]

_SOURCE = """simulation_description("int arithmetic on x in a SIMD body");
lattices { lattice u(1, 2, real, 8, true); }
initializer I { u.out[x | 0] = 100 + x; u.out[x | 1] = 3 * x - 1; }
dynamic D { u.out[x | :] = u.in[x | :]; }
gauge G -> (real v, real w) { v = u.in[x | 0]; w = u.in[x | 1]; }
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""


def test_no_cast_of_a_vector(tmp_path):
    src = tmp_path / "cast.gelb"
    src.write_text(_SOURCE)
    out = tmp_path / "cast.cpp"
    gelbc_cli.main(args=[str(src), "--backend", "cpu_highway", "-o", str(out)],
                   standalone_mode=False)
    assert "static_cast<double>((hn::" not in out.read_text()


@requires_cpp_highway_compiler
def test_values(tmp_path):
    src = tmp_path / "cast.gelb"
    src.write_text(_SOURCE)
    subprocess.run([str(_REPO / "scripts" / "gelb-run"), "-b", "cpu_highway",
                    "-n", "1", "-w", "1", str(src)],
                   cwd=tmp_path, env=dict(os.environ, GELB_PYTHON=sys.executable),
                   check=True, capture_output=True, timeout=600)
    nc = netCDF4.Dataset(next(tmp_path.glob("*.nc")))
    assert nc["v"][0].astype(int).tolist() == [100 + x for x in range(8)]
    assert nc["w"][0].astype(int).tolist() == [3 * x - 1 for x in range(8)]
