================
Design decisions
================

Ten decisions a contributor needs to know in order not to undo them.

**The generated parser is committed.**  ``GeLBLexer.py``,
``GeLBParser.py`` and ``GeLBVisitor.py`` in
:source:`gelb/antlr_part/generated_code/` are tracked so that the
package installs and runs without a JDK (:source:`CONTRIBUTING.md`).
:source:`gelb/frontend/stage1_frontend.py` falls back to
``invoke_antlr4_tool`` only when the import fails, and that function
(:source:`gelb/utils/misc.py`) writes into a scratch directory and
replaces the live files only on success
(:source:`gelb/tests/unit/test_antlr_regeneration.py`).  A grammar
change and its regenerated files belong in one commit.

**The midware simplifies only by identities that hold bit for bit.**
:source:`gelb/midware/ast_simplify.py` lists what the two rewrite
passes may do: ``1*x``, ``-1*x``, ``x/1``, ``-(-x)``, the zero
identities only where the sign of a zero cannot change, sign moves
that IEEE 754 defines, literal folding in the expression's width,
and sharing of identical *ordered* subtrees.  Nothing re-associates.
The payoff is the first column of *What must agree*: a default and a
plain build give the same bits, which
:source:`gelb/tests/numeric/test_generated_runtime.py` checks on every
backend.  A rewrite that is "close enough" belongs behind a flag, not
in the default passes.

**The collinearity rewrite is off by default.**
:source:`gelb/midware/CollinearityRewriteVisitor.py` turns ``X - C*(X -
Y)`` into ``(1-C)*X + C*Y``, a re-association without a general error
bound.  ``PipelineOptions.enable_collinearity_rewrite`` in
:source:`gelb/compiler_pipeline.py` defaults to ``False`` and
:source:`gelb/gelbc.py` always passes ``False``; the
``--no-collinearity-rewrite`` option is accepted so that existing
command lines keep working.
:source:`gelb/tests/unit/test_compiler_pipeline.py` asserts that the
pass runs only when enabled.

**The storage layout is chosen per instruction set.**
``_auto_layout_choice`` in :source:`gelb/backends/highway/layout.py`
resolves ``--storage-layout auto``: SoA in 1D; in 2D and 3D the
cell-block-tiled layout when the host compiler defines
``__AVX512F__`` under ``-march=native`` (``_detect_avx512_available``
in :source:`gelb/backends/highway/common.py`, overridable with
``GELB_HAS_AVX512``), SoA otherwise, because the tile shuffle assumes
eight lanes.  The CUDA generator fixes ``storage_layout='soa'``.
Every layout gives the same bits, which
:source:`gelb/tests/integration/test_reproducibility.py` checks.

**The three backends must agree.**  The table *What must agree* in
:source:`docs/user/19_numerical_semantics.rst` is the contract, and
the chapter says that where the compiler disagrees with it, the
compiler is wrong.  The numeric battery, the tutorial regressions
(:source:`gelb/tests/integration/test_tutorial_regressions.py`) and
the examples smoke test can run on all three backends, and
``emission_snapshot.py diff-backends`` fails when an example compiles
on one backend and not on another.  A feature is not done when one
backend emits it.

**The native compiler fuses nothing on the CPU; a strict build fuses
nothing anywhere.**  The default ``GELB_FFLAGS`` and ``GELB_CXXFLAGS``
of :source:`scripts/gelb-run` carry ``-ffp-contract=off``; the one
fusion GeLB decides itself is ``gelb_mul_add`` in
:source:`gelb/backends/cpu_highway_runtime.hpp`, selected once by
``GELB_STRICT_FP``.  A default CUDA build keeps nvcc's fusion;
``--strict-fp`` adds ``-fmad=false``.
:source:`gelb/tests/integration/test_real_width_contract.py` checks
the flags and the fusion probe.

**The CUDA generator is a subclass of the Highway generator.**
``CudaCppCodeGenerator`` in
:source:`gelb/backends/stage3_backend_gpu_cuda_cpp.py` inherits
expression and statement emission from ``HighwayCodeGenerator`` and
overrides the loops with kernels, so expression semantics are written
once for both C++ backends; the Fortran generator is the independent
second implementation.

**``random()`` draws are sequenced before anything moves.**
:source:`gelb/midware/DrawSequencing.py` runs before the inliner and
the rewrites (``compile_source``), giving every draw its own
temporary in source order, because C++ and Fortran leave the order of
two calls in one expression unspecified and the language promises one
draw per element, left to right.

**A diagnostic is an exception that prints itself and exits.**
``GeLBException`` in :source:`gelb/utils/exceptions.py` prints the
source excerpt, the problem and the hint in its constructor and calls
``os._exit(1)``, except under pytest and in ``--diagnostics-json``
mode (``_suppress_print_and_exit``).  A pass reports a problem by
raising, never by printing, so the JSON contract of the VS Code
extension holds.

**Visitor dispatch is explicit.**  ``ASTBaseVisitor.visit``
(:source:`gelb/frontend/ASTBaseVisitor.py`) raises
``GeLBExMissingASTVisitationMethod`` instead of skipping a node, so a
new node class must be handled in every visitor that can reach it,
and an unhandled one fails in the tests rather than in the output.
