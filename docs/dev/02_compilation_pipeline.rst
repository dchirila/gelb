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
:source:`gelb/frontend/stage1_frontend.py` and the midware checks by
those of :source:`gelb/midware/stage2_midware.py`;
``apply_constant_overrides``, ``sequence_draws``, ``inline_functions``,
``hoist_intrinsic_args``, ``check_stage1``, ``check_stage2``, the three rewrites and ``resolve_geometry``
are imported straight from their own modules (the two runs after
inlining are ``fold_constants`` and ``validate_division_by_zero``
again).  The module behind each
pass is named below, under the names ``record`` uses.  Two sanity
checks: ``validate_ast_root`` confirms that the root is a
``Program_N``, and ``validate_midware_input`` confirms that again and
that the root carries the seven block attributes
(``global_constants`` through ``geometry``).

Not every pass runs in every profile: ``detect_function_recursion``
and the midware passes from ``validate_streaming_intrinsic_args`` to
``slice_df_expansion`` run under ``CODEGEN`` and ``DIAGNOSTICS`` only;
``extract_stencils`` and the checks after it run only with
``PipelineOptions.require_stencils``, the map-based checks only with
``require_geometry``, and ``geometry_lint`` not under
``--no-geometry-lint``; ``PROGRAM_ANALYSIS`` runs ``resolve_geometry``
(with ``require_geometry``) and then ``extract_stencils`` (with
``require_stencils``) and none of the coverage, wall,
write-destination or lint checks
(:source:`gelb/tests/unit/test_compiler_pipeline.py`).

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
   gauges declare named results; a gauge output is a scalar, and a gauge
   assigns all of its outputs; gauges that declare an output of the same
   name give it one type (``int64`` is ``int``, ``real64`` is ``real``);
   no gauge output is named ``time``, the output file's time-step
   variable.
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
   user symbol is named like an implicit one that applies in its block
   (``reserved_definition_names_for_block`` in
   :source:`gelb/frontend/implicit_symbols.py`; a function may name a
   local ``x`` or ``t``, but not ``Nx``).
``detect_function_recursion``
   in ``stage1_frontend.py`` itself: a depth-first search over the
   user-function call graph.
``add_implicit_symbols``
   :source:`gelb/frontend/ImplicitSymbolsAdderVisitor.py` adds the
   dimension constants (``Nx``, and ``Ny``, ``Nz`` as the dimensionality
   allows) to the program's table and the coordinates and ``t`` to each
   initializer, dynamic and gauge; the geometry block gets the
   coordinates but not ``t``.
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
   range bounds with ``0`` and ``Nx-1`` (``Ny-1``, ``Nz-1``), including
   in ``global_constants``. Type inference resolves synthetic open array
   bounds against the declared array extents.
``resolve_declared_shapes``
   :source:`gelb/frontend/declared_shapes.py` resolves all declared array
   extents before type inference, including function signatures regardless
   of declaration order. It uses the declaration block's typed constants
   and, in initializers, dynamics and gauges, active grid dimensions.
   Extents must be positive integers; shapes become literal dimensions.
``infer_types``, ``promote_types``, ``validate_types``
   :source:`gelb/frontend/TypeInferenceVisitor.py` sets
   ``inferred_type`` on every expression,
   :source:`gelb/frontend/TypePromotionVisitor.py` inserts
   ``TypePromotionNode_N`` where a conversion is implicit,
   :source:`gelb/frontend/TypeValidationVisitor.py` rejects what is
   left; the first two ask :source:`gelb/frontend/type_rules.py`.
   A store (``_converted_for_store``, ``_store_mismatch``) is converted
   and checked by one rule, whether it is a declaration's initializer,
   a call's argument stored in its parameter, or a destructuring call's
   output stored in its target (recorded as ``output_stores`` for the
   inliner).
``canonicalize_types``
   :source:`gelb/frontend/ASTInvariantValidator.py` attaches immutable
   :source:`gelb/gelb_ast/CanonicalType.py` metadata after type validation.
   Scalars have dimensions ``()``, singleton arrays ``(1,)``; aliases
   ``int64`` and ``real64`` map to ``int`` and ``real`` without rewriting
   declared element-type spelling. Assigning ``inferred_type`` synchronizes
   concrete expression metadata. This pass reads the already resolved
   shapes directly; unresolved shapes fail ``check_stage1``.
``validate_static_selectors``
   :source:`gelb/frontend/static_selectors.py` checks block and function
   ``const`` initializers, DF read/write selectors, and array indices after
   ``canonicalize_types`` and before ``validate_constant_assignments`` in
   every profile. Expression and call-graph walks use explicit stacks;
   recursive calls cannot qualify as constant selectors. DF bounds must
   evaluate to integers in the lattice's DF range. Spatial indices retain
   the stencil pass's coordinate-plus-constant check.
``validate_constant_assignments``, ``validate_lattice_consistency``
   :source:`gelb/frontend/ConstantAssignmentValidationVisitor.py`: no
   assignment to a constant;
   :source:`gelb/frontend/LatticeConsistencyValidator.py`: all
   lattices share one grid size and periodicity.
``validate_node_classes``, ``initial_validation_geometry``
   :source:`gelb/frontend/NodeClassesValidationVisitor.py` and
   :source:`gelb/frontend/GeometryInitialValidationVisitor.py`: the
   blocks a node class names, and the node classes a paint names, exist.

``check_stage1``
   :source:`gelb/frontend/ASTInvariantValidator.py`. Immediately after
   geometry's initial validation and before
   ``validate_midware_input``, check live types, symbol metadata, computational
   expressions, and deterministic structural children. Both type attachment
   and this check use explicit stacks. Syntactic names, shape/selection bounds,
   inner array row wrappers, and the specified non-value expressions retain
   their existing inference behavior; typed paint bounds and literal leaves
   are still checked. Live inferred types are cross-checked to catch in-place
   edits that bypass assignment synchronization.

   ``PipelineOptions.strict_invariants`` defaults to true in every profile:
   internal violations raise ``GeLBInternalInvariantError``. Editor diagnostics
   and program-analysis entry points explicitly disable strictness and report
   structured ``(internal)`` warnings. User errors remain errors.

Midware
=======

The seven statement mutators below use
:source:`gelb/midware/BlockMutationHelper.py` to register new declarations,
replace existing entries in place and remove dead entries. Each local symbol
points to its live declaration and carries its canonical type; parameters,
outputs, implicit symbols and parent tables stay intact. Temporary names skip
names already in the local or parent table. Each block restarts its temporary
counters at zero; successive straight-line CSE runs within a block share its
counter.
Slice expansion keeps an array whole when any of its scalar names is taken.
The inliner finishes each program block against the original function bodies,
using flat prefixes from a counter local to that block. Its ``inline_call_args``
IDs remain unique across the program, independently of these prefix counters.
It then processes retained functions callees first, breaking call-graph ties
alphabetically and restarting the prefix counter for each function. These
synchronized definitions remain available for geometry evaluation. Both block
and function declaration order therefore leave emitted temporary names unchanged.


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
``inline_functions``, ``fold_constants_after_inlining``, ``validate_division_by_zero_after_inlining``, ``hoist_intrinsic_args``
   :source:`gelb/midware/inline_functions.py` replaces every user
   function call by the function body, copying every statement with
   the caller's values; a parameter the body stores into is bound to a
   copy of the argument, and an output to a variable of its own where
   an argument reads its target, another output goes to the same
   target, it has another type, the body reads it, or the target is
   not a variable of the caller's block (a name of a function body or of
   the inliner); whether a call is a call of constants, only the
   folder decides.  It inlines again until a pass inlines no call; a
   call left in the DF selector or a spatial index of a lattice store
   is reported by the stencil check.  It records, on each statement it
   emits, the calls it comes from (``inline_calls``), on each
   declaration of a name only inlined code holds its binding
   (``inline_binding``: argument, parameter copy, local or output, and
   the call), and on the program each call's argument sources
   (``inline_call_args``).  The folder and the zero-divisor check (the
   modules of ``fold_constants`` and
   ``validate_division_by_zero``) then run again.  Following each block
   in order, the folder decides at a call's first statement whether its
   arguments hold constants there (a constant array among them: any
   global constant, an array literal of constants, an array a name of
   the inliner holds; constant arrays are carried into constant-index
   element and slice selections as well as reductions); such a call is a constant
   expression, folded and checked like the rest, with the constants
   its names hold carried into their uses (an argument's always, its
   locals' and outputs' only in a call of constants, a block-local
   constant's (``lowered_const``) always, a user variable's never) and
   its names dropped where nothing reads them; an error found in
   inlined code names the calls. Constant selections retain the array
   element width and selected shape; 2-D ``sum`` folds row by row, left
   to right. Folded indices on array reads and stores are checked against
   declared extents after inlining. Unread inliner array copies are pruned;
   block-local constant declarations stay. Overflowing narrow-real
   conversions fold to signed infinities, while finite standalone
   promotions remain explicit.
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

``check_stage2``
   :source:`gelb/frontend/ASTInvariantValidator.py` checks the program and
   every block table against live declarations, including retained functions,
   parameters, outputs and implicit symbols. It rejects residual local
   constants, stale or missing entries, duplicate names, dangling references
   and inconsistent canonical types. Its explicit stacks also check retained
   function trees and deterministic children without recursive expression
   walks. Expressions whose inferred type is absent retain that behavior.

   This check runs once at the end of ``compile_source``, after any requested
   geometry and stencil passes. Normal CLI codegen defers it: ``gelbc`` calls
   it immediately after ``resolve_geometry_for_compile`` and before
   ``build_backend_context``. ``--stencils`` and ``--show-mapping`` use the
   non-deferred pipeline check. With ``strict_invariants=True`` it raises
   ``GeLBInternalInvariantError``; diagnostics and program-analysis entry
   points disable strictness and report ``(internal)`` warnings instead.
   Mutation-helper errors are ordinary internal exceptions, never user-error
   constructors that terminate the process.

How a diagnostic is produced
============================

Every error is a subclass of ``GeLBException``
(:source:`gelb/utils/exceptions.py`; one more subclass sits in
:source:`gelb/frontend/LatticeConsistencyValidator.py`), constructed
with an ``error`` and a ``hint``; twelve of the twenty-five subclasses
in ``exceptions.py`` also carry a source location (the offending node
or token, or a source line) that ``_source_location`` returns as a
line and column.  The constructor prints the exception at once:
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
``config.DIAGNOSTICS_MODE``, runs the ``DIAGNOSTICS`` profile with
stencils and geometry required, locates the one ``GeLBException`` it
catches with ``resolve_error_location`` (``error_utils.py``, 1-based
lines) and turns that into a 0-based range with ``_diag_range`` (any
other exception becomes a file-level ``(internal)`` error), appends
the warnings that
``warning_with_hint_to_term`` collected in
``config.DIAGNOSTICS_WARNINGS``, writes one JSON document
``{"diagnostics": [...]}`` to stdout and exits 1 when an error is
among them.
