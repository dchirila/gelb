"""Compile and run compiler regressions on every backend: logical negation,
boolean locals, and node classes that use different gauges on one lattice."""

import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from gelb.tests.integration._toolchain import (
    requires_compiler,
    requires_cpp_highway_compiler,
    requires_gpu_cuda_cpp_compiler,
)

netCDF4 = pytest.importorskip("netCDF4")
ROOT = Path(__file__).resolve().parents[3]
BACKENDS = [
    pytest.param("cpu_fortran_serial", marks=requires_compiler),
    pytest.param("cpu_highway", marks=requires_cpp_highway_compiler),
    pytest.param("gpu_cuda_cpp", marks=requires_gpu_cuda_cpp_compiler),
]


def run_source(tmp_path, backend, source, *, timesteps=1, write_every=1, python=None):
    path = tmp_path / "probe.gelb"
    path.write_text(source)
    result = subprocess.run(
        [str(ROOT / "scripts/gelb-run"), "-b", backend,
         "-n", str(timesteps), "-w", str(write_every), str(path)],
        cwd=tmp_path, env=dict(os.environ, GELB_PYTHON=python or sys.executable),
        capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    with netCDF4.Dataset(next(tmp_path.glob("*.nc"))) as nc:
        return {name: np.asarray(var[:]) for name, var in nc.variables.items()}


@pytest.mark.parametrize("backend", BACKENDS)
def test_logical_negation(tmp_path, backend):
    # Seventeen cells exercise both full SIMD chunks and the scalar tail.
    data = run_source(tmp_path, backend, """
simulation_description("logical negation");
lattices { lattice f(1, 1, real, 17, false); }
initializer I { f.out[x | 0] = real(x); }
dynamic D { f.out[x | 0] = real(!(f.in[x | 0] < 4.0)); }
gauge G -> (real value, real negated, real double_negated) {
    bool flag = t == 0;
    value = f.in[x | 0];
    negated = real(!flag);
    double_negated = real(!!flag);
}
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
""")
    expected = (np.arange(17) >= 4).astype(float)
    np.testing.assert_array_equal(data["value"][-1], expected)
    np.testing.assert_array_equal(data["negated"][-1], np.ones(17))
    np.testing.assert_array_equal(data["double_negated"][-1], np.zeros(17))


@pytest.mark.parametrize("backend", BACKENDS)
def test_bool_locals(tmp_path, backend):
    data = run_source(tmp_path, backend, """
simulation_description("boolean locals in vector bodies");
lattices { lattice f(1, 4, real, 17, false); }
initializer I { f.out[x | :] = real(x); }
dynamic D {
    bool cond = f.in[x | 0] < 4.0;
    f.out[x | 0] = real(cond) * 10.0 + (1.0 - real(cond)) * 20.0;
    bool other;
    other = !cond;
    f.out[x | 1] = real(other);
    bool enabled = true;
    enabled = false;
    cond = (other || enabled) && (t > 0);
    f.out[x | 2] = real(cond);
    other = true;
    f.out[x | 3] = real(other);
}
gauge G -> (real chosen, real negated, real combined, real uniform) {
    chosen = f.in[x | 0];
    negated = f.in[x | 1];
    combined = f.in[x | 2];
    uniform = f.in[x | 3];
}
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
""")
    high = np.arange(17) >= 4
    np.testing.assert_array_equal(data["chosen"][-1], np.where(high, 20, 10))
    np.testing.assert_array_equal(data["negated"][-1], high)
    np.testing.assert_array_equal(data["combined"][-1], high)
    np.testing.assert_array_equal(data["uniform"][-1], np.ones(17))


@pytest.mark.parametrize("backend", BACKENDS)
def test_mixed_gauges(tmp_path, backend):
    source = (ROOT / "gelb/tests/fixtures/regressions/mixed_gauges.gelb").read_text()
    data = run_source(tmp_path, backend, source)
    expected_local = np.ones((2, 8))
    expected_local[:, [2, 3]] = np.nan
    np.testing.assert_array_equal(data["local"], expected_local)
    for name, values in {"a": [7, 7], "b": [0, 9], "c": [0, 0]}.items():
        expected = np.full((2, 8), np.nan)
        expected[:, 2] = values
        assert name in data, f"missing output from the second gauge: {name}"
        np.testing.assert_array_equal(data[name], expected)


@pytest.mark.parametrize("backend", BACKENDS)
def test_mixed_gauges_dense_shared_output(tmp_path, backend):
    # Both classes have dense SIMD-sized runs and different gauge bodies.
    # The shared output must be declared once and filled by the right body.
    data = run_source(tmp_path, backend, """
simulation_description("different dense gauges with a shared output");
lattices { lattice f(1, 1, real, 34, false); }
initializer I { f.out[x | 0] = real(x); }
dynamic D { f.out[x | 0] = f.in[x | 0] + 1.0; }
gauge A -> (real shared, real first) {
    shared = f.in[x | 0]; first = shared * 2.0;
}
gauge B -> (real shared, real second) {
    shared = -f.in[x | 0]; second = shared * 3.0;
}
node_classes { node_class C1(I, D, A); node_class C2(I, D, B); }
geometry { nodes[:] = C1; nodes[17:33] = C2; }
""", timesteps=3, write_every=2)
    np.testing.assert_array_equal(data["time"], [0, 2, 3])
    expected = np.arange(34)[None, :] + np.array([0, 2, 3])[:, None]
    expected[:, 17:] *= -1
    np.testing.assert_array_equal(data["shared"], expected)
    for name, factor, absent in [("first", 2, slice(17, None)),
                                  ("second", 3, slice(None, 17))]:
        field = (expected * factor).astype(float)
        field[:, absent] = np.nan
        np.testing.assert_array_equal(data[name], field)
