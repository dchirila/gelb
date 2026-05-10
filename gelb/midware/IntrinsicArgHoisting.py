"""Hoist non-identifier ``dot_prod`` arguments into local temporaries.

The cpu_highway backend's ``dot_prod`` emit (and similar emits in
other backends) requires both arguments to be bare ``Identifier_N``
nodes naming either a global-constant array or a local array
variable -- this is what enables the codegen-time coefficient pruning
and the ``gelb_signed_sum`` / ``gelb_dot_prod_const`` helper-call
paths.

User code like::

    array[real, 9] cx = EX - ux;
    real k_20 = dot_prod(fIn, cx * cx);

violates that restriction (the second arg is a ``Mul_N``, not an
``Identifier_N``) and previously produced a backend
``NotImplementedError`` deep in codegen with no source-line context.

This pass rewrites such call sites by hoisting the non-identifier
arg into a fresh local declaration *before* the enclosing statement::

    array[real, 9] cx = EX - ux;
    array[real, 9] _gelb_dpa_0 = cx * cx;     // hoisted
    real k_20 = dot_prod(fIn, _gelb_dpa_0);

The transformation is semantics-preserving: the hoisted expression
is evaluated exactly once (where the original would have been), and
the hoisted variable's lifetime matches that of the enclosing block.

Runs AFTER ``inline_functions`` (so we see the inlined call sites,
not the function-definition placeholders) and AFTER
``ConstantFoldingVisitor`` (so e.g. ``EX * EX`` for global-const
``EX`` has already folded to an ``Array1DLiteral_N`` and may already
be the fold target -- but a non-foldable mix like
``cx * cx`` with runtime ``cx`` needs hoisting).
"""

import itertools

from gelb.gelb_ast.ASTNodes import (
    Array1DLiteral_N,
    ArrayDataType_N,
    BroadcastNode_N,
    DynamicBlock_N,
    GaugeBlock_N,
    Identifier_N,
    InitializerBlock_N,
    IntrinsicFunctionCall_N,
    List_N,
    Node_N,
    Program_N,
    TypePromotionNode_N,
    VariableDeclarationStmt_N,
)


# Intrinsics whose arguments the cpu_highway backend (and the array-
# emit paths of the other backends) require to be bare identifiers.
# The midware hoists non-identifier args for each into a temporary
# local.
_HOIST_INTRINSICS = ('dot_prod',)


def hoist_intrinsic_args(ast: Program_N) -> None:
    """In-place rewrite: hoist non-identifier args of every
    ``dot_prod`` call into freshly-named local declarations placed
    immediately before the enclosing statement."""
    counter = itertools.count(0)

    for block in _iter_blocks(ast):
        if block.stmts is None:
            continue
        new_stmts = []
        for stmt in block.stmts.elements:
            hoisted, _ = _rewrite_stmt(stmt, counter)
            new_stmts.extend(hoisted)
            new_stmts.append(stmt)
        block.stmts.elements = new_stmts


def _iter_blocks(ast: Program_N):
    """Yield every Initializer/Dynamic/Gauge block in the program.
    User functions are not visited because ``inline_functions`` runs
    first; what reaches this pass is post-inlining program-level
    blocks only."""
    if ast.initializers is not None:
        for blk in ast.initializers.elements:
            if isinstance(blk, InitializerBlock_N):
                yield blk
    if ast.dynamics is not None:
        for blk in ast.dynamics.elements:
            if isinstance(blk, DynamicBlock_N):
                yield blk
    if ast.gauges is not None:
        for blk in ast.gauges.elements:
            if isinstance(blk, GaugeBlock_N):
                yield blk


def _rewrite_stmt(stmt, counter):
    """Walk ``stmt``'s sub-tree, hoisting non-identifier args of every
    matching intrinsic call into fresh decls.  Returns
    (hoisted_decls, mutated_stmt) where ``hoisted_decls`` is a list of
    new ``VariableDeclarationStmt_N`` to insert *before* ``stmt``."""
    hoisted = []
    _walk_and_rewrite(stmt, hoisted, counter)
    return hoisted, stmt


def _walk_and_rewrite(node, hoisted, counter):
    """Recursive walk that mutates ``IntrinsicFunctionCall_N`` nodes
    in-place by replacing their non-Identifier args with fresh
    Identifier_N references to hoisted temporaries.  ``hoisted``
    accumulates the new ``VariableDeclarationStmt_N`` decls."""
    if isinstance(node, IntrinsicFunctionCall_N) \
            and node.function_name in _HOIST_INTRINSICS:
        _maybe_hoist_args(node, hoisted, counter)

    if isinstance(node, List_N):
        for elem in node.elements:
            _walk_and_rewrite(elem, hoisted, counter)
        return
    if isinstance(node, Node_N):
        for child_name in node.get_children_names():
            child = getattr(node, child_name, None)
            if child is not None:
                _walk_and_rewrite(child, hoisted, counter)


def _maybe_hoist_args(call: IntrinsicFunctionCall_N, hoisted, counter):
    """For each arg of ``call`` that isn't an ``Identifier_N``
    (modulo type/broadcast wrappers), build a hoisted decl and
    substitute the call's arg with an Identifier_N to it."""
    if call.arguments is None:
        return
    args = call.arguments.elements
    for i, arg in enumerate(args):
        if _is_bare_identifier(arg):
            continue
        # Determine the temp's data type from the argument's
        # inferred_type (set by TypeInferenceVisitor).  Falls back to
        # a default 1-D real array shape when type info is missing --
        # in practice every dot_prod arg gets typed because both
        # operand and result shapes are checked at validate-types.
        temp_dtype = _arg_data_type(arg)
        if temp_dtype is None:
            # No usable type info -- leave the argument alone.  The
            # backend will still error, but we won't make matters
            # worse by emitting an untyped decl.
            continue
        temp_name = f'_gelb_dpa_{next(counter)}'
        decl = VariableDeclarationStmt_N(
            call.code_range,
            temp_dtype,
            Identifier_N(call.code_range, temp_name),
            initial_value=arg,
        )
        # Tag the decl's name so downstream passes that look for
        # inferred_type on identifier nodes find one.
        if hasattr(arg, 'inferred_type'):
            decl.name.inferred_type = arg.inferred_type
        hoisted.append(decl)
        # Replace the arg in-place with a reference to the temp.
        replacement = Identifier_N(call.code_range, temp_name)
        if hasattr(arg, 'inferred_type'):
            replacement.inferred_type = arg.inferred_type
        args[i] = replacement


def _is_bare_identifier(node) -> bool:
    """True iff ``node`` is an ``Identifier_N``, possibly under a
    ``TypePromotionNode_N`` or ``BroadcastNode_N`` wrapper that the
    backend already strips."""
    while isinstance(node, TypePromotionNode_N):
        node = node.expr
    while isinstance(node, BroadcastNode_N):
        node = node.scalar_expr
    return isinstance(node, Identifier_N)


def _arg_data_type(arg):
    """Best-effort: derive an ``ArrayDataType_N`` for a hoisted temp
    from the arg's ``inferred_type``.  Returns the ArrayDataType_N or
    None when type info is missing or unusable."""
    inferred = getattr(arg, 'inferred_type', None)
    if isinstance(inferred, ArrayDataType_N):
        # Reuse the inferred_type directly -- same element_dtype +
        # shape as the original expression.
        return inferred
    return None
