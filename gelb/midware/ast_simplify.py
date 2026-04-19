"""Exact simplification and structural CSE on ordered expression trees.

``SliceDFExpansionVisitor`` and ``ScalarBlockCSEVisitor`` used to lower
expressions into SymPy, whose ``Add``/``Mul`` canonicalisation flattens,
sorts and combines terms: ``(u + 16777217) - 16777216`` became
``u + 1``, ``(u + a) - a`` became ``u``, and every sum was re-associated
into canonical order.  None of that is within the accuracy the manual
promises (user manual, Numerical semantics: What the optimizer
promises).  This module does only what cannot change a result, signed
zeros, infinities and NaNs included (a NaN's sign and payload, which
IEEE 754 leaves unspecified, aside):

* the identities that hold bit for bit: ``1*x``, ``-1*x``, ``x/1``,
  ``-(-x)``; the zero identities only where the sign of a zero cannot
  change, that is ``x + (-0)``, ``(-0) + x``, ``x - (+0)`` and
  ``(-0) - x -> -x`` in real arithmetic, and all of ``0*x``, ``x+0``,
  ``x-0``, ``0-x`` in integer arithmetic (``u*0.0`` is -0 for u = -1,
  ``u + 0.0`` is +0 for u = -0, ``0.0 - u`` is +0 for u = +0); and the
  sign moves that IEEE defines or that are symmetric under sign,
  ``a + (-b) -> a - b``, ``(-a) + b -> b - a``, ``a - (-b) -> a + b``,
  ``(-a) * b -> -(a * b)``, ``(-a) / b -> -(a / b)``, both negated.
  ``(-a) + (-b) -> -(a + b)`` is not among them: an exact cancellation
  gives +0 on the left and -0 on the right.  Powers are left to the
  backend, which evaluates them its own way (the Fortran backend calls
  ``pow``, whose result need not equal the repeated product);
* folding of literal-only subtrees of ``+ - * /`` and negation in the
  width of the expression: correctly rounded, as the native arithmetic;
* sharing of identical *ordered* subtrees across the expressions of one
  statement group (structural CSE): a shared value is computed once, in
  the same order, and read back.  A subtree containing a stateful call
  (``random()``, arguments of other calls included) is never shared, and
  no rule drops one: two calls are two draws.

Evaluation order is the source order throughout.

Promotions that change the numeric kind of their operand are part of a
subtree's identity, so a real32 product is never shared with a real one;
a literal's identity includes the sign of a zero.
"""

import math

from gelb.gelb_ast.ASTNodes import (
    Add_N,
    ArrayDataType_N,
    BroadcastNode_N,
    Div_N,
    Identifier_N,
    IntLiteral_N,
    IntrinsicFunctionCall_N,
    List_N,
    Mul_N,
    Node_N,
    Pow_N,
    RealLiteral_N,
    Sub_N,
    TypePromotionNode_N,
    UnaryMinusExpr_N,
)
from gelb.frontend.intrinsic_functions import STATEFUL_INTRINSIC_NAMES
from gelb.midware.ast_eval import convert_plain, eval_const_expr


# --- numeric kinds ----------------------------------------------------

_NUMERIC_KIND = {'real': 'real64', 'real64': 'real64',
                 'real32': 'real32', 'real16': 'real16',
                 'int': 'int64', 'int64': 'int64', 'int32': 'int32',
                 'int16': 'int16', 'int8': 'int8'}
_REAL_WIDTH = {name: kind for name, kind in _NUMERIC_KIND.items()
               if kind.startswith('real')}

_ALGEBRAIC = (Add_N, Sub_N, Mul_N, Div_N, Pow_N, UnaryMinusExpr_N)


def numeric_kind(type_node):
    """The numeric kind ('real64', 'real32', 'real16', 'int64', 'int32',
    'int16', 'int8') of a type node, or None for a non-numeric or
    unknown type."""
    return _NUMERIC_KIND.get(getattr(type_node, 'element_dtype', None))


def real_width(type_node):
    """The real width class ('real64', 'real32', 'real16') of a type
    node, or None for a non-real or unknown type."""
    return _REAL_WIDTH.get(getattr(type_node, 'element_dtype', None))


def is_algebraic(node):
    return isinstance(node, _ALGEBRAIC)


def is_pure(node):
    """No call to a stateful intrinsic (``random()``) anywhere in
    ``node``, the arguments of other calls included: evaluating it once
    or twice gives the same value and leaves no trace."""
    stack = [node]
    while stack:
        n = stack.pop()
        if n is None:
            continue
        if isinstance(n, IntrinsicFunctionCall_N) \
                and n.function_name in STATEFUL_INTRINSIC_NAMES:
            return False
        if isinstance(n, (list, tuple)):
            stack.extend(n)
        elif isinstance(n, List_N):
            stack.extend(n.elements)
        elif isinstance(n, Node_N):
            stack.extend(getattr(n, name) for name in n.get_children_names())
    return True


def _promoted_operand(node):
    inner = node.expr
    while isinstance(inner, BroadcastNode_N):
        inner = inner.scalar_expr
    return inner


def kind_changing(node):
    """A promotion whose target kind differs from its operand's (both
    known): a conversion, not a no-op wrapper."""
    target = numeric_kind(node.target_type)
    source = numeric_kind(getattr(_promoted_operand(node), 'inferred_type', None))
    return target is not None and source is not None and target != source


# --- structural identity ------------------------------------------------

def structural_key(node):
    """A hashable key identifying an expression tree's shape, ignoring
    ``code_range``.  Wrappers are transparent, except a promotion that
    changes its operand's numeric kind, whose target kind is part of
    the key: the same product in real32 and in real are different
    values."""
    while isinstance(node, TypePromotionNode_N):
        if kind_changing(node):
            return ('Promote', numeric_kind(node.target_type),
                    structural_key(node.expr))
        node = node.expr
    while isinstance(node, BroadcastNode_N):
        node = node.scalar_expr
    if node is None:
        return ('None',)
    if isinstance(node, Identifier_N):
        return ('Identifier_N', node.name)
    if isinstance(node, RealLiteral_N):
        # The hexadecimal spelling tells -0.0 from 0.0, which compare equal.
        return ('RealLiteral_N', float(node.value).hex())
    if isinstance(node, IntLiteral_N):
        return ('IntLiteral_N', node.value)
    if isinstance(node, List_N):
        return ('List_N', tuple(structural_key(e) for e in node.elements))
    if isinstance(node, Node_N):
        return (type(node).__name__,
                tuple((nm, structural_key(getattr(node, nm)))
                      for nm in node.get_children_names()))
    return ('raw', type(node).__name__, repr(node))


# --- exact simplification ----------------------------------------------

def _unwrapped(node):
    while isinstance(node, (TypePromotionNode_N, BroadcastNode_N)):
        node = node.expr if isinstance(node, TypePromotionNode_N) \
            else node.scalar_expr
    return node


def _literal_value(node):
    """The payload of a numeric literal, seen through its wrappers
    (a promotion does not change 0, 1 or -1); None otherwise."""
    inner = _unwrapped(node)
    if isinstance(inner, (IntLiteral_N, RealLiteral_N)) \
            and not isinstance(inner.value, bool):
        return inner.value
    return None


def _is_value(node, value):
    v = _literal_value(node)
    return v is not None and v == value


def _is_signed_zero(node, negative):
    """A zero literal of the given sign: -0 when ``negative``, +0
    otherwise.  An integer zero converts to +0."""
    v = _literal_value(node)
    return (v is not None and v == 0
            and (math.copysign(1.0, float(v)) < 0) == negative)


def _integer_arithmetic(node):
    """The operation is evaluated in an integer kind, where a zero has
    no sign.  An untyped (hand-built) tree counts as real."""
    kind = numeric_kind(getattr(node, 'inferred_type', None))
    return kind is not None and kind.startswith('int')


def _is_literal_tree(node):
    """A numeric literal, or a tree of ``+ - * /`` and negation over
    numeric literals (powers are not folded: see the module notes)."""
    inner = _unwrapped(node)
    if isinstance(inner, (IntLiteral_N, RealLiteral_N)):
        return not isinstance(inner.value, bool)
    if isinstance(inner, UnaryMinusExpr_N):
        return _is_literal_tree(inner.value)
    if isinstance(inner, Pow_N):
        return False
    if isinstance(inner, _ALGEBRAIC):
        return _is_literal_tree(inner.left) and _is_literal_tree(inner.right)
    return False


def _scalar_type_like(type_node):
    """The scalar type with ``type_node``'s element type (a per-direction
    expression may still carry the array type of the statement)."""
    return ArrayDataType_N(type_node.code_range, type_node.element_dtype,
                           List_N(type_node.code_range))


def _typed_literal(ref, value):
    """A scalar literal holding ``value`` in ``ref``'s numeric kind and
    width.  Without a known kind (hand-built trees), the literal takes
    the value's own kind and no type."""
    kind = numeric_kind(getattr(ref, 'inferred_type', None))
    if kind is None:
        if isinstance(value, bool) or (not isinstance(value, (int, float))):
            return None
        return (IntLiteral_N if isinstance(value, int) else RealLiteral_N)(
            ref.code_range, value)
    dtype = ref.inferred_type.element_dtype
    if kind.startswith('real'):
        lit = RealLiteral_N(ref.code_range, float(convert_plain(value, dtype)))
    else:
        lit = IntLiteral_N(ref.code_range, int(convert_plain(value, dtype)))
    lit.inferred_type = _scalar_type_like(ref.inferred_type)
    return lit


def _fold(node):
    """``node``, a literal-only algebraic tree, as one literal of its
    value in its own width; ``node`` itself when it cannot be folded."""
    try:
        value = eval_const_expr(node)
    except Exception:          # a value error, division by zero, ...: keep the tree
        return node
    if isinstance(value, (bool, list)):
        return node
    folded = _typed_literal(node, value)
    return node if folded is None else folded


def _negated(node, ref):
    neg = UnaryMinusExpr_N(ref.code_range, node)
    if getattr(ref, 'inferred_type', None) is not None:
        neg.inferred_type = ref.inferred_type
    return neg


def simplify_exact(node):
    """An equivalent tree with the exact identities applied and
    literal-only subtrees folded, in place where possible.  Only
    algebraic nodes, and the wrappers around them, are entered; an
    intrinsic call, a lattice read or an array selection is left as it
    is, arguments included.  A power keeps its form; its operands are
    simplified."""
    if isinstance(node, TypePromotionNode_N):
        node.expr = simplify_exact(node.expr)
        return node
    if isinstance(node, BroadcastNode_N):
        node.scalar_expr = simplify_exact(node.scalar_expr)
        return node
    if not is_algebraic(node):
        return node

    if isinstance(node, UnaryMinusExpr_N):
        node.value = simplify_exact(node.value)
        if isinstance(node.value, UnaryMinusExpr_N):
            return node.value.value
        if _is_literal_tree(node):
            return _fold(node)
        return node

    node.left = simplify_exact(node.left)
    node.right = simplify_exact(node.right)
    a, b = node.left, node.right

    if isinstance(node, Pow_N):
        return node
    if _is_literal_tree(node):
        return _fold(node)

    integer = _integer_arithmetic(node)
    neg_a = isinstance(a, UnaryMinusExpr_N)
    neg_b = isinstance(b, UnaryMinusExpr_N)
    if isinstance(node, Mul_N):
        # A real product with zero is a zero of the other operand's
        # sign (or NaN): only an integer one is the literal zero, and
        # only when the dropped operand makes no call to random().
        if integer and ((_is_value(a, 0) and is_pure(b))
                        or (_is_value(b, 0) and is_pure(a))):
            return _typed_literal(node, 0)
        if _is_value(a, 1):
            return b
        if _is_value(b, 1):
            return a
        if _is_value(a, -1):
            return _negated(b, node)
        if _is_value(b, -1):
            return _negated(a, node)
        if neg_a and neg_b:                        # (-a) * (-b) -> a * b
            node.left, node.right = a.value, b.value
            return node
        if neg_a or neg_b:                         # (-a) * b -> -(a * b)
            node.left, node.right = (a.value if neg_a else a), (b.value if neg_b else b)
            return _negated(node, node)
    elif isinstance(node, Add_N):
        # (-0) + x is x for every x; (+0) + (-0) is +0.
        if _is_value(a, 0) and (integer or _is_signed_zero(a, True)):
            return b
        if _is_value(b, 0) and (integer or _is_signed_zero(b, True)):
            return a
        if neg_b:                                  # a + (-b) -> a - b
            diff = Sub_N(node.code_range, a, b.value)
            diff.inferred_type = getattr(node, 'inferred_type', None)
            return diff
        if neg_a:                                  # (-a) + b -> b - a
            diff = Sub_N(node.code_range, b, a.value)
            diff.inferred_type = getattr(node, 'inferred_type', None)
            return diff
    elif isinstance(node, Sub_N):
        # x - (+0) is x + (-0), which is x; (-0) - x is (-0) + (-x).
        if _is_value(b, 0) and (integer or _is_signed_zero(b, False)):
            return a
        if _is_value(a, 0) and (integer or _is_signed_zero(a, True)):
            return _negated(b, node)
        if neg_b:                                  # a - (-b) -> a + b
            total = Add_N(node.code_range, a, b.value)
            total.inferred_type = getattr(node, 'inferred_type', None)
            return total
    elif isinstance(node, Div_N):
        if _is_value(b, 1):
            return a
        if neg_a and neg_b:                        # (-a) / (-b) -> a / b
            node.left, node.right = a.value, b.value
            return node
        if neg_a or neg_b:                         # (-a) / b -> -(a / b)
            node.left, node.right = (a.value if neg_a else a), (b.value if neg_b else b)
            return _negated(node, node)
    return node


# --- structural CSE ------------------------------------------------------

def _is_leaf(node):
    inner = _unwrapped(node)
    return not is_algebraic(inner)


def _trivial(node):
    """Too cheap to hoist: a bare negation of a leaf."""
    return isinstance(node, UnaryMinusExpr_N) and _is_leaf(node.value)


def _children_slots(node):
    """The attribute names through which the CSE walks: algebraic
    operands and the wrappers around them.  Anything else (an intrinsic
    call, a lattice read, an array selection) is a leaf."""
    if isinstance(node, TypePromotionNode_N):
        return ('expr',)
    if isinstance(node, BroadcastNode_N):
        return ('scalar_expr',)
    if isinstance(node, UnaryMinusExpr_N):
        return ('value',)
    if is_algebraic(node):
        return ('left', 'right')
    return ()


def hoist_common_subtrees(exprs, name_for):
    """Share the identical ordered algebraic subtrees of ``exprs``.

    Returns ``(temps, rewritten)``: ``temps`` is a list of
    ``(name, body)`` in the order the temporaries must be declared (a
    body may reference an earlier one), ``rewritten`` the expressions
    with each shared subtree replaced by an identifier of the
    temporary's name, typed like the subtree.  ``name_for(i)`` names
    the ``i``-th temporary.  A subtree is shared when it is an
    algebraic node, other than a bare negation and other than one
    containing a stateful call, that occurs at least twice; shared
    subtrees inside a shared subtree are hoisted first,
    as ``sympy.cse`` ordered its output.  ``([], exprs)`` when nothing
    is shared.  The trees are rewritten in place."""
    counts = {}

    def count(node):
        """Count the shareable subtrees of ``node``; return whether it
        is pure (a leaf, such as a call, is inspected whole)."""
        slots = _children_slots(node)
        pure = True if slots else is_pure(node)
        for slot in slots:
            pure = count(getattr(node, slot)) and pure
        if pure and is_algebraic(node) and not _trivial(node):
            key = structural_key(node)
            counts[key] = counts.get(key, 0) + 1
        return pure

    for expr in exprs:
        count(expr)
    shared = {key for key, n in counts.items() if n >= 2}
    if not shared:
        return [], list(exprs)

    temps, made = [], {}

    def rewrite(node):
        key = structural_key(node) if is_algebraic(node) else None
        for slot in _children_slots(node):
            setattr(node, slot, rewrite(getattr(node, slot)))
        if key is None or key not in shared:
            return node
        name = made.get(key)
        if name is None:
            name = name_for(len(temps))
            made[key] = name
            temps.append((name, node))
        ident = Identifier_N(node.code_range, name)
        if getattr(node, 'inferred_type', None) is not None:
            ident.inferred_type = scalar_type_of(node, None)
        return ident

    rewritten = [rewrite(expr) for expr in exprs]
    return temps, rewritten


def scalar_type_of(node, fallback):
    """The scalar type a temporary holding ``node`` is declared with:
    the node's own inferred type, scalarised (a per-direction subtree
    may still carry the statement's array type; its element type is
    the width of its value), else ``fallback`` for an untyped tree."""
    t = getattr(node, 'inferred_type', None)
    if isinstance(t, ArrayDataType_N):
        shape = t.shape
        if shape is None or (isinstance(shape, List_N) and not shape.elements):
            return t
        return _scalar_type_like(t)
    return fallback
