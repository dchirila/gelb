========================
The AST and the visitors
========================

Nodes
=====

Every AST node class lives in :source:`gelb/gelb_ast/ASTNodes.py` and
derives from ``Node_N``, an abstract class whose constructor takes a
``code_range`` (a ``CodeRange`` from :source:`gelb/utils/CodeRange.py`:
1-based ``start_line`` and ``stop_line``, 0-based ``start_col`` and
``stop_col``).  ``Node_N`` has no field list: ``get_children_names``
discovers a node's children with ``dir()``, skipping private names,
``code_range``, ``symbol_defs`` and the metadata attributes that
later passes attach (``_AST_METADATA_FIELD_NAMES``: ``inferred_type``,
``symbol_tag`` and the others) and the names of ``Node_N``'s own
methods, so a new public attribute, and a new public method, on a node
is a child unless it is listed there; give helper methods a leading
underscore.  On top of that come
``get_children``, ``get_referenced_symbols`` (the ``SymbolReference``
objects of :source:`gelb/gelb_ast/SymbolReference.py` reached from a
subtree), ``replace_symbol_references`` and ``is_terminal_node``.
``List_N`` wraps a Python list of nodes.  ``Program_N`` is the root,
with one attribute per top-level construct
(``simulation_description``, ``global_constants``, ``lattices``,
``initializers``, ``dynamics``, ``gauges``, ``functions``,
``node_classes``, ``geometry``); the root and the blocks carry a
``symbol_defs`` table once ``build_symbols_tables`` has run
(``SymbolsTable`` in :source:`gelb/frontend/SymbolsTable.py`, a list of
``SymbolDefinition`` from :source:`gelb/gelb_ast/SymbolDefinition.py`
with a parent table).  ``Stmt_N``, ``Expr_N`` and ``Block_N`` are the
intermediate bases; ``Div_N`` has ``left`` and ``right``,
``IntrinsicFunctionCall_N`` has ``function_name`` (a string) and
``arguments`` (a ``List_N``).

From the parse tree to the AST
==============================

:source:`gelb/antlr_part/grammars/GeLB.g4` (with the tokens of
:source:`gelb/antlr_part/grammars/CommonLexerRules.g4`) is the grammar;
``GeLBLexer.py``, ``GeLBParser.py`` and ``GeLBVisitor.py`` in
:source:`gelb/antlr_part/generated_code/` are generated from it by
``invoke_antlr4_tool`` in :source:`gelb/utils/misc.py`, which
:source:`scripts/regenerate_antlr.sh` runs.  ``get_ast`` in
:source:`gelb/frontend/stage1_frontend.py` parses the source with the
start rule ``gelb_program``, then hands the parse tree to
``ASTBuilderVisitor`` (:source:`gelb/frontend/ASTBuilderVisitor.py`), a
subclass of the generated ``GeLBVisitor``.  Its
``visitGelb_program`` creates the ``Program_N`` and sorts the
children returned by ``get_list_of_children_sub_asts`` into the root's
attributes; that helper visits every child of a rule context and keeps
the results that are truthy (``None`` is dropped, and so is an empty
``List_N``, because ``List_N`` defines ``__len__``), so a rule with no
``visit...`` override contributes nothing to the AST.  The builder counts the
blocks it meets and raises ``GeLBExInvalidNoOfOccurrences`` against
the multiplicities written as comments on the ``gelb_program`` rule
in ``GeLB.g4``.  Every node the builder creates gets its
``code_range`` from ``code_range_from_ctx`` in ``CodeRange.py``, except
the four ``List_N`` containers on the root for the repeatable blocks
(``initializers``, ``dynamics``, ``gauges``, ``functions``), whose
``code_range`` is ``None`` because their members need not be
contiguous in the source.

Visitors
========

``ASTBaseVisitor`` in :source:`gelb/frontend/ASTBaseVisitor.py` has one
method, ``visit(node, ast_root_node)``: it looks up
``visit<ClassName>`` on itself, calls it with the node and the root,
and raises ``GeLBExMissingASTVisitationMethod`` if the method is
missing; the root is passed everywhere so that no visitor needs a
global.  Most frontend passes and the rewriting midware passes of
:doc:`02_compilation_pipeline` are such visitors (the classes in
:source:`gelb/frontend/` and :source:`gelb/midware/` that derive from
``ASTBaseVisitor``); the remaining passes, among them
``detect_function_recursion``, ``lower_local_constants``,
``sequence_draws``, ``inline_functions``, ``hoist_intrinsic_args``,
``resolve_geometry`` and the stencil checks after ``extract_stencils``,
are plain functions, or walkers of their own
(``StencilExtractionVisitor``, ``LatticeAccessContextValidator``),
over the AST or over ``ProgramStencils``.
:source:`gelb/frontend/visitor_mixins.py` supplies the shared parts:
``BinaryOperationMixin`` (one handler for all binary operators),
``ArrayLiteralProcessingMixin``, ``ProgramTraversalMixin``
(``traverse_program_blocks`` visits the blocks in a fixed order and
calls the ``_before_block_visit`` and ``_after_block_visit`` hooks;
``_visit_block_stmts`` visits a block's ``stmts``) and
``SymbolTableUtilityMixin``.

The pattern, in one existing visitor
====================================

:source:`gelb/midware/DivisionByZeroValidator.py` is a complete small
pass.  ``class DivisionByZeroValidator(ASTBaseVisitor,
ProgramTraversalMixin)``; ``visitProgram_N`` calls
``traverse_program_blocks``; the block methods call
``_visit_block_stmts``; ``visitDiv_N`` visits ``left`` and ``right``
and raises ``GeLBExTypeError(node.right, error, hint)`` when the
divisor is a literal zero (``0``, ``0.0`` or ``false``), possibly
under a ``TypePromotionNode_N``; ``visitIntrinsicFunctionCall_N`` does
the same for ``mod`` with a zero second argument and ``visitPow_N`` for
an integer ``0`` raised to a negative integer literal; every other
expression method visits its children, and the terminal
methods (``visitIntLiteral_N`` and the like) return the node.  The
wrapper ``validate_division_by_zero`` in
:source:`gelb/midware/stage2_midware.py` instantiates it and calls
``visit(ast, ast)``; ``compile_source`` calls the wrapper and
``record("validate_division_by_zero")``;
:source:`gelb/tests/unit/midware/test_division_by_zero_validation.py`
tests it and :source:`gelb/tests/unit/test_compiler_pipeline.py`
pins its place in the sequence (:doc:`05_extending_gelb`).
