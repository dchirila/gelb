"""Writes at an offset ("push"), end to end: programs are compiled and run
with ``scripts/gelb-run`` on each CPU backend, and every value is checked
against an expectation computed here, never against another backend,
on both the scalar and the SIMD path.

Covered: 1-D push shifts at +/-1, +/-2, +/-3 and beyond the domain size, on a
domain that takes Highway's SIMD path (8 cells) and one that takes its
scalar path (7 cells); 2-D pushes in all 8 directions and 3-D pushes in
the 8 corner directions plus the axes, on grids wide enough for SIMD;
pushes from an initializer; ordered overwrites, including two pushes at
offsets congruent modulo the domain; a static class initialized through
an offset that wraps back to the writing cell; and a push-streaming D2Q9
Taylor-Green vortex against the shipped pull-streaming example.
"""

import itertools
import os
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


def _run(tmp_path, source, backend, steps=1, defines=(), name="prog"):
    """Compile and run ``source``; return the NetCDF output."""
    work = tmp_path / f"{name}_{backend}"
    work.mkdir()
    src = work / f"{name}.gelb"
    src.write_text(source)
    env = dict(os.environ, GELB_PYTHON=sys.executable)
    cmd = [str(_GELB_RUN), "-b", backend, "-n", str(steps), "-w", "1"]
    for define in defines:
        cmd += ["-D", define]
    result = subprocess.run(cmd + [str(src)], cwd=work, env=env,
                            capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stdout + result.stderr
    return netCDF4.Dataset(next(work.glob("*.nc")))


def _offset_index(dims, offset):
    return ", ".join(
        n if o == 0 else f"{n} {'+' if o > 0 else '-'} {abs(o)}"
        for n, o in zip(dims, offset))


# --------------------------------------------------------------------------
# 1-D shifts
# --------------------------------------------------------------------------

def _shift_program(n, k, init_push=False):
    sign = "+" if k >= 0 else "-"
    init = (f"u.out[x {sign} {abs(k)} | 0] = x;" if init_push
            else "u.out[x | 0] = x;")
    return f"""simulation_description("push shift");
lattices {{ lattice u(1, 1, real, {n}, true); }}
initializer I {{ {init} }}
dynamic D {{ u.out[x {sign} {abs(k)} | 0] = u.in[x | 0]; }}
gauge G -> (real v) {{ v = u.in[x | 0]; }}
node_classes {{ node_class B(I, D, G); }}
geometry {{ nodes[:] = B; }}
"""


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("n", [8, 7])          # SIMD path / scalar path on Highway
def test_1d_push_shifts(tmp_path, backend, n):
    for k in (1, -1, 2, -3, n + 1):
        nc = _run(tmp_path, _shift_program(n, k), backend, steps=3,
                  name=f"shift{k:+d}")
        v = np.asarray(nc["v"][:])
        for step in range(4):
            expected = [(x - step * k) % n for x in range(n)]
            assert v[step].tolist() == expected, (k, step)


@pytest.mark.parametrize("backend", BACKENDS)
def test_initializer_push(tmp_path, backend):
    n = 8
    nc = _run(tmp_path, _shift_program(n, 3, init_push=True), backend, steps=1)
    v = np.asarray(nc["v"][:])
    assert v[0].tolist() == [(x - 3) % n for x in range(n)]      # t = 0
    assert v[1].tolist() == [(x - 6) % n for x in range(n)]      # one more push


# --------------------------------------------------------------------------
# 2-D and 3-D directions
# --------------------------------------------------------------------------

def _direction_program(sizes, offsets):
    """u holds a distinct value per cell; every cell pushes u into lattice r
    at each offset, one DF per offset.  One step, then the gauge reports r."""
    d = len(sizes)
    dims = "xyz"[:d]
    here = ", ".join(dims)
    shape = ("{" + ", ".join(map(str, sizes)) + "}, {"
             + ", ".join(["true"] * d) + "}")
    value = " + ".join(f"{10 ** i} * {n}" for i, n in enumerate(dims))
    pushes = "\n".join(
        f"    r.out[{_offset_index(dims, o)} | {k}] = u.in[{here} | 0];"
        for k, o in enumerate(offsets))
    outs = ", ".join(f"real r{k}" for k in range(len(offsets)))
    body = " ".join(f"r{k} = r.in[{here} | {k}];" for k in range(len(offsets)))
    return f"""simulation_description("push directions");
lattices {{ lattice u({d}, 1, real, {shape});
           lattice r({d}, {len(offsets)}, real, {shape}); }}
initializer I {{ u.out[{here} | 0] = {value}; r.out[{here} | :] = -1.0; }}
dynamic D {{
    u.out[{here} | 0] = u.in[{here} | 0];
{pushes}
}}
gauge G -> ({outs}) {{ {body} }}
node_classes {{ node_class B(I, D, G); }}
geometry {{ nodes[{", ".join([":"] * d)}] = B; }}
"""


def _check_directions(nc, sizes, offsets):
    for k, offset in enumerate(offsets):
        got = np.asarray(nc[f"r{k}"][-1])              # dims ([z,] y, x)
        want = np.empty_like(got)
        for index in np.ndindex(*got.shape):
            pos = index[::-1]                            # (x, y[, z])
            source = [(p - o) % n for p, o, n in zip(pos, offset, sizes)]
            want[index] = sum(10 ** i * c for i, c in enumerate(source))
        assert np.array_equal(got, want), f"offset {offset}"


@pytest.mark.parametrize("backend", BACKENDS)
def test_2d_all_directions(tmp_path, backend):
    sizes = (16, 6)
    offsets = [o for o in itertools.product((-1, 0, 1), repeat=2) if any(o)]
    nc = _run(tmp_path, _direction_program(sizes, offsets), backend)
    _check_directions(nc, sizes, offsets)


@pytest.mark.parametrize("backend", BACKENDS)
def test_3d_corners_and_axes(tmp_path, backend):
    sizes = (16, 4, 3)
    offsets = (list(itertools.product((-1, 1), repeat=3))
               + [(1, 0, 0), (0, -1, 0), (0, 0, 1)])
    nc = _run(tmp_path, _direction_program(sizes, offsets), backend)
    _check_directions(nc, sizes, offsets)


@pytest.mark.parametrize("backend", BACKENDS)
def test_2d_wide_push(tmp_path, backend):
    sizes = (16, 6)
    offsets = [(2, 0), (-3, 1), (0, -2)]
    nc = _run(tmp_path, _direction_program(sizes, offsets), backend)
    _check_directions(nc, sizes, offsets)


# --------------------------------------------------------------------------
# Ordered overwrites
# --------------------------------------------------------------------------

@pytest.mark.parametrize("backend", BACKENDS)
def test_ordered_overwrites_from_one_source_cell(tmp_path, backend):
    n = 8
    source = f"""simulation_description("ordered overwrites");
lattices {{ lattice u(1, 2, real, {n}, true); }}
initializer I {{ u.out[x | :] = 0.0; }}
dynamic D {{
    u.out[x | 0] = 2.0;
    u.out[x | 0] = 3.0;
    u.out[x + 1 | 1] = 10.0 + x;
    u.out[x + {n + 1} | 1] = 20.0 + x;
}}
gauge G -> (real a, real b) {{ a = u.in[x | 0]; b = u.in[x | 1]; }}
node_classes {{ node_class B(I, D, G); }}
geometry {{ nodes[:] = B; }}
"""
    nc = _run(tmp_path, source, backend)
    a = np.asarray(nc["a"][1]); b = np.asarray(nc["b"][1])
    assert a.tolist() == [3.0] * n
    # DF 0: two local writes, the later wins.  DF 1: two pushes from the
    # same source cell (offsets +1 and +9 coincide on 8 periodic cells),
    # the later statement wins.
    assert b.tolist() == [20.0 + (x - 1) % n for x in range(n)]


@pytest.mark.parametrize("backend", BACKENDS)
def test_static_class_initialized_through_a_wrapped_self_write(tmp_path, backend):
    # On 8 periodic cells the offset +8 is the writing cell itself, so a
    # static class may initialize its own cells that way; as static
    # cells, they keep the value in both buffers.
    n = 8
    source = f"""simulation_description("wrapped self write");
lattices {{ lattice u(1, 1, real, {n}, true); }}
initializer I {{ u.out[x | 0] = x; }}
initializer IS {{ u.out[x + {n} | 0] = 10.0 + x; }}
dynamic D {{ u.out[x | 0] = u.in[x | 0] + 1.0; }}
gauge G -> (real v) {{ v = u.in[x | 0]; }}
node_classes {{ node_class B(I, D, G); node_class S(IS, G); }}
geometry {{ nodes[:] = B; nodes[2:5] = S; }}
"""
    nc = _run(tmp_path, source, backend, steps=2)
    v = np.asarray(nc["v"][:])
    for step in range(3):
        expected = [10.0 + x if 2 <= x <= 5 else float(x + step) for x in range(n)]
        assert v[step].tolist() == expected, step


# --------------------------------------------------------------------------
# Push-streaming D2Q9 against the shipped pull-streaming example
# --------------------------------------------------------------------------

_PUSH_TGV = """simulation_description("2D Taylor-Green vortex, push streaming");
global_constants {
    const int N = 32;
    const real NU = 1.0 / 6.0;
    const real TAU_INV = 2.0 / (6.0 * NU + 1.0);
    const real U_MAX = 0.04;
    const real PI = 3.141592653589793;
    const real K = 2.0 * PI / N;
    const array[real, 9] EX = {0.0, 1.0, 0.0, -1.0,  0.0, 1.0, -1.0, -1.0,  1.0};
    const array[real, 9] EY = {0.0, 0.0, 1.0,  0.0, -1.0, 1.0,  1.0, -1.0, -1.0};
    const array[real, 9] W = {4.0/9.0,
        1.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0,
        1.0/36.0, 1.0/36.0, 1.0/36.0, 1.0/36.0};
}
lattices { lattice f(2, 9, real, {N, N}, {true, true}); }
function Macro(array[real, 9] fIn) -> (real rho, real ux, real uy) {
    rho = sum(fIn);
    ux = dot_prod(EX, fIn) / rho;
    uy = dot_prod(EY, fIn) / rho;
}
function Eq(real rho, real ux, real uy) -> (array[real, 9] feq) {
    real usq = ux*ux + uy*uy;
    array[real, 9] eu = EX * ux + EY * uy;
    feq = W * rho * (1.0 + 3.0*eu + 4.5*eu*eu - 1.5*usq);
}
initializer InitTG {
    real xc = x + 0.5;
    real yc = y + 0.5;
    real rho = 1.0 - 0.75 * U_MAX^2 * (cos(2.0*K*xc) + cos(2.0*K*yc));
    real ux = -1.0 * U_MAX * cos(K*xc) * sin(K*yc);
    real uy = U_MAX * sin(K*xc) * cos(K*yc);
    f.out[x, y | :] = Eq(rho, ux, uy);
}
dynamic BGKCollidePush {
    array[real, 9] fIn = f.in[x, y | :];
    real rho;
    real ux;
    real uy;
    {rho, ux, uy} = Macro(fIn);
    array[real, 9] fPost = fIn - TAU_INV * (fIn - Eq(rho, ux, uy));
    f.out[x, y | 0] = fPost[0];
    f.out[x + 1, y | 1] = fPost[1];
    f.out[x, y + 1 | 2] = fPost[2];
    f.out[x - 1, y | 3] = fPost[3];
    f.out[x, y - 1 | 4] = fPost[4];
    f.out[x + 1, y + 1 | 5] = fPost[5];
    f.out[x - 1, y + 1 | 6] = fPost[6];
    f.out[x - 1, y - 1 | 7] = fPost[7];
    f.out[x + 1, y - 1 | 8] = fPost[8];
}
gauge Hydro -> (real rho, real ux, real uy) {
    {rho, ux, uy} = Macro(f.in[x, y | :]);
}
node_classes { node_class BULK(InitTG, BGKCollidePush, Hydro); }
geometry { nodes[:,:] = BULK; }
"""


@pytest.mark.parametrize("backend", BACKENDS)
def test_push_streaming_matches_pull_streaming(tmp_path, backend):
    """Starting from an equilibrium, collide-then-push and stream-then-collide
    differ by one collision, which conserves the moments the gauge reports;
    so the two programs must agree to round-off at every step."""
    steps = 20
    pull = (_REPO / "examples/lbm/2d/taylor_green_vortex_2d_bgk.gelb").read_text()
    nc_pull = _run(tmp_path, pull, backend, steps=steps, defines=("N=32",), name="pull")
    nc_push = _run(tmp_path, _PUSH_TGV, backend, steps=steps, name="push")
    for var in ("rho", "ux", "uy"):
        a = np.asarray(nc_pull[var][:]); b = np.asarray(nc_push[var][:])
        assert a.shape == b.shape
        assert np.max(np.abs(a - b)) < 1e-12, var
    # and the flow actually decays, so the comparison is not vacuous
    ux = np.asarray(nc_push["ux"][:])
    assert np.max(np.abs(ux[-1])) < np.max(np.abs(ux[0]))
