"""BGK collinearity rewrite midware pass.

Rewrites ``X - C * (X - Y)`` (the source-form BGK collision step) into
``(1 - C) * X + C * Y``, saving one ``vsubpd`` per direction at codegen
time.  A symbolic-algebra pass would find the same simplification;
here it is a small targeted pattern match on the AST, so SymPy stays
out of the dyn-block path.

Pattern matched (after constant folding and function inlining):

    Sub_N(X, Mul_N(C, Sub_N(X', Y)))
            |  rewrite when ast_structurally_equal(X, X') and C
            v  is a literal-or-identifier scalar
    Add_N(Mul_N((1 - C), X), Mul_N(C, Y))

If ``C`` is a numeric literal (``RealLiteral_N`` / ``IntLiteral_N``),
``(1 - C)`` is precomputed as a single literal -- trims one extra
operation gcc would otherwise leave alive at -O3 due to IEEE-754 strict
semantics.

Bit-equivalence: NOT bit-equal -- this is FP reassociation.  The error
is bounded <= 2 ULP per direction, well within the project-wide <= 2.6
ULP budget already documented for the slice-DF unroll.  Users
requesting bit-exact reproducibility can disable this pass via the
``--no-collinearity-rewrite`` flag on ``gelbc``.

Pipeline position: between ``inline_functions`` and
``extract_stencils`` in ``gelb/gelbc.py``.
"""

import copy

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.frontend.visitor_mixins import ProgramTraversalMixin
from gelb.gelb_ast.ASTNodes import (
    Add_N,
    ArrayDataType_N,
    BroadcastNode_N,
    Identifier_N,
    IntLiteral_N,
    List_N,
    Mul_N,
    Program_N,
    RealLiteral_N,
    Sub_N,
    TypePromotionNode_N,
)
from gelb.midware.ast_simplify import is_pure
from gelb.midware.ast_structural_eq import ast_structurally_equal


class CollinearityRewriteVisitor(ASTBaseVisitor, ProgramTraversalMixin):
    """Visitor that rewrites BGK collinearity patterns.

    Walks every block via ``ProgramTraversalMixin``.  Bottom-up: the
    children are visited first, so nested rewrites apply.  Returns the
    rewritten node from each visit method, leaving the parent's
    ``__setattr__`` to splice the result back.
    """

    def __init__(self):
        super().__init__()
        self.rewrites_applied = 0

    # Dispatcher --------------------------------------------------------

    def visit(self, node, ast_root_node):
        """Override the strict ASTBaseVisitor dispatcher with a
        generic-fallback that recurses into children for any node
        type without an explicit ``visit<Type>_N`` method.

        ``ASTBaseVisitor.visit`` requires a visitor method for every
        node type seen, which suits the type-checking and
        constant-folding passes that touch every node intentionally.
        For this pass we only care about ``Sub_N``; everything else
        should be traversed transparently."""
        if node is None:
            return None
        method_name = f"visit{type(node).__name__}"
        method = getattr(self, method_name, None)
        if method is not None:
            return method(node, ast_root_node)
        # Generic recurse: walk every named child and replace it with
        # the result of visiting it.  Mirrors the pattern in
        # ``Node_N.replace_symbol_references``.
        from gelb.gelb_ast.ASTNodes import Node_N, List_N
        if isinstance(node, List_N):
            new_elements = []
            for elem in node.elements:
                new_elements.append(self.visit(elem, ast_root_node))
            node.elements = new_elements
            return node
        if isinstance(node, Node_N):
            for child_name in node.get_children_names():
                child = getattr(node, child_name)
                if child is None:
                    continue
                if isinstance(child, (Node_N, List_N)):
                    setattr(node, child_name,
                            self.visit(child, ast_root_node))
            return node
        return node

    # Program traversal -------------------------------------------------

    def visitProgram_N(self, node, ast_root_node):
        self.traverse_program_blocks(node, ast_root_node)
        return node

    # Block-level entry points (so ProgramTraversalMixin enters them).
    # We don't need block-specific logic; just recurse via generic visit.
    def visitInitializerBlock_N(self, node, ast_root_node):
        return self._recurse_into(node, ast_root_node)

    def visitDynamicBlock_N(self, node, ast_root_node):
        return self._recurse_into(node, ast_root_node)

    def visitGaugeBlock_N(self, node, ast_root_node):
        return self._recurse_into(node, ast_root_node)

    def _recurse_into(self, node, ast_root_node):
        """Recurse through a block's children explicitly (the generic
        fallback in ``visit`` would loop on the block itself if called
        from ``ProgramTraversalMixin.traverse_program_blocks``)."""
        from gelb.gelb_ast.ASTNodes import Node_N, List_N
        for child_name in node.get_children_names():
            child = getattr(node, child_name)
            if child is None:
                continue
            if isinstance(child, (Node_N, List_N)):
                setattr(node, child_name, self.visit(child, ast_root_node))
        return node

    # Pattern detection -------------------------------------------------

    def visitSub_N(self, node: Sub_N, ast_root_node: Program_N):
        # Bottom-up: rewrite children first so we don't miss nested
        # patterns (e.g., a forcing-term BGK in the same dyn block).
        node.left = self.visit(node.left, ast_root_node)
        node.right = self.visit(node.right, ast_root_node)
        rewritten = self._try_rewrite_collinearity(node)
        return rewritten if rewritten is not None else node

    # Rewrite logic -----------------------------------------------------

    def _try_rewrite_collinearity(self, node: Sub_N):
        """Try to match ``X - C * (X - Y)``; return rewritten node or
        None if the pattern does not fire."""
        outer_left = node.left
        outer_right = self._unwrap_promotion(node.right)
        if not isinstance(outer_right, Mul_N):
            return None
        # Determine which side of the Mul_N is the coefficient C and
        # which is the inner Sub_N.  Allow either order: ``C * (X-Y)``
        # or ``(X-Y) * C``.
        c_node, inner = self._classify_mul_for_collinearity(outer_right)
        if c_node is None or inner is None:
            return None
        if not isinstance(inner, Sub_N):
            return None
        x_again = self._unwrap_promotion(inner.left)
        y_node = inner.right
        if not ast_structurally_equal(outer_left, x_again):
            return None
        # The rewrite evaluates X once where the source evaluates it
        # twice: two random() calls are two draws, and a subtree that
        # draws is never shared or dropped.
        if not is_pure(outer_left):
            return None
        # Pattern matches.  Build the rewrite.
        rewritten = self._build_rewrite(node, outer_left, c_node, y_node)
        if rewritten is not None:
            self.rewrites_applied += 1
        return rewritten

    @staticmethod
    def _classify_mul_for_collinearity(mul_node: Mul_N):
        """Return (C, inner_Sub) for the form ``C * (X - Y)`` or
        ``(X - Y) * C``; return (None, None) if neither side is a
        valid coefficient."""
        candidates = (
            (mul_node.left, mul_node.right),
            (mul_node.right, mul_node.left),
        )
        for cand_c, cand_inner in candidates:
            unwrapped_c = CollinearityRewriteVisitor._unwrap_promotion(
                cand_c)
            if isinstance(unwrapped_c,
                          (RealLiteral_N, IntLiteral_N, Identifier_N)):
                return unwrapped_c, cand_inner
        return None, None

    @staticmethod
    def _unwrap_promotion(node):
        """Strip type-promotion / broadcast wrappers."""
        while isinstance(node, TypePromotionNode_N):
            node = node.expr
        while isinstance(node, BroadcastNode_N):
            node = node.scalar_expr
        return node

    def _build_rewrite(self, original_sub, x_node, c_node, y_node):
        """Return ``Add_N(Mul_N((1-C), X), Mul_N(C, Y))``."""
        cr = original_sub.code_range
        # (1 - C): precompute when C is a numeric literal.
        if isinstance(c_node, RealLiteral_N):
            one_minus_c = self._make_real_literal(
                1.0 - float(c_node.value), cr, original_sub)
        elif isinstance(c_node, IntLiteral_N):
            # Integer C in BGK collision is unusual but possible --
            # promote to real to keep the result real-typed.
            one_minus_c = self._make_real_literal(
                1.0 - float(c_node.value), cr, original_sub)
        else:
            # Identifier_N: emit Sub_N(1.0, C); subsequent passes
            # (or the C++ compiler) will fold further if C is
            # actually loop-invariant.
            one_lit = self._make_real_literal(1.0, cr, original_sub)
            one_minus_c = Sub_N(cr, one_lit, copy.deepcopy(c_node))
            self._copy_inferred_type(one_minus_c, original_sub)
        # (1 - C) * X
        left_term = Mul_N(cr, one_minus_c, copy.deepcopy(x_node))
        self._copy_inferred_type(left_term, original_sub)
        # C * Y
        right_term = Mul_N(cr, copy.deepcopy(c_node), y_node)
        self._copy_inferred_type(right_term, original_sub)
        # Sum
        result = Add_N(cr, left_term, right_term)
        self._copy_inferred_type(result, original_sub)
        return result

    # Helpers -----------------------------------------------------------

    @staticmethod
    def _copy_inferred_type(target, source):
        if hasattr(source, 'inferred_type'):
            target.inferred_type = source.inferred_type

    def _make_real_literal(self, value, code_range, ref_node):
        """Construct a ``RealLiteral_N`` carrying the appropriate
        ``inferred_type`` (mirrors the helper of the same name in
        ``ConstantFoldingVisitor`` so both passes synthesize literals
        consistently)."""
        lit = RealLiteral_N(code_range, float(value))
        if ref_node is not None and hasattr(ref_node, 'inferred_type'):
            lit.inferred_type = ref_node.inferred_type
        else:
            empty_shape = List_N(code_range)
            lit.inferred_type = ArrayDataType_N(
                code_range, 'real64', empty_shape)
        return lit


def collinearity_rewrite(ast):
    """Run the collinearity-rewrite pass over ``ast`` (a
    ``Program_N``).  Returns the (mutated) AST.  Counts of applied
    rewrites are stashed on the AST as ``ast.collinearity_rewrites``
    for downstream introspection / logging."""
    visitor = CollinearityRewriteVisitor()
    visitor.visit(ast, ast)
    setattr(ast, 'collinearity_rewrites', visitor.rewrites_applied)
    return ast
