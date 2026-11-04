"""A gauge output that is not binary64 takes the scalar gauge path on
``cpu_highway``, and the backends agree on its values.

The vector gauge path stores a binary64 vector into the output buffer,
so a gauge with an integer, ``real32`` or ``bool`` output on a real
lattice is emitted as scalar code, where each cell converts its value
to the output's type: an integer truncates toward zero (user manual,
Numerical semantics: Types and promotion, What must agree).  The
lattice is wide enough for the vector body to fire, and a gauge with
only binary64 outputs keeps the vector store.  Gauges of different
classes that share an output name fill one field, whose type is that of
the first-painted class's declaration; a real gauge filling an integer,
``real32`` or ``bool`` field also takes the scalar path, and every
backend stores the same values.
"""

import os
import pathlib
import re
import subprocess
import sys

import numpy as np
import pytest
from click.testing import CliRunner

from gelb.backends.highway import common
from gelb.gelbc import cli
from gelb.tests.integration._toolchain import (
    requires_compiler, requires_cpp_highway_compiler)
from gelb.tests.integration.test_tutorial_regressions import BACKENDS, run_source

netCDF4 = pytest.importorskip("netCDF4")

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_GELB_RUN = _ROOT / "scripts" / "gelb-run"

# 64 cells along x: more than one SIMD chunk, plus the periodic seams.
# The lattice holds x - 3.5, so that a cast truncates negative and
# positive fractions toward zero.
INT_OUTPUTS = """
simulation_description("integer gauge outputs on a real lattice");
lattices { lattice f(2, 9, real, {64, 8}, {true, true}); }
initializer Init { f.out[x, y | :] = real(x) - 3.5; }
dynamic Step { f.out[x, y | :] = f.in[x, y | :]; }
gauge G -> (int tt, int tx, int64 tc, real s) {
    tt = t;
    tx = x;
    int k = int(f.in[x, y | 0]);
    tc = k * 2;
    s = f.in[x, y | 0];
}
node_classes { node_class BULK(Init, Step, G); }
geometry { nodes[:, :] = BULK; }
"""

ONE_OUTPUT = """
simulation_description("one gauge output of type {dtype}");
lattices {{ lattice f(2, 9, real, {{64, 8}}, {{true, true}}); }}
initializer Init {{ f.out[x, y | :] = real(x) - 3.5; }}
dynamic Step {{ f.out[x, y | :] = f.in[x, y | :]; }}
gauge G -> ({dtype} v) {{ v = {value}; }}
node_classes {{ node_class BULK(Init, Step, G); }}
geometry {{ nodes[:, :] = BULK; }}
"""


def _check(data):
    time = data["time"]
    x = data["x"][None, :]
    value = x - 3.5
    assert time.tolist() == [0, 1, 2]
    for k, step in enumerate(time):
        assert (data["tt"][k] == step).all()
        assert (data["tx"][k] == x).all()
        assert (data["tc"][k] == 2 * np.trunc(value)).all()
        assert (data["s"][k] == value).all()


@pytest.mark.parametrize("backend", BACKENDS)
def test_integer_outputs_agree_across_backends(tmp_path, backend):
    _check(run_source(tmp_path, backend, INT_OUTPUTS, timesteps=2))


def _layout_available(layout):
    return layout != "cbt" or common._detect_avx512_available()


def _run(directory, backend, source, layout=None):
    directory.mkdir()
    path = directory / "probe.gelb"
    path.write_text(source)
    env = dict(os.environ, GELB_PYTHON=sys.executable)
    if layout is not None:
        env["GELBC_EXTRA"] = f"--storage-layout {layout}"
    result = subprocess.run(
        [str(_GELB_RUN), "-b", backend, "-n", "2", "-w", "1", str(path)],
        cwd=directory, env=env, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stdout + result.stderr
    with netCDF4.Dataset(next(directory.glob("*.nc"))) as nc:
        return {name: np.asarray(var[:]) for name, var in nc.variables.items()}


@requires_cpp_highway_compiler
@pytest.mark.parametrize("layout", ["soa", "aos", "cbt"])
def test_integer_outputs_on_every_highway_layout(tmp_path, layout):
    if not _layout_available(layout):
        pytest.skip("the cbt layout needs an AVX-512 host")
    _check(_run(tmp_path / layout, "cpu_highway", INT_OUTPUTS, layout))


# The WALL row is painted first, so its gauge's declaration types the
# shared field v; the BULK rows fill it from a real gauge.
SHARED_NAME = """
simulation_description("two gauges share the output name v");
lattices {{ lattice f(2, 9, real, {{64, 8}}, {{true, false}}); }}
initializer Init {{ f.out[x, y | :] = real(x) - 3.5; }}
dynamic Step {{ f.out[x, y | :] = f.in[x, y | :]; }}
gauge GFirst -> ({dtype} v) {{ v = {value}; }}
gauge GReal -> (real v) {{ v = f.in[x, y | 0]; }}
node_classes {{
    node_class WALL(Init, Step, GFirst);
    node_class BULK(Init, Step, GReal);
}}
geometry {{
    nodes[:, 0] = WALL;
    nodes[:, 1:7] = BULK;
}}
"""

_FIRST_VALUES = {
    "int": "int(f.in[x, y | 0])",
    "real32": "real32(f.in[x, y | 0])",
    "bool": "f.in[x, y | 0] > 0.0",
}


@requires_compiler
@requires_cpp_highway_compiler
@pytest.mark.parametrize("layout", ["soa", "cbt"])
@pytest.mark.parametrize("dtype", sorted(_FIRST_VALUES))
def test_a_real_gauge_filling_a_shared_non_double_field(tmp_path, dtype, layout):
    if not _layout_available(layout):
        pytest.skip("the cbt layout needs an AVX-512 host")
    source = SHARED_NAME.format(dtype=dtype, value=_FIRST_VALUES[dtype])
    reference = _run(tmp_path / "fortran", "cpu_fortran_serial", source)
    data = _run(tmp_path / layout, "cpu_highway", source, layout)
    assert data["v"].dtype.kind == reference["v"].dtype.kind
    assert np.array_equal(data["v"], reference["v"])


def _highway_source(tmp_path, source):
    path = tmp_path / "prog.gelb"
    path.write_text(source)
    out = tmp_path / "prog.cpp"
    result = CliRunner().invoke(
        cli, [str(path), "-o", str(out), "--storage-layout", "soa"])
    assert result.exit_code == 0, result.output
    return out.read_text()


# Any Highway store of a vector into the output buffer, and a scalar
# assignment to one of its elements.
_VECTOR_STORE = re.compile(r"hn::(?:Store\w*|Stream)\s*\([^;]*&gelb_buf_v\b")
_SCALAR_STORE = re.compile(r"\bgelb_buf_v(?:\[[^\]]+\])+\s*=")


def _one_output(dtype):
    if dtype == "bool":
        value = "f.in[x, y | 0] > 3.0"
    elif dtype in ("real", "real64"):
        value = "f.in[x, y | 0]"
    elif dtype in ("int", "int64"):
        # int is int64; a width cast would send the block to the scalar
        # path by itself.
        value = "int(f.in[x, y | 0])"
    else:
        value = f"{dtype}(f.in[x, y | 0])"
    return ONE_OUTPUT.format(dtype=dtype, value=value)


@pytest.mark.parametrize(
    "dtype", ["int", "int8", "int16", "int32", "int64", "real32", "bool"])
def test_a_non_double_output_takes_the_scalar_gauge_path(tmp_path, dtype):
    cpp = _highway_source(tmp_path, _one_output(dtype))
    assert not _VECTOR_STORE.search(cpp)
    assert _SCALAR_STORE.search(cpp)


@pytest.mark.parametrize("dtype", ["real", "real64"])
def test_a_double_output_keeps_the_vector_gauge_path(tmp_path, dtype):
    cpp = _highway_source(tmp_path, _one_output(dtype))
    assert _VECTOR_STORE.search(cpp)
