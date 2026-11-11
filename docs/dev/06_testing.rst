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
  :source:`gelb/tests/integration/test_same_name_block_locals.py`,
  :source:`gelb/tests/integration/test_simd_comparisons.py`,
  :source:`gelb/tests/integration/test_literal_types.py`,
  :source:`gelb/tests/integration/test_int_values_simd.py` and
  :source:`gelb/tests/integration/test_function_calls.py`, which
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
- *tests, constant coefficients*, *tests, function calls*, *tests,
  backends*, *tests, backends-2*, *tests, widths-and-math* and *tests,
  diagnostics, lint, viewer, runner*: the focused
  integration files
  listed in the workflow, grouped so that the files whose cases each
  build and run a program share no runner with the quick ones.

The six integration jobs run with ``pytest-xdist`` (``-n auto``, one
worker per core of the runner), and every pytest job passes
``--durations=25``, so its log ends with its slowest tests.
CI has no GPU, so the ``gpu`` cases skip there.

The ``backends-2`` shard includes the vector-body and compiler-defect
tests, native lowering, streaming, boundaries, and tutorial regressions.
``widths-and-math`` contains math-library accuracy, predicate precision,
and real-width contracts. Public example diagnostics are parametrized
per example so workers can share the work. The unit test
:source:`gelb/tests/unit/test_ci_integration_coverage.py` checks that each
integration file belongs to exactly one shard or an explicit exemption.
The empty ``test_frontend.py`` placeholder has no tests; the example
smoke, plain-build, and reproducibility sweeps run in the local gate.

The local refactoring gate
==========================

:source:`scripts/run_refactor_gate.sh` accepts ``--tree``, ``--base``,
``--snapshots``, ``--baseline-values``, and a new ``--out`` directory.
Snapshots contain ``default``, ``soa``, ``aos``, ``cbt``, ``plain``, and
``strict`` directories; ``emis_<variant>`` and ``emis_*_<variant>`` names
also work. ``--extra-snapshots DIR`` supplies missing variants from a
second directory. ``--snapshot-tool`` optionally replaces the repo driver.
Value baselines contain ``default`` and ``strict`` recordings.

The gate verifies the imported checkout and runtime header bytes, then
writes all six candidate variants under ``OUT/emissions/<variant>``.
It compares those files and syntax-checks the candidate C++ and Fortran
sources. Fortran uses the default GNU dialect, without ``-std=f2008`` or
``-fno-range-check``. Backend compilation outcomes must agree.
Strict Fortran 2008 checks remain on the focused fixtures in
:source:`gelb/tests/integration/test_negated_negative_constant.py`.
``--emission-mode byte`` is the default; ``structural`` uses
:source:`scripts/emission_structural_diff.py` to allow only bijective
compiler-temporary renaming within lexical scopes. Operators, grouping,
casts, literals, indices, non-temporary names, and statement order remain
fixed. ``--allow-emission-changed`` and ``--allow-value-changed`` are
separate comma-separated lists of exact corpus-relative example filenames:
allowing an emission change never excuses a value difference.

The integration stages are independent:

- ``integration-ci49`` runs exactly the 49 non-smoke CI files identified by
  ``ci_files()`` in :source:`gelb/tests/unit/test_ci_integration_coverage.py`,
  at ``-n JOBS`` (``--jobs``, default 12), with wall time in ``timings.txt``.
- ``reproducibility`` runs when ``git diff --name-only BASE`` touches
  ``gelb/**`` outside ``gelb/tests/**``, any of
  ``gelb/tests/integration/{test_reproducibility.py,conftest.py,_toolchain.py}``,
  ``scripts/gelb-run``, ``third_party/**``, ``pyproject.toml``, or ``uv.lock``.
  New files must be intent-to-add (``git add -N``) to appear in that diff.
  Otherwise it logs ``SKIP``. Neither build-sweep skip flag suppresses it.
- ``plain-build`` runs :source:`gelb/tests/integration/test_plain_build_compiles.py`.
- ``smoke`` runs :source:`gelb/tests/integration/test_examples_smoke.py` with
  ``--run-smoke``, ``--smoke-iters`` (default 10), and ``--smoke-backends``.

The unit and numeric suites and a strict offline Sphinx HTML build also run.
Missing CUDA/GPU or AVX-512 fails unless explicitly waived with
``--allow-no-gpu`` or ``--allow-no-avx512``. The selected configurations,
stage commands, logs, outcomes, and timings are saved under ``--out``.
Tests use a short temporary directory under ``/tmp``, with a Git discovery
ceiling, so long output paths and enclosing worktrees do not affect them.
The temporary directory is removed on exit; stage logs remain under ``--out``.

:source:`scripts/differential_value_gate.py` provides these commands:

- ``record --tree TREE --out DIR`` runs every example for three steps,
  writing every step with seed 42. ``--strict-fp`` selects strict mode;
  ``--configs`` selects configurations and ``-j`` bounds concurrency.
  ``--omp-threads`` defaults to 4. The recorder uses ``gelb-run -k``, hashes
  the exact compiled source, then removes that source and executable.
  It retains logs and NetCDF output, hashing variable names, dimensions,
  shapes, dtypes, values, signed zeros, and NaN positions. NaN payloads
  and signs are ignored; integer values retain all 64 bits.
- ``compare-baseline --baseline DIR --candidate DIR`` compares values
  and input fingerprints across revisions with compatible settings,
  toolchains, runtime headers, and Highway. ``--allow-changed`` excuses
  only named corpus-relative examples. Existing format-1 recordings
  remain comparable without the new per-entry ``source_sha256`` or
  top-level ``runners`` fields.
- ``verify-sources --tree TREE --baseline DIR`` requires those new fields
  and regenerates each source with the recorder's exact code-generation
  flags, without compiling or executing it. ``--configs``, ``--strict-fp``,
  ``-n`` (steps), and ``--omp-threads`` must match the recording. Every
  source hash, input, setting, header, runner, toolchain, and Highway
  revision must match. Missing or differing hashes name the affected entry.
- ``record-build-hashes`` and ``verify-build-hashes`` take ``--tree TREE``,
  ``--build-hashes DIR``, ``--kind smoke|plain-build``, and ``--backends``.
  Smoke pins ``--smoke-iters`` and normalized backends (``serial`` means
  ``cpu_fortran_serial``), using the sweep's output cadence and
  ``--nc-output smoke.nc``, without a seed. Plain-build pins the backends,
  one timestep, write interval one, and ``--no-slice-simplify --no-scalar-cse``
  with no explicit NetCDF filename. Each kind has its own manifest and
  exact source hashes, inputs, headers, runners, and environment guards.
- ``compare-backends --run-dir DIR`` checks strict SoA/AoS/CBT identity
  for non-random examples. ``record --exact-probes --strict-fp`` records
  bounded exact-intermediate fixtures (one to three steps) that compare
  across all selected configurations, including Fortran and CUDA.

``--skip-values``, ``--skip-smoke``, and ``--skip-plain-build`` each require
matching exact-source evidence and unchanged headers and both runner files
relative to ``--base``. Build manifests come from ``--build-hashes DIR``
(default ``SNAPSHOTS/build_hashes``); plain-build also requires a byte-equal
plain emission comparison. A failed guard logs the affected stage as
``FAIL`` and exits **1 immediately**, without running the omitted stage or
logging ``PASS``/``SKIP`` for it. A successful guard logs **SKIP**, never
PASS. Old baselines lacking source hashes cannot authorize skips. Omit a
skip flag to execute its stage.

``--allow-changed-headers`` accepts only exact paths from the value tool's
three runtime ``HEADERS``. It excuses only those hashes in the header stage
and baseline comparison, retains all other guards, and is incompatible
with **every** skip flag. Runner changes cannot authorize skips.

An optional ``--fuzz-dir`` with ``--fuzz-baseline`` checks a supplied corpus
with the same seeded value recorder. ``--corpus DIR`` on the value and
build-hash commands supports small scratch round trips independently.
