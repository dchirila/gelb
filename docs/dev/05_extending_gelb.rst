==============
Extending GeLB
==============

Each checklist names the files one existing feature touches.  Run
the checks of :doc:`06_testing` afterwards; a change not meant to
alter the generated code must leave the emission snapshot identical.

Adding an intrinsic
===================

``bounce_back_dfs`` is the model.  It passes through:

1. **Grammar.**  The token ``BOUNCE_BACK_DFS : 'bounce_back_dfs' ;``
   in :source:`gelb/antlr_part/grammars/CommonLexerRules.g4` and the
   alternative in the rule ``intrinsic_function_name`` of
   :source:`gelb/antlr_part/grammars/GeLB.g4`.  Run
   :source:`scripts/regenerate_antlr.sh` and commit the regenerated
   files of :source:`gelb/antlr_part/generated_code/` in the same
   commit (:source:`CONTRIBUTING.md`).
2. **AST.**  ``visitIntrinsicFunctionCallExpr`` in
   :source:`gelb/frontend/ASTBuilderVisitor.py` maps the token to the
   string ``"bounce_back_dfs"`` and builds an
   ``IntrinsicFunctionCall_N``; no new node class is needed.
3. **Type rule.**  The entry in ``INTRINSIC_FUNCTIONS`` of
   :source:`gelb/frontend/intrinsic_functions.py` names the argument
   checker (``_check_streaming_dfs_arguments``) and the return-type
   computer (``_compute_streaming_dfs_return_type``);
   ``TypeInferenceVisitor.visitIntrinsicFunctionCall_N`` looks the
   entry up (a streaming intrinsic also goes into the
   ``_STREAMING_INTRINSICS`` set of that method, which skips the
   lattice-name argument and fixes the ``array[real, q]`` result) and
   ``TypePromotionVisitor.visitIntrinsicFunctionCall_N`` converts the
   arguments.  A scalar intrinsic also goes into ``SCALAR_INTRINSICS``,
   ``intrinsic_argument_types`` (the conversions
   ``TypePromotionVisitor`` applies) and ``intrinsic_result_type`` of
   :source:`gelb/frontend/type_rules.py`.
4. **Constant folding.**  ``_try_evaluate_intrinsic`` in
   :source:`gelb/midware/ConstantFoldingVisitor.py` dispatches to
   ``intrinsic`` and ``_LIBRARY`` in :source:`gelb/midware/ast_eval.py`
   for scalar intrinsics and returns ``None`` for the streaming ones,
   which are never folded.
5. **Midware.**  ``_STENCIL_INTRINSICS`` in
   :source:`gelb/midware/StencilArgValidator.py` (argument validation),
   the ``function_name`` test in
   :source:`gelb/midware/StencilExtractionVisitor.py` (the reads it
   implies), ``_KNOWN_ARRAY_INTRINSICS`` in
   :source:`gelb/midware/SliceDFExpansionVisitor.py`, and
   ``visitIntrinsicFunctionCall_N`` in
   :source:`gelb/midware/DivisionByZeroValidator.py` for an intrinsic
   with a divisor.
6. **Backends.**  Fortran: ``_emit_intrinsic_call`` and
   ``_emit_streaming_dfs`` in
   :source:`gelb/backends/stage3_backend_cpu_fortran_serial.py`.
   Highway: ``_emit_intrinsic_call`` and
   ``_emit_intrinsic_bounce_back_dfs`` in
   :source:`gelb/backends/highway/expr.py`,
   ``_collect_bounce_back_dfs_keys`` and
   ``_emit_bounce_back_dfs_tables`` in
   :source:`gelb/backends/highway/statements.py`, the table cache, the
   call of the tables emitter and the eligibility walk in
   :source:`gelb/backends/stage3_backend_cpu_highway.py`, and the SIMD
   case in :source:`gelb/backends/highway/simd.py`.  CUDA inherits these
   (nothing under :source:`gelb/backends/cuda/` names the intrinsic).
7. **Tests.**  :source:`gelb/tests/unit/parsing/test_parse_intrinsic_functions.py`,
   :source:`gelb/tests/unit/type_inference/test_intrinsic_function_type_inference.py`,
   :source:`gelb/tests/unit/midware/test_intrinsic_folding.py`,
   :source:`gelb/tests/unit/midware/test_stencil_arg_validation.py`,
   :source:`gelb/tests/unit/midware/test_streaming_intrinsic_stencils.py`,
   :source:`gelb/tests/unit/midware/test_slice_df_expansion.py`,
   :source:`gelb/tests/unit/midware/test_bounce_back_dfs.py` and
   :source:`gelb/tests/integration/test_bounce_back_dfs.py` (every
   backend, through ``gelb-run``).
8. **Documentation.**  The section *Built-in intrinsics* of
   :source:`docs/user/03_gelb_in_10_minutes.rst`, the matching section
   of :source:`docs/LANGUAGE_DESIGN.md` (*Lattice operations* for the
   streaming ones), the ``INTRINSIC_FUNCTIONS`` tuple of
   :source:`docs/_ext/gelb_lexer.py`
   (syntax highlighting in the manual) and, if the numerical
   semantics change, :source:`docs/user/19_numerical_semantics.rst`.
9. **VS Code.**  The ``intrinsic-functions`` pattern of
   :source:`vscode-gelb/syntaxes/gelb.tmLanguage.json` and a snippet in
   :source:`vscode-gelb/snippets/gelb.json`; ``npm test`` in
   ``vscode-gelb/`` checks the grammar.

Adding a validation pass
========================

1. A module in :source:`gelb/frontend/` or :source:`gelb/midware/` with
   a visitor derived from ``ASTBaseVisitor`` (and
   ``ProgramTraversalMixin``), on the pattern of
   :source:`gelb/midware/DivisionByZeroValidator.py`
   (:doc:`03_ast_and_visitors`).
2. An error class in :source:`gelb/utils/exceptions.py` that takes the
   offending node and returns its location from ``_source_location``,
   or an existing one such as ``GeLBExTypeError``.  A warning instead
   returns ``(message, hint, source_line)`` tuples fed to
   ``emit_warning`` in ``compile_source``, like ``warn_unused_lattices``.
3. A wrapper in :source:`gelb/frontend/stage1_frontend.py` or
   :source:`gelb/midware/stage2_midware.py`, and the call plus
   ``record(name)`` at its place in ``compile_source`` of
   :source:`gelb/compiler_pipeline.py`.
4. The expected sequences in
   :source:`gelb/tests/unit/test_compiler_pipeline.py`, tests under
   :source:`gelb/tests/unit/validation/` or
   :source:`gelb/tests/unit/midware/` written with the helpers of
   :source:`gelb/tests/test_utils.py` (``minimal_gelb_program_1d``,
   ``get_typed_ast`` and the ``assert_*_error`` functions), and, if
   the diagnostics of an example change,
   :source:`gelb/tests/integration/test_example_diagnostics.py`.

Adding a backend
================

1. ``gelb/backends/stage3_backend_<name>.py`` with a
   ``generate_...(ast, ..., backend_context=...)`` function returning
   the program text (``generate_fortran``, ``generate_cpu_highway`` and
   ``generate_cuda_cpp`` are the existing ones; ``gelbc`` imports each
   by name); a runtime header next to the others is shipped by the
   ``package-data`` globs of :source:`pyproject.toml` (``*.hpp`` and
   ``*.cuh`` under ``gelb.backends``), so a header with another
   extension needs its own glob there.
2. The ``click.Choice`` of ``--backend`` and the dispatch branch in
   :source:`gelb/gelbc.py`.
3. A ``case`` branch in :source:`gelb/scripts/gelb-run` (``EXT`` and
   ``compile_src``), its validation list and the text of
   ``_die_unknown_backend``.
4. ``BACKENDS`` in :source:`scripts/emission_snapshot.py`; a toolchain
   guard in :source:`gelb/tests/integration/_toolchain.py`; the backend
   list of :source:`gelb/tests/integration/test_examples_smoke.py` (its
   own names: ``serial`` stands for ``cpu_fortran_serial``) and the
   ``--smoke-backends`` option of
   :source:`gelb/tests/integration/conftest.py`; the backend lists of
   :source:`gelb/tests/integration/test_tutorial_regressions.py` and
   :source:`gelb/tests/numeric/test_generated_runtime.py`, so that the
   numeric contract is enforced on it.
5. :source:`docs/user/16_performance_backends.rst`, the *What must
   agree* table of :source:`docs/user/19_numerical_semantics.rst`, the
   toolchain list in :source:`CONTRIBUTING.md` and, if CI is to build
   it, the ``apt`` line of :source:`.github/workflows/release-health.yml`.
6. **VS Code.**  The ``Backend`` type and the ``BACKENDS`` picker list
   of :source:`vscode-gelb/src/runCommand.ts`, and
   :source:`vscode-gelb/test/runCommand.test.js`.
