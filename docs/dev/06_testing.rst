=======
Testing
=======

The test tree
=============

Everything is under :source:`gelb/tests/`: ``unit/`` (grouped by
stage: ``lexing``, ``parsing``, ``ast_building``, ``symbols``,
``data_types``, ``type_inference``, ``type_promotion``,
``type_validation``, ``validation``, ``midware``, and an empty
``debugging`` package, plus top-level modules such as :source:`gelb/tests/unit/test_compiler_pipeline.py`),
``integration/`` (end-to-end runs through ``gelbc`` and ``gelb-run``),
``numeric/`` (the conformance battery, :doc:`04_backends`),
``fixtures/`` (``.gelb`` programs for the regression and hardening
cases), ``gelb_snippets/`` and ``data/``.  :source:`gelb/tests/test_utils.py`
holds the shared helpers and the minimal-program generators.
:source:`gelb/conftest.py` regenerates the parser with
``invoke_antlr4_tool()`` in ``pytest_sessionstart``, so a test run
needs a Java runtime.

Running the suite
=================

``uv run pytest`` from the repository root collects all of
``gelb/tests``; ``uv run pytest -q gelb/tests/unit`` is the fast
subset.  Tests that need a native toolchain skip themselves:
``requires_compiler`` (gfortran and NetCDF-Fortran),
``requires_cpp_highway_compiler`` (g++, NetCDF-C and the Highway
submodule) and ``requires_gpu_cuda_cpp_compiler`` in
:source:`gelb/tests/integration/_toolchain.py`; the numeric runtime
test and :source:`gelb/tests/integration/test_real_width_contract.py`
gate their Fortran cases on gfortran and NetCDF-C instead; and the
``numeric_oracle`` fixture in :source:`gelb/tests/numeric/conftest.py`
needs a C++17 compiler.  ``uv run pytest -rs`` prints the reasons.

Markers and options
===================

- ``gpu`` is registered in ``[tool.pytest.ini_options]`` of
  :source:`pyproject.toml` and marks the CUDA cases of the numeric
  suite, :source:`gelb/tests/integration/test_real_width_contract.py`
  and :source:`gelb/tests/integration/test_reproducibility.py`, which
  also carry ``requires_gpu_cuda_cpp_compiler``; the smoke test's CUDA
  case carries neither and skips through its own toolchain check.
- ``smoke`` is registered in
  :source:`gelb/tests/integration/conftest.py`, which also adds
  ``--run-smoke``, ``--smoke-iters`` (default 10) and
  ``--smoke-backends`` (default ``serial``; also ``cpu_highway`` and
  ``gpu_cuda_cpp``).  Without ``--run-smoke`` every ``smoke`` test is
  skipped.  :source:`gelb/tests/integration/test_examples_smoke.py`
  compiles and runs every ``.gelb`` file under ``examples/`` on the
  selected backends.

The emission snapshot
=====================

:source:`scripts/emission_snapshot.py` compiles every example under
``examples/`` with the three backends (``--num-timesteps 10
--write-every 10 --nc-output out.nc --seed 42``), stores the
generated sources and writes a ``MANIFEST.json`` (the snapshot's own
index) that records which examples fail to compile::

   uv run python scripts/emission_snapshot.py snapshot -o /tmp/emis
   # ... change the compiler ...
   uv run python scripts/emission_snapshot.py compare  -o /tmp/emis

``compare`` exits 1 on any byte difference, new failure, new pass or
emission missing from the baseline;
``diff-backends`` needs no baseline and reports examples whose
outcome differs between backends.  :source:`CONTRIBUTING.md` requires
the snapshot to be identical for any backend work whose change to
the generated code is not intentional and explained; a frontend or
midware change that alters the AST handed to the backends changes
the emission too.

The numeric suite
=================

``uv run pytest -q gelb/tests/numeric`` runs the battery described
in :source:`gelb/tests/numeric/README.md` and :doc:`04_backends`:
``test_generated_constants.py`` needs only the oracle,
``test_generated_runtime.py`` builds the runtime cases on each
available backend with ``-O0`` strict native flags and compares every
cell bit for bit.  :source:`gelb/tests/numeric/known_failures.py`
lists diagnosed expected failures; it is empty.

What CI runs
============

:source:`.github/workflows/release-health.yml`, on every push and
pull request, on ``ubuntu-latest``: installs ``g++``, ``gfortran``,
``libnetcdf-dev`` and ``libnetcdff-dev``; ``uv sync --all-extras``;
``uv build --wheel --sdist``; installs the wheel into a fresh venv and
runs ``gelbc examples/basic/1d/ex0_int_vec_setto_one.gelb
--diagnostics-json`` from it; then ``uv run pytest`` on
:source:`gelb/tests/integration/test_example_diagnostics.py`,
:source:`gelb/tests/integration/test_geometry_lint.py`,
:source:`gelb/tests/unit/midware/test_periodic_continuity_validator.py`
and :source:`gelb/tests/numeric/`; and finally ``uv run sphinx-build
-b html -W --keep-going docs /tmp/gelb-docs``, so a Sphinx warning
fails the build.  CI has no GPU, so the ``gpu`` cases skip there.
