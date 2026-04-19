"""Structural equality test for GeLB AST nodes.

Used by ``CollinearityRewriteVisitor`` to verify that two sub-expressions
are syntactically identical before rewriting a BGK collinearity pattern
``f_in - omega * (f_in - feq)`` into ``(1 - omega) * f_in + omega * feq``.

The check ignores ``code_range`` (the sub-trees may originate from
different source positions yet be structurally identical) and ignores
type-promotion wrapping (since constant-folding may have wrapped one
position but not the other).  Two nodes are equal iff:

  * they have the same Python type, AND
  * for atomic types (literals, identifiers): their value/name matches,
  * for composite types: every named child is recursively equal.

The traversal uses ``Node_N.get_children_names()`` to enumerate the
children, so it works uniformly for any AST node defined in
``gelb/gelb_ast/ASTNodes.py`` without per-class knowledge.
"""

from gelb.gelb_ast.ASTNodes import (
    Node_N,
    Identifier_N,
    IntLiteral_N,
    RealLiteral_N,
    BoolLiteral_N,
    List_N,
)


def _unwrap(node):
    """Strip type-promotion / broadcast wrappers if present.  Mirrors
    ``ConstantFoldingVisitor._unwrap_promotion`` but local to this
    module so the helper has no upstream dependency."""
    # Lazy import to avoid circular dependencies; the wrapper classes
    # are defined in the type-promotion pass output.
    try:
        from gelb.gelb_ast.ASTNodes import TypePromotionNode_N
        while isinstance(node, TypePromotionNode_N):
            node = node.value
    except (ImportError, AttributeError):
        pass
    try:
        from gelb.gelb_ast.ASTNodes import BroadcastNode_N
        while isinstance(node, BroadcastNode_N):
            node = node.scalar
    except (ImportError, AttributeError):
        pass
    return node


def ast_structurally_equal(a, b) -> bool:
    """Return True iff two AST sub-trees are structurally identical.

    Ignores ``code_range``, type-promotion wrappers, and broadcast
    wrappers; otherwise compares type -> name/value -> children
    recursively."""
    a = _unwrap(a)
    b = _unwrap(b)
    if type(a) is not type(b):
        return False
    # Atomic leaves with a meaningful value field.
    if isinstance(a, Identifier_N):
        return a.name == b.name
    if isinstance(a, (IntLiteral_N, RealLiteral_N, BoolLiteral_N)):
        return a.value == b.value
    # List_N: compare element lists.
    if isinstance(a, List_N):
        if len(a.elements) != len(b.elements):
            return False
        return all(ast_structurally_equal(x, y)
                   for x, y in zip(a.elements, b.elements))
    # Composite Node_N: compare every named child.
    if isinstance(a, Node_N):
        names_a = a.get_children_names()
        names_b = b.get_children_names()
        if names_a != names_b:
            return False
        for nm in names_a:
            ca = getattr(a, nm)
            cb = getattr(b, nm)
            if ca is None and cb is None:
                continue
            if ca is None or cb is None:
                return False
            if not ast_structurally_equal(ca, cb):
                return False
        return True
    # Plain Python values (e.g., bare strings, ints in element_ranges).
    return a == b
