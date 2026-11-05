"""A node class with no cells runs none of its blocks, on every backend.

A class can end up with no cells: every paint of it overridden, a
``where`` that matches nothing, a reversed range, or a ``border()``
rule that converts all of its cells (user manual, GeLB in 10 minutes:
geometry paints).  Its initializer, dynamic and gauge then run nowhere,
so every other cell keeps its own class's values, and a gauge field
that only the empty class writes holds NaN (real) or 0 (integer) at
every cell.  The values are exact, so the backends and layouts must
agree bit for bit.
"""

import os
import pathlib
import subprocess
import sys

import numpy as np
import pytest
from click.testing import CliRunner

from gelb.backends.highway import common
from gelb.gelbc import cli
from gelb.tests.integration._toolchain import (
    requires_compiler, requires_cpp_highway_compiler,
    requires_gpu_cuda_cpp_compiler)

netCDF4 = pytest.importorskip("netCDF4")

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_GELB_RUN = _ROOT / "scripts" / "gelb-run"

# Every class with cells starts at x - 31.5 and adds 1 per step; the
# empty class OBST would write -999 (or -555 in its own gauge field).
PROGRAM = """
simulation_description("a node class with no cells");
global_constants {{ const real R = 0.0; }}
lattices {{ lattice f({lattice}); }}
initializer Init {{ f.out[{c} | :] = real(x) - 31.5; }}
initializer InitO {{ f.out[{c} | :] = -999.0; }}
dynamic Step {{ f.out[{c} | :] = f.in[{c} | :] + 1.0; }}
dynamic StepO {{ f.out[{c} | :] = -999.0; }}
gauge GB -> (real v) {{ v = f.in[{c} | 0]; }}
gauge GO -> (real v) {{ v = -555.0; }}
gauge GW -> (real w) {{ w = -555.0; }}
gauge GK -> (int k) {{ k = 7; }}
node_classes {{
{classes}
}}
geometry {{
{paints}
}}
"""

_2D = dict(lattice="2, 9, real, {64, 8}, {true, true}", c="x, y")
_OBST = ("    node_class BULK(Init, Step, GB);\n"
         "    node_class OBST(InitO, StepO, GB);")
_WHERE_2D = ("    nodes[:, :] = BULK;\n"
             "    nodes[where (real(x) - 32.0)^2 + (real(y) - 4.0)^2 < R^2]"
             " = OBST;")

# name: (lattice and coordinates, classes, paints)
SHAPES = {
    "overwritten": (_2D, _OBST + "\n    node_class WALL(Init, Step, GB);",
                    "    nodes[:, :] = BULK;\n    nodes[10:20, 2:5] = OBST;\n"
                    "    nodes[10:20, 2:5] = WALL;"),
    "where_matches_nothing": (_2D, _OBST, _WHERE_2D),
    "reversed_range": (_2D, _OBST,
                       "    nodes[:, :] = BULK;\n"
                       "    nodes[40:30, 2:5] = OBST;"),
    # The paper cylinder's pattern: a masked obstacle and its border().
    "border_of_an_empty_class": (
        _2D,
        "    node_class BULK(Init, Step, GB);\n"
        "    node_class SOLID() masked;\n"
        "    node_class WALL(InitO, StepO, GB);",
        "    nodes[:, :] = BULK;\n"
        "    nodes[where (real(x) - 32.0)^2 + (real(y) - 4.0)^2 < R^2]"
        " = SOLID;\n"
        "    border(SOLID) = WALL;"),
    "border_converts_every_cell": (
        _2D, _OBST + "\n    node_class WALL(Init, Step, GB);",
        "    nodes[:, :] = BULK;\n    nodes[10:11, 3:4] = OBST;\n"
        "    border(OBST) = WALL;"),
    "static": (_2D,
               "    node_class BULK(Init, Step, GB);\n"
               "    node_class OBST(InitO, GB);", _WHERE_2D),
    "own_gauge": (_2D,
                  "    node_class BULK(Init, Step, GB);\n"
                  "    node_class OBST(InitO, StepO, GO);", _WHERE_2D),
    "one_d": (dict(lattice="1, 3, real, 64, true", c="x"), _OBST,
              "    nodes[:] = BULK;\n"
              "    nodes[where (real(x) - 32.0)^2 < R^2] = OBST;"),
    "three_d": (dict(lattice="3, 7, real, {64, 8, 4}, {true, true, true}",
                     c="x, y, z"), _OBST,
                "    nodes[:, :, :] = BULK;\n"
                "    nodes[where (real(x) - 32.0)^2 + (real(y) - 4.0)^2"
                " < R^2] = OBST;"),
}


def _program(shape):
    lattice, classes, paints = SHAPES[shape]
    return PROGRAM.format(classes=classes, paints=paints, **lattice)


CONFIGS = [
    pytest.param("cpu_fortran_serial", None, marks=requires_compiler,
                 id="fortran"),
    *(pytest.param("cpu_highway", layout,
                   marks=requires_cpp_highway_compiler,
                   id=f"highway-{layout}")
      for layout in ("soa", "aos", "cbt")),
    pytest.param("gpu_cuda_cpp", None, marks=requires_gpu_cuda_cpp_compiler,
                 id="cuda"),
]


def _run(directory, backend, source, layout=None, steps=2, defines=()):
    directory.mkdir()
    path = directory / "probe.gelb"
    path.write_text(source)
    env = dict(os.environ, GELB_PYTHON=sys.executable)
    if layout is not None:
        env["GELBC_EXTRA"] = f"--storage-layout {layout}"
    result = subprocess.run(
        [str(_GELB_RUN), "-b", backend, "-n", str(steps), "-w", "1",
         *(arg for d in defines for arg in ("-D", d)), str(path)],
        cwd=directory, env=env, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stdout + result.stderr
    with netCDF4.Dataset(next(directory.glob("*.nc"))) as nc:
        nc.set_auto_mask(False)
        return {name: np.asarray(var[:]) for name, var in nc.variables.items()}


def _skip_unsupported(shape, layout):
    if layout == "cbt" and not common._detect_avx512_available():
        pytest.skip("the cbt layout needs an AVX-512 host")


@pytest.mark.parametrize("backend, layout", CONFIGS)
@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_an_empty_class_runs_nothing(tmp_path, shape, backend, layout):
    _skip_unsupported(shape, layout)
    v = _run(tmp_path / "run", backend, _program(shape), layout)["v"]
    # Records t = 0, 1, 2; the x axis is the last one.
    x = np.arange(v.shape[-1], dtype=np.float64)
    t = np.arange(3, dtype=np.float64)
    expected = (x - 31.5) + t.reshape((3,) + (1,) * (v.ndim - 1))
    np.testing.assert_array_equal(v, np.broadcast_to(expected, v.shape))


# A static program whose only dynamic belongs to the empty class (CUDA
# then has no step to capture in a graph).
ONLY_DYNAMIC_EMPTY = PROGRAM.format(
    classes="    node_class BULK(Init, GB);\n"
            "    node_class OBST(InitO, StepO, GB);",
    paints=_WHERE_2D, **_2D)


@pytest.mark.parametrize("backend, layout", CONFIGS)
def test_the_only_dynamic_is_empty(tmp_path, backend, layout):
    _skip_unsupported("only_dynamic", layout)
    v = _run(tmp_path / "run", backend, ONLY_DYNAMIC_EMPTY, layout)["v"]
    x = np.arange(64, dtype=np.float64)
    np.testing.assert_array_equal(v, np.broadcast_to(x - 31.5, v.shape))


# Fields that only the empty class's gauge writes stay in the file.
GAUGE_ONLY = {
    "real": ("GW", "w", np.nan),
    "int": ("GK", "k", 0),
}


@pytest.mark.parametrize("backend, layout", CONFIGS)
@pytest.mark.parametrize("kind", sorted(GAUGE_ONLY))
def test_a_field_only_the_empty_class_writes(tmp_path, kind, backend,
                                             layout):
    _skip_unsupported(kind, layout)
    gauge, name, fill = GAUGE_ONLY[kind]
    source = PROGRAM.format(
        classes="    node_class BULK(Init, Step, GB);\n"
                f"    node_class OBST(Init, Step, {gauge});",
        paints=_WHERE_2D, **_2D)
    data = _run(tmp_path / "run", backend, source, layout)
    assert data[name].shape == data["v"].shape
    np.testing.assert_array_equal(
        data[name].astype(np.float64),
        np.full(data[name].shape, fill, dtype=np.float64))


@requires_cpp_highway_compiler
def test_the_paper_cylinder_without_an_obstacle(tmp_path):
    """With R = 0 the cylinder's SOLID and WALL classes are empty, and
    the channel carries the inflow, uy = -U_IN = -0.05 (the outlet's
    transient adds a cross flow of order 1e-3).  When the empty WALL ran
    over the whole grid, every cell was at rest: uy = 0, rho = 1."""
    program = (_ROOT / "examples" / "softwarex-2026-paper"
               / "flow_past_cylinder_2d_bgk_zouhe.gelb")
    data = _run(tmp_path / "run", "cpu_highway", program.read_text(),
                steps=4, defines=("NX=64", "NY=96", "R=0"))
    np.testing.assert_allclose(data["uy"][-1], -0.05, atol=1e-3)
    assert np.abs(data["ux"][-1]).max() < 1e-2


def _source(tmp_path, source, *args):
    path = tmp_path / "prog.gelb"
    path.write_text(source)
    out = tmp_path / "prog.out"
    result = CliRunner().invoke(cli, [str(path), "-o", str(out), *args])
    assert result.exit_code == 0, result.output
    return out.read_text()


@pytest.mark.parametrize("layout", ["soa", "aos"])
def test_no_loop_is_emitted_for_an_empty_class(tmp_path, layout):
    cpp = _source(tmp_path, _program("overwritten"),
                  "--storage-layout", layout)
    assert "(OBST)" not in cpp
    assert "(WALL)" in cpp


# An empty masked class zeroes nothing: Highway emits no zero-init loop,
# and CUDA no zero-init kernel (whose guard would have no term).
EMPTY_MASKED = PROGRAM.format(
    classes="    node_class BULK(Init, Step, GB);\n"
            "    node_class SOLID() masked;",
    paints=_WHERE_2D.replace("OBST", "SOLID"), **_2D)


def test_an_empty_masked_class_zeroes_nothing(tmp_path):
    cpp = _source(tmp_path, EMPTY_MASKED, "--storage-layout", "aos")
    assert "Masked zero-init" not in cpp
    cu = _source(tmp_path, EMPTY_MASKED, "-b", "gpu_cuda_cpp")
    assert "gelb_masked_zero_init" not in cu
    assert "if (!())" not in cu


def test_an_empty_masked_class_beside_an_occupied_one(tmp_path):
    """CUDA's zero-init guard names only the occupied masked class."""
    source = PROGRAM.format(
        classes="    node_class BULK(Init, Step, GB);\n"
                "    node_class SOLID() masked;\n"
                "    node_class OBST() masked;",
        paints="    nodes[:, :] = BULK;\n    nodes[20:21, 2:3] = SOLID;\n"
               "    nodes[40:30, 2:5] = OBST;", **_2D)
    cu = _source(tmp_path, source, "-b", "gpu_cuda_cpp")
    assert "gelb_masked_zero_init" in cu
    assert "|| true" not in cu


def test_an_empty_dynamic_is_not_captured_in_a_cuda_graph(tmp_path):
    """With only an empty class's dynamic, CUDA has no step to capture
    and falls back to plain launches."""
    cu = _source(tmp_path, ONLY_DYNAMIC_EMPTY, "-b", "gpu_cuda_cpp")
    assert "cudaStreamBeginCapture" not in cu
    assert "cudaGraphLaunch" not in cu
