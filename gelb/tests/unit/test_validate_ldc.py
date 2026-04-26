"""Cavity geometry and failure handling in the benchmark sampler."""

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/validate_ldc.py"
spec = importlib.util.spec_from_file_location("validate_ldc", SCRIPT)
ldc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ldc)


@pytest.mark.parametrize("n", [8, 9, 129, 257])
def test_reynolds_length_matches_sampled_wall_positions(n):
    tau = ldc._compute_tau(100, n, 0.05)
    viscosity = (tau - 0.5) / 3
    # Nearest fluid cell is half a lattice spacing from each wall.
    positions, _ = ldc._extract_centerlines(np.zeros((n, n)), "x", 0.05)
    physical_height = 0.5 / positions[1]
    assert physical_height == pytest.approx(n - 2)
    assert 0.05 * physical_height / viscosity == pytest.approx(100)


@pytest.mark.parametrize("n", [8, 9])
@pytest.mark.parametrize("axis", ["x", "y"])
def test_sampler_uses_geometric_center_and_ignores_boundary_cells(n, axis):
    y, x = np.mgrid[:n, :n]
    field = (2 * x + 3 * y).astype(float)
    field[[0, -1], :] = 1e6
    field[:, [0, -1]] = 1e6
    positions, values = ldc._extract_centerlines(field, axis, 2)
    coord = 0.5 + positions[1:-1] * (n - 2)
    centre = (n - 1) / 2
    expected = (2 * centre + 3 * coord if axis == "y"
                else 2 * coord + 3 * centre) / 2
    np.testing.assert_allclose(values[1:-1], expected)
    np.testing.assert_array_equal(values[[0, -1]], [0, 1 if axis == "y" else 0])


def test_failed_run_does_not_publish_partial_or_stale_results(tmp_path, monkeypatch):
    output = tmp_path / "results.json"
    original = '{"schema_version": 2, "results": {"bgk": {"100": {"old": true}}}}'
    output.write_text(original)
    monkeypatch.setattr(ldc, "_run_one", lambda *args, **kwargs: None)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--re", "100", "--out", str(output)])
    assert ldc.main() == 1
    assert output.read_text() == original
