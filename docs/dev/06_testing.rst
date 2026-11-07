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
  suite, :source:`gelb/tests/integration/test_real_width_contract.py`,
  :source:`gelb/tests/integration/test_reproducibility.py`,
  :source:`gelb/tests/integration/test_constant_coefficients.py`,
  :source:`gelb/tests/integration/test_same_name_block_locals.py` and
  :source:`gelb/tests/integration/test_simd_comparisons.py`, which
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
- ``pytest-xdist`` is a dev dependency for the integration files whose
  cases each build and run their own program, such as
  :source:`gelb/tests/integration/test_constant_coefficients.py`:
  ``uv run pytest -n 12 <file>`` runs the builds in parallel.  Run the
  full suite without ``-n``: collecting a path under ``gelb/``
  regenerates the parser (see below), and the numeric suite shares its
  oracle builds.

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
the emission too.  The snapshot does not compile what it stores:
:source:`gelb/tests/integration/test_plain_build_compiles.py`
generates every example's plain build (``--no-slice-simplify
--no-scalar-cse``) on each backend and runs the native compiler's
syntax check on it, with gelb-run's default flags on Linux
(``GELB_CXXFLAGS``, ``GELB_FFLAGS`` and ``GELB_NVCC_FLAGS`` do not
apply).

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

:source:`.github/workflows/release-health.yml` runs on every push to
``main``, on every ``v*`` tag and on every pull request (a new push to a
pull-request branch cancels the run of the previous one), on
``ubuntu-latest``.  Every job starts with the composite action
:source:`.github/actions/setup/action.yml`: Python 3.12, ``uv`` with its
cache, ``g++``, ``gfortran``, ``libnetcdf-dev``, ``libnetcdff-dev`` and
the GL libraries the viewer tests load, the ANTLR jar from the Actions
cache, then ``uv sync --all-extras``.  The jobs run on separate runners:

- *package, wheel smoke, docs*: ``uv build --wheel --sdist``; installs
  the wheel into a fresh venv and, from a directory outside the checkout
  with ``uv`` off the ``PATH`` and ``GELB_PYTHON`` unset, checks that
  ``gelb`` imports from that venv, ``gelbc --version``, ``gelbc
  --diagnostics-json`` on ``examples/basic/1d/ex0_int_vec_setto_one.gelb``,
  a one-step ``gelb-run -b cpu_fortran_serial`` that writes its ``.nc``,
  and that the default backend stops with the "no Highway" message; then
  ``uv run sphinx-build -b html -W --keep-going docs /tmp/gelb-docs``, so
  a Sphinx warning fails the build.
- *tests, unit*: all of :source:`gelb/tests/unit/`, in one process,
  because :source:`gelb/conftest.py` regenerates the parser in the tree
  at session start.
- *tests, numeric*: all of :source:`gelb/tests/numeric/`, in one
  process: its runtime corpus is built once per module and backend, and
  workers would each build it again.
- *tests, constant coefficients*, *tests, backends* and *tests,
  diagnostics, lint, viewer, runner*: the focused integration files
  listed in the workflow, grouped so that the files whose cases each
  build and run a program share no runner with the quick ones.

The three integration jobs run with ``pytest-xdist`` (``-n auto``, one
worker per core of the runner), and every pytest job passes
``--durations=25``, so its log ends with its slowest tests.
CI has no GPU, so the ``gpu`` cases skip there.
