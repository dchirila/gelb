========================
The compilation pipeline
========================

``compile_source`` in :source:`gelb/compiler_pipeline.py` is the one
place that orders the passes.  ``gelbc`` calls it (through
``compile_file``) with the ``CODEGEN`` profile, ``gelbc
--diagnostics-json`` with ``DIAGNOSTICS``, and the ``gelb-view``
analysis modes (through :source:`gelb/midware/program_analysis.py`)
with ``PROGRAM_ANALYSIS``; the three are the ``PipelineProfile``
enum.  Every pass is followed by ``record(name)``, so
``CompilationResult.pass_names`` is the executed sequence, and
:source:`gelb/tests/unit/test_compiler_pipeline.py` asserts it per
profile.  The frontend passes are wrapped by the functions of
:source:`gelb/frontend/stage1_frontend.py`, the midware passes by
those of :source:`gelb/midware/stage2_midware.py`; the visitor behind
each wrapper is named below, under the names ``record`` uses.  Two
sanity checks, ``validate_ast_root`` and ``validate_midware_input``,
only confirm that the root is a ``Program_N``.

Frontend
========

``parse``
   ``get_ast``: the lexer and parser from
   :source:`gelb/antlr_part/generated_code/` build the parse tree,
   :source:`gelb/frontend/ParsingError.py` turns a syntax error into
   ``GeLBExSyntaxError``, and
   :source:`gelb/frontend/ASTBuilderVisitor.py` builds the AST.
``validate_lattice_access_context``
   :source:`gelb/frontend/LatticeAccessContextValidator.py`: ``f.out``
   only in initializers and dynamics, ``f.in`` only in dynamics and
   gauges, neither in ``global_constants``.
``validate_block_signatures``
   :source:`gelb/frontend/GaugeValidationVisitor.py`: functions and
   gauges declare named results, and a gauge assigns all of its outputs.
``prevent_symbol_ref_implicit_clashes``
   :source:`gelb/frontend/ImplicitsRefsClashPreventerVisitor.py`: the
   implicit symbols (``x``, ``y``, ``z``, ``t``, ``Nx``, ``Ny``,
   ``Nz``) are not referenced in blocks where they do not apply, and
   the coordinates are not assigned to.
``build_symbols_tables``, ``prevent_symbol_def_implicit_clashes``
   :source:`gelb/frontend/SymbolsTablesBuilderVisitor.py` attaches a
   ``SymbolsTable`` (:source:`gelb/frontend/SymbolsTable.py`) to the
   program and to each block, after the wrapper has checked every
   lattice's grid-size rank against its ``d``; then
   :source:`gelb/frontend/ImplicitsDefsClashPreventerVisitor.py`: no
   user symbol is named like an implicit one.
``detect_function_recursion``
   in ``stage1_frontend.py`` itself: a depth-first search over the
   user-function call graph (``CODEGEN`` and ``DIAGNOSTICS`` only).
``add_implicit_symbols``
   :source:`gelb/frontend/ImplicitSymbolsAdderVisitor.py` adds ``Nx``,
   ``Ny``, ``Nz``, ``x``, ``y``, ``z`` and ``t`` to the tables.
``validate_fixed_geometry``, ``apply_constant_overrides``
   :source:`gelb/frontend/GeometryDependencyValidator.py`: paints
   depend only on coordinates and constants; then
   :source:`gelb/frontend/constant_overrides.py`, only with ``-D
   NAME=VALUE``.
``validate_global_constant_initializers``
   :source:`gelb/frontend/GlobalConstantsInitializerValidator.py`: no
   ``random()`` or user function in a global constant's initializer.
``resolve_all_constants``, ``resolve_ranges``
   :source:`gelb/frontend/ConstantsResolverVisitor.py` substitutes
   explicit and implicit constants into their uses;
   :source:`gelb/frontend/RangeResolverVisitor.py` fills omitted
   range bounds with ``0`` and ``Nx-1`` (``Ny-1``, ``Nz-1``).
``infer_types``, ``promote_types``, ``validate_types``
   :source:`gelb/frontend/TypeInferenceVisitor.py` sets
   ``inferred_type`` on every expression,
   :source:`gelb/frontend/TypePromotionVisitor.py` inserts
   ``TypePromotionNode_N`` where a conversion is implicit,
   :source:`gelb/frontend/TypeValidationVisitor.py` rejects what is
   left; the first two ask :source:`gelb/frontend/type_rules.py`.
``validate_constant_assignments``, ``validate_lattice_consistency``
   :source:`gelb/frontend/ConstantAssignmentValidationVisitor.py`: no
   assignment to a constant;
   :source:`gelb/frontend/LatticeConsistencyValidator.py`: all
   lattices share one grid size and periodicity.
``validate_node_classes``, ``initial_validation_geometry``
   :source:`gelb/frontend/NodeClassesValidationVisitor.py` and
   :source:`gelb/frontend/GeometryInitialValidationVisitor.py`: the
   blocks a node class names, and the node classes a paint names, exist.

Midware
=======

``fold_constants``, ``validate_division_by_zero``, ``lower_local_constants``
   :source:`gelb/midware/ConstantFoldingVisitor.py` folds, evaluating
   with :source:`gelb/midware/ast_eval.py`;
   :source:`gelb/midware/DivisionByZeroValidator.py` runs after it so
   that a folded zero is caught;
   :source:`gelb/midware/LocalConstantLowering.py` rewrites a
   block-local ``const`` as a typed declaration.
``validate_streaming_intrinsic_args``, ``sequence_draws``
   :source:`gelb/midware/StencilArgValidator.py` checks the velocity
   sets passed to ``upstream_dfs`` and ``bounce_back_dfs``;
   :source:`gelb/midware/DrawSequencing.py` moves each ``random()``
   call into its own temporary, in source order.
``inline_functions``, ``hoist_intrinsic_args``
   :source:`gelb/midware/inline_functions.py` replaces every user
   function call by the function body;
   :source:`gelb/midware/IntrinsicArgHoisting.py` gives ``dot_prod``
   bare identifiers as arguments.
``collinearity_rewrite``, ``scalar_block_cse``, ``slice_df_expansion``
   :source:`gelb/midware/CollinearityRewriteVisitor.py` (off unless
   ``PipelineOptions.enable_collinearity_rewrite`` is set, which
   ``gelbc`` never does), :source:`gelb/midware/ScalarBlockCSEVisitor.py`
   (``--no-scalar-cse`` turns it off) and
   :source:`gelb/midware/SliceDFExpansionVisitor.py`
   (``--no-slice-simplify`` turns it off), the last two simplifying
   through :source:`gelb/midware/ast_simplify.py`
   (:doc:`07_design_decisions`).
``extract_stencils``, ``validate_initializer_coverage``, ``warn_writeonly_dynamics``, ``warn_unused_lattices``
   :source:`gelb/midware/StencilExtractionVisitor.py` collects the
   lattice reads and writes of every block into a ``ProgramStencils``
   (:source:`gelb/midware/stencil.py`); ``stage2_midware.py`` then
   checks that an initializer that writes a lattice writes all of its
   DFs, and emits two warnings.
``resolve_geometry``, ``validate_boundary_access``, ``validate_write_destinations``, ``validate_df_coverage``, ``geometry_lint``
   :source:`gelb/midware/geometry.py` resolves the paints into the
   per-cell node-class map; on that map ``stage2_midware.py`` checks
   reads and writes off a wall, the destinations of writes at an
   offset, and that every DF a block reads is written in time; then
   :source:`gelb/midware/geometry_lint.py` warns.  ``gelbc`` validates
   ``--output-mode`` first and gets the same checks from
   ``resolve_geometry_for_compile``.

How a diagnostic is produced
============================

Every error is a subclass of ``GeLBException`` in
:source:`gelb/utils/exceptions.py`, constructed with an ``error`` and a
``hint``; twelve of its twenty-five subclasses also take the
offending node or token and return its line and column from
``_source_location``.  The constructor prints the exception at once:
``__str__`` calls ``show_error_in_src`` from
:source:`gelb/utils/error_utils.py`, which prints the source lines
around the location (``GELB_ERROR_CONTEXT = 2`` in
:source:`gelb/utils/config.py` on either side), a caret under the
column, ``[Problem] <error>`` in red and ``[Hint] <hint>`` in green,
and then ``os._exit(1)``; without a location it prints the two
banners alone (``error_with_hint_to_term`` in
:source:`gelb/utils/output_to_terminal.py`).  ``gelbc`` sets
``sys.tracebacklimit = 0`` unless ``-t`` is given, so no traceback
follows.  Warnings go to stderr with a ``[Warning]`` label.

Under pytest and in diagnostics mode, ``_suppress_print_and_exit``
in ``exceptions.py`` suppresses the printing and the exit.
``_run_diagnostics`` in :source:`gelb/gelbc.py` sets
``config.DIAGNOSTICS_MODE``, runs the ``DIAGNOSTICS`` profile,
converts the one caught exception with ``resolve_error_location``
(``error_utils.py``) into a 0-based range, appends the warnings that
``warning_with_hint_to_term`` collected in
``config.DIAGNOSTICS_WARNINGS``, writes one JSON document
``{"diagnostics": [...]}`` to stdout and exits 1 when an error is
among them.
