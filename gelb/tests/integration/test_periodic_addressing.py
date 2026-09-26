"""Periodic boundaries, end to end: small programs are compiled and run
with ``scripts/gelb-run`` on each CPU backend, and every value is
checked against an independently computed expectation -- never against
another backend, which would share the backends' common storage layout.

Covered: reads at every nearest-neighbour offset in 1-D, 2-D and 3-D
(corners included), reads two or more cells across a periodic edge and
beyond the domain size, gauges that read neighbours (at t=0 and after
buffer swaps), and a radius-2 program against a NumPy reference.
"""

import os
import itertools
import pathlib
import shutil
import subprocess
import sys

import numpy as np
import pytest

from gelb.tests.integration._toolchain import (
    HAS_NETCDF_C,
    requires_cpp_highway_compiler,
)

netCDF4 = pytest.importorskip("netCDF4")

_REPO = pathlib.Path(__file__).resolve().parents[3]
_GELB_RUN = _REPO / "scripts" / "gelb-run"

_requires_gfortran = pytest.mark.skipif(
    not (shutil.which("gfortran") and HAS_NETCDF_C),
    reason="gfortran or NetCDF-C not found")

BACKENDS = [
    pytest.param("cpu_fortran_serial", marks=_requires_gfortran),
    pytest.param("cpu_highway", marks=requires_cpp_highway_compiler),
]

def _run(tmp_path, source, backend, steps=1, defines=()):
    """Compile and run ``source``; return the NetCDF output."""
    src = tmp_path / "prog.gelb"
    src.write_text(source)
    env = dict(os.environ, GELB_PYTHON=sys.executable)
    cmd = [str(_GELB_RUN), "-b", backend, "-n", str(steps), "-w", "1"]
    for define in defines:
        cmd += ["-D", define]
    result = subprocess.run(cmd + [str(src)], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stdout + result.stderr
    return netCDF4.Dataset(next(tmp_path.glob("*.nc")))


def _neighbour_program(sizes, offsets):
    """u holds a distinct value per cell; lattice r stores, one DF per
    offset, the value of u read at that offset.  One step, then the
    gauge reports r."""
    dims = "xyz"[:len(sizes)]
    here = ", ".join(dims)

    def index(offset):
        return ", ".join(
            n if o == 0 else f"{n} {'+' if o > 0 else '-'} {abs(o)}"
            for n, o in zip(dims, offset))

    shape = (f"{sizes[0]}, true" if len(sizes) == 1 else
             "{" + ", ".join(map(str, sizes)) + "}, {"
             + ", ".join(["true"] * len(sizes)) + "}")
    value = " + ".join(f"{10 ** i} * {n}" for i, n in enumerate(dims))
    reads = "\n".join(f"    r.out[{here} | {k}] = u.in[{index(o)} | 0];"
                      for k, o in enumerate(offsets))
    outs = ", ".join(f"real r{k}" for k in range(len(offsets)))
    body = " ".join(f"r{k} = r.in[{here} | {k}];"
                    for k in range(len(offsets)))
    return f"""simulation_description("periodic neighbour reads");
lattices {{ lattice u({len(sizes)}, 1, real, {shape});
           lattice r({len(sizes)}, {len(offsets)}, real, {shape}); }}
initializer I {{ u.out[{here} | 0] = {value}; r.out[{here} | :] = -1.0; }}
dynamic D {{
    u.out[{here} | 0] = u.in[{here} | 0];
{reads}
}}
gauge G -> ({outs}) {{ {body} }}
node_classes {{ node_class B(I, D, G); }}
geometry {{ nodes[{", ".join([":"] * len(sizes))}] = B; }}
"""


def _check_neighbours(nc, sizes, offsets):
    for k, offset in enumerate(offsets):
        got = np.asarray(nc[f"r{k}"][-1])            # dims ([z,] y, x)
        want = np.empty_like(got)
        for index in np.ndindex(*got.shape):
            pos = index[::-1]                          # (x, y[, z])
            cell = [(p + o) % n for p, o, n in zip(pos, offset, sizes)]
            want[index] = sum(10 ** i * c for i, c in enumerate(cell))
        assert np.array_equal(got, want), f"offset {offset}"


@pytest.mark.parametrize("backend", BACKENDS)
def test_1d_nearest_neighbours(tmp_path, backend):
    offsets = [(-1,), (0,), (1,)]
    nc = _run(tmp_path, _neighbour_program((8,), offsets), backend)
    _check_neighbours(nc, (8,), offsets)


@pytest.mark.parametrize("backend", BACKENDS)
def test_1d_wide_and_beyond_the_domain(tmp_path, backend):
    offsets = [(-3,), (-2,), (2,), (3,), (9,), (-10,)]
    nc = _run(tmp_path, _neighbour_program((8,), offsets), backend)
    _check_neighbours(nc, (8,), offsets)


@pytest.mark.parametrize("backend", BACKENDS)
def test_tiny_domain(tmp_path, backend):
    offsets = [(-4,), (-1,), (1,), (2,), (4,)]
    nc = _run(tmp_path, _neighbour_program((3,), offsets), backend)
    _check_neighbours(nc, (3,), offsets)


@pytest.mark.parametrize("backend", BACKENDS)
def test_2d_all_nearest_neighbours(tmp_path, backend):
    offsets = [o for o in itertools.product((-1, 0, 1), repeat=2) if any(o)]
    nc = _run(tmp_path, _neighbour_program((5, 4), offsets), backend)
    _check_neighbours(nc, (5, 4), offsets)


@pytest.mark.parametrize("backend", BACKENDS)
def test_2d_wide(tmp_path, backend):
    offsets = [(2, 0), (0, -2), (2, 2), (-3, 1), (-2, -2)]
    nc = _run(tmp_path, _neighbour_program((5, 4), offsets), backend)
    _check_neighbours(nc, (5, 4), offsets)


@pytest.mark.parametrize("backend", BACKENDS)
def test_3d_all_nearest_neighbours(tmp_path, backend):
    offsets = [o for o in itertools.product((-1, 0, 1), repeat=3) if any(o)]
    nc = _run(tmp_path, _neighbour_program((5, 4, 3), offsets), backend)
    _check_neighbours(nc, (5, 4, 3), offsets)


_UPSTREAM_D1Q5 = """simulation_description("upstream_dfs with speeds of 2");
global_constants { const array[real, 5] EX = {0.0, 1.0, -1.0, 2.0, -2.0}; }
lattices { lattice f(1, 5, real, 8, true); }
initializer I {
    f.out[x | 0] = x; f.out[x | 1] = x + 10; f.out[x | 2] = x + 20;
    f.out[x | 3] = x + 30; f.out[x | 4] = x + 40;
}
dynamic D { array[real, 5] fIn = upstream_dfs(f, x, EX); f.out[x | :] = fIn; }
gauge G -> (real f0, real f1, real f2, real f3, real f4) {
    f0 = f.in[x | 0]; f1 = f.in[x | 1]; f2 = f.in[x | 2];
    f3 = f.in[x | 3]; f4 = f.in[x | 4];
}
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""


@pytest.mark.parametrize("backend", BACKENDS)
def test_upstream_dfs_with_speed_two(tmp_path, backend):
    """Streaming at speeds of 1 and 2: DF k at x comes from x - EX[k]."""
    nc = _run(tmp_path, _UPSTREAM_D1Q5, backend)
    for k, speed in enumerate((0, 1, -1, 2, -2)):
        want = [((x - speed) % 8) + 10 * k for x in range(8)]
        assert nc[f"f{k}"][1].astype(int).tolist() == want, k


_GAUGE_NEIGHBOURS = """simulation_description("gauge neighbour reads");
lattices { lattice u(1, 1, real, 8, true); }
initializer I { u.out[x | 0] = x; }
dynamic D { u.out[x | 0] = u.in[x | 0] + 10; }
gauge G -> (real c, real e, real w) {
    c = u.in[x | 0]; e = u.in[x + 1 | 0]; w = u.in[x - 1 | 0];
}
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""


@pytest.mark.parametrize("backend", BACKENDS)
def test_gauge_reads_neighbours_across_the_seam(tmp_path, backend):
    """Gauges run at t=0 and after each buffer swap; the ghost cells
    they read must be current then too."""
    nc = _run(tmp_path, _GAUGE_NEIGHBOURS, backend, steps=2)
    for frame in range(3):
        centre = np.arange(8) + 10.0 * frame
        assert np.array_equal(nc["c"][frame], centre)
        assert np.array_equal(nc["e"][frame], np.roll(centre, -1)), frame
        assert np.array_equal(nc["w"][frame], np.roll(centre, 1)), frame


@pytest.mark.parametrize("backend", BACKENDS)
def test_fisher_kpp_matches_numpy(tmp_path, backend):
    """The radius-2 RK2 example against the same scheme in NumPy, run
    long enough for the solution to cross the periodic seam."""
    n, seed_r, diff, rate, dt, steps = 32, 5, 0.2, 0.5, 0.5, 60

    def rhs(v):
        lap = (np.roll(v, 1, 0) + np.roll(v, -1, 0) + np.roll(v, 1, 1)
               + np.roll(v, -1, 1) - 4.0 * v)
        return diff * lap + rate * v * (1.0 - v)

    y, x = np.mgrid[0:n, 0:n]
    u = (((x - n // 2) ** 2 + (y - n // 2) ** 2) < seed_r ** 2).astype(float)
    for _ in range(steps):
        u = u + dt * rhs(u + 0.5 * dt * rhs(u))

    example = _REPO / "examples" / "fd" / "2d" / "fisher_kpp_rk2.gelb"
    nc = _run(tmp_path, example.read_text(), backend, steps=steps,
              defines=(f"N={n}", f"SEED_R={seed_r}"))
    assert np.abs(np.asarray(nc["u_val"][-1]) - u).max() < 1e-12
