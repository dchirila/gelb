"""SIMD (Google Highway Vec8d/Vec8q) emission for cpu_highway.

SIMD eligibility predicates, vectorized block emission, the x-split
machinery for boundary-adjacent SIMD bodies, CBT cross-tile loads, and
aligned/NT store selection.
"""

from __future__ import annotations

from gelb.backends.highway.common import (
    _lname,
    _CBT_TILE,
    _TYPE_MAP,
)

from gelb.gelb_ast.ASTNodes import (
    Add_N,
    And_N,
    Array1DLiteral_N,
    BoolLiteral_N,
    BroadcastNode_N,
    Div_N,
    Equal_N,
    GreaterEqual_N,
    Greater_N,
    Identifier_N,
    IntLiteral_N,
    IntrinsicFunctionCall_N,
    LessEqual_N,
    Less_N,
    List_N,
    Mul_N,
    Node_N,
    NotEqual_N,
    Or_N,
    Pow_N,
    RealLiteral_N,
    RectSelOfArrayElems_N,
    RectSelOfLatticeInDFs_N,
    Sub_N,
    TypePromotionNode_N,
    UnaryMinusExpr_N,
)

from gelb.midware.ast_eval import (
    is_periodic,
)


class SimdEmitMixin:
    """Mixin: see module docstring.  Assembled into
    ``HighwayCodeGenerator`` (stage3_backend_cpu_highway).
    """

    def _emit_simd_store(self, vname: str, lhs_addr: str) -> str:
        """Return the C++ source for a SIMD-mode lattice-store call,
        dispatching on the active layout's alignment / NT-store
        decision:

          * SoA (``_cbt_store_suffix() == ''``)         -> ``hn::StoreU(v, d, &addr)``.
            Cells aren't 64-byte aligned in general (head/tail of
            the SoA range can land anywhere); ``LoadU`` /
            ``StoreU`` lower to a zero-cost aligned op when the
            address turns out aligned at runtime.
          * CBT-no-NT (``_cbt_store_suffix() == '_a'``) -> ``hn::Store(v, d, &cbt_addr)``.
            Tile-aligned iteration guarantees the lane subscript
            folds to 0 at runtime; ``hn::Store`` is the aligned
            variant.  The address is rewritten via
            ``_cbt_aligned_addr`` to drop the trailing ``[(...)%8]``
            lane subscript and replace it with ``[0]``, giving gcc
            a static alignment hint.
          * CBT+NT (``_cbt_store_suffix() == '_nt'``)    -> ``hn::Stream(v, d, &cbt_addr)``.
            NT-store path.  The gate (``_should_use_nt_stores()``)
            decides when the backend can safely use streaming stores;
            otherwise CBT stays on the aligned ``Store`` path.

        ``store`` / ``store_a`` / ``store_nt`` map 1:1 to the three
        Highway calls.
        """
        suffix = self._cbt_store_suffix()
        if suffix == '_nt':
            return (f'hn::Stream({vname}, d, '
                    f'&{self._cbt_aligned_addr(lhs_addr)})')
        if suffix == '_a':
            return (f'hn::Store({vname}, d, '
                    f'&{self._cbt_aligned_addr(lhs_addr)})')
        return f'hn::StoreU({vname}, d, &{lhs_addr})'

    def _block_simd_eligible(self, block, info) -> bool:
        """Context-agnostic predicate: is this block (initializer /
        dynamic / gauge) eligible for SIMD emission?

        A block is SIMD-eligible when:
          - its NC fills its bbox densely,
          - the bbox's innermost (x) axis spans at least
            Vec8d::size cells (after deducting head/tail), AND
          - any upstream_dfs offsets are foldable to small integers
            (which the offset analysis takes care of), AND
          - the body does not contain a mixed-width boolean expression
            (Highway mask types don't compose with scalar bools -- bail
            out to scalar when the body has comparison or logical
            operators that may produce a vector mask on one side and a
            scalar bool on the other).
        """
        if info.bbox is None or not info.bbox_dense:
            return False
        # Gauge stores currently use double-vector StoreU. Boolean output
        # is a byte buffer and must take the scalar store path.
        if any(getattr(decl.data_type, 'element_dtype', None) == 'bool'
               for decl in getattr(block, 'outputs', ())):
            return False
        # Vec8d is double-precision only.  If any lattice (this block
        # may read from or write to multiple) isn't double, fall back
        # to scalar emission.
        if any(_TYPE_MAP.get(info['dtype']) != 'double'
               for info in self._lattice_info.values()):
            return False
        x_lo, x_hi = info.bbox[0]
        # After deducting head/tail along x, the SIMD interior must
        # still span >= VW cells for the vector body to fire even once.
        offsets = self._compute_stencil_offsets(block)
        if (self._block_has_bounce_back(block) and self._any_cbt_lattice()
                and max(offsets[0]) >= _CBT_TILE):
            # The cross-tile loader covers adjacent tiles. Wider links
            # still work through scalar addressing (including modulo).
            return False
        woffs = self._compute_write_offsets(block)
        neg_x = max(offsets[0][0], woffs[0][0])
        pos_x = max(offsets[0][1], woffs[0][1])
        periodic_x = is_periodic(self._lattice_info, 0)
        sizes = self._grid_sizes()
        head_x = neg_x if (periodic_x and x_lo == 0) else 0
        tail_x = pos_x if (periodic_x and x_hi == sizes[0] - 1) else 0
        interior = (x_hi - tail_x) - (x_lo + head_x) + 1
        if interior < self._simd_vw:
            return False
        # Guard: bool-op + spatial-x mix produces Vec8db && scalar-bool
        # ambiguous overload at C++ level (e.g. RB-MRT init has
        # ``x == DELTA_PERTURB_X && y == DELTA_PERTURB_Y``).  Bail out
        # to scalar if such mixed boolean ops are present.
        if self._block_has_xref_bool_op(block):
            return False
        # Integer arithmetic on the spatial x has no vector form here:
        # x is a GeLB `int` but a double vector in the SIMD body, so
        # ``(x - 7) / 2`` would be a real division.  Such a block takes
        # the scalar path.
        if self._block_has_integer_arithmetic_on_x(block):
            return False
        # An intrinsic with no vector form (``mod``, ``atan2``, a
        # width-specific cast, a power that is not unrolled) is emitted
        # once, as scalar code, so that every cell takes the same path
        # (user manual, Numerical semantics: Types and promotion, Library
        # functions).  Conservative: any such call in a value expression
        # sends the block to the scalar path.  (``tan`` has a lane-wise
        # vector helper, the platform's tan on every lane.)
        if self._block_has_scalar_only_intrinsic(block):
            return False
        # The SIMD body holds every real local as a binary64 vector and
        # has no vector of a narrow width, so a block that declares a
        # ``real32``/``int8``/``int16``/``int32`` local, or converts a
        # value to such a width, is emitted once as scalar code, where
        # every operation rounds to its width (user manual, Numerical
        # semantics: Types and promotion); a narrow-width local was once
        # computed as a double vector here.
        if self._block_has_narrow_width(block):
            return False
        return True

    def _block_has_narrow_width(self, block) -> bool:
        """Whether ``block`` declares a local of a narrow width or holds
        a value expression typed, or converted to, a narrow width
        (``real32``, ``int8``, ``int16``, ``int32``).  Lattice and array
        index expressions are skipped."""
        from gelb.gelb_ast.ASTNodes import (
            Node_N as _Node, List_N as _List,
            VariableDeclarationStmt_N as _Decl,
            RectSelOfLatticeInDFs_N as _LIn,
            RectSelOfLatticeOutDFs_N as _LOut, RectSelOfArrayElems_N as _ASel,
        )
        narrow = ('real32', 'int8', 'int16', 'int32')
        selections = (_LIn, _LOut, _ASel)

        def width_of(data_type):
            return getattr(data_type, 'element_dtype', None)

        def children(n):
            if isinstance(n, _List):
                return list(n.elements)
            if isinstance(n, _Node):
                try:
                    return [getattr(n, nm) for nm in n.get_children_names()]
                except Exception:
                    return []
            return []

        def found(n):
            if isinstance(n, selections):
                return False
            if isinstance(n, _Decl) and width_of(n.data_type) in narrow:
                return True
            if isinstance(n, TypePromotionNode_N) and width_of(n.target_type) in narrow:
                return True
            if isinstance(n, _Node) and \
                    width_of(getattr(n, 'inferred_type', None)) in narrow:
                return True
            return any(found(c) for c in children(n))

        stmts = getattr(getattr(block, 'stmts', None), 'elements', None) or []
        outputs = getattr(getattr(block, 'outputs', None), 'elements', None) or []
        return any(found(s) for s in list(outputs) + list(stmts))

    def _block_has_scalar_only_intrinsic(self, block) -> bool:
        """Whether a value expression of ``block`` calls ``mod`` or
        ``atan2``, a cast other than ``real``/``int``, or
        raises to a power that is not an integer literal in 0..8 (which
        the emitter unrolls).  Lattice and array index expressions are
        skipped."""
        from gelb.gelb_ast.ASTNodes import (
            Pow_N as _Pow, Node_N as _Node, List_N as _List,
            IntrinsicFunctionCall_N as _Call,
            RectSelOfLatticeInDFs_N as _LIn,
            RectSelOfLatticeOutDFs_N as _LOut, RectSelOfArrayElems_N as _ASel,
        )
        selections = (_LIn, _LOut, _ASel)
        scalar_only = ('mod', 'atan2')
        width_casts = ('real32', 'real64', 'int8', 'int16', 'int32', 'int64')

        def children(n):
            if isinstance(n, _List):
                return list(n.elements)
            if isinstance(n, _Node):
                try:
                    return [getattr(n, nm) for nm in n.get_children_names()]
                except Exception:
                    return []
            return []

        def unrolled_exponent(n):
            while isinstance(n, TypePromotionNode_N):
                n = n.expr
            return isinstance(n, IntLiteral_N) and 0 <= n.value <= 8

        def found(n):
            if isinstance(n, selections):
                return False
            if isinstance(n, _Call) and (
                    n.function_name in scalar_only
                    or n.function_name in width_casts):
                return True
            if isinstance(n, _Pow) and not unrolled_exponent(n.right):
                return True
            return any(found(c) for c in children(n))

        stmts = getattr(getattr(block, 'stmts', None), 'elements', None) or []
        return any(found(stmt) for stmt in stmts)

    def _block_has_integer_arithmetic_on_x(self, block) -> bool:
        """Whether a value expression of ``block`` applies an integer
        operation (``+ - * / ^``, unary minus) to a subtree that
        mentions the spatial x, directly or through an int local
        assigned from such a subtree.  Lattice and array index
        expressions are not value expressions and are skipped."""
        from gelb.gelb_ast.ASTNodes import (
            Add_N as _Add, Sub_N as _Sub, Mul_N as _Mul, Div_N as _Div,
            Pow_N as _Pow, UnaryMinusExpr_N as _Neg, Node_N as _Node,
            List_N as _List, RectSelOfLatticeInDFs_N as _LIn,
            RectSelOfLatticeOutDFs_N as _LOut, RectSelOfArrayElems_N as _ASel,
            VariableDeclarationStmt_N as _Decl,
            VariableAssignmentStmt_N as _Assign,
        )
        int_kinds = ('int', 'int64', 'int32', 'int16', 'int8')
        ops = (_Add, _Sub, _Mul, _Div, _Pow, _Neg)
        selections = (_LIn, _LOut, _ASel)

        def children(n):
            if isinstance(n, _List):
                return list(n.elements)
            if isinstance(n, _Node):
                try:
                    return [getattr(n, nm) for nm in n.get_children_names()]
                except Exception:
                    return []
            return []

        def mentions(n, names):
            if isinstance(n, selections):
                return False
            if isinstance(n, Identifier_N):
                return n.name in names
            return any(mentions(c, names) for c in children(n))

        def int_op_on(n, names):
            if isinstance(n, selections):
                return False
            if isinstance(n, ops):
                dtype = getattr(getattr(n, 'inferred_type', None),
                                'element_dtype', None)
                if dtype in int_kinds and mentions(n, names):
                    return True
            return any(int_op_on(c, names) for c in children(n))

        tainted = {'x'}
        stmts = getattr(getattr(block, 'stmts', None), 'elements', None) or []
        for stmt in stmts:
            if int_op_on(stmt, tainted):
                return True
            rhs, name = None, None
            if isinstance(stmt, _Decl):
                rhs = stmt.initial_value
                name = getattr(stmt.name, 'name', None)
            elif isinstance(stmt, _Assign) and isinstance(stmt.lhs, Identifier_N):
                rhs, name = stmt.rhs, stmt.lhs.name
            if rhs is not None and name is not None and mentions(rhs, tainted):
                dtype = getattr(getattr(rhs, 'inferred_type', None),
                                'element_dtype', None)
                if dtype in int_kinds:
                    tainted.add(name)
        return False

    def _block_has_xref_bool_op(self, block) -> bool:
        """Walk ``block`` looking for an And_N / Or_N whose subtree
        references the spatial-x identifier (``x``).  Comparisons and
        boolean ops that touch ``x`` produce a Vec8db in SIMD mode,
        which combines incorrectly with neighbouring scalar booleans.
        Conservative: trigger on any And_N/Or_N that has ``x`` in its
        descendants.  False positives only cost SIMD opportunity, not
        correctness."""
        from gelb.gelb_ast.ASTNodes import (
            And_N as _And, Or_N as _Or, Node_N as _Node,
        )

        def _children(n):
            if not isinstance(n, _Node):
                return ()
            try:
                return n.get_children()
            except Exception:
                return ()

        def has_x(n):
            if not isinstance(n, _Node):
                return False
            if isinstance(n, Identifier_N) and n.name == 'x':
                return True
            for child in _children(n):
                if has_x(child):
                    return True
            return False

        def walk(n):
            if not isinstance(n, _Node):
                return False
            if isinstance(n, (_And, _Or)) and has_x(n):
                return True
            for child in _children(n):
                if walk(child):
                    return True
            return False

        return walk(block)

    def _expr_contains_spatial_x(self, node) -> bool:
        """True iff ``node`` references the spatial-x identifier
        (which becomes ``gelb_xv`` Vec8d in the SIMD inner body).
        Any expression containing it propagates as Vec8d through
        arithmetic -- needed to detect when a user's scalar-int
        local declaration has a Vec-typed RHS and must be retyped."""
        if isinstance(node, Identifier_N) and node.name == 'x':
            return True
        if isinstance(node, List_N):
            return any(self._expr_contains_spatial_x(e)
                       for e in node.elements)
        if isinstance(node, Node_N):
            for child_name in node.get_children_names():
                child = getattr(node, child_name, None)
                if child is not None and \
                        self._expr_contains_spatial_x(child):
                    return True
        return False

    def _rhs_simd_vec_kind(self, node):
        """Determine which Highway vector type a RHS expression would
        emit as in SIMD mode (``self._simd_mode == 'vec8d'``).

        Returns one of:
          * ``'vec8q'`` -- true int64-V (an Identifier referring to
            a registered ``vec8q`` local).  Genuine int-arithmetic
            on int-typed locals.
          * ``'vec8d'`` -- V (double).  Includes:
              - spatial-x arithmetic
              - inline ``bool->int`` casts (which cpu_highway lowers
                as ``hn::IfThenElse(mask, Set(d, 1.0), Set(d, 0.0))``
                via the int64 shortcut documented in the cast
                helper -- yields double-V despite the AST claiming
                int)
          * ``None`` -- scalar (no SIMD-vector promotion required).

        Used to decide whether a user's ``int local = expr;``
        declaration in a SIMD body needs to be retyped to V or
        ``hn::Vec<CappedTag<int64_t, 8>>``.
        """
        if self._simd_mode != 'vec8d' or node is None:
            return None
        # Genuine int64-V: an Identifier_N that already names a
        # registered vec8q local.  Inline ``bool->int`` casts are
        # NOT genuine int64-V under cpu_highway -- they go through
        # the double-V shortcut.
        from gelb.gelb_ast.ASTNodes import Identifier_N as _Id
        if (isinstance(node, _Id)
                and self._simd_int_locals.get(node.name) == 'vec8q'):
            return 'vec8q'
        # Inline ``bool->int`` cast (TypePromotionNode_N over a
        # comparison, anywhere in the subtree) -- the int64 shortcut
        # emits double-V.  ``_inner_yields_simd_int`` was the old
        # signal; under cpu_highway it now drives the 'vec8d' (not
        # 'vec8q') branch.
        if self._inner_yields_simd_int(node):
            return 'vec8d'
        if self._produces_simd_bool_mask(node):
            return 'vec8d'
        # Spatial-x in arithmetic => V propagates.
        if self._expr_contains_spatial_x(node):
            return 'vec8d'
        return None

    def _inner_yields_simd_int(self, node) -> bool:
        """Return True iff the inner expression evaluates to a Vec8q
        (int64 SIMD vector) in SIMD mode.  Used to gate the
        ``to_double(Vec8q)`` emit instead of ``static_cast<double>``.

        A node yields Vec8q when:
          * it is int-typed (per ``inferred_type``), AND
          * it contains a bool->Vec8q-producing subtree somewhere
            (a comparison/bool-op, which is lowered as
            ``select(mask, Vec8q(1), Vec8q(0))``).

        Without the second clause, plain scalar int loop counters
        (e.g. the outer ``g_y`` of a 2-D SIMD body) would also pass
        the int-typed check and erroneously trigger
        ``to_double(g_y)`` -- wrong for TGV-2D BGK init's
        ``y + 0.5`` formula.  In that case the expression has no
        comparison, so the result is a plain scalar int that
        ``static_cast<double>`` handles correctly (and the
        surrounding Vec8d arithmetic broadcasts the scalar via
        ``hn::Set(d, ...)``)."""
        # An identifier referring to a user-level int local that has
        # been retyped to ``Vec8q`` in this SIMD body -- its name is
        # registered in ``_simd_int_locals`` with kind ``'vec8q'``.
        if (isinstance(node, Identifier_N)
                and self._simd_int_locals.get(node.name) == 'vec8q'):
            return True
        inf = getattr(node, 'inferred_type', None)
        if inf is None:
            return False
        elem = (getattr(inf, 'element_dtype', None)
                or getattr(inf, 'name', None))
        if elem not in ('int', 'int8', 'int16', 'int32', 'int64'):
            return False
        return self._expr_contains_simd_bool_op(node)

    def _emit_simd_aware_cast(self, inner_str: str, inner_node,
                               cpp_target: str) -> str:
        """Emit a SIMD-correct cast of ``inner_str`` (the already-
        emitted C++ for ``inner_node``) to ``cpp_target``.

        In scalar mode this just returns ``static_cast<T>(inner)``.
        In SIMD mode (``self._simd_mode == 'vec8d'``) several special
        cases apply because plain ``static_cast<T>(simd_vector)`` is
        either ill-defined (Vec8db->T reinterprets mask bits as bytes)
        or absent (no implicit Vec8q->Vec8d).  Specifically:

          * ``inner_node`` is the spatial-x identifier (already
            ``gelb_xv``, Vec8d) AND target is double -> no cast.
          * ``inner_node`` is a comparison/bool-op (Vec8db) AND
            target is a numeric type -> ``select(mask, V(1), V(0))``
            with V chosen per target.
          * ``inner_node`` yields a Vec8q (int-typed AND contains a
            bool-op-Vec8q producer) AND target is double ->
            ``to_double(...)``.
          * Otherwise -> plain ``static_cast<T>(inner)``.

        Used by both ``TypePromotionNode_N`` and the ``real``/``int``
        type-cast intrinsics so the same fix applies to each.
        """
        if self._simd_mode != 'vec8d':
            return f'static_cast<{cpp_target}>({inner_str})'
        # Spatial-x is already Vec8d in SIMD mode.
        if (cpp_target == 'double'
                and isinstance(inner_node, Identifier_N)
                and inner_node.name == 'x'):
            return inner_str
        # An Identifier referring to a SIMD-retyped int local
        # (declared by the user as ``int`` but actually a
        # Highway vector due to Vec-typed RHS) needs the
        # corresponding cast for double-target promotion: a
        # ``V`` (double-vec) is already double; an int64-vec needs
        # ``hn::ConvertTo(d, ...)``.
        if (cpp_target == 'double'
                and isinstance(inner_node, Identifier_N)):
            simd_kind = self._simd_int_locals.get(inner_node.name)
            if simd_kind == 'vec8d':
                return inner_str
            if simd_kind == 'vec8q':
                return f'hn::ConvertTo(d, {inner_str})'
        # Bool mask -> numeric, lane-wise.  Highway's ``Mask<D>`` is
        # an opaque type separate from ``Vec<D>``; ``hn::IfThenElse``
        # selects between two same-type vectors based on the mask.
        if self._produces_simd_bool_mask(inner_node):
            if cpp_target == 'double':
                return (f'hn::IfThenElse({inner_str}, '
                        f'hn::Set(d, 1.0), hn::Set(d, 0.0))')
            if cpp_target == 'float':
                # ``CappedTag<float, 8>`` resolves at compile time
                # to up to 8 lanes per the host ISA's
                # ``MaxLanes<float>``.  NOTE: this descriptor's lane
                # count may differ from ``D``'s on AVX-2 / NEON
                # (``MaxLanes<float> = 4`` vs ``MaxLanes<double>``
                # = 2 on NEON, etc.), so the ``IfThenElse`` here
                # would mismatch the inner mask's width on those
                # ISAs.  Mixed-precision SIMD needs a per-target
                # rebroadcast here before this path is enabled broadly.
                return (f'hn::IfThenElse({inner_str}, '
                        f'hn::Set(hn::CappedTag<float, 8>{{}}, 1.0f), '
                        f'hn::Set(hn::CappedTag<float, 8>{{}}, 0.0f))')
            if cpp_target == 'int64_t':
                # bool->int64 cast in SIMD mode: emit a *double*-V
                # carrying 1.0/0.0 instead of an int64-V carrying
                # 1/0.  Rationale: every consumer of an int-typed
                # bool-cast in GeLB programs eventually promotes
                # back to double for arithmetic (e.g.
                # ``W[df] * (1 + (x < r))``), and the global
                # ``_broadcast_for_binop`` helper uses ``d`` (the
                # double descriptor) for any mixed scalar/V binop.
                # Going via int64-V would produce an
                # ``int64-V + double-V`` mismatch at the next
                # arithmetic level -- Highway has no implicit
                # cross-type promotion.  The 1.0/0.0 round-trip
                # through double<->int64 is bit-exact, so user
                # semantics are preserved.  Highway has no implicit
                # int-vector / double-vector cross-type promotion.
                return (f'hn::IfThenElse({inner_str}, '
                        f'hn::Set(d, 1.0), hn::Set(d, 0.0))')
        # int-vec -> double-vec via Highway's lane-wise int64->double
        # conversion.  ``_inner_yields_simd_int`` is True for two
        # disjoint cases:
        #   (a) Identifier_N referring to a registered ``vec8q``
        #       local -- those were handled in an earlier branch
        #       above (``simd_kind == 'vec8q' -> ConvertTo``).
        #   (b) An inline ``bool->int`` cast (TypePromotionNode_N
        #       over a comparison, anywhere in the subtree).  Per
        #       the int64_t branch's shortcut, those ALREADY emit
        #       as double-V (1.0/0.0) -- there's no real int64-V to
        #       convert from.  ``hn::ConvertTo(d, double-V)`` is
        #       undefined / errors; forward the inner string
        #       unchanged.  This collapses the redundant
        #       ``ConvertTo(d, IfThenElse(mask, Set(d, 1.0), Set(d,
        #       0.0)))`` shape that the cast pipeline would
        #       otherwise emit.
        if (cpp_target == 'double'
                and self._inner_yields_simd_int(inner_node)):
            return inner_str
        # Arithmetic on the spatial x (``100 + x``, ``1 * x``) is
        # already a double vector: x is ``gelb_xv`` and the constants
        # are broadcast with ``hn::Set(d, ...)``, while
        # ``static_cast<double>`` of a vector does not compile.
        if (cpp_target == 'double'
                and self._expr_contains_spatial_x(inner_node)):
            return inner_str
        return f'static_cast<{cpp_target}>({inner_str})'

    def _expr_contains_simd_bool_op(self, node) -> bool:
        """Recursively check whether ``node`` contains any
        comparison or boolean operator.  In SIMD mode such ops
        produce a ``Vec8db`` (mask) and propagate as a ``Vec8q``
        once cast to int via the ``select(...)`` lowering, which
        makes any enclosing arithmetic vector-typed."""
        from gelb.gelb_ast.ASTNodes import Node_N as _Node, List_N as _List
        if self._produces_simd_bool_mask(node):
            return True
        if isinstance(node, _List):
            return any(self._expr_contains_simd_bool_op(e)
                        for e in node.elements)
        if isinstance(node, _Node):
            for nm in node.get_children_names():
                child = getattr(node, nm)
                if isinstance(child, (_Node, _List)):
                    if self._expr_contains_simd_bool_op(child):
                        return True
        return False

    def _produces_simd_bool_mask(self, node) -> bool:
        """Whether this expression emits a Highway mask in the current body.

        A comparison of scalar operands stays scalar even inside a SIMD
        loop. Logical operators inherit the representation of their operands.
        """
        if self._simd_mode != 'vec8d':
            return False
        from gelb.gelb_ast.ASTNodes import (
            Less_N as _Less, LessEqual_N as _LE,
            Greater_N as _Gr, GreaterEqual_N as _GE,
            Equal_N as _Eq, NotEqual_N as _NE,
            And_N as _And, Or_N as _Or, NotExpr_N as _Not,
        )
        if isinstance(node, Identifier_N):
            return self._simd_int_locals.get(node.name) == 'mask'
        if isinstance(node, (_Less, _LE, _Gr, _GE, _Eq, _NE)):
            return (self._yields_simd_vector(node.left)
                    or self._yields_simd_vector(node.right))
        if isinstance(node, (_And, _Or)):
            return (self._produces_simd_bool_mask(node.left)
                    or self._produces_simd_bool_mask(node.right))
        if isinstance(node, _Not):
            return self._produces_simd_bool_mask(node.value)
        return False

    def _broadcast_simd_bool(self, node, emitted: str) -> str:
        """Broadcast a scalar bool when a SIMD mask is required."""
        if self._produces_simd_bool_mask(node):
            return emitted
        return f'hn::FirstN(d, ({emitted}) ? hn::Lanes(d) : 0)'

    def _block_has_bounce_back(self, node):
        if (isinstance(node, IntrinsicFunctionCall_N)
                and node.function_name == 'bounce_back_dfs'):
            return True
        return (isinstance(node, Node_N) and
                any(self._block_has_bounce_back(c) for c in node.get_children()))

    def _emit_block_simd(self, block, info, *,
                        context: str = 'dynamic') -> None:
        """Context-agnostic SIMD emit: head/body/tail x-axis split with
        outer-axis recursion.  ``context`` controls how
        ``_emit_block_body`` resolves lattice slot / output destination
        (``'dynamic'`` writes f_new, ``'initializer'`` writes f_old,
        ``'gauge'`` reads only and fills gauge buffers).

        Outer (non-x) axes get a 3-way split: head / body / tail.
        The innermost (x) axis ALWAYS gets head / SIMD-body / tail --
        independently of whether the outer axes are at their safe
        body sub-range or in a head/tail boundary row.  The outer
        axes' safety only affects which axes we mark as
        ``_wrap_safe_axes`` (so cross-axis reads can drop the
        modulo) -- it does NOT gate SIMD vectorisation along x.

        Outer (non-x) axes get a 3-way split: head / body / tail.
        The innermost (x) axis ALWAYS gets head / SIMD-body / tail --
        independently of whether the outer axes are at their safe
        body sub-range or in a head/tail boundary row.  The outer
        axes' safety only affects which axes we mark as
        ``_wrap_safe_axes`` (so cross-axis reads can drop the
        modulo) -- it does NOT gate SIMD vectorisation along x.

        Gating on the outer axes would emit the entire inner-x range
        of a y- or z-boundary row as a single scalar loop, leaving
        ~6 % of cells (TGV-3D N=64) running scalar despite a
        62-cell-wide SIMD-eligible interior."""
        dblock = block  # alias kept for readability in the body
        d = self._d
        sizes = self._grid_sizes()
        offsets = self._compute_stencil_offsets(dblock)
        woffs = self._compute_write_offsets(dblock)
        bbox = info.bbox
        # Per-axis head/tail peel counts.  The halo-update kernel
        # pre-stages the periodic wrap into one ghost cell per axis
        # end, so reads at +-1 cross the boundary unconditionally and a
        # block that reaches no further peels nothing: the SIMD body
        # extends over the whole bbox.  A block reaching k > 1 cells
        # along a periodic axis peels the k - 1 cells per side whose
        # reads would leave the halo; they run scalar, where
        # _coord_with_wrap wraps those reads with a modulo.  A write at
        # offset k (a push) peels the full k cells per side: a ghost
        # cell is never copied back, so the destination must be in the
        # interior; the peeled cells wrap their stores with a modulo.
        # Non-periodic axes never peel (their bboxes are restricted to
        # interior regions -- walls live in a separate NC), and the
        # clamp ternary in _coord_with_wrap handles boundary reads
        # (writes off a wall are rejected by the validators).
        head = [0] * d
        tail = [0] * d
        bounce = self._block_has_bounce_back(block)
        for axis in range(d):
            if not is_periodic(self._lattice_info, axis):
                if bounce and axis == 0:
                    # Guarded reads may occur at grid-edge cells. Keep
                    # those lanes scalar; the vector body has valid x
                    # neighbours, while y/z use uniform load guards.
                    span = bbox[axis][1] - bbox[axis][0] + 1
                    head[axis] = min(span, max(0, offsets[axis][0] - bbox[axis][0]))
                    tail[axis] = min(span - head[axis], max(
                        0, bbox[axis][1] + offsets[axis][1] - sizes[axis] + 1))
                continue
            head[axis] = max(0, offsets[axis][0] - 1, woffs[axis][0])
            tail[axis] = max(0, offsets[axis][1] - 1, woffs[axis][1])
            span = bbox[axis][1] - bbox[axis][0] + 1
            if head[axis] + tail[axis] > span:
                head[axis], tail[axis] = span, 0    # all of it scalar
        # 1-D: only the x-axis split.  No outer axes => no outer-safe
        # set to thread through.
        if d == 1:
            self._emit_x_split(dblock, info, head[0], tail[0],
                               outer_safe_axes=frozenset(),
                               context=context)
            return

        def _maybe_omp(lo, hi, is_outermost):
            # Only put #pragma omp parallel for on the outermost loop
            # of the nest -- nested pragmas with default settings cause
            # team-explosion overhead.
            if (is_outermost and self.use_openmp
                    and (hi - lo + 1) >= 2):
                self._emit('#pragma omp parallel for schedule(static)')

        def _emit_axis_split(axis_idx: int,
                             outer_safe_axes: frozenset):
            """Recursively emit the per-axis head/body/tail split.
            ``outer_safe_axes`` is the set of axis indices among
            (axis_idx+1, ..., d-1) currently in their safe body
            sub-range.  At axis_idx == 0 we delegate to
            ``_emit_x_split`` and pass the set through; the SIMD body
            always fires."""
            if axis_idx == 0:
                self._emit_x_split(dblock, info, head[0], tail[0],
                                   outer_safe_axes=outer_safe_axes,
                                   context=context)
                return
            bbox_lo, bbox_hi = bbox[axis_idx]
            safe_lo = bbox_lo + head[axis_idx]
            safe_hi = bbox_hi - tail[axis_idx]
            ax = self._axis(axis_idx)
            is_outermost = (axis_idx == d - 1)
            omp_request = is_outermost and self.use_openmp
            # Head (axis unsafe -- cross-row reads need modulo wrap).
            if safe_lo > bbox_lo:
                self._emit_axis_loop_open(
                    ax, bbox_lo, safe_lo - 1,
                    label=f"{ax} = head ({ax}-axis unsafe; "
                          f"cross-{ax} reads use modulo wrap)",
                    omp=omp_request and (safe_lo - bbox_lo) >= 2)
                _emit_axis_split(axis_idx - 1, outer_safe_axes)
                self._emit_axis_loop_close()
            # Body (axis safe -- drop modulo wrap on this axis).
            if safe_hi >= safe_lo:
                self._emit_axis_loop_open(
                    ax, safe_lo, safe_hi,
                    label=f"{ax} = interior ({ax}-axis safe; "
                          f"cross-{ax} reads skip modulo)",
                    omp=omp_request and (safe_hi - safe_lo + 1) >= 2)
                _emit_axis_split(axis_idx - 1,
                                 outer_safe_axes | {axis_idx})
                self._emit_axis_loop_close()
            # Tail (axis unsafe).
            if safe_hi < bbox_hi:
                self._emit_axis_loop_open(
                    ax, safe_hi + 1, bbox_hi,
                    label=f"{ax} = tail ({ax}-axis unsafe; "
                          f"cross-{ax} reads use modulo wrap)",
                    omp=omp_request and (bbox_hi - safe_hi) >= 2)
                _emit_axis_split(axis_idx - 1, outer_safe_axes)
                self._emit_axis_loop_close()

        _emit_axis_split(d - 1, frozenset())

    def _emit_x_split(self, dblock, info, x_head, x_tail, *,
                      outer_safe_axes: frozenset,
                      context: str = 'dynamic'):
        """Emit the x-axis split: scalar-with-wrap head, SIMD-eligible
        interior (Vec8d body + scalar tail), scalar-with-wrap tail.

        ``outer_safe_axes`` is the set of outer-axis indices in their
        safe body sub-range (so cross-row reads on those axes can drop
        the modulo).  The x-axis's SIMD body fires unconditionally
        regardless of outer-axis safety -- the y/z wrap modulos are
        applied at the per-direction read level via
        ``_wrap_safe_axes``."""
        bbox_x_lo, bbox_x_hi = info.bbox[0]
        x_safe_lo = bbox_x_lo + x_head
        x_safe_hi = bbox_x_hi - x_tail
        vw = self._simd_vw
        outer_safe_set = set(outer_safe_axes)
        # scalar head (with wrap on x; outer-axis safety unchanged).
        if x_safe_lo > bbox_x_lo:
            self._emit_axis_loop_open(
                'x', bbox_x_lo, x_safe_lo - 1,
                label="x = scalar head (x-axis unsafe; "
                      "x reads use modulo wrap)")
            old = self._wrap_safe_axes
            self._wrap_safe_axes = outer_safe_set
            self._emit_block_body(dblock, context=context)
            self._wrap_safe_axes = old
            self._emit_axis_loop_close()
        # interior (x in its safe range): SIMD body + scalar remainder.
        interior_safe_set = outer_safe_set | {0}
        if x_safe_hi >= x_safe_lo:
            if self._any_aos_lattice():
                # AoS: Vec8d.load(&storage[buf][y][x][df]) would load 8
                # DFs of one cell, not 8 cells of one DF -- wrong
                # semantics.  Fall back to a single scalar x-loop for
                # correctness.
                self._emit('// x = scalar interior (AoS storage; '
                           'across-cell SIMD disabled, x-axis safe)')
                self._emit(f'for (int64_t g_x = {x_safe_lo}; '
                           f'g_x <= {x_safe_hi}; ++g_x) {{')
                self._indent += 1
                old_axes = self._wrap_safe_axes
                self._wrap_safe_axes = interior_safe_set
                self._emit_block_body(dblock, context=context)
                self._wrap_safe_axes = old_axes
                self._indent -= 1
                self._emit('}')
            elif self._any_cbt_lattice():
                # CBT: tile-aligned SIMD body.  Iterate tile_id over
                # all tiles overlapping the x_safe range, with
                # ``g_x = tile_id * TILE - 1`` so storage_x = g_x + 1
                # is a multiple of TILE and lattice loads/stores use
                # ``Vec8d.load_a`` / ``store_a``.  Cross-tile stencil
                # reads (DF with EX[i] = +/-1) emit a valignq pattern
                # via _emit_upstream_dfs.
                #
                # Cells outside the x_safe range that fall within the
                # iterated tiles get processed by the SIMD body too.
                # We split this into two cases by *what's outside the
                # range*:
                #   (a) **halo / padding cells** -- i.e. the straddle
                #       lands at user_x < 0 (left halo) or
                #       user_x >= N (right halo + post-grid padding).
                #       The wide SIMD store is fine: halo is
                #       overwritten by the halo-update kernel each
                #       step, and padding is allocated-but-never-read.
                #   (b) **real interior cells of OTHER node classes**
                #       -- i.e. the straddle lands at
                #       0 <= user_x < N but outside this rect's bbox.
                #       Two sub-cases:
                #         (b1) the cell belongs to *another NC* whose
                #              dispatch will overwrite it later in
                #              the same timestep -- fine.
                #         (b2) the cell belongs to a *masked NC*
                #              (SOLID, etc.) -- there is no
                #              overwriting dispatch.  The wide SIMD
                #              store leaves spurious values in
                #              masked-cell storage, which then feeds
                #              the next timestep's neighbour reads
                #              and propagates wrong-answer errors.
                # We can't tell (b1) from (b2) from per-rect bbox
                # alone (would need full NC-map knowledge here), but
                # both sub-cases are handled correctly by peeling the
                # straddler tiles to per-lane scalar stores covering
                # only the in-bbox lanes -- that respects every NC's
                # exclusive ownership of its own cells.
                #
                # Gauge context is special: the gauge buffer has no
                # halo or padding, so *any* straddle (including what
                # would be "halo" for the lattice) would corrupt
                # adjacent rows.  Gauge therefore always peels both
                # ends, regardless of bbox endpoint.
                #
                # Bit-equivalence regression tests cover 2D and 3D
                # obstacle cases.
                n_x = self._grid_sizes()[0]
                first_tile = (x_safe_lo + 1) // _CBT_TILE
                last_tile = (x_safe_hi + 1) // _CBT_TILE
                # A tile T is "fully in safe range" iff
                #   T*TILE - 1 >= x_safe_lo  AND
                #   T*TILE + (TILE - 2) <= x_safe_hi
                first_full_tile = (x_safe_lo + _CBT_TILE) // _CBT_TILE
                last_full_tile = ((x_safe_hi - (_CBT_TILE - 2))
                                  // _CBT_TILE)
                # Per-side peel decisions.  Gauge always peels (no
                # halo/padding to soak the overshoot).  Init/dyn
                # peel only when the straddle lands in real interior
                # cells (i.e. bbox doesn't reach the corresponding
                # grid edge).
                guarded_reads = self._block_has_bounce_back(dblock)
                # Guarded neighbour loads describe real grid cells only.
                # Do not execute them for halo/padding lanes: a shifted
                # whole-tile load could otherwise reach past storage.
                head_peel = (first_tile < first_full_tile and
                             (context == 'gauge' or guarded_reads or x_safe_lo > 0))
                tail_peel = (last_tile > last_full_tile and
                             (context == 'gauge' or guarded_reads
                              or x_safe_hi < n_x - 1))
                body_first_tile = (first_full_tile if head_peel
                                   else first_tile)
                body_last_tile = (last_full_tile if tail_peel
                                  else last_tile)
                peel_partial = head_peel or tail_peel

                if peel_partial and body_last_tile < body_first_tile:
                    # No full tiles fit between the peels -- emit a
                    # single scalar loop covering the whole safe
                    # range.  Triggers when the NC bbox is narrower
                    # than 2*TILE - 1 cells AND both sides need to
                    # peel (e.g. a wall column one tile wide
                    # straddling a tile boundary).
                    label_suffix = ('gauge-buffer overrun guard'
                                    if context == 'gauge'
                                    else 'masked-cell spillover guard')
                    self._emit_axis_loop_open(
                        'x', x_safe_lo, x_safe_hi,
                        label=f'x = scalar (CBT, no full tiles in '
                              f'safe range; {label_suffix})')
                    old = self._wrap_safe_axes
                    self._wrap_safe_axes = interior_safe_set
                    self._emit_block_body(dblock, context=context)
                    self._wrap_safe_axes = old
                    self._emit_axis_loop_close()
                else:
                    body_lo = body_first_tile * _CBT_TILE - 1
                    body_hi = (((body_last_tile + 1) * _CBT_TILE - 2)
                               if tail_peel else x_safe_hi)
                    label_suffix = ('gauge-buffer overrun guard'
                                    if context == 'gauge'
                                    else 'masked-cell spillover guard')
                    # Scalar peel: partial first tile.
                    if head_peel and x_safe_lo <= body_lo - 1:
                        self._emit_axis_loop_open(
                            'x', x_safe_lo, body_lo - 1,
                            label=f'x = scalar peel (CBT partial '
                                  f'first tile; {label_suffix})')
                        old = self._wrap_safe_axes
                        self._wrap_safe_axes = interior_safe_set
                        self._emit_block_body(dblock, context=context)
                        self._wrap_safe_axes = old
                        self._emit_axis_loop_close()
                    # SIMD body.  When peeling either side, iterate
                    # only fully-in-bbox tiles; otherwise iterate
                    # every tile overlapping x_safe (the dyn / init
                    # contexts rely on this to write halo/padding
                    # cells, which are then overwritten by halo
                    # update or are unread allocated padding).
                    self._emit('// x = SIMD body: tile-aligned CBT iteration')
                    self._emit('{')
                    self._indent += 1
                    if peel_partial:
                        body_comment = ('; partial-tile peels '
                                        'emitted separately to '
                                        f'avoid {label_suffix}')
                    else:
                        body_comment = (
                            '; cells outside the safe range get '
                            'overwritten by halo update or land in '
                            'allocated padding storage.')
                    self._emit(f'// tiles {body_first_tile}..'
                               f'{body_last_tile} cover x_safe = '
                               f'[{x_safe_lo}, {x_safe_hi}]'
                               + body_comment)
                    self._emit(f'for (int g_x_tile = {body_first_tile}; '
                               f'g_x_tile <= {body_last_tile}; '
                               f'++g_x_tile) {{')
                    self._indent += 1
                    self._emit(f'int64_t g_x = g_x_tile * {_CBT_TILE} - 1;')
                    # This CBT branch is kept separate from the plain
                    # SoA path because it needs Highway cross-tile
                    # ``hn::CombineShiftRightLanes`` shuffles.
                    #
                    # NOTE (NEON): this block hardcodes the tile-wide
                    # ``Vec`` ops to ``Lanes(d) == _CBT_TILE``
                    # -- both ``hn::Iota(d, g_x)`` covering the whole
                    # tile and the cross-tile ``TwoTablesLookupLanes``
                    # below uses 8-element indices.  On NEON
                    # (Lanes=2) the indices are oversized and the
                    # blend silently produces wrong results -- a TILE=2
                    # native-NEON layout is the planned replacement.
                    # Until then the auto-layout
                    # selector gates CBT on AVX-512 (see
                    # ``_auto_layout_choice``), gelbc rejects
                    # ``--storage-layout cbt`` without AVX-512, and
                    # every CBT program static_asserts eight lanes.
                    self._emit(f'V gelb_xv = hn::Iota(d, '
                               f'static_cast<double>(g_x));')
                    old_mode, old_axes = (self._simd_mode,
                                          self._wrap_safe_axes)
                    self._simd_mode = 'vec8d'
                    self._wrap_safe_axes = interior_safe_set
                    self._emit_block_body(dblock, context=context)
                    self._simd_mode = old_mode
                    self._wrap_safe_axes = old_axes
                    self._indent -= 1
                    self._emit('}')
                    self._indent -= 1
                    self._emit('}')
                    # Scalar peel: partial last tile.
                    if tail_peel and body_hi + 1 <= x_safe_hi:
                        self._emit_axis_loop_open(
                            'x', body_hi + 1, x_safe_hi,
                            label=f'x = scalar peel (CBT partial '
                                  f'last tile; {label_suffix})')
                        old = self._wrap_safe_axes
                        self._wrap_safe_axes = interior_safe_set
                        self._emit_block_body(dblock, context=context)
                        self._wrap_safe_axes = old
                        self._emit_axis_loop_close()
            else:
                # SoA: full SIMD body + scalar remainder.
                # Wrap in an extra scope so the bare ``int g_x`` decl
                # doesn't collide with subsequent dynamic-block emits at
                # the same nesting level (1-D programs with multiple
                # per-NC dyn loops produce two SIMD x-splits one after
                # the other in the same enclosing block).
                interior_cells = x_safe_hi - x_safe_lo + 1
                # Codegen-time eligibility / remainder decisions use
                # the x86 AVX-512 lane count (``self._simd_vw == 8``)
                # because that is the AVX-512 build target used to tune
                # this code path.
                # The emitted source uses ``hn::Lanes(d)`` (constexpr
                # in Highway) for the actual per-iteration stride --
                # so the SAME .cpp recompiled with -march for AVX-2
                # (4 lanes) or NEON (2 lanes) produces a correct
                # loop with a different stride.  A non-zero codegen-
                # time remainder is conservatively over-emitted: on
                # narrower ISAs the SIMD loop covers more iterations
                # so the remainder runs over fewer cells (or zero),
                # which is still correct.
                needs_remainder = interior_cells % vw != 0
                self._emit('// x = SIMD body' +
                           (' + scalar remainder' if needs_remainder
                            else '') +
                           ' (x-axis safe; modulo elided)')
                self._emit('{')
                self._indent += 1
                self._emit(f'int64_t g_x = {x_safe_lo};')
                # ``d.MaxLanes()`` is the constexpr lane count;
                # ``hn::Lanes(d)`` is runtime-only on some Highway
                # builds and would force the loop bound off the
                # constexpr path.
                self._emit('constexpr int VW = '
                           'static_cast<int>(d.MaxLanes());')
                self._emit('// SIMD body: V x VW cells/iter '
                           f'(VW = {vw} on AVX-512)')
                self._emit(f'for (; g_x + VW <= {x_safe_hi + 1}; '
                           f'g_x += VW) {{')
                self._indent += 1
                # Per-lane x coordinate.  Each V lane needs to see
                # x = g_x + lane_idx so any arithmetic involving the
                # spatial-x identifier (e.g. r = R_INNER + 1.0 * x)
                # gets the correct per-cell value.  ``hn::Iota(d,
                # start)`` produces lanes [start, start+1, ...,
                # start+VW-1] of the descriptor's element type
                # (double).  Lattice indexing still uses the scalar
                # g_x (it computes the address of the first lane,
                # then ``hn::LoadU`` slurps VW contiguous cells).
                self._emit(f'V gelb_xv = hn::Iota(d, '
                           f'static_cast<double>(g_x));')
                old_mode, old_axes = (self._simd_mode,
                                      self._wrap_safe_axes)
                self._simd_mode = 'vec8d'
                self._wrap_safe_axes = interior_safe_set
                self._emit_block_body(dblock, context=context)
                self._simd_mode = old_mode
                self._wrap_safe_axes = old_axes
                self._indent -= 1
                self._emit('}')
                # Scalar remainder of the SIMD body -- only emit when
                # the SIMD-eligible range isn't an exact multiple of
                # the vector width.  When ``(x_safe_hi - x_safe_lo + 1)
                # % vw == 0`` the SIMD body covers every cell exactly
                # and the remainder loop would run zero iterations;
                # eliding the emit keeps the generated source compact.
                if needs_remainder:
                    self._emit('// scalar remainder of SIMD body '
                               '(x-axis still safe)')
                    self._emit(f'for (; g_x <= {x_safe_hi}; ++g_x) {{')
                    self._indent += 1
                    old_axes = self._wrap_safe_axes
                    self._wrap_safe_axes = interior_safe_set
                    self._emit_block_body(dblock, context=context)
                    self._wrap_safe_axes = old_axes
                    self._indent -= 1
                    self._emit('}')
                # Close the extra scope wrapper opened above.
                self._indent -= 1
                self._emit('}')
        # scalar tail (x wraps).
        if x_safe_hi < bbox_x_hi:
            self._emit_axis_loop_open(
                'x', x_safe_hi + 1, bbox_x_hi,
                label="x = scalar tail (x-axis unsafe; "
                      "x reads use modulo wrap)")
            old = self._wrap_safe_axes
            self._wrap_safe_axes = outer_safe_set
            self._emit_block_body(dblock, context=context)
            self._wrap_safe_axes = old
            self._emit_axis_loop_close()

    def _emit_simd_lattice_load(self, lname: str, coord_strs: list,
                                df_idx_str: str,
                                x_offset: int | None) -> str:
        """Emit a SIMD lattice-input read for one DF at ``coord_strs``.

        Branches on storage layout:
        - **CBT cross-tile** path (``x_offset != 0`` AND lattice is CBT
          AND axis 0 is periodic / wrap-safe): emit
          ``hn::TwoTablesLookupLanes`` over two consecutive tile loads
          for the same df.  This is the same pattern
          ``_emit_upstream_dfs`` uses; mirroring it here closes the
          long-standing bug where explicit ``f.in[x +/- k, ...]`` reads
          in boundary kernels (Zou-He, MRT walls, reduced-gravity,
          etc.) silently spilled across df boundaries under CBT.
        - **Fallthrough** (SoA, scalar mode, or x-aligned reads): emit
          the previous ``hn::LoadU`` form (or the bare lvalue in scalar
          mode).  In SoA, ``LoadU`` with stride-1 contiguity along x is
          the natural CBT-free pattern.

        ``x_offset`` is the parsed integer offset of the x-coord
        relative to ``g_x``.  Pass ``None`` (or 0) when the offset
        cannot be determined as a literal -- the LoadU fallthrough
        is the correct emit in that case.
        """
        cbt_xshift = (
            self._simd_mode == 'vec8d'
            and self._use_cbt.get(lname, False)
            and x_offset is not None
            and x_offset != 0
            and (0 in self._wrap_safe_axes
                 or is_periodic(self._lattice_info, 0)))
        if not cbt_xshift:
            coord_idx = self._storage_subscript(
                coord_strs, df_idx_str=df_idx_str, lattice_name=lname)
            addr = f'{_lname(lname)}_storage[{_lname(lname)}_old]{coord_idx}'
            if self._simd_mode == 'vec8d':
                return f'hn::LoadU(d, &{addr})'
            return addr

        # CBT cross-tile sliding-window read.  ``g_x_tile`` is in scope
        # in every CBT iteration body (boundary and bulk).  Two
        # aligned ``hn::Load``s of (tile_lo, tile_hi) for the same df,
        # then a single ``hn::TwoTablesLookupLanes`` permute by
        # ``imm = x_offset mod 8`` (Python modulo gives a non-negative
        # result; for ``x_offset`` in {-1, +1} this is {7, 1}).
        #
        # Sign convention (CRITICAL): ``x_offset`` is the *source's*
        # x position relative to ``g_x``.  For ``f.in[x - 1, y, df]``
        # source = ``x - 1``, so ``x_offset == -1``; for
        # ``f.in[x + 1, y, df]`` source = ``x + 1``, so
        # ``x_offset == +1``.  ``_emit_upstream_dfs`` uses an
        # *inverse* convention -- its ``off_x`` is the velocity
        # component ``EX[i]``, so source = ``c_expr - off_x``.  The
        # formulas below are therefore mirrored relative to that
        # path:
        #   off_x > 0 (bulk: source at c_expr - off_x) <-> x_offset < 0
        #
        # Earlier versions of this helper accidentally used the bulk
        # path's velocity-component formulas verbatim, which silently
        # works on x-translation-invariant problems (couette,
        # poiseuille -- uniform in x) but produces wrong results on
        # x-varying ones (Shan-Chen, Sukop's taylor_dispersion solute
        # strip, Sukop's pressure-Zou-He inlet/outlet).
        imm_const = x_offset % _CBT_TILE
        if x_offset < 0:
            tile_lo_expr = '(g_x_tile - 1)'
            tile_hi_expr = 'g_x_tile'
        else:  # x_offset > 0
            tile_lo_expr = 'g_x_tile'
            tile_hi_expr = '(g_x_tile + 1)'
        non_x_spatial = ''.join(
            f'[({c}) + 1]' for c in reversed(coord_strs[1:]))
        addr_lo = (f'{_lname(lname)}_storage[{_lname(lname)}_old]'
                   f'{non_x_spatial}[{tile_lo_expr}][{df_idx_str}][0]')
        addr_hi = (f'{_lname(lname)}_storage[{_lname(lname)}_old]'
                   f'{non_x_spatial}[{tile_hi_expr}][{df_idx_str}][0]')
        blend_indices = tuple(imm_const + k for k in range(_CBT_TILE))
        idx_arr_name = self._register_constexpr_array(
            'gelb_cbt_idx', 'int64_t', blend_indices)
        return (f'hn::TwoTablesLookupLanes(d, '
                f'hn::Load(d, &{addr_lo}), '
                f'hn::Load(d, &{addr_hi}), '
                f'hn::SetTableIndices(d, {idx_arr_name}))')

    def _yields_simd_vector(self, node) -> bool:
        """Return True iff ``node`` evaluates to a Highway ``V`` (vector
        of doubles) under the current ``_simd_mode == 'vec8d'`` context.

        Used by the binary-op emit code to decide where to wrap a
        scalar operand in ``hn::Set(d, ...)`` so Highway's operator
        overloads (which require both sides to be the same V) resolve.
        Highway has no implicit scalar->V conversion, so any binop
        that mixes a V and a scalar must broadcast the scalar
        explicitly -- this predicate drives that decision.

        Conservative for unrecognised node types (returns False) -- the
        worst that can happen is an unnecessary ``hn::Set`` wrap, which
        is harmless when the receiving op is itself scalar.
        """
        if self._simd_mode != 'vec8d' or node is None:
            return False
        if isinstance(node, Identifier_N):
            if node.name == 'x':
                # Innermost-axis spatial coord becomes ``gelb_xv`` (V).
                return True
            return self._simd_int_locals.get(node.name) in ('vec8d', 'vec8q')
        if isinstance(node, (RealLiteral_N, IntLiteral_N, BoolLiteral_N)):
            return False
        if isinstance(node, RectSelOfLatticeInDFs_N):
            # Lattice DF read in SIMD mode lowers to ``hn::LoadU(d, ...)``.
            return True
        if isinstance(node, RectSelOfArrayElems_N):
            # Local arrays may have been retyped to V[] (init yields V);
            # global constant arrays are always scalar (double[]).
            arr_name = (node.array_name.name
                        if hasattr(node.array_name, 'name')
                        else str(node.array_name))
            return self._simd_int_locals.get(arr_name) == 'vec8d'
        if isinstance(node, (Add_N, Sub_N, Mul_N, Div_N)):
            return (self._yields_simd_vector(node.left)
                    or self._yields_simd_vector(node.right))
        if isinstance(node, Pow_N):
            return self._yields_simd_vector(node.left)
        if isinstance(node, UnaryMinusExpr_N):
            return self._yields_simd_vector(node.value)
        if isinstance(node, TypePromotionNode_N):
            # When a TypePromotionNode_N wraps a comparison / bool-op
            # in SIMD mode, ``_emit_simd_aware_cast`` lowers it as
            # ``hn::IfThenElse(mask, V(1), V(0))`` (or the int64-vec
            # / float-vec equivalent), all of which produce a vector.
            # Without this branch the predicate would say "scalar"
            # for the cast and incorrectly broadcast the cast result
            # at the next binop up.
            if self._produces_simd_bool_mask(node.expr):
                return True
            return self._yields_simd_vector(node.expr)
        if isinstance(node, BroadcastNode_N):
            return self._yields_simd_vector(node.scalar_expr)
        if isinstance(node, IntrinsicFunctionCall_N):
            fname = node.function_name
            # Math intrinsics: V iff at least one arg is V.
            if fname in ('sin', 'cos', 'tan', 'tanh', 'sqrt',
                         'exp', 'log', 'abs',
                         'min', 'max', 'atan2', 'mod'):
                return any(self._yields_simd_vector(a)
                           for a in node.arguments)
            # Lattice-driven intrinsics produce V in SIMD mode.
            # ``random()`` in SIMD mode lowers to
            # ``gelb::gelb_random_vec()`` which returns V (8 lanes
            # of independent uniform-[0,1) doubles); the scalar
            # mode lowers to ``gelb::gelb_random()`` (a single
            # double).  Since this predicate is only consulted in
            # SIMD mode, ``random`` always yields V here.
            if fname in ('upstream_dfs', 'bounce_back_dfs',
                         'sum', 'dot_prod', 'matmul', 'random'):
                return True
            if fname in ('real', 'int'):
                # ``real(comparison)`` / ``int(comparison)`` lower
                # to ``hn::IfThenElse(mask, V(1), V(0))`` (or the
                # int64-shortcut double-V variant) via
                # ``_emit_simd_aware_cast``.  Either form yields V.
                if self._produces_simd_bool_mask(node.arguments[0]):
                    return True
                return self._yields_simd_vector(node.arguments[0])
            return False
        # Comparisons / boolean ops yield ``hn::Mask<D>`` rather than V.
        # The cast helper turns them into V via ``hn::IfThenElse``, but
        # at the AST layer they're not V themselves.
        return False

    def _unrolled_element_yields_simd_vector(self, rhs, i: int) -> bool:
        """True iff the ``i``-th element of an unrolled-slice RHS yields
        a Highway V in SIMD mode.  Used by the array-init / whole-
        array-assign paths which substitute ``df_var = str(i)`` into
        ``rhs`` and then need to decide whether to wrap the resulting
        scalar in ``hn::Set(d, ...)``.

        For an ``Array1DLiteral_N`` RHS, each element has its own AST
        node -- the i-th literal element drives the V-ness independently
        (e.g. ``meq = {rho, -2*rho + 3*rho*usq, ...}`` has element 0 =
        V (Identifier rho), element 1 = V (Mul of V and scalars), etc.,
        but element 0 alone wouldn't tell us about element 7).  For
        non-literal RHSs (constexpr-array refs that resolve per-i,
        local-array refs, broadcast arithmetic), the whole-RHS
        predicate already gives the right answer because every
        substituted element shares the same broad type.
        """
        if isinstance(rhs, Array1DLiteral_N):
            try:
                elem = rhs.value.elements[i]
            except (IndexError, AttributeError):
                return False
            return self._yields_simd_vector(elem)
        return self._yields_simd_vector(rhs)

    def _broadcast_for_binop(self, left, right, df_var):
        """Emit (left_str, right_str) with cpu_highway scalar-broadcast
        wrapping applied to the binop arguments.  When exactly one
        operand yields a V, the other is wrapped in ``hn::Set(d, ...)``
        so Highway operator overloads resolve.  When both yield V (or
        both yield scalar), no wrapping is needed.  In scalar mode the
        wrap is bypassed entirely.

        ``df_var`` is forwarded to the V-ness predicate so that
        ``Array1DLiteral_N`` operands resolved per-element via a
        literal-digit substitution (``df_var = '2'`` -> returns
        ``elements[2]``) get an element-specific V-ness check.
        Without this, RHSs like ``moments + {0, 0, scalar*V_local,
        ...}`` mistakenly broadcast the V-yielding element 2 in
        ``hn::Set(d, V)``.
        """
        a = self._emit_expression(left, df_var)
        b = self._emit_expression(right, df_var)
        if self._simd_mode != 'vec8d':
            return a, b
        a_vec = self._yields_simd_vector_at_df(left, df_var)
        b_vec = self._yields_simd_vector_at_df(right, df_var)
        if a_vec and not b_vec:
            b = f'hn::Set(d, {b})'
        elif b_vec and not a_vec:
            a = f'hn::Set(d, {a})'
        return a, b

    def _yields_simd_vector_at_df(self, node, df_var):
        """``_yields_simd_vector`` with df_var-aware Array1DLiteral
        peeking.  When ``node`` is an Array1DLiteral_N and
        ``df_var`` is a literal-digit string, inspect the resolved
        element directly -- that's the value the surrounding
        ``_emit_expression(node, df_var)`` actually returns.  For
        any other shape, fall back to the AST-only predicate.
        """
        if (isinstance(node, Array1DLiteral_N)
                and df_var is not None
                and df_var.lstrip('-').isdigit()):
            try:
                elem = node.value.elements[int(df_var)]
            except (IndexError, AttributeError):
                return False
            return self._yields_simd_vector(elem)
        return self._yields_simd_vector(node)
