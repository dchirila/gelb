"""DF slices give the same numbers on every backend and layout.

``f.in[x, y | lo:hi]`` reads DFs lo..hi as an array whose element i is
DF lo+i, and ``f.out[x, y | lo:hi] = <array of hi-lo+1>`` writes them
the same way (user manual, chapter 3, the ``|`` notation). The Highway
and CUDA backends used to ignore the lower bound of a read (DFs 1..4
for ``| 2:5``), silently. The DFs hold 1..9, so every expected value is
a small integer sum, exact in double on every backend.
"""
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from gelb.tests.integration._toolchain import (
    requires_compiler, requires_cpp_highway_compiler, requires_gpu_cuda_cpp_compiler)

netCDF4 = pytest.importorskip('netCDF4')

ROOT = Path(__file__).resolve().parents[3]

PROBE = """
simulation_description("DF slices: reads and writes with a nonzero lower bound");
global_constants {
    const array[real, 9] INIT = {1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0};
    const int LO = 2;
    const int HI = 5;
}
lattices { lattice f(2, 9, real, {16, 4}, {true, true}); }
initializer Init { f.out[x, y | :] = INIT; }
dynamic Step {
    f.out[x, y | 0:4] = f.in[x, y | 0:4];
    array[real, 4] a = {100.0, 200.0, 300.0, 400.0};
    f.out[x, y | 5:8] = a + f.in[x, y | 1:4] - f.in[x, y | 0];
}
gauge G -> (real s_local, real s_direct, real d, real s_open, real s_head,
            real s_scaled, real s_tail, real s_mix, real s_mix_nb, real s_const, real s_one) {
    array[real, 4] v = f.in[x, y | 2:5];
    s_local = sum(v);
    s_direct = sum(f.in[x, y | 2:5]);
    array[real, 4] c = {1.0, 2.0, 3.0, 4.0};
    d = dot_prod(c, v);
    array[real, 3] w = f.in[x, y | 6:];
    s_open = sum(w);
    array[real, 3] h = f.in[x, y | :2];
    s_head = sum(h);
    array[real, 4] twice = f.in[x, y | 2:5] * 2.0;
    s_scaled = sum(twice);
    s_tail = sum(f.in[x, y | 5:8]);
    array[real, 4] mix = f.in[x, y | 2:5] + f.in[x, y | 0];
    s_mix = sum(mix);
    array[real, 4] mix_nb = f.in[x, y | 2:5] + f.in[x + 1, y | 8];
    s_mix_nb = sum(mix_nb);
    s_const = sum(f.in[x, y | LO:HI]);
    array[real, 1] one = f.in[x, y | 8:];
    s_one = sum(one);
}
node_classes { node_class BULK(Init, Step, G); }
geometry { nodes[:, :] = BULK; }
"""

# DFs 1..9 at t = 0; from t = 1 on, DFs 5..8 are a + DFs 1..4 - DF 0 = 101, 202, 303, 404.
# The grid is uniform, so the neighbour's DF 8 equals the cell's own.
DFS = {0: [1, 2, 3, 4, 5, 6, 7, 8, 9], 1: [1, 2, 3, 4, 5, 101, 202, 303, 404]}
DFS[2] = DFS[1]


def expected(t):
    f = DFS[t]
    v = f[2:6]
    d = 1 * v[0] + 2 * v[1] + 3 * v[2] + 4 * v[3]
    return {'s_local': sum(v), 's_direct': sum(v), 'd': d,
            's_open': sum(f[6:]), 's_head': sum(f[:3]), 's_scaled': 2 * sum(v),
            's_tail': sum(f[5:9]), 's_mix': sum(v) + 4 * f[0], 's_mix_nb': sum(v) + 4 * f[8],
            's_const': sum(v), 's_one': f[8]}

LAYOUTS = [('cpu_fortran_serial', None, requires_compiler),
           ('cpu_highway', 'soa', requires_cpp_highway_compiler),
           ('cpu_highway', 'cbt', requires_cpp_highway_compiler),
           ('gpu_cuda_cpp', None, requires_gpu_cuda_cpp_compiler)]


def run(tmp_path, backend, layout):
    path = tmp_path / 'probe.gelb'
    path.write_text(PROBE)
    env = dict(os.environ, GELB_PYTHON=sys.executable)
    if layout:
        env['GELBC_EXTRA'] = f'--storage-layout {layout}'
    result = subprocess.run(
        [str(ROOT / 'scripts/gelb-run'), '-b', backend, '-n', '2', '-w', '1', str(path)],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=600)
    if layout == 'cbt' and 'cbt' in result.stderr and result.returncode != 0 \
            and 'AVX-512' in result.stderr + result.stdout:
        pytest.skip('the cbt layout needs an AVX-512 host')
    assert result.returncode == 0, result.stdout + result.stderr
    with netCDF4.Dataset(tmp_path / 'probe.nc') as nc:
        return {name: np.asarray(var[:]) for name, var in nc.variables.items()}


@pytest.mark.parametrize(('backend', 'layout'), [
    pytest.param(b, l, marks=m, id=f'{b}-{l or "default"}') for b, l, m in LAYOUTS])
def test_df_slices_read_and_write_the_right_dfs(tmp_path, backend, layout):
    data = run(tmp_path, backend, layout)
    assert data['s_local'].shape[0] == 3
    for t in range(3):
        for name, value in expected(t).items():
            assert np.all(data[name][t] == value), (t, name, value, np.unique(data[name][t]))


# A single DF index computed at run time inside a slice statement: the
# Fortran backend runs it; the C++ backends reject it with a located
# message (they used to read the loop index instead, silently).
RUNTIME_INDEX = """
simulation_description("a run-time DF index inside a slice statement");
global_constants { const array[real, 9] INIT = {1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0}; }
lattices { lattice f(2, 9, real, {16, 4}, {true, true}); }
initializer Init { f.out[x, y | :] = INIT; }
dynamic Step {
    f.out[x, y | 0:4] = f.in[x, y | 0:4];
    f.out[x, y | 5:8] = f.in[x, y | mod(x, 9)];
}
gauge G -> (real s) { s = sum(f.in[x, y | :]); }
node_classes { node_class BULK(Init, Step, G); }
geometry { nodes[:, :] = BULK; }
"""


def run_text(tmp_path, backend, layout, source):
    path = tmp_path / 'probe.gelb'
    path.write_text(source)
    env = dict(os.environ, GELB_PYTHON=sys.executable)
    if layout:
        env['GELBC_EXTRA'] = f'--storage-layout {layout}'
    return subprocess.run(
        [str(ROOT / 'scripts/gelb-run'), '-b', backend, '-n', '2', '-w', '1', str(path)],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=600)


@pytest.mark.parametrize(('backend', 'layout'), [
    pytest.param(b, l, marks=m, id=f'{b}-{l or "default"}') for b, l, m in LAYOUTS])
def test_a_run_time_df_index_runs_on_fortran_and_is_rejected_elsewhere(tmp_path, backend, layout):
    result = run_text(tmp_path, backend, layout, RUNTIME_INDEX)
    if backend == 'cpu_fortran_serial':
        assert result.returncode == 0, result.stdout + result.stderr
        with netCDF4.Dataset(tmp_path / 'probe.nc') as nc:
            s = np.asarray(nc.variables['s'][:])     # (time, y, x)
        x = np.arange(16)
        assert np.all(s[0] == 45)
        # DFs 5..8 become four copies of DF (x mod 9), whose value is x mod 9 + 1.
        assert np.all(s[1] == 15 + 4 * (x % 9 + 1))
        assert np.all(s[2] == 15 + 4 * (x % 9 + 1))
    else:
        if layout == 'cbt' and result.returncode != 0 and 'AVX-512' in result.stdout + result.stderr:
            pytest.skip('the cbt layout needs an AVX-512 host')
        assert result.returncode != 0
        assert 'DF index computed at run time is not supported' in result.stdout + result.stderr
        assert 'Traceback' not in result.stderr


# A full slice of a q = 1 lattice is an array of one element (user
# manual, chapter 3, the ``|`` notation): a local array, a function's
# array result, a draw and an expression of the slice are stored into it,
# and ``sum`` reads it.  The backends used to emit it as the single DF
# when its bounds were equal, which failed to build on every backend.
Q1 = """
simulation_description("a full slice of a q = 1 lattice is an array of one element");
function Twice(array[real, 1] s) -> (array[real, 1] r) { r = s * 2.0; }
lattices {
    lattice a(2, 1, real, {67, 4}, {true, true});
    lattice b(2, 1, real, {67, 4}, {true, true});
    lattice c(2, 1, real, {67, 4}, {true, true});
    lattice r(2, 1, real, {67, 4}, {true, true});
}
initializer Init {
    a.out[x, y | :] = real(x) + 0.5;
    b.out[x, y | :] = real(x) + 0.5;
    c.out[x, y | :] = real(x) + 0.5;
    r.out[x, y | :] = random();
}
dynamic Step {
    array[real, 1] la = a.in[x, y | :] + 1.0;
    a.out[x, y | :] = la;
    b.out[x, y | :] = Twice(b.in[x, y | :]) - (real(x) + 0.5);
    c.out[x, y | 0:] = c.in[x, y | 0:] + 1.0;
    r.out[x, y | :] = r.in[x, y | :];
}
gauge G -> (real sa, real sb, real sc, real sum_a, real draw) {
    sa = a.in[x, y | 0];
    sb = b.in[x, y | 0];
    sc = c.in[x, y | 0];
    sum_a = sum(a.in[x, y | :]);
    draw = r.in[x, y | 0];
}
node_classes { node_class BULK(Init, Step, G); }
geometry { nodes[:, :] = BULK; }
"""

ALL_LAYOUTS = LAYOUTS[:2] + [('cpu_highway', 'aos', requires_cpp_highway_compiler)] + LAYOUTS[2:]


@pytest.mark.parametrize(('backend', 'layout'), [
    pytest.param(b, l, marks=m, id=f'{b}-{l or "default"}') for b, l, m in ALL_LAYOUTS])
def test_a_full_slice_of_a_q1_lattice_is_an_array_of_one(tmp_path, backend, layout):
    result = run_text(tmp_path, backend, layout, Q1)
    if layout == 'cbt' and result.returncode != 0 and 'AVX-512' in result.stdout + result.stderr:
        pytest.skip('the cbt layout needs an AVX-512 host')
    assert result.returncode == 0, result.stdout + result.stderr
    with netCDF4.Dataset(tmp_path / 'probe.nc') as nc:
        data = {name: np.asarray(var[:]) for name, var in nc.variables.items()}
    x = np.arange(67) + 0.5
    for t in range(3):
        assert np.all(data['sa'][t] == x + t), t
        assert np.all(data['sb'][t] == x), t
        assert np.all(data['sc'][t] == x + t), t
        assert np.all(data['sum_a'][t] == x + t), t
        assert np.all(data['draw'][t] == data['draw'][0]), t
    draw = data['draw'][0]
    assert np.all((0.0 <= draw) & (draw < 1.0)) and np.unique(draw).size > 1


@pytest.mark.parametrize(('q', 'selection', 'is_array'), [
    (1, ':', True), (1, '0:', True),
    (9, ':', True), (9, '3:3', False), (9, ':0', False), (9, '8:', False), (9, '3', False),
])
def test_which_df_selections_are_arrays(q, selection, is_array):
    """``| :`` (and ``| 0:``) is all DFs, an array even when q = 1; a
    range with equal bounds (``| 3:3``, an open end that reaches one DF)
    is the single DF, a scalar (user manual, chapter 3)."""
    from gelb.compiler_pipeline import PipelineOptions, PipelineProfile, compile_source
    from gelb.utils.exceptions import GeLBExTypeError
    source = f"""
simulation_description("which selections are arrays");
lattices {{ lattice f(2, {q}, real, {{16, 4}}, {{true, true}}); }}
initializer Init {{ f.out[x, y | :] = 1.0; }}
dynamic Step {{ f.out[x, y | :] = f.in[x, y | :]; }}
gauge G -> (real s) {{ s = sum(f.in[x, y | {selection}]); }}
node_classes {{ node_class BULK(Init, Step, G); }}
geometry {{ nodes[:, :] = BULK; }}
"""
    if is_array:
        compile_source(source, PipelineProfile.CODEGEN, PipelineOptions())
    else:
        with pytest.raises(GeLBExTypeError, match="expects an array argument"):
            compile_source(source, PipelineProfile.CODEGEN, PipelineOptions())
