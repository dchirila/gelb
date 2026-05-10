#!/usr/bin/env python3
"""Unit tests for the CollinearityRewriteVisitor pass.

The pass rewrites the BGK collinearity pattern
``X - C * (X - Y)`` into ``(1 - C) * X + C * Y``.

Tests use direct AST construction (no full pipeline) to verify the
visitor's pattern matching, structural-equality check, and rewrite
output.
"""

import pytest
from gelb.gelb_ast.ASTNodes import (
    Add_N, Sub_N, Mul_N,
    Identifier_N, RealLiteral_N, IntLiteral_N,
)
from gelb.midware.CollinearityRewriteVisitor import (
    CollinearityRewriteVisitor,
)
from gelb.midware.ast_structural_eq import ast_structurally_equal
from gelb.utils.CodeRange import CodeRange


_CR = CodeRange(1, 1, 1, 1)


def _ident(name):
    return Identifier_N(_CR, name)


def _real(value):
    return RealLiteral_N(_CR, value)


# --- Structural-equality helper --------------------------------------


class TestStructuralEquality:
    def test_identifier_same_name(self):
        assert ast_structurally_equal(_ident("fIn"), _ident("fIn"))

    def test_identifier_different_name(self):
        assert not ast_structurally_equal(_ident("fIn"), _ident("feq"))

    def test_real_literal_same_value(self):
        assert ast_structurally_equal(_real(1.4514), _real(1.4514))

    def test_real_literal_different_value(self):
        assert not ast_structurally_equal(_real(1.0), _real(2.0))

    def test_different_node_types(self):
        # Identifier_N vs RealLiteral_N -> not equal even if string repr similar.
        assert not ast_structurally_equal(_ident("a"), _real(1.0))

    def test_nested_expression_equal(self):
        a = Add_N(_CR, _ident("x"), _real(2.0))
        b = Add_N(_CR, _ident("x"), _real(2.0))
        assert ast_structurally_equal(a, b)

    def test_nested_expression_unequal(self):
        a = Add_N(_CR, _ident("x"), _real(2.0))
        b = Add_N(_CR, _ident("x"), _real(3.0))
        assert not ast_structurally_equal(a, b)


# --- BGK rewrite -----------------------------------------------------


class TestCollinearityRewrite:
    def _bgk_pattern(self, x_node, c_node, y_node):
        """Build ``X - C * (X - Y)``."""
        inner = Sub_N(_CR, x_node, y_node)   # X - Y
        scaled = Mul_N(_CR, c_node, inner)   # C * (X - Y)
        outer = Sub_N(_CR, x_node, scaled)   # X - C * (X - Y)
        return outer

    def test_canonical_bgk_with_real_coeff(self):
        """``fIn - 1.5 * (fIn - feq)`` -> ``-0.5 * fIn + 1.5 * feq``."""
        outer = self._bgk_pattern(_ident("fIn"), _real(1.5),
                                   _ident("feq"))
        visitor = CollinearityRewriteVisitor()
        result = visitor.visit(outer, None)
        assert visitor.rewrites_applied == 1
        # Result should be Add_N(Mul_N(-0.5, fIn), Mul_N(1.5, feq)).
        assert isinstance(result, Add_N)
        left, right = result.left, result.right
        assert isinstance(left, Mul_N) and isinstance(right, Mul_N)
        # Left: -0.5 * fIn
        assert isinstance(left.left, RealLiteral_N)
        assert left.left.value == pytest.approx(-0.5)
        assert isinstance(left.right, Identifier_N)
        assert left.right.name == "fIn"
        # Right: 1.5 * feq
        assert isinstance(right.left, RealLiteral_N)
        assert right.left.value == pytest.approx(1.5)
        assert isinstance(right.right, Identifier_N)
        assert right.right.name == "feq"

    def test_a_random_draw_is_not_merged(self):
        """``random() - 0.5 * (random() - y)`` evaluates random() twice;
        the rewrite would evaluate it once; a subtree containing a draw
        is never merged."""
        from gelb.gelb_ast.ASTNodes import IntrinsicFunctionCall_N, List_N
        draw = lambda: IntrinsicFunctionCall_N(_CR, "random", List_N(_CR))
        outer = self._bgk_pattern(draw(), _real(0.5), _ident("y"))
        inner_draw = outer.right.right.left
        outer.right.right.left = draw()        # two distinct call nodes
        assert inner_draw is not outer.right.right.left
        visitor = CollinearityRewriteVisitor()
        result = visitor.visit(outer, None)
        assert visitor.rewrites_applied == 0
        assert result is outer

    def test_int_literal_coeff_is_promoted_to_real(self):
        """``X - 1 * (X - Y)`` (integer C) -> real-typed rewrite."""
        outer = self._bgk_pattern(_ident("a"), IntLiteral_N(_CR, 1),
                                   _ident("b"))
        visitor = CollinearityRewriteVisitor()
        result = visitor.visit(outer, None)
        assert visitor.rewrites_applied == 1
        # (1 - 1) = 0.0 -> left term collapses to (0.0 * a).
        # The pass itself doesn't fold 0*a; that's the next pass.
        assert isinstance(result, Add_N)
        assert isinstance(result.left.left, RealLiteral_N)
        assert result.left.left.value == pytest.approx(0.0)

    def test_identifier_coeff_emits_subtract(self):
        """``X - omega * (X - Y)`` with omega as Identifier -> emits
        ``Sub_N(1.0, omega) * X + omega * Y`` (no precompute)."""
        outer = self._bgk_pattern(_ident("X"), _ident("omega"),
                                   _ident("Y"))
        visitor = CollinearityRewriteVisitor()
        result = visitor.visit(outer, None)
        assert visitor.rewrites_applied == 1
        assert isinstance(result, Add_N)
        # Left: Sub_N(1.0, omega) * X
        assert isinstance(result.left.left, Sub_N)
        assert isinstance(result.left.left.left, RealLiteral_N)
        assert result.left.left.left.value == pytest.approx(1.0)
        assert isinstance(result.left.left.right, Identifier_N)
        assert result.left.left.right.name == "omega"

    def test_mul_with_coeff_on_right_side(self):
        """Pattern with ``(X - Y) * C`` instead of ``C * (X - Y)``
        also matches."""
        x = _ident("fIn")
        c = _real(0.6)
        y = _ident("feq")
        inner = Sub_N(_CR, x, y)
        scaled = Mul_N(_CR, inner, c)        # (X - Y) * C, not C * (X - Y)
        outer = Sub_N(_CR, x, scaled)
        visitor = CollinearityRewriteVisitor()
        result = visitor.visit(outer, None)
        assert visitor.rewrites_applied == 1
        assert isinstance(result, Add_N)

    def test_x_unequal_does_not_rewrite(self):
        """``X1 - C * (X2 - Y)`` with X1 != X2 must NOT rewrite."""
        outer = self._bgk_pattern(_ident("X1"), _real(0.5),
                                   _ident("Y"))
        # Tamper: replace the second X with a different identifier.
        outer.right.right.left = _ident("X2")
        visitor = CollinearityRewriteVisitor()
        result = visitor.visit(outer, None)
        assert visitor.rewrites_applied == 0
        assert result is outer  # untouched

    def test_inverse_pattern_does_not_rewrite(self):
        """``X + C * (X - Y)`` (Add_N at outer, not Sub_N) must NOT
        rewrite -- the pattern only matches subtraction at the top."""
        x = _ident("X")
        c = _real(0.5)
        y = _ident("Y")
        inner = Sub_N(_CR, x, y)
        scaled = Mul_N(_CR, c, inner)
        outer = Add_N(_CR, x, scaled)        # Add_N, not Sub_N
        visitor = CollinearityRewriteVisitor()
        result = visitor.visit(outer, None)
        assert visitor.rewrites_applied == 0
        # Still an Add_N, unchanged.
        assert isinstance(result, Add_N)

    def test_outer_subtract_without_inner_subtract_does_not_match(self):
        """``X - C * X`` (no inner Sub_N) must NOT rewrite."""
        x = _ident("X")
        c = _real(0.5)
        scaled = Mul_N(_CR, c, x)
        outer = Sub_N(_CR, x, scaled)
        visitor = CollinearityRewriteVisitor()
        result = visitor.visit(outer, None)
        assert visitor.rewrites_applied == 0

    def test_nested_bgk_patterns(self):
        """Two BGK collisions in one expression both rewrite."""
        # Outer:  (fIn1 - 1.5 * (fIn1 - feq1)) + (fIn2 - 0.6 * (fIn2 - feq2))
        bgk1 = self._bgk_pattern(_ident("fIn1"), _real(1.5),
                                  _ident("feq1"))
        bgk2 = self._bgk_pattern(_ident("fIn2"), _real(0.6),
                                  _ident("feq2"))
        outer = Add_N(_CR, bgk1, bgk2)
        visitor = CollinearityRewriteVisitor()
        result = visitor.visit(outer, None)
        # Bottom-up traversal rewrites both patterns.
        assert visitor.rewrites_applied == 2
        assert isinstance(result, Add_N)
        # Each subtree rewritten to Add_N.
        assert isinstance(result.left, Add_N)
        assert isinstance(result.right, Add_N)
