==============
Repository map
==============

Every path is relative to the repository root; ``git ls-files``
lists the tracked files.

Top-level directories
=====================

``gelb/``
   The compiler package.  :source:`gelb/gelbc.py` is the ``gelbc``
   driver and :source:`gelb/compiler_pipeline.py` orders the passes
   (:doc:`02_compilation_pipeline`).  The sub-packages follow the
   three stages: :source:`gelb/frontend/` (parse tree to AST, symbol
   tables, types), :source:`gelb/midware/` (constant folding,
   stencils, geometry, the rewrites) and :source:`gelb/backends/` (the
   three generators and their runtime headers, :doc:`04_backends`).
   :source:`gelb/gelb_ast/` holds the node classes,
   :source:`gelb/antlr_part/` the grammar and the generated parser,
   :source:`gelb/utils/` diagnostics and configuration,
   :source:`gelb/visualization/` the ``gelb-view`` tool,
   :source:`gelb/debugging/` the AST drawing behind ``gelbc
   --visualize-ast``, and :source:`gelb/tests/` the suite
   (:doc:`06_testing`).  In :source:`pyproject.toml`,
   ``[tool.setuptools.packages.find]`` keeps ``gelb.tests*`` out of
   the wheel and ``package-data`` ships the ``*.hpp`` and ``*.cuh``
   runtime headers with it.

``examples/``
   The ``.gelb`` programs, in ``basic/``, ``fd/``, ``lbm/`` (``1d``,
   ``2d``, ``3d``), ``lgca/``, ``sukop/`` and
   ``softwarex-2026-paper/``.  The worked chapters of the user
   tutorial are each anchored by one of them, the emission snapshot
   compiles all of them (:doc:`06_testing`), and
   :source:`examples/VALIDATION.md` describes the analytical
   validation that :source:`scripts/validate_analytical.py` runs.

``docs/``
   The Sphinx project: :source:`docs/conf.py`, :source:`docs/index.rst`,
   the user tutorial under :source:`docs/user/` rooted at
   :source:`docs/usrman.rst`, this manual under ``docs/dev/`` rooted at
   :source:`docs/devman.rst`, the Pygments lexer for ``.. code-block::
   gelb`` in :source:`docs/_ext/gelb_lexer.py`, and :source:`docs/figs/`.
   :source:`docs/LANGUAGE_DESIGN.md` records language design decisions
   and is excluded from the build by ``exclude_patterns`` in
   :source:`docs/conf.py`.

``scripts/``
   Developer tools.  This manual relies on :source:`scripts/gelb-run`
   (compile and run a program, :doc:`04_backends`),
   :source:`scripts/emission_snapshot.py` (byte-compare the generated
   code of every example), :source:`scripts/regenerate_antlr.sh`
   (rebuild the parser), :source:`scripts/gelb_bootstrap.sh` (create
   the ``uv`` environment), :source:`scripts/build_manual_pdfs.py`
   with :source:`scripts/build_usrman_pdf.py` and
   :source:`scripts/build_devman_pdf.py` (the release PDFs),
   :source:`scripts/clean_artifacts.sh` (remove build output) and
   :source:`scripts/install-vscode-ext.sh`.  The ``bench*``,
   ``compare_backends.py`` and ``validate_*.py`` scripts measure and
   validate simulations.

``vscode-gelb/``
   The VS Code extension: the TextMate grammar
   :source:`vscode-gelb/syntaxes/gelb.tmLanguage.json`, the snippets
   :source:`vscode-gelb/snippets/gelb.json`, the TypeScript sources
   under :source:`vscode-gelb/src/` and the Node tests under
   :source:`vscode-gelb/test/` (``npm test``).  ``extension.ts`` calls
   ``gelbc --diagnostics-json`` to fill the Problems panel.

``third_party/``
   ``highway/`` is the Google Highway SIMD library, a git submodule
   (:source:`.gitmodules`) that ``gelb-run`` puts on the include path.

Top-level files
===============

:source:`pyproject.toml` defines the package, its dependencies and
the extras ``gui`` (PySide6), ``docs`` (Sphinx, furo, copybutton) and
``dev`` (pytest and friends); ``uv sync --all-extras`` installs them
all, as :source:`CONTRIBUTING.md` says.  :source:`.readthedocs.yaml`
points ReadTheDocs at :source:`docs/conf.py`;
:source:`.github/workflows/release-health.yml` is the only CI
workflow (:doc:`06_testing`).

The three commands
==================

``[project.scripts]`` in :source:`pyproject.toml` defines two console
entry points: ``gelbc = "gelb.gelbc:cli"`` and
``gelb-view = "gelb.visualization.gelb_view:cli"``.  Both are
``click`` commands; ``gelb-view`` is a group whose subcommands are
``data`` (the default, a NetCDF output file), ``algo`` (the stencils
of a program), ``geo`` (its node-class map) and ``source``.
``gelb-run`` is the bash script :source:`scripts/gelb-run`, not a
Python entry point: it runs ``gelbc`` through ``uv run --project
<checkout>`` or through the interpreter named by ``GELB_PYTHON``,
compiles the result with the native compiler of the chosen backend,
runs the executable and, with ``--view``, hands the output to
``gelb-view`` (:doc:`04_backends`).
