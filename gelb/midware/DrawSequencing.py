"""Sequence ``random()`` draws (user manual, Numerical semantics:
Random numbers).

The contract: in a slice or array expression ``random()`` draws once
per element, in element index order; several calls in one expression
draw left to right; default and plain builds of one program draw the
same numbers (Numerical semantics: What the optimizer promises).  C,
C++ and Fortran leave the order of two calls in one expression
unspecified, and Fortran broadcasts one draw over an array section, so
the emitters cannot be left to decide.

This pass rewrites every statement that calls ``random()``, directly
or through a user function whose body draws, so that no expression
contains more than the draws of one temporary, in source order.  Each
call, in the order a left-to-right walk of the statement meets them,
becomes a fresh local declared before the statement and initialised by
that one call:

- a call in a scalar context becomes ``real _gelb_draw_k = random();``
- a call whose nearest enclosing array-typed expression (or the
  statement's array-typed left-hand side) has ``Q`` elements becomes
  ``array[real, Q] _gelb_draw_k = random();``, a broadcast that every
  backend evaluates once per element, in index order -- the NumPy model,
  where ``rng.random(9) - rng.random(9)`` draws nine numbers and then
  nine more.  An element of an array constructor (``{random(),
  random(), random()}``) is a scalar context: three scalar draws.
- a call of a user function whose body draws (itself or through the
  functions it calls) is one unit of the left-to-right order, as a
  Python call is: nested in a larger expression it becomes
  ``<output type> _gelb_call_k = F(args);`` after the temporaries of
  its arguments, so that the arguments draw first, then the body, then
  whatever follows in the expression.  A call that is the whole
  right-hand side needs no temporary.

The statement then reads the temporaries instead.  A broadcast whose
scalar expression drew per element becomes the array-valued expression
itself (``arr = 0.5 * random()`` reads as ``arr = 0.5 * _gelb_draw_k``,
``arr = sqrt(random())`` as ``arr = sqrt(_gelb_draw_k)``); the emitters
evaluate such an expression element by element.

Function bodies are sequenced like blocks, so that a draw inside a
function happens where the inlined body does.  The pass runs before
``inline_functions``, which hoists a call's arguments ahead of the
statement and would otherwise reorder ``random() - F(random())``, and
before every other pass that moves an expression.  Later passes keep
the order: the scalar CSE never shares a subtree with a draw
(``ast_simplify.is_pure``), the slice expansion treats a broadcast draw
as opaque and indexes it per direction, and ``IntrinsicArgHoisting``
finds no draw left inside an intrinsic argument.
"""

import copy
import itertools

from gelb.gelb_ast.ASTNodes import (
    Array1DLiteral_N,
    Array2DLiteral_N,
    ArrayDataType_N,
    BroadcastNode_N,
    DynamicBlock_N,
    GaugeBlock_N,
    Identifier_N,
    InitializerBlock_N,
    IntLiteral_N,
    IntrinsicFunctionCall_N,
    List_N,
    Node_N,
    Program_N,
    UserFunctionCall_N,
    VariableDeclarationStmt_N,
)

DRAW_PREFIX = '_gelb_draw_'
CALL_PREFIX = '_gelb_call_'


def sequence_draws(ast: Program_N) -> None:
    """In-place rewrite of every function body, initializer, dynamic
    and gauge block."""
    functions = {}
    if ast.functions is not None:
        functions = {func.name.name: func for func in ast.functions.elements}
    drawing = _drawing_functions(functions)
    counter = itertools.count(0)
    blocks = list(functions.values()) + list(_iter_blocks(ast))
    for block in blocks:
        if block.stmts is None:
            continue
        new_stmts = []
        for stmt in block.stmts.elements:
            new_stmts.extend(_sequence_statement(stmt, counter, functions, drawing))
            new_stmts.append(stmt)
        block.stmts.elements = new_stmts


def _iter_blocks(ast: Program_N):
    for blocks, kind in ((ast.initializers, InitializerBlock_N),
                         (ast.dynamics, DynamicBlock_N),
                         (ast.gauges, GaugeBlock_N)):
        if blocks is not None:
            for blk in blocks.elements:
                if isinstance(blk, kind):
                    yield blk


def _is_draw(node) -> bool:
    return isinstance(node, IntrinsicFunctionCall_N) and node.function_name == 'random'


def _drawing_functions(functions):
    """The names of the user functions whose body draws, directly or
    through a function it calls (a fixpoint over the call graph)."""
    calls = {name: _calls_in(func.stmts) for name, func in functions.items()}
    draws = {name for name, (direct, _) in calls.items() if direct}
    changed = True
    while changed:
        changed = False
        for name, (_, callees) in calls.items():
            if name not in draws and callees & draws:
                draws.add(name)
                changed = True
    return draws


def _calls_in(stmts):
    """(whether ``random()`` is called, the user functions called) in a
    statement list."""
    direct = False
    callees = set()
    stack = [stmts]
    while stack:
        node = stack.pop()
        if _is_draw(node):
            direct = True
        elif isinstance(node, UserFunctionCall_N):
            callees.add(node.function_name.name)
        if isinstance(node, List_N):
            stack.extend(node.elements)
        elif isinstance(node, Node_N):
            stack.extend(getattr(node, name, None) for name in node.get_children_names())
    return direct, callees


def _element_count(data_type):
    """The element count of a one-dimensional array type, else None."""
    if not isinstance(data_type, ArrayDataType_N):
        return None
    shape = data_type.shape
    if isinstance(shape, IntLiteral_N):
        return shape.value
    if isinstance(shape, List_N):
        if len(shape.elements) == 1 and isinstance(shape.elements[0], IntLiteral_N):
            return shape.elements[0].value
        return None
    return None


def _statement_lhs_count(stmt):
    """The element count of the statement's array-typed target, if any:
    a slice store, an array declaration or an array assignment."""
    lhs = getattr(stmt, 'lhs', None)
    if lhs is None and isinstance(stmt, VariableDeclarationStmt_N):
        return _element_count(stmt.data_type)
    if lhs is not None:
        return _element_count(getattr(lhs, 'inferred_type', None))
    return None


class _Walk:
    """One statement's rewrite: the temporaries declared so far, in
    draw order, and the counter shared by the whole program."""

    def __init__(self, stmt, counter, functions, drawing):
        self.stmt = stmt
        self.counter = counter
        self.functions = functions
        self.drawing = drawing
        self.decls = []


def _sequence_statement(stmt, counter, functions, drawing):
    """Replace the draws of ``stmt`` by temporaries; return the new
    declarations, in draw order."""
    walk = _Walk(stmt, counter, functions, drawing)
    outer = _statement_lhs_count(stmt)
    # The statement's own value expressions: everything but an index.
    for child_name in _value_children(stmt):
        child = getattr(stmt, child_name, None)
        if child is None:
            continue
        replacement = _walk(child, outer, walk, top=True)
        if replacement is not child:
            setattr(stmt, child_name, replacement)
    return walk.decls


def _value_children(stmt):
    """The attributes of a statement that hold value expressions."""
    if isinstance(stmt, VariableDeclarationStmt_N):
        return ('initial_value',)
    names = []
    for name in ('rhs', 'value'):
        if hasattr(stmt, name):
            names.append(name)
    return tuple(names)


def _walk(node, enclosing, walk, top=False):
    """Return ``node`` with its draws replaced, declaring the
    temporaries into ``walk.decls`` in left-to-right order.
    ``enclosing`` is the element count of the nearest enclosing
    array-typed expression, or None in a scalar context; ``top`` says
    the node is a statement's whole value expression."""
    if _is_draw(node):
        return _draw_temporary(node, enclosing, walk)
    if isinstance(node, List_N):
        for i, elem in enumerate(node.elements):
            node.elements[i] = _walk(elem, enclosing, walk)
        return node
    if not isinstance(node, Node_N):
        return node
    if isinstance(node, UserFunctionCall_N):
        # The arguments draw first, each in its own context (a scalar
        # parameter is a scalar context; an array argument carries its
        # own shape); then the body, if it draws, as one unit.
        node.arguments = _walk(node.arguments, None, walk)
        name = node.function_name.name
        if name in walk.drawing and not top:
            return _call_temporary(node, walk)
        return node
    if isinstance(node, BroadcastNode_N):
        # A scalar expression broadcast over an array: a draw inside it
        # is once per element, so it becomes an array temporary, and
        # the expression, now array-valued through that temporary,
        # replaces the broadcast (``arr = 0.5 * random()`` reads as
        # ``arr = 0.5 * _gelb_draw_k``).  A call temporary is a scalar
        # and keeps the broadcast.
        count = _element_count(node.target_array_type)
        before = len(walk.decls)
        rewritten = _walk(node.scalar_expr, count, walk)
        per_element = any(_element_count(d.data_type) is not None
                          for d in walk.decls[before:])
        if not per_element:
            node.scalar_expr = rewritten
            return node
        rewritten.inferred_type = node.target_array_type
        return rewritten
    if isinstance(node, (Array1DLiteral_N, Array2DLiteral_N)):
        # An element of a constructor is a scalar expression.
        node.value = _walk(node.value, None, walk)
        return node
    here = _element_count(getattr(node, 'inferred_type', None))
    inner = here if here is not None else enclosing
    for child_name in node.get_children_names():
        child = getattr(node, child_name, None)
        if child is None:
            continue
        setattr(node, child_name, _walk(child, inner, walk))
    return node


def _declare(walk, name, data_type, init):
    decl_name = Identifier_N(init.code_range, name)
    decl_name.inferred_type = data_type
    walk.decls.append(VariableDeclarationStmt_N(
        init.code_range, data_type, decl_name, initial_value=init))
    ref = Identifier_N(init.code_range, name)
    ref.inferred_type = data_type
    return ref


def _draw_temporary(call, count, walk):
    """A fresh temporary for one draw, scalar or ``count``-element."""
    cr = call.code_range
    name = f'{DRAW_PREFIX}{next(walk.counter)}'
    scalar = ArrayDataType_N(cr, 'real', List_N(cr))
    if count is None:
        data_type = scalar
        init = call
    else:
        data_type = ArrayDataType_N(cr, 'real', IntLiteral_N(cr, count))
        init = BroadcastNode_N(cr, call, data_type)
        init.inferred_type = data_type
    call.inferred_type = scalar
    return _declare(walk, name, data_type, init)


def _call_temporary(call, walk):
    """A fresh temporary of the function's output type for one call
    whose body draws."""
    func = walk.functions[call.function_name.name]
    output = func.outputs.elements[0]
    data_type = copy.deepcopy(output.data_type)
    name = f'{CALL_PREFIX}{next(walk.counter)}'
    if getattr(call, 'inferred_type', None) is None:
        call.inferred_type = data_type
    return _declare(walk, name, data_type, call)
