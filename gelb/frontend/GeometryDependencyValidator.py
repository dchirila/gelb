#!/usr/bin/env python3
"""Reject geometry that depends on anything but coordinates and constants.

In this version of GeLB the geometry is fixed for the whole run: the
``geometry`` block is resolved once, at compile time.  A ``where``
predicate may therefore use only the implicit coordinates, constants,
dimension constants and pure functions of them; a range or point paint
may use only constants.  Anything else (a lattice value, ``random()``,
a coordinate in a range bound) is reported here with a message that says
what is missing, instead of failing later inside the compile-time
evaluator with a Python error.

Runs after the symbol tables and implicit symbols exist, before type
inference.
"""

from gelb.frontend.implicit_symbols import (
    COORDINATE_SYMBOL_NAMES,
    TIMESTEP_SYMBOL_NAME,
)
from gelb.gelb_ast.ASTNodes import (
    BorderStmt_N,
    ConditionalPaintStmt_N,
    FunctionBlock_N,
    Identifier_N,
    IntrinsicFunctionCall_N,
    List_N,
    Node_N,
    PaintNodesStmt_N,
    RectSelOfLatticeInDFs_N,
    RectSelOfLatticeOutDFs_N,
    UserFunctionCall_N,
    VariableAssignmentStmt_N,
    VariableDeclarationStmt_N,
)
from gelb.utils.exceptions import GeLBExTypeError


_FIXED_GEOMETRY_HINT = (
    "In this version the geometry is fixed for the whole run: a paint"
    " predicate may use only the coordinates (x, y, z), constants and"
    " pure functions of them, and a range or point paint only constants."
)

# Intrinsics the compile-time evaluator supports in a predicate.  They
# are deterministic scalar functions; everything else is rejected here.
PREDICATE_INTRINSICS = frozenset(
    ('abs', 'min', 'max', 'mod', 'sqrt', 'sin', 'cos', 'tan', 'tanh',
     'exp', 'log', 'atan2',
     # numeric conversions
     'int', 'int8', 'int16', 'int32', 'int64',
     'real', 'real16', 'real32', 'real64'))


def _walk(node):
    """Yield every AST node below ``node`` (including it)."""
    if node is None:
        return
    if isinstance(node, List_N):
        for elem in node.elements:
            yield from _walk(elem)
        return
    if not isinstance(node, Node_N):
        return
    yield node
    for child in node.get_children():
        if isinstance(child, (Node_N, list)):
            if isinstance(child, list):
                for c in child:
                    yield from _walk(c)
            else:
                yield from _walk(child)


def _check_expr(expr, ast, *, where, calls):
    """Reject run-time dependencies in ``expr`` and in the functions it calls.

    ``where`` is 'a where predicate' or 'a range or point paint'.
    """
    for node in _walk(expr):
        if isinstance(node, (RectSelOfLatticeInDFs_N, RectSelOfLatticeOutDFs_N)):
            lattice = getattr(getattr(node, 'lattice_name', None), 'name', '?')
            raise GeLBExTypeError(
                node,
                f"{where.capitalize()} in the geometry block reads lattice"
                f" '{lattice}', but state-dependent geometry is not"
                f" supported in this version of GeLB",
                _FIXED_GEOMETRY_HINT)
        if isinstance(node, IntrinsicFunctionCall_N):
            name = str(node.function_name)
            if name == 'random':
                raise GeLBExTypeError(
                    node,
                    f"{where.capitalize()} in the geometry block calls"
                    f" random(), which is not allowed: the geometry is"
                    f" resolved once, at compile time, and must be"
                    f" deterministic",
                    _FIXED_GEOMETRY_HINT)
            if name not in PREDICATE_INTRINSICS:
                raise GeLBExTypeError(
                    node,
                    f"{where.capitalize()} in the geometry block calls"
                    f" {name}(), which the compile-time evaluator does not"
                    f" support",
                    "Supported here: " + ", ".join(sorted(PREDICATE_INTRINSICS))
                    + ". Array intrinsics (sum, dot_prod, matmul, ...)"
                    " and lattice intrinsics are not.")
        if isinstance(node, Identifier_N):
            if node.name == TIMESTEP_SYMBOL_NAME and where != 'a function':
                raise GeLBExTypeError(
                    node,
                    "The geometry block refers to the time step 't', but"
                    " time-dependent geometry is not supported in this"
                    " version of GeLB",
                    _FIXED_GEOMETRY_HINT)
            if (node.name in COORDINATE_SYMBOL_NAMES
                    and where == 'a range or point paint'):
                raise GeLBExTypeError(
                    node,
                    f"A range or point paint cannot use the coordinate"
                    f" '{node.name}'; coordinates are available only"
                    f" inside a 'where' predicate",
                    "Write nodes[where <condition on x, y, z>] = CLASS;"
                    " to paint the cells that satisfy a condition, or"
                    " give constant bounds: nodes[lo:hi, ...] = CLASS;")
        if isinstance(node, UserFunctionCall_N):
            _check_function(node, ast, calls)


class _Calls:
    """Functions on the current call chain (``active``) and the ones
    already checked (``done``).  Keeping the two apart is what turns a
    cycle into a diagnostic instead of a silent return; a recursive
    predicate once reached the evaluator as a Python RecursionError."""

    def __init__(self):
        self.active: list[str] = []
        self.done: set[str] = set()


def _check_function(call, ast, calls):
    name = call.function_name.name
    if name in calls.active:
        chain = ' -> '.join(calls.active[calls.active.index(name):] + [name])
        raise GeLBExTypeError(
            call,
            f"Function '{name}' is used by the geometry block and calls"
            f" itself ({chain}); a paint predicate cannot use a recursive"
            f" function",
            "A paint predicate is evaluated once per cell at compile time"
            " by running the functions it calls in source order; write"
            " the function without recursion.")
    if name in calls.done:
        return
    func = _find_function(ast, name)
    if func is None:
        return  # unknown function: reported by type inference
    outputs = func.outputs.elements if func.outputs is not None else []
    if len(outputs) != 1:
        raise GeLBExTypeError(
            call,
            f"Function '{name}' has {len(outputs)} outputs; a function"
            f" called from the geometry block must have exactly one",
            "A paint predicate is a scalar bool; write a single-output"
            " function (or a plain expression) for it.")
    calls.active.append(name)
    try:
        for stmt in func.stmts:
            if isinstance(stmt, VariableDeclarationStmt_N):
                value = getattr(stmt, 'initial_value', None)
                if value is not None:
                    _check_expr(value, ast, where='a function', calls=calls)
            elif isinstance(stmt, VariableAssignmentStmt_N):
                _check_expr(stmt.rhs, ast, where='a function', calls=calls)
            else:
                raise GeLBExTypeError(
                    stmt,
                    f"Function '{name}' is called from the geometry block,"
                    f" but contains a statement the compile-time evaluator"
                    f" does not support",
                    "A function used in a paint predicate may contain only"
                    " scalar declarations and assignments, evaluated in"
                    " source order.")
    finally:
        calls.active.pop()
    calls.done.add(name)


def _find_function(ast, name):
    if ast.symbol_defs is not None:
        sdef = ast.symbol_defs.get_symbol_definition(name)
        if sdef is not None and sdef.tag == 'function' and \
                isinstance(sdef.value, FunctionBlock_N):
            return sdef.value
    if ast.functions:
        for func in ast.functions:
            if func.name.name == name:
                return func
    return None


def validate_geometry_dependencies(ast):
    """Entry point: check every statement of the geometry block."""
    if ast.geometry is None:
        return
    calls = _Calls()
    for stmt in ast.geometry.stmts:
        if isinstance(stmt, ConditionalPaintStmt_N):
            _check_expr(stmt.predicate, ast, where='a where predicate',
                        calls=calls)
        elif isinstance(stmt, PaintNodesStmt_N):
            _check_expr(stmt.lhs, ast, where='a range or point paint',
                        calls=calls)
        elif isinstance(stmt, BorderStmt_N):
            continue
