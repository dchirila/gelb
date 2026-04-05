"""Pytest configuration for integration tests.

Adds opt-in command-line options for the examples smoke test:

    --run-smoke            Enable the full examples smoke test suite
                           (otherwise skipped by default).
    --smoke-iters=N        Number of timesteps each example is run for
                           inside the smoke test (default: 10).
    --smoke-backends=LIST  Comma-separated list of backends to exercise
                           (default: 'serial').  Valid entries:
                           'serial', 'cpu_highway', 'gpu_cuda_cpp'.
                           The non-default entries are opt-in because
                           they need additional toolchains (g++ +
                           NetCDF-C + Highway headers; nvcc + an
                           NVIDIA GPU + NetCDF-C respectively).

The smoke test compiles every ``.gelb`` file under ``examples/`` with
the selected backend(s), links the resulting source against NetCDF,
runs the binary for ``--smoke-iters`` timesteps, and checks that the
process exits cleanly.  It is gated behind ``--run-smoke`` because
compiling every example for every backend takes ~2 minutes even at
N=10 -- not something you want on every ``pytest`` invocation.

Typical usage:

    # Quick default test run -- smoke tests are skipped
    uv run pytest gelb/tests/

    # Peace-of-mind run before committing
    uv run pytest gelb/tests/integration/test_examples_smoke.py \\
        --run-smoke --smoke-iters=50

    # Extra-thorough pre-release run
    uv run pytest gelb/tests/integration/test_examples_smoke.py \\
        --run-smoke --smoke-iters=200
"""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-smoke",
        action="store_true",
        default=False,
        help="Run the examples smoke test suite (compiles + runs every "
             ".gelb file under examples/).  Off by default.",
    )
    parser.addoption(
        "--smoke-iters",
        type=int,
        default=10,
        help="Number of timesteps for each example in the smoke test "
             "(default: 10).  Increase for more peace of mind, "
             "decrease for faster runs.",
    )
    parser.addoption(
        "--smoke-backends",
        type=str,
        default="serial",
        help="Comma-separated list of backends to exercise in the "
             "smoke test (default: 'serial').",
    )


def pytest_collection_modifyitems(config, items):
    """Skip any test marked ``smoke`` unless ``--run-smoke`` was passed."""
    if config.getoption("--run-smoke"):
        return
    skip_smoke = pytest.mark.skip(
        reason="smoke tests are opt-in; pass --run-smoke to enable")
    for item in items:
        if "smoke" in item.keywords:
            item.add_marker(skip_smoke)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "smoke: slow end-to-end smoke test that compiles and runs all "
        ".gelb examples (opt-in via --run-smoke)",
    )


@pytest.fixture
def smoke_iters(request):
    """Number of timesteps for the current smoke test run."""
    return request.config.getoption("--smoke-iters")


@pytest.fixture
def smoke_backends(request):
    """Parsed list of backend names from --smoke-backends."""
    raw = request.config.getoption("--smoke-backends")
    return [b.strip() for b in raw.split(",") if b.strip()]
