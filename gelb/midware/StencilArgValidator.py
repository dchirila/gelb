"""Validation pass for streaming intrinsic velocity-
vector arguments.



These intrinsics drive every backend's stencil-aware codegen
(neighbor-offset emission, valign immediates in CBT, opposite-DF
permutations).  All backends consume the velocity-vector argument
the same way: resolve each identifier in ``global_constants``,
fold the array element values to integers, and use those values
directly.

Today the language doesn't enforce any preconditions on these
arguments -- if a user passes a non-existent identifier, a non-
array, the wrong number of vectors, an array of the wrong length,
or a vector with non-integer values, the failure surfaces as an
internal codegen exception (``RuntimeError`` from cpu_highway,
silent truncation in cpu_fortran_serial, etc.) with no source-
line context.  The user has to debug a backend stack trace for
what is fundamentally a misuse of the intrinsic.

This pass walks every streaming intrinsic call,
checks the velocity-vector argument against the consuming
lattice's ``q`` and ``d``, and raises ``GeLBExStencilError`` with
the call site's ``code_range`` so the standard error reporter
points the user at the offending source line.

Runs AFTER ``fold_constants`` (so values are folded) and BEFORE
``inline_functions`` (so the identifier names in the call sites
are still readable for error messages).
"""

import math

from gelb.gelb_ast.ASTNodes import (
    Array1DLiteral_N,
    BroadcastNode_N,
    ConstantDefinitionStmt_N,
    Identifier_N,
    IntrinsicFunctionCall_N,
    List_N,
    Node_N,
    Program_N,
    TypePromotionNode_N,
)
from gelb.midware.ast_eval import collect_lattice_info, eval_const_expr
from gelb.utils.exceptions import GeLBExStencilError


_STENCIL_INTRINSICS = ('upstream_dfs', 'bounce_back_dfs')


def validate_streaming_intrinsic_args(ast: Program_N) -> None:
    """Validate every streaming intrinsic call site.

    Checks:

    1. Number of velocity-vector entries equals the consuming
       lattice's ``d``.
    2. Each velocity-vector argument is an ``Identifier_N``
       resolving to a 1-D array global constant.
    3. The resolved array has ``q`` elements (matching the
       lattice's ``q``).
    4. Folded element values are all integer-valued (accepts
       both ``array[int, q]`` literally and ``array[real, q]``
       whose folded values happen to be integral -- every existing
       LBM example uses the latter form).

    Raises:
        GeLBExStencilError: with the call-site ``code_range`` and
        a message naming the offending identifier when any check
        fails.
    """
    lattice_info = collect_lattice_info(ast)
    for call_node in _walk_intrinsic_calls(ast, _STENCIL_INTRINSICS):
        _validate_one_call(call_node, ast, lattice_info)


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------


def _validate_one_call(call: IntrinsicFunctionCall_N, ast: Program_N,
                       lattice_info: dict) -> None:
    fname = call.function_name
    args = call.arguments.elements if call.arguments is not None else []

    # Streaming intrinsics share the shape: (lattice, x[, y[, z]], vel_set).
    # The velocity argument is the LAST positional argument; the
    # lattice identifier is the FIRST.
    if len(args) < 2:
        # Underflow caught by the frontend's intrinsic-arity check;
        # belt-and-braces here.
        return
    lattice_arg = args[0]
    vel_set_arg = args[-1]
    lname = (lattice_arg.name if isinstance(lattice_arg, Identifier_N)
             else None)
    if lname is None or lname not in lattice_info:
        # Lattice identifier itself is bogus -- that's a separate
        # validation owned by the symbol-table check.  Bail.
        return
    info = lattice_info[lname]
    expected_q = info['q']
    expected_d = info['d']

    # Velocity-vector list extraction.  1-D programs pass a single
    # bare identifier (no braces); higher-d programs pass an
    # ``Array1DLiteral_N`` wrapping ``{EX, EY[, EZ]}``.
    vel_nodes = _extract_velocity_nodes(vel_set_arg)

    # Check #1: count matches lattice.d.
    if len(vel_nodes) != expected_d:
        raise GeLBExStencilError(
            f"{fname}() expects {expected_d} velocity vector(s) for "
            f"lattice '{lname}' (d={expected_d}), got "
            f"{len(vel_nodes)}.",
            f"Pass exactly {expected_d} velocity-vector identifier"
            f"{'s' if expected_d != 1 else ''} as the last "
            f"argument — for D{expected_d}Q{expected_q} this is "
            f"{'EX' if expected_d == 1 else '{EX, EY' + (', EZ' if expected_d == 3 else '') + '}'}"
            f" (or any equivalently-named integer-valued constants).",
            source_line=call.code_range.start_line,
            source_end_line=call.code_range.stop_line,
        )

    # Check each velocity-vector identifier against checks #2-#4.
    for axis_idx, vel_node in enumerate(vel_nodes):
        _validate_one_velocity_vector(
            call, vel_node, axis_idx, lname, expected_q, ast)

    if fname == 'bounce_back_dfs':
        if len(args) != expected_d + 2:
            raise GeLBExStencilError(
                f"{fname}() expects lattice, {expected_d} coordinate(s), "
                "and a velocity set",
                "Pass the current cell coordinates in x, y, z order.",
                source_line=call.code_range.start_line,
                source_end_line=call.code_range.stop_line,
            )
        vectors = []
        for vel_node in vel_nodes:
            value = _find_global_constant(ast, vel_node.name).value
            while isinstance(value, TypePromotionNode_N):
                value = value.expr
            vectors.append([int(eval_const_expr(e, ast=ast))
                            for e in value.value.elements])
        directions = set(zip(*vectors))
        for direction in directions:
            if tuple(-v for v in direction) not in directions:
                raise GeLBExStencilError(
                    f"{fname}() has no opposite for velocity {direction}",
                    "Use a symmetric velocity set containing every opposite direction.",
                    source_line=call.code_range.start_line,
                    source_end_line=call.code_range.stop_line,
                )


def _validate_one_velocity_vector(call: IntrinsicFunctionCall_N,
                                  vel_node, axis_idx: int,
                                  lname: str, expected_q: int,
                                  ast: Program_N) -> None:
    """Run checks #2-#4 on one entry of the velocity-vector list."""
    # Strip any wrappers.
    while isinstance(vel_node, TypePromotionNode_N):
        vel_node = vel_node.expr
    while isinstance(vel_node, BroadcastNode_N):
        vel_node = vel_node.scalar_expr

    fname = call.function_name
    axis_label = ('EX', 'EY', 'EZ')[axis_idx] if axis_idx < 3 \
        else f'velocity[{axis_idx}]'

    # Check #2: identifier referencing a global constant.
    if not isinstance(vel_node, Identifier_N):
        raise GeLBExStencilError(
            f"{fname}() {axis_label} argument must be an identifier "
            f"naming a global-constant velocity-vector array; got "
            f"{type(vel_node).__name__}.",
            "Declare the velocity vector as a `const array[..., q]` "
            "in `global_constants` and pass its identifier name "
            "(e.g. `EX`).",
            source_line=call.code_range.start_line,
            source_end_line=call.code_range.stop_line,
        )
    name = vel_node.name
    const_stmt = _find_global_constant(ast, name)
    if const_stmt is None:
        raise GeLBExStencilError(
            f"{fname}() {axis_label} argument '{name}' is not a "
            f"global constant.",
            "Declare it as `const array[..., q] = {{...}}` in the "
            "`global_constants` block.  Local variables, function "
            "parameters, and lattice-derived arrays are not "
            "supported as stencil-vector arguments.",
            source_line=call.code_range.start_line,
            source_end_line=call.code_range.stop_line,
        )

    # Check #3: array-typed, 1-D, length q.
    arr_value = const_stmt.value
    while isinstance(arr_value, TypePromotionNode_N):
        arr_value = arr_value.expr
    while isinstance(arr_value, BroadcastNode_N):
        arr_value = arr_value.scalar_expr
    if not isinstance(arr_value, Array1DLiteral_N):
        raise GeLBExStencilError(
            f"{fname}() {axis_label} argument '{name}' must be a 1-D "
            f"array literal; got {type(arr_value).__name__}.",
            "Stencil vectors must be `const array[..., q] = "
            "{{c0, c1, ...}}` literals (post-folding).  Computed "
            "or 2-D-shaped constants aren't supported here.",
            source_line=call.code_range.start_line,
            source_end_line=call.code_range.stop_line,
        )
    elements = arr_value.value.elements
    actual_q = len(elements)
    if actual_q != expected_q:
        raise GeLBExStencilError(
            f"{fname}() {axis_label} argument '{name}' has "
            f"{actual_q} elements but lattice '{lname}' has "
            f"q={expected_q}.",
            f"Resize the array to {expected_q} elements, or use a "
            f"different velocity-vector constant matching the "
            f"lattice's stencil width.",
            source_line=call.code_range.start_line,
            source_end_line=call.code_range.stop_line,
        )

    # Check #4: every element is integer-valued (as a folded value,
    # regardless of the declared element type).  All current LBM
    # examples declare as ``array[real, q]`` with integer literals
    # (0.0, 1.0, -1.0); accept that form too.
    for i, elem in enumerate(elements):
        try:
            v = eval_const_expr(elem, ast=ast)
        except (ValueError, TypeError) as e:
            raise GeLBExStencilError(
                f"{fname}() {axis_label}[{i}] (in '{name}') could "
                f"not be folded to a constant value: {e}.",
                "Stencil-vector array elements must fold to compile-"
                "time integer constants (typically -1, 0, or +1).",
                source_line=call.code_range.start_line,
                source_end_line=call.code_range.stop_line,
            )
        if not _is_integer_valued(v):
            raise GeLBExStencilError(
                f"{fname}() {axis_label}[{i}] (in '{name}') is "
                f"{v!r}, which is not integer-valued.",
                "Stencil vectors describe lattice-cell offsets "
                "(typically -1, 0, or +1).  Non-integer values "
                "would produce nonsense neighbour reads.  Fix the "
                "constant or use an `array[int, q]` declaration.",
                source_line=call.code_range.start_line,
                source_end_line=call.code_range.stop_line,
            )


def _extract_velocity_nodes(vel_set):
    """The velocity argument is either a bare identifier (1-D
    program) or an ``Array1DLiteral_N`` wrapping a List_N of
    identifiers (D>=2).  Strip wrappers and return the list."""
    while isinstance(vel_set, TypePromotionNode_N):
        vel_set = vel_set.expr
    while isinstance(vel_set, BroadcastNode_N):
        vel_set = vel_set.scalar_expr
    if isinstance(vel_set, Array1DLiteral_N):
        return list(vel_set.value.elements)
    # 1-D form: bare identifier (or whatever expression the user
    # passed).  Wrap in a single-element list so the per-axis
    # validator handles it uniformly.
    return [vel_set]


def _find_global_constant(ast: Program_N, name: str):
    """Return the ``ConstantDefinitionStmt_N`` whose name matches
    ``name``, or None if no such top-level constant exists."""
    if ast.global_constants is None:
        return None
    for stmt in ast.global_constants.stmts.elements:
        if (isinstance(stmt, ConstantDefinitionStmt_N)
                and stmt.name.name == name):
            return stmt
    return None


def _is_integer_valued(v) -> bool:
    """True iff v is a Python int OR a float that equals its int
    truncation exactly (i.e. an integer-valued real)."""
    if isinstance(v, bool):
        # bool is a subclass of int; reject so `True`/`False`
        # aren't silently accepted as 1/0 stencil offsets.
        return False
    if isinstance(v, int):
        return True
    if isinstance(v, float):
        return math.isfinite(v) and v == int(v)
    return False


def _walk_intrinsic_calls(node, names):
    """Yield every ``IntrinsicFunctionCall_N`` in the AST whose
    ``function_name`` is in ``names``."""
    if isinstance(node, IntrinsicFunctionCall_N) \
            and node.function_name in names:
        yield node
    if isinstance(node, List_N):
        for elem in node.elements:
            yield from _walk_intrinsic_calls(elem, names)
        return
    if isinstance(node, Node_N):
        for child_name in node.get_children_names():
            child = getattr(node, child_name)
            if child is not None:
                yield from _walk_intrinsic_calls(child, names)
