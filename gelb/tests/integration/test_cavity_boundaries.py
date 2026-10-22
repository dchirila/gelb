"""Physical invariants of the shipped cavity's pull/bounce-back treatment."""

import re

import numpy as np
import pytest

from gelb.tests.integration.test_tutorial_regressions import BACKENDS, ROOT, run_source

EXAMPLES = ["bgk", "bgk_re1000", "mrt", "incomp_zou"]


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("collision", EXAMPLES)
def test_closed_cavity_mass_and_lid_motion(tmp_path, backend, collision):
    source = (ROOT / "examples/lbm/2d" /
              f"lid_driven_cavity_2d_{collision}.gelb").read_text()
    # 19 fluid cells exercise SIMD chunks and tails on Highway.
    source = re.sub(r"const int N = \d+;", "const int N = 21;", source)
    source = re.sub(r"const real U_LID = [\d.]+;", "const real U_LID = 0.05;", source)
    source = re.sub(r"const real TAU = [^;]+;", "const real TAU = 0.8;", source)
    # A density pulse next to the stationary side wall must remain in
    # the closed fluid/link system; a fixed wall reservoir would lose it.
    source = source.replace(
        "f.out[x, y | :] = W;",
        "f.out[x, y | :] = W * (1.0 + 0.01 * real(x == 1 && y == 10));",
        1,
    )
    # Full-way walls hold reflected mass for one step. Count only wall
    # slots whose next pull goes to a fluid cell; unused slots are outside
    # the closed fluid/link system (especially at corners).
    inflight = " + ".join(
        f"real(x + EX[{i}] >= 1 && x + EX[{i}] <= N - 2 && "
        f"y + EY[{i}] >= 1 && y + EY[{i}] <= N - 2) * f.in[x, y | {i}]"
        for i in range(9))
    source = source.replace("gauge Hydro -> (real rho, real ux, real uy) {",
        "gauge Hydro -> (real rho, real ux, real uy, real stored) {\n"
        "    stored = sum(f.in[x, y | :]);")
    source = source.replace("gauge BoundaryHydro -> (real rho, real ux, real uy) {",
        "gauge BoundaryHydro -> (real rho, real ux, real uy, real stored) {\n"
        f"    stored = {inflight};")
    data = run_source(tmp_path, backend, source, timesteps=30, write_every=1)
    for field in ("rho", "ux", "uy"):
        assert np.isfinite(data[field]).all()
    mass = data["stored"].sum(axis=(1, 2))
    np.testing.assert_allclose(mass, mass[0], rtol=2e-13, atol=0)
    # The wall receives/reverses at step 1; the fluid pulls at step 2.
    assert data["ux"][1, -2, 10] == pytest.approx(0, abs=1e-14)
    assert data["ux"][2, -2, 10] == pytest.approx(0.05 / 3, abs=1e-14)
    assert data["ux"][-1, -2, 10] > 0
    # Boundary gauges show prescribed values, never an alternating 0/2U.
    np.testing.assert_allclose(data["ux"][:, -1, :], 0.05, rtol=0, atol=0)
    np.testing.assert_allclose(data["ux"][:, 0, :], 0, rtol=0, atol=0)
    np.testing.assert_allclose(data["uy"][:, -1, :], 0, rtol=0, atol=0)
