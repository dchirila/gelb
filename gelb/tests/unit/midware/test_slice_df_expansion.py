#!/usr/bin/env python3
"""Unit tests for the SliceDFExpansionVisitor midware pass.

The pass walks each block's statement list and expands Q-element-array
statements (Q >= 9) per direction, substituting literal-indexed array
constants and applying the exact identities (``0/1/-1*x``).

Tests use direct AST construction (not the full pipeline) and verify
the visitor's classification, substitution rules, and per-direction
expansion output.  End-to-end correctness is covered by
``test_examples_smoke.py``.
"""

import copy

import pytest

from gelb.gelb_ast.ASTNodes import (
    Add_N,
    Array1DLiteral_N,
    ArrayDataType_N,
    BroadcastNode_N,
    ConstantDefinitionStmt_N,
    Div_N,
    DynamicBlock_N,
    GlobalConstantsBlock_N,
    Identifier_N,
    InitializerBlock_N,
    IntLiteral_N,
    IntrinsicFunctionCall_N,
    LatticeOutSelectionAssignmentStmt_N,
    Pow_N,
    List_N,
    Mul_N,
    Program_N,
    Range_N,
    RealLiteral_N,
    RectSelOfArrayElems_N,
    RectSelOfLatticeInDFs_N,
    RectSelOfLatticeOutDFs_N,
    Sub_N,
    TypePromotionNode_N,
    UnaryMinusExpr_N,
    VariableAssignmentStmt_N,
    VariableDeclarationStmt_N,
)
from gelb.midware.SliceDFExpansionVisitor import (
    SliceDFExpansionVisitor,
    _collect_constexpr_arrays,
)
from gelb.utils.CodeRange import CodeRange


_CR = CodeRange(1, 1, 1, 1)


def _ident(name):
    return Identifier_N(_CR, name)


def _real(v):
    return RealLiteral_N(_CR, float(v))


def _int(v):
    return IntLiteral_N(_CR, int(v))


def _scalar_real():
    return ArrayDataType_N(_CR, 'real64', List_N(_CR))


def _array_real(q):
    return ArrayDataType_N(_CR, 'real64', IntLiteral_N(_CR, q))


def _typed(node, dtype):
    node.inferred_type = dtype
    return node


# D2Q9 EX/EY values (the ordering the examples use).
_D2Q9_EX = [0, 1, 0, -1, 0, 1, -1, -1, 1]
_D2Q9_EY = [0, 0, 1, 0, -1, 1, 1, -1, -1]


def _render(node):
    """A compact infix spelling of an expression tree, wrappers dropped."""
    while isinstance(node, (TypePromotionNode_N, BroadcastNode_N)):
        node = node.expr if isinstance(node, TypePromotionNode_N) else node.scalar_expr
    if isinstance(node, Identifier_N):
        return node.name
    if isinstance(node, (IntLiteral_N, RealLiteral_N)):
        return repr(node.value)
    if isinstance(node, UnaryMinusExpr_N):
        return f'(-{_render(node.value)})'
    ops = {Add_N: '+', Sub_N: '-', Mul_N: '*', Div_N: '/', Pow_N: '^'}
    return f'({_render(node.left)}{ops[type(node)]}{_render(node.right)})'


def _make_visitor(array_constants=None, lattice_q=9, enable_cse=True):
    lattice_info = {'f': {'d': 2, 'q': lattice_q, 'dtype': 'real',
                          'grid_size': [16, 16],
                          'periodic': [True, True]}}
    return SliceDFExpansionVisitor(
        lattice_info=lattice_info,
        array_constants=array_constants or {},
        enable_cse=enable_cse)


def _wrap_block_stmts(stmts):
    """Build a DynamicBlock_N around a list of statements."""
    stmt_list = List_N(_CR)
    for s in stmts:
        stmt_list.append(s)
    return DynamicBlock_N(_CR, _ident('TestBlock'), stmt_list)


def _process_block(visitor, block):
    """Convenience: run the visitor's per-block processing on a single
    block, ignoring program-level traversal."""
    visitor._process_block(block, None)
    return block


# --- Test cases ------------------------------------------------------


class TestVariableDeclarationExpansion:
    def test_d2q9_eu_substitution(self):
        """``__eu = EX*ux + EY*uy`` (Q=9 array decl) -- expand to 9
        scalar decls with EX[i]/EY[i] folded."""
        # __eu = EX*ux + EY*uy
        ux = _typed(_ident('ux'), _scalar_real())
        uy = _typed(_ident('uy'), _scalar_real())
        ex = _ident('EX')  # constexpr global; not typed (resolved by visitor)
        ey = _ident('EY')
        rhs = Add_N(_CR, Mul_N(_CR, ex, ux), Mul_N(_CR, ey, uy))
        rhs.inferred_type = _array_real(9)
        decl = VariableDeclarationStmt_N(
            _CR, _array_real(9), _ident('__eu'), initial_value=rhs)
        block = _wrap_block_stmts([decl])
        v = _make_visitor(array_constants={'EX': _D2Q9_EX, 'EY': _D2Q9_EY},
                          enable_cse=False)
        _process_block(v, block)
        # Expected: 9 scalar decls __eu_0 .. __eu_8.
        assert len(block.stmts.elements) == 9
        assert all(isinstance(d, VariableDeclarationStmt_N) and d.name.name == f'__eu_{i}'
                   for i, d in enumerate(block.stmts.elements))
        forms = [_render(d.initial_value) for d in block.stmts.elements]
        # A product with a zero component stays: it is -0 for a negative
        # velocity, and the sum's sign follows.  1*u and
        # -1*u are exact; (-ux) + (0*uy) is (0*uy) - ux by IEEE's
        # definition of subtraction.
        assert forms[0] == '((0*ux)+(0*uy))'
        assert forms[1] == '(ux+(0*uy))'
        assert forms[3] == '((0*uy)-ux)'
        assert forms[5] == '(ux+uy)'
        assert forms[7] == '((-ux)-uy)'

    def test_d3q19_three_axes(self):
        """``__eu = EX*ux + EY*uy + EZ*uz`` for Q=19 -> 19 scalar decls."""
        ux = _typed(_ident('ux'), _scalar_real())
        uy = _typed(_ident('uy'), _scalar_real())
        uz = _typed(_ident('uz'), _scalar_real())
        rhs = Add_N(_CR,
                    Add_N(_CR,
                          Mul_N(_CR, _ident('EX'), ux),
                          Mul_N(_CR, _ident('EY'), uy)),
                    Mul_N(_CR, _ident('EZ'), uz))
        rhs.inferred_type = _array_real(19)
        decl = VariableDeclarationStmt_N(
            _CR, _array_real(19), _ident('__eu'), initial_value=rhs)
        block = _wrap_block_stmts([decl])
        # D3Q19 ex/ey/ez (the ordering the examples use).
        ex19 = [0, 1, -1, 0, 0, 0, 0, 1, -1, 1, -1, 1, -1, 1, -1, 0, 0, 0, 0]
        ey19 = [0, 0, 0, 1, -1, 0, 0, 1, -1, -1, 1, 0, 0, 0, 0, 1, -1, 1, -1]
        ez19 = [0, 0, 0, 0, 0, 1, -1, 0, 0, 0, 0, 1, -1, -1, 1, 1, -1, -1, 1]
        v = _make_visitor(
            array_constants={'EX': ex19, 'EY': ey19, 'EZ': ez19},
            lattice_q=19,
            enable_cse=False)
        _process_block(v, block)
        assert len(block.stmts.elements) == 19
        # Direction 0: all zero components, kept as written.
        d0 = block.stmts.elements[0]
        assert d0.name.name == '__eu_0'
        assert _render(d0.initial_value) == '(((0*ux)+(0*uy))+(0*uz))'
        assert _render(block.stmts.elements[7].initial_value) == '((ux+uy)+(0*uz))'


class TestSkipUnexpandable:
    def test_opaque_only_intrinsic_skipped(self):
        """``fIn = upstream_dfs(...)`` (single intrinsic) is left as-is."""
        args = List_N(_CR)
        args.append(_ident('f'))
        intrinsic = IntrinsicFunctionCall_N(_CR, 'upstream_dfs', args)
        intrinsic.inferred_type = _array_real(9)
        decl = VariableDeclarationStmt_N(
            _CR, _array_real(9), _ident('fIn'), initial_value=intrinsic)
        block = _wrap_block_stmts([decl])
        v = _make_visitor()
        _process_block(v, block)
        # Should be unchanged -- single decl.
        assert len(block.stmts.elements) == 1
        assert block.stmts.elements[0] is decl

    def test_lattice_out_with_known_array_intrinsic_skipped(self):
        """``f.out[x,y|:] = bounce_back_dfs(...) + correction`` -- backend
        handles via slice-DF unroll; pass leaves it alone."""
        opp_args = List_N(_CR); opp_args.append(_ident('f'))
        opp = IntrinsicFunctionCall_N(_CR, 'bounce_back_dfs', opp_args)
        rhs = Add_N(_CR, opp, _real(0.1))
        rhs.inferred_type = _array_real(9)
        # f.out[x,y|0:8] LHS
        x_range = Range_N(_CR, _ident('x'), _ident('x'))
        y_range = Range_N(_CR, _ident('y'), _ident('y'))
        df_range = Range_N(_CR, _int(0), _int(8))
        lhs = RectSelOfLatticeOutDFs_N(_CR, _ident('f'),
                                        [x_range, y_range, df_range])
        stmt = LatticeOutSelectionAssignmentStmt_N(_CR, lhs, rhs)
        block = _wrap_block_stmts([stmt])
        v = _make_visitor()
        _process_block(v, block)
        # Should be unchanged.
        assert len(block.stmts.elements) == 1
        assert block.stmts.elements[0] is stmt

    def test_q_below_gate_not_expanded(self):
        """Q=3 (below the Q>=9 gate) -- left alone."""
        rhs = _typed(Add_N(_CR, _real(1.0), _real(2.0)), _array_real(3))
        decl = VariableDeclarationStmt_N(
            _CR, _array_real(3), _ident('arr'), initial_value=rhs)
        block = _wrap_block_stmts([decl])
        v = _make_visitor(lattice_q=3)
        _process_block(v, block)
        assert len(block.stmts.elements) == 1
        assert block.stmts.elements[0] is decl


class TestForcedWhole:
    def test_forced_whole_by_unexpandable_stmt(self):
        """If a downstream stmt references the array as a whole and
        won't be expanded, the array's decl must NOT be expanded."""
        # __eu = EX*ux + EY*uy (would normally be expanded)
        ux = _typed(_ident('ux'), _scalar_real())
        uy = _typed(_ident('uy'), _scalar_real())
        rhs = Add_N(_CR,
                    Mul_N(_CR, _ident('EX'), ux),
                    Mul_N(_CR, _ident('EY'), uy))
        rhs.inferred_type = _array_real(9)
        decl_eu = VariableDeclarationStmt_N(
            _CR, _array_real(9), _ident('__eu'), initial_value=rhs)
        # rho = sum(__eu) -- scalar stmt referencing __eu as whole array
        sum_args = List_N(_CR); sum_args.append(_ident('__eu'))
        sum_call = IntrinsicFunctionCall_N(_CR, 'sum', sum_args)
        rho_decl = VariableDeclarationStmt_N(
            _CR, _scalar_real(), _ident('rho'),
            initial_value=sum_call)
        block = _wrap_block_stmts([decl_eu, rho_decl])
        v = _make_visitor(array_constants={'EX': _D2Q9_EX,
                                            'EY': _D2Q9_EY})
        _process_block(v, block)
        # __eu must remain a single Q-element decl.
        assert len(block.stmts.elements) == 2
        assert block.stmts.elements[0] is decl_eu
        assert block.stmts.elements[1] is rho_decl


class TestLatticeOutSliceExpansion:
    def test_simple_slice_expansion(self):
        """``f.out[x,y|:] = scalar_expr`` -- expand to 9 single-DF stmts."""
        x_range = Range_N(_CR, _ident('x'), _ident('x'))
        y_range = Range_N(_CR, _ident('y'), _ident('y'))
        df_range = Range_N(_CR, _int(0), _int(8))
        lhs = RectSelOfLatticeOutDFs_N(_CR, _ident('f'),
                                        [x_range, y_range, df_range])
        # RHS: ux (a bare scalar identifier -- keeps it simple)
        rhs = _typed(_ident('ux'), _array_real(9))
        stmt = LatticeOutSelectionAssignmentStmt_N(_CR, lhs, rhs)
        block = _wrap_block_stmts([stmt])
        v = _make_visitor()
        _process_block(v, block)
        # Expected: 9 single-DF stmts.
        assert len(block.stmts.elements) == 9
        for i, new_stmt in enumerate(block.stmts.elements):
            assert isinstance(new_stmt,
                              LatticeOutSelectionAssignmentStmt_N)
            new_df_range = new_stmt.lhs.element_ranges[-1]
            assert new_df_range.low.value == i
            assert new_df_range.high.value == i

    def test_lattice_in_slice_narrowed_per_direction(self):
        """``f.out[x|:] = f.in[x|:] + 1`` -- per direction, the f.in
        slice should narrow to f.in[x|i]."""
        x_range_in = Range_N(_CR, _ident('x'), _ident('x'))
        df_in = Range_N(_CR, _int(0), _int(8))
        fin = RectSelOfLatticeInDFs_N(_CR, _ident('f'),
                                       [x_range_in, df_in])
        rhs = Add_N(_CR, fin, _real(1.0))
        rhs.inferred_type = _array_real(9)
        x_range_out = Range_N(_CR, _ident('x'), _ident('x'))
        df_out = Range_N(_CR, _int(0), _int(8))
        lhs = RectSelOfLatticeOutDFs_N(_CR, _ident('f'),
                                        [x_range_out, df_out])
        stmt = LatticeOutSelectionAssignmentStmt_N(_CR, lhs, rhs)
        block = _wrap_block_stmts([stmt])
        v = _make_visitor()
        _process_block(v, block)
        assert len(block.stmts.elements) == 9
        # Each new stmt's RHS should contain a f.in selection narrowed
        # to the per-direction index.
        for i, new_stmt in enumerate(block.stmts.elements):
            # Walk RHS for RectSelOfLatticeInDFs_N.
            def _find_lattice_in(node):
                if isinstance(node, RectSelOfLatticeInDFs_N):
                    return node
                if hasattr(node, 'get_children_names'):
                    for nm in node.get_children_names():
                        c = getattr(node, nm)
                        if c is not None:
                            r = _find_lattice_in(c)
                            if r is not None:
                                return r
                return None
            sel = _find_lattice_in(new_stmt.rhs)
            assert sel is not None
            df_r = sel.element_ranges[-1]
            assert df_r.low.value == i
            assert df_r.high.value == i


class TestVariableAssignmentExpansion:
    def test_assign_following_decl(self):
        """``arr (decl, no init); arr = (...algebra...)`` -- both expand
        consistently."""
        decl = VariableDeclarationStmt_N(
            _CR, _array_real(9), _ident('__eu'), initial_value=None)
        ux = _typed(_ident('ux'), _scalar_real())
        rhs = _typed(Mul_N(_CR, _ident('EX'), ux), _array_real(9))
        assign = VariableAssignmentStmt_N(_CR, _ident('__eu'), rhs)
        block = _wrap_block_stmts([decl, assign])
        v = _make_visitor(array_constants={'EX': _D2Q9_EX})
        _process_block(v, block)
        # 9 decls + the shared 0*ux + 9 assignments = 19 stmts
        assert len(block.stmts.elements) == 19
        # First 9 are declarations of __eu_0 .. __eu_8.
        for i in range(9):
            d = block.stmts.elements[i]
            assert isinstance(d, VariableDeclarationStmt_N)
            assert d.name.name == f'__eu_{i}'
            assert d.initial_value is None
        # Then the product the zero directions share (EX = 0 at 0, 2, 4).
        temp = block.stmts.elements[9]
        assert temp.name.name.startswith('_gelb_cse_')
        assert _render(temp.initial_value) == '(0*ux)'
        # Next 9 are assignments.
        for i in range(9):
            a = block.stmts.elements[10 + i]
            assert isinstance(a, VariableAssignmentStmt_N)
            assert a.lhs.name == f'__eu_{i}'
        assert _render(block.stmts.elements[10].rhs) == temp.name.name

    def test_assign_array1d_literal_per_direction(self):
        """``arr = ArrayLiteral1D(e_0, e_1, ..., e_8)`` -- each direction
        gets its corresponding element."""
        decl = VariableDeclarationStmt_N(
            _CR, _array_real(9), _ident('__meq'), initial_value=None)
        # Make a literal of 9 distinct scalar identifiers.
        elem_list = List_N(_CR)
        for i in range(9):
            elem_list.append(_typed(_ident(f'm{i}'), _scalar_real()))
        lit = Array1DLiteral_N(_CR, elem_list)
        lit.inferred_type = _array_real(9)
        assign = VariableAssignmentStmt_N(_CR, _ident('__meq'), lit)
        block = _wrap_block_stmts([decl, assign])
        v = _make_visitor()
        _process_block(v, block)
        # Filter to just the assignments.
        assigns = [s for s in block.stmts.elements
                   if isinstance(s, VariableAssignmentStmt_N)]
        assert len(assigns) == 9
        for i, a in enumerate(assigns):
            assert a.lhs.name == f'__meq_{i}'
            # RHS should be the i-th element identifier.
            assert isinstance(a.rhs, Identifier_N)
            assert a.rhs.name == f'm{i}'


class TestArrayElemAccess:
    def test_local_array_indexed_access_substituted(self):
        """A reference to ``__eu[3]`` (RectSelOfArrayElems_N) inside an
        expanded RHS should resolve to the per-direction scalar
        ``__eu_3``."""
        # Decl of __eu so the visitor knows it.
        ux = _typed(_ident('ux'), _scalar_real())
        eu_rhs = _typed(Mul_N(_CR, _ident('EX'), ux), _array_real(9))
        decl_eu = VariableDeclarationStmt_N(
            _CR, _array_real(9), _ident('__eu'),
            initial_value=eu_rhs)
        # __feq = ArrayLiteral1D(__eu[3], __eu[5], ...) -- 9 entries
        elem_list = List_N(_CR)
        for j in range(9):
            sel = RectSelOfArrayElems_N(
                _CR, _ident('__eu'),
                [Range_N(_CR, _int(j), _int(j))])
            sel.inferred_type = _scalar_real()
            elem_list.append(sel)
        lit = Array1DLiteral_N(_CR, elem_list)
        lit.inferred_type = _array_real(9)
        decl_feq = VariableDeclarationStmt_N(
            _CR, _array_real(9), _ident('__feq'), initial_value=lit)
        block = _wrap_block_stmts([decl_eu, decl_feq])
        v = _make_visitor(array_constants={'EX': _D2Q9_EX})
        _process_block(v, block)
        # Expected total: 9 (decl_eu expanded) + 9 (decl_feq expanded) = 18,
        # besides the temporary holding the shared 0*ux.
        decls = [s for s in block.stmts.elements
                 if isinstance(s, VariableDeclarationStmt_N)
                 and not s.name.name.startswith('_gelb_cse_')]
        assert len(decls) == 18
        # The feq decls should reference __eu_<i>.
        feq_decls = [d for d in decls if d.name.name.startswith('__feq_')]
        assert len(feq_decls) == 9
        for i, d in enumerate(feq_decls):
            assert d.name.name == f'__feq_{i}'
            assert isinstance(d.initial_value, Identifier_N)
            assert d.initial_value.name == f'__eu_{i}'


class TestCommonSubexpressionHoisting:
    """Common-subexpression hoisting (structural, ordered)."""

    def test_shared_subexpr_hoisted(self):
        """Each direction contains ``rho * eu * eu`` (a 2-mult product) --
        with the same rho*usq factor the CSE should hoist it."""
        decl = VariableDeclarationStmt_N(
            _CR, _array_real(9), _ident('__feq'), initial_value=None)
        elems = List_N(_CR)
        # Each direction's RHS is ``W[i] * rho * usq + ...`` where W[i]
        # is a literal but rho*usq is shared.
        for i in range(9):
            rho = _typed(_ident('rho'), _scalar_real())
            usq = _typed(_ident('usq'), _scalar_real())
            wi = _real(0.1 * (i + 1))   # different per direction
            # rho * usq * wi  -> CSE should hoist rho*usq.
            inner = Mul_N(_CR, rho, usq)
            inner.inferred_type = _scalar_real()
            outer = Mul_N(_CR, wi, inner)
            outer.inferred_type = _scalar_real()
            elems.append(outer)
        lit = Array1DLiteral_N(_CR, elems)
        lit.inferred_type = _array_real(9)
        assign = VariableAssignmentStmt_N(_CR, _ident('__feq'), lit)
        block = _wrap_block_stmts([decl, assign])
        v = _make_visitor()  # enable_cse=True by default
        _process_block(v, block)
        # Expected: 1 CSE temp for ``rho * usq``, used by all 9 directions.
        assert v.cse_temps_emitted >= 1

    def test_no_shared_subexpr_no_temps(self):
        """All directions independent -- no CSE temps emitted."""
        decl = VariableDeclarationStmt_N(
            _CR, _array_real(9), _ident('__indep'), initial_value=None)
        elems = List_N(_CR)
        for i in range(9):
            # Use a unique scalar identifier per direction.
            elems.append(_typed(_ident(f'a{i}'), _scalar_real()))
        lit = Array1DLiteral_N(_CR, elems)
        lit.inferred_type = _array_real(9)
        assign = VariableAssignmentStmt_N(_CR, _ident('__indep'), lit)
        block = _wrap_block_stmts([decl, assign])
        v = _make_visitor()
        _process_block(v, block)
        # No shared sub-expressions -> no temps.
        assert v.cse_temps_emitted == 0

    def test_cse_disabled_by_flag(self):
        """``enable_cse=False`` must skip the CSE pass entirely."""
        decl = VariableDeclarationStmt_N(
            _CR, _array_real(9), _ident('__feq'), initial_value=None)
        elems = List_N(_CR)
        for i in range(9):
            ux = _typed(_ident('ux'), _scalar_real())
            uy = _typed(_ident('uy'), _scalar_real())
            elems.append(Add_N(_CR, ux, uy))
        lit = Array1DLiteral_N(_CR, elems)
        lit.inferred_type = _array_real(9)
        assign = VariableAssignmentStmt_N(_CR, _ident('__feq'), lit)
        block = _wrap_block_stmts([decl, assign])
        # Construct a visitor with CSE explicitly disabled.
        from gelb.midware.SliceDFExpansionVisitor import (
            SliceDFExpansionVisitor as Visitor)
        v = Visitor(
            lattice_info={'f': {'d': 2, 'q': 9, 'dtype': 'real',
                                'grid_size': [16, 16],
                                'periodic': [True, True]}},
            array_constants={},
            enable_cse=False)
        _process_block(v, block)
        assert v.cse_temps_emitted == 0


class TestEntryPoint:
    def test_expand_slice_dfs_returns_ast(self):
        """The module entry point should accept the AST and stash
        counters."""
        from gelb.gelb_ast.ASTNodes import (
            Program_N, LatticesBlock_N, LatticeInstaStmt_N,
        )
        from gelb.midware.SliceDFExpansionVisitor import expand_slice_dfs
        # Minimal AST: a Program_N with a Q=9 lattice and no blocks to
        # process.  expand_slice_dfs should set the counters and not
        # raise.
        prog = Program_N(_CR)
        lattices_stmts = List_N(_CR)
        lattices_stmts.append(LatticeInstaStmt_N(
            _CR, _ident('f'), IntLiteral_N(_CR, 2),
            IntLiteral_N(_CR, 9), _scalar_real(),
            IntLiteral_N(_CR, 16), IntLiteral_N(_CR, 1)))
        prog.lattices = LatticesBlock_N(_CR, lattices_stmts)
        result = expand_slice_dfs(prog)
        assert hasattr(result, 'slice_df_expansions')
        assert result.slice_df_expansions == 0


class TestCollectConstexprArrays:
    """Cover the ``_collect_constexpr_arrays`` harvesting helper.

    The slice-DF expansion pass relies on this dict to substitute
    references to constexpr global Q-element arrays (W, EX, EY, ...) with
    their literal values per direction.  An empty dict (e.g. when the
    helper fails to recognise a wrapped ``Array1DLiteral_N``) silently
    breaks per-direction substitution: bare-array identifiers survive
    to codegen and the backend emits ``g_W * scalar`` (whole-array *
    scalar), which fails to compile.
    """

    def _prog_with_constants(self, stmts):
        prog = Program_N(_CR)
        stmts_list = List_N(_CR)
        for s in stmts:
            stmts_list.append(s)
        prog.global_constants = GlobalConstantsBlock_N(_CR, stmts_list)
        return prog

    def _array1d_literal(self, values):
        elements = List_N(_CR)
        for v in values:
            elements.append(_real(v))
        return Array1DLiteral_N(_CR, elements)

    def test_bare_array1d_literal(self):
        """fp64 case: ``const array[real, 9] EX = {...}`` -- bare
        ``Array1DLiteral_N`` is harvested directly."""
        stmt = ConstantDefinitionStmt_N(
            _CR, _array_real(9), _ident('EX'),
            self._array1d_literal(_D2Q9_EX))
        out = _collect_constexpr_arrays(
            self._prog_with_constants([stmt]))
        assert out == {'EX': list(_D2Q9_EX)}

    def test_narrow_array_elements_are_the_values_the_array_stores(self):
        """``const array[real32, 9] W = {16777217, -16777216, 0, ...}``:
        the collector converts every element to the declared element
        type, so W[0] is the real 16777216.0 (binary32 has 24 significand
        bits) and an integer element becomes a real."""
        ints = [16777217, -16777216, 0, 0, 0, 0, 0, 0, 0]
        real32_9 = ArrayDataType_N(_CR, 'real32', IntLiteral_N(_CR, 9))
        elems = [IntLiteral_N(_CR, v) for v in ints]
        lit = Array1DLiteral_N(_CR, List_N(_CR))
        for e in elems:
            lit.value.append(e)
        wrapped = TypePromotionNode_N(_CR, lit, real32_9)
        stmt = ConstantDefinitionStmt_N(_CR, real32_9, _ident('W'), wrapped)
        out = _collect_constexpr_arrays(self._prog_with_constants([stmt]))
        assert out == {'W': [16777216.0, -16777216.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]}
        assert all(isinstance(v, float) for v in out['W'])

    def test_type_promoted_array1d_literal(self):
        """fp32 case: ``const array[real32, 9] W = {...}`` -- the
        Array1DLiteral_N is wrapped in TypePromotionNode_N to record
        the implicit narrowing of the (default-real64) elements to
        real32.  The harvester must see through the wrapper."""
        weights = [4.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0,
                   1.0/36.0, 1.0/36.0, 1.0/36.0, 1.0/36.0]
        wrapped = TypePromotionNode_N(
            _CR, self._array1d_literal(weights), _array_real(9))
        stmt = ConstantDefinitionStmt_N(
            _CR, _array_real(9), _ident('W'), wrapped)
        out = _collect_constexpr_arrays(
            self._prog_with_constants([stmt]))
        assert out == {'W': weights}

    def test_nested_wrappers_stripped(self):
        """Defensive: nested ``BroadcastNode_N(TypePromotionNode_N(...))``
        wrappers should also be stripped.  Doesn't actually occur in
        practice (broadcast wraps scalars, not array literals), but the
        unwrap loop should cope with both wrapper kinds."""
        lit = self._array1d_literal(_D2Q9_EX)
        wrapped = TypePromotionNode_N(_CR, lit, _array_real(9))
        broadcasted = BroadcastNode_N(_CR, wrapped, _array_real(9))
        stmt = ConstantDefinitionStmt_N(
            _CR, _array_real(9), _ident('EX'), broadcasted)
        out = _collect_constexpr_arrays(
            self._prog_with_constants([stmt]))
        assert out == {'EX': list(_D2Q9_EX)}

    def test_non_array_literal_skipped(self):
        """A scalar constant (``const real PI = 3.14``) is not a
        Q-element array -- should be excluded from the harvest."""
        stmt = ConstantDefinitionStmt_N(
            _CR, _scalar_real(), _ident('PI'), _real(3.14))
        out = _collect_constexpr_arrays(
            self._prog_with_constants([stmt]))
        assert out == {}

    def test_no_global_constants_block(self):
        """A program without a global_constants block returns an empty
        dict (rather than raising)."""
        prog = Program_N(_CR)
        prog.global_constants = None
        assert _collect_constexpr_arrays(prog) == {}


class TestExactSimplification:
    """``simplify_exact`` applies only the identities IEEE arithmetic
    makes exact and folds literal-only subtrees in their own width; it
    never re-associates or combines literal terms across a variable
    (user manual, Numerical semantics: What the optimizer promises)."""

    @staticmethod
    def _scalar(dtype):
        return ArrayDataType_N(_CR, dtype, List_N(_CR))

    def _lit(self, value, dtype='real'):
        node = IntLiteral_N(_CR, value) if isinstance(value, int) else RealLiteral_N(_CR, float(value))
        return _typed(node, self._scalar(dtype))

    def _var(self, name, dtype='real'):
        return _typed(_ident(name), self._scalar(dtype))

    def _op(self, cls, a, b, dtype='real'):
        return _typed(cls(_CR, a, b), self._scalar(dtype))

    def _promoted(self, node, dtype):
        return TypePromotionNode_N(_CR, node, self._scalar(dtype))

    def test_the_exact_identities(self):
        from gelb.midware.ast_simplify import simplify_exact
        x = lambda: self._var('x')
        one, minus_one = self._lit(1.0), self._lit(-1.0)
        assert simplify_exact(self._op(Mul_N, x(), copy.deepcopy(one))).name == 'x'
        assert simplify_exact(self._op(Mul_N, one, x())).name == 'x'
        neg = simplify_exact(self._op(Mul_N, minus_one, x()))
        assert isinstance(neg, UnaryMinusExpr_N) and neg.value.name == 'x'
        assert simplify_exact(self._op(Div_N, x(), copy.deepcopy(one))).name == 'x'
        assert simplify_exact(_typed(UnaryMinusExpr_N(_CR, _typed(UnaryMinusExpr_N(_CR, x()), self._scalar('real'))), self._scalar('real'))).name == 'x'
        # A promoted 1 is still 1 (the type pass promotes an int velocity component).
        assert simplify_exact(self._op(Mul_N, x(), self._promoted(self._lit(1, 'int'), 'real'))).name == 'x'
        # The zeros whose sign cannot change the result.
        assert simplify_exact(self._op(Add_N, x(), self._lit(-0.0))).name == 'x'
        assert simplify_exact(self._op(Add_N, self._lit(-0.0), x())).name == 'x'
        assert simplify_exact(self._op(Sub_N, x(), self._lit(0.0))).name == 'x'
        assert _render(simplify_exact(self._op(Sub_N, self._lit(-0.0), x()))) == '(-x)'

    def test_a_real_zero_keeps_its_sign(self):
        # u*0.0 is -0 for u = -1, u + 0.0 is +0 for u = -0 and
        # 0.0 - u is +0 for u = +0; the rewritten forms gave +0, -0 and -0.
        import numpy as np
        from gelb.midware.ast_simplify import simplify_exact
        assert np.signbit(np.float64(-1.0) * 0.0)
        assert not np.signbit(np.float64(-0.0) + 0.0)
        assert not np.signbit(np.float64(0.0) - np.float64(0.0))
        x = lambda: self._var('x')
        kept = [self._op(Mul_N, self._lit(0.0), x()), self._op(Mul_N, x(), self._lit(0.0)),
                self._op(Add_N, x(), self._lit(0.0)), self._op(Add_N, self._lit(0.0), x()),
                self._op(Sub_N, x(), self._lit(-0.0)), self._op(Sub_N, self._lit(0.0), x()),
                # An integer zero converts to +0.
                self._op(Add_N, x(), self._promoted(self._lit(0, 'int'), 'real')),
                self._op(Mul_N, self._promoted(self._lit(0, 'int'), 'real'), x())]
        for tree in kept:
            before = _render(tree)
            assert _render(simplify_exact(tree)) == before

    def test_an_integer_zero_has_no_sign(self):
        from gelb.midware.ast_simplify import simplify_exact
        i = lambda: self._var('i', 'int')
        zero = lambda: self._lit(0, 'int')
        product = simplify_exact(self._op(Mul_N, zero(), i(), 'int'))
        assert isinstance(product, IntLiteral_N) and product.value == 0
        assert product.inferred_type.element_dtype == 'int'
        assert simplify_exact(self._op(Add_N, i(), zero(), 'int')).name == 'i'
        assert simplify_exact(self._op(Sub_N, i(), zero(), 'int')).name == 'i'
        assert _render(simplify_exact(self._op(Sub_N, zero(), i(), 'int'))) == '(-i)'

    def test_an_integer_zero_keeps_a_random_draw(self):
        # 0 * int(random()) is 0, but dropping the operand drops a draw.
        from gelb.gelb_ast.ASTNodes import IntrinsicFunctionCall_N
        from gelb.midware.ast_simplify import is_pure, simplify_exact
        draw = IntrinsicFunctionCall_N(_CR, 'random', List_N(_CR))
        args = List_N(_CR)
        args.append(draw)
        cast = _typed(IntrinsicFunctionCall_N(_CR, 'int', args), self._scalar('int'))
        assert not is_pure(cast) and is_pure(self._var('i', 'int'))
        product = self._op(Mul_N, self._lit(0, 'int'), cast, 'int')
        assert isinstance(simplify_exact(product), Mul_N)

    def test_powers_are_left_to_the_backend(self):
        # The Fortran backend evaluates x**2.0 with pow, which need not
        # equal x*x (on macOS it differs for about 0.1 % of inputs at -O0).
        from gelb.midware.ast_simplify import simplify_exact
        for exponent in (1, 2, 3, 4):
            tree = self._op(Pow_N, self._var('x'), self._promoted(self._lit(exponent, 'int'), 'real'))
            assert isinstance(simplify_exact(tree), Pow_N)
        literal = self._op(Pow_N, self._lit(1.1), self._promoted(self._lit(3, 'int'), 'real'))
        assert isinstance(simplify_exact(literal), Pow_N)
        # Its operands are still simplified.
        tree = self._op(Pow_N, self._op(Mul_N, self._lit(1.0), self._var('x')),
                        self._promoted(self._lit(3, 'int'), 'real'))
        assert _render(simplify_exact(tree)) == '(x^3)'

    def test_sign_moves_are_exact_and_a_cancellation_keeps_its_sign(self):
        # IEEE defines a - b as a + (-b), and rounding is symmetric under
        # sign for products and quotients.  (-a) + (-b) -> -(a + b) is not
        # exact: a = 1, b = -1 gives +0 on the left and -0 on the right.
        import numpy as np
        from gelb.midware.ast_simplify import simplify_exact
        a, b = np.float64(1.0), np.float64(-1.0)
        assert not np.signbit((-a) + (-b)) and np.signbit(-(a + b))
        neg = lambda n: _typed(UnaryMinusExpr_N(_CR, n), self._scalar('real'))
        x, y = lambda: self._var('x'), lambda: self._var('y')
        assert _render(simplify_exact(self._op(Add_N, neg(x()), neg(y())))) == '((-x)-y)'
        assert _render(simplify_exact(self._op(Sub_N, neg(x()), y()))) == '((-x)-y)'
        assert _render(simplify_exact(self._op(Add_N, x(), neg(y())))) == '(x-y)'
        assert _render(simplify_exact(self._op(Add_N, neg(x()), y()))) == '(y-x)'
        assert _render(simplify_exact(self._op(Sub_N, x(), neg(y())))) == '(x+y)'
        assert _render(simplify_exact(self._op(Mul_N, neg(x()), y()))) == '(-(x*y))'
        assert _render(simplify_exact(self._op(Div_N, neg(x()), neg(y())))) == '(x/y)'
        # The velocity-set case: -1*ux + -1*uy.
        m1 = lambda: self._promoted(self._lit(-1, 'int'), 'real')
        out = simplify_exact(self._op(Add_N, self._op(Mul_N, m1(), self._var('ux')), self._op(Mul_N, m1(), self._var('uy'))))
        assert _render(out) == '((-ux)-uy)'

    def test_literal_only_subtrees_fold_in_their_width(self):
        import numpy as np
        from gelb.midware.ast_simplify import simplify_exact
        narrow = simplify_exact(self._op(Mul_N, self._lit(0.1, 'real32'), self._lit(3.0, 'real32'), 'real32'))
        assert isinstance(narrow, RealLiteral_N)
        assert narrow.value == float(np.float32(0.1) * np.float32(3.0))
        assert narrow.inferred_type.element_dtype == 'real32'
        wide = simplify_exact(self._op(Mul_N, self._lit(0.1), self._lit(3.0)))
        assert wide.value == 0.1 * 3.0
        quotient = simplify_exact(self._op(Div_N, self._lit(-7, 'int'), self._lit(2, 'int'), 'int'))
        assert isinstance(quotient, IntLiteral_N) and quotient.value == -3   # truncation

    def test_no_reassociation_and_no_literal_combination(self):
        # `(u + 16777217) - 16777216` in real32 stays as written,
        # so u = 0.5 gives 0 like the single-direction form.
        from gelb.midware.ast_simplify import simplify_exact, structural_key
        u = self._var('u', 'real32')
        total = self._op(Add_N, u, self._promoted(self._lit(16777217, 'int'), 'real32'), 'real32')
        rhs = self._op(Sub_N, total, self._promoted(self._lit(16777216, 'int'), 'real32'), 'real32')
        before = structural_key(rhs)
        assert structural_key(simplify_exact(rhs)) == before
        # A promoted real32 composite and an integer division stay as written.
        a = self._var('a', 'real32')
        inner = self._op(Mul_N, a, copy.deepcopy(a), 'real32')
        rhs = self._op(Mul_N, self._lit(3.0), self._promoted(inner, 'real'))
        assert structural_key(simplify_exact(rhs)) == structural_key(rhs)
        diff = self._op(Sub_N, self._var('x', 'int'), self._lit(7, 'int'), 'int')
        quot = self._op(Div_N, diff, self._lit(2, 'int'), 'int')
        rhs = self._op(Mul_N, self._var('u', 'real32'), self._promoted(quot, 'real32'), 'real32')
        assert structural_key(simplify_exact(rhs)) == structural_key(rhs)

    def test_a_kind_changing_promotion_is_part_of_the_identity(self):
        from gelb.midware.ast_simplify import structural_key
        bare = self._lit(5, 'int')
        promoted = self._promoted(self._lit(5, 'int'), 'real32')
        assert structural_key(promoted) != structural_key(bare)
        assert structural_key(promoted) == structural_key(copy.deepcopy(promoted))

    def test_the_sign_of_a_zero_is_part_of_the_identity(self):
        # 0.0 == -0.0 in Python; x + 0.0 and x + (-0.0) differ at x = -0.
        from gelb.midware.ast_simplify import structural_key
        plus = self._op(Add_N, self._var('x'), self._lit(0.0))
        minus = self._op(Add_N, self._var('x'), self._lit(-0.0))
        assert structural_key(plus) != structural_key(minus)


class TestStructuralCSE:
    """``hoist_common_subtrees`` shares identical *ordered* subtrees
    only, inner shared subtrees first, and never a bare negation."""

    @staticmethod
    def _scalar():
        return ArrayDataType_N(_CR, 'real', List_N(_CR))

    def _var(self, name):
        return _typed(_ident(name), self._scalar())

    def _mul(self, a, b):
        return _typed(Mul_N(_CR, a, b), self._scalar())

    def test_identical_ordered_subtrees_are_shared_once(self):
        from gelb.midware.ast_simplify import hoist_common_subtrees
        exprs = [self._mul(_typed(_real(0.1), self._scalar()), self._mul(self._var('a'), self._var('b'))),
                 self._mul(_typed(_real(0.2), self._scalar()), self._mul(self._var('a'), self._var('b'))),
                 self._mul(self._var('b'), self._var('a'))]
        temps, rewritten = hoist_common_subtrees(exprs, lambda i: f't{i}')
        assert [name for name, _ in temps] == ['t0']
        body = temps[0][1]
        assert isinstance(body, Mul_N) and body.left.name == 'a' and body.right.name == 'b'
        assert body.inferred_type.element_dtype == 'real'
        assert rewritten[0].right.name == 't0' and rewritten[1].right.name == 't0'
        assert isinstance(rewritten[2], Mul_N) and rewritten[2].left.name == 'b'   # b*a is another tree

    def test_nested_shared_subtrees_are_declared_inner_first(self):
        from gelb.midware.ast_simplify import hoist_common_subtrees
        def outer():
            return self._mul(self._var('w'), self._mul(self._var('a'), self._var('b')))
        exprs = [outer(), outer(), self._mul(self._var('a'), self._var('b'))]
        temps, rewritten = hoist_common_subtrees(exprs, lambda i: f't{i}')
        assert [name for name, _ in temps] == ['t0', 't1']
        assert temps[0][1].left.name == 'a'                   # a*b first
        assert temps[1][1].right.name == 't0'                 # w * t0
        assert rewritten[0].name == 't1' and rewritten[2].name == 't0'

    def test_a_subtree_with_a_random_draw_is_not_shared(self):
        from gelb.gelb_ast.ASTNodes import IntrinsicFunctionCall_N
        from gelb.midware.ast_simplify import hoist_common_subtrees
        def draw_sum():
            call = _typed(IntrinsicFunctionCall_N(_CR, 'random', List_N(_CR)), self._scalar())
            return self._mul(self._var('a'), _typed(Add_N(_CR, call, self._var('b')), self._scalar()))
        temps, _ = hoist_common_subtrees([draw_sum(), draw_sum()], lambda i: f't{i}')
        assert temps == []
        # Nor inside another call's arguments.
        def sqrt_of_draw():
            call = _typed(IntrinsicFunctionCall_N(_CR, 'random', List_N(_CR)), self._scalar())
            args = List_N(_CR)
            args.append(call)
            root = _typed(IntrinsicFunctionCall_N(_CR, 'sqrt', args), self._scalar())
            return self._mul(self._var('a'), root)
        temps, _ = hoist_common_subtrees([sqrt_of_draw(), sqrt_of_draw()], lambda i: f't{i}')
        assert temps == []

    def test_nothing_shared_and_bare_negations_are_left_alone(self):
        from gelb.midware.ast_simplify import hoist_common_subtrees
        exprs = [self._var('a'), self._var('b')]
        assert hoist_common_subtrees(exprs, lambda i: f't{i}') == ([], exprs)
        neg = lambda: _typed(UnaryMinusExpr_N(_CR, self._var('a')), self._scalar())
        temps, _ = hoist_common_subtrees([neg(), neg()], lambda i: f't{i}')
        assert temps == []

    def test_a_temporary_takes_the_element_width_of_its_subtree(self):
        # In a per-direction tree, (u*u) on a real32 lattice still
        # carries the statement's real32[9] type; the temporary holding it
        # was declared real64, so t*t was a double product.
        from gelb.midware.ast_simplify import hoist_common_subtrees, scalar_type_of
        narrow_array = lambda: ArrayDataType_N(_CR, 'real32', IntLiteral_N(_CR, 9))
        square = lambda: _typed(Mul_N(_CR, _typed(_ident('u'), narrow_array()),
                                      _typed(_ident('u'), narrow_array())), narrow_array())
        product = _typed(Mul_N(_CR, square(), square()), narrow_array())
        temps, rewritten = hoist_common_subtrees([product], lambda i: f't{i}')
        assert [name for name, _ in temps] == ['t0']
        declared = scalar_type_of(temps[0][1], _scalar_real())
        assert declared.element_dtype == 'real32'
        assert isinstance(declared.shape, List_N) and not declared.shape.elements
        for ref in (rewritten[0].left, rewritten[0].right):
            assert ref.name == 't0' and ref.inferred_type.element_dtype == 'real32'
            assert not ref.inferred_type.shape.elements
        # An untyped tree takes the fallback.
        assert scalar_type_of(_ident('v'), _scalar_real()).element_dtype == 'real64'
