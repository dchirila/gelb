"""Statement and block-body emission for cpu_highway.

The statement dispatcher, lattice read/write emission (including the
streaming ``upstream_dfs``/``bounce_back_dfs`` machinery and matmul
lowering), and the literal-folding helpers used during emission.
"""

from __future__ import annotations

from gelb.backends.highway.addressing import LatticeAddress, AxisOffset, ConstCoord, ExprCoord, spatial_subscript

from gelb.backends.real_literals import cpp_real
from gelb.backends.highway.expr import ConstantOperand
from gelb.midware.ast_simplify import is_pure, numeric_kind

import math

from gelb.backends.highway.common import (
    _lname,
    _TYPE_MAP,
    _CBT_TILE,
    _uname,
    int64_typed_literal,
)

from gelb.gelb_ast.ASTNodes import (
    Add_N,
    Array1DLiteral_N,
    AssignmentStmt_N,
    GaugeBlock_N,
    Identifier_N,
    IntLiteral_N,
    IntrinsicFunctionCall_N,
    List_N,
    Node_N,
    Range_N,
    RectSelOfArrayElems_N,
    RectSelOfLatticeInDFs_N,
    RectSelOfLatticeOutDFs_N,
    Sub_N,
    TypePromotionNode_N,
    VariableDeclarationStmt_N,
)

from gelb.midware.StencilExtractionVisitor import affine_index
from gelb.midware.ast_eval import (
    add as ev_add, mul as ev_mul, sub as ev_sub,
    convert_plain,
    is_periodic,
)


def _is_array_typed(node) -> bool:
    """Whether the computational type has at least one array dimension."""
    return bool(node.canonical_type is not None and node.canonical_type.is_array)


class StatementEmitMixin:
    """Mixin: see module docstring.  Assembled into
    ``HighwayCodeGenerator`` (stage3_backend_cpu_highway).
    """

    def _emit_block_body(self, block, *, context: str) -> None:
        # The block's locals are scoped to one body emit: the same
        # block is re-emitted for the SIMD body and for any scalar
        # peel/remainder, with a fresh set of decls each time, and a
        # name declared in another block (an array of another length,
        # or a scalar of the same name) must not be visible here.
        # Save/restore so a parent caller's sets (if any) are preserved.
        prev_simd_int_locals = self._simd_int_locals
        prev_block = self._current_block
        self._simd_int_locals = {}
        self._current_block = block
        try:
            self._emit_block_body_inner(block, context=context)
        finally:
            self._simd_int_locals = prev_simd_int_locals
            self._current_block = prev_block

    def _emit_block_body_inner(self, block, *, context: str) -> None:
        # Emit declarations for gauge outputs explicitly so
        # they're available for assignment inside the loop body.  In
        # SIMD mode, decl as ``V`` (per-output 8-lane register
        # initialised via ``hn::Zero(d)`` since Highway's ``V`` is
        # opaque and has no scalar-broadcast constructor); in scalar
        # mode, decl as the source-level type.
        if isinstance(block, GaugeBlock_N):
            for decl in block.outputs:
                if isinstance(decl, VariableDeclarationStmt_N):
                    if self._simd_mode == 'vec8d':
                        # Register the gauge output as V-typed so
                        # downstream ``_yields_simd_vector`` returns
                        # True for references to it.  Without this,
                        # ``rho`` in ``ux = ... / rho;`` would be
                        # treated as scalar and incorrectly broadcast
                        # via ``hn::Set(d, V)``.
                        self._simd_int_locals[decl.name.name] = 'vec8d'
                        self._emit(f'V {_uname(decl.name.name)} = '
                                   f'hn::Zero(d);')
                    else:
                        self._emit(f'{self._decl_cpp_type(decl)} '
                                   f'{_uname(decl.name.name)} = 0;')
        for stmt in block.stmts:
            self._emit_statement(stmt, context)
        # Per-iter gauge buffer fill -- emit at the end of the body so
        # both SIMD and scalar dispatch paths handle it uniformly.
        if isinstance(block, GaugeBlock_N):
            self._emit_gauge_buffer_fill(block)

    def _df_range(self, sel) -> tuple[int, int]:
        """Return (df_lo, df_hi) for a RectSelOfLatticeDFs.  Both
        endpoints are inclusive ints -- the midware has resolved
        ``:`` to the full ``0..q-1`` range by this point."""
        df = sel.element_ranges[-1]
        if isinstance(df, IntLiteral_N):
            return df.value, df.value
        if isinstance(df, Range_N):
            lo = self._range_int(df.low)
            hi = self._range_int(df.high)
            return lo, hi
        raise NotImplementedError(
            f"cpu_highway: unsupported DF range type: {type(df).__name__}")

    @staticmethod
    def _single_df_literal(df_node):
        """The index of a single-DF access with a literal index (``| k``,
        also spelled ``k:k``), else None."""
        if isinstance(df_node, IntLiteral_N):
            return df_node.value
        if (isinstance(df_node, Range_N)
                and isinstance(df_node.low, IntLiteral_N)
                and isinstance(df_node.high, IntLiteral_N)
                and df_node.low.value == df_node.high.value
                and not getattr(df_node, 'is_full_df_range', False)):
            return df_node.low.value
        return None

    @staticmethod
    def _slice_low(df_node) -> int:
        """The lower bound of a multi-DF slice with literal bounds; 0 for
        a single index, a full range or anything unresolved."""
        if (isinstance(df_node, Range_N)
                and isinstance(df_node.low, IntLiteral_N)
                and isinstance(df_node.high, IntLiteral_N)
                and df_node.low.value < df_node.high.value):
            return df_node.low.value
        return 0

    @staticmethod
    def _range_int(node) -> int:
        if isinstance(node, IntLiteral_N):
            return node.value
        raise NotImplementedError(
            f"cpu_highway: DF range bound must be a resolved int literal "
            f"(got {type(node).__name__}).")

    def _emit_intrinsic_into_array(self, name: str, n: int,
                                   call: IntrinsicFunctionCall_N) -> None:
        """Emit per-element initialisation of a local array from an
        intrinsic function call."""
        fname = call.function_name
        if fname == 'upstream_dfs':
            self._emit_upstream_dfs(name, n, call)
            return
        if fname == 'matmul':
            self._emit_matmul_into_array(name, n, call)
            return
        # Any other call (``sqrt(_gelb_draw_0)``, an element-wise
        # intrinsic of an array-valued argument) is an array-valued
        # expression and takes the per-element loop of the caller.
        raise NotImplementedError(
            f"cpu_highway: array initialisation from intrinsic "
            f"'{fname}' is emitted element-wise by the caller.")

    def _expr_contains_array_literal(self, expr) -> bool:
        """True iff the AST sub-tree rooted at ``expr`` contains any
        Array1DLiteral_N node.  The whole-array assign emit uses this
        to decide between a slice loop (no literals) and per-element
        unrolling (literals present)."""
        from gelb.gelb_ast.ASTNodes import Node_N
        if not isinstance(expr, Node_N):
            return False
        if isinstance(expr, Array1DLiteral_N):
            return True
        for c in expr.get_children():
            if self._expr_contains_array_literal(c):
                return True
        return False

    def _expr_should_unroll_slice(self, expr) -> bool:
        """True iff the slice loop for ``expr`` should be fully
        unrolled (one statement per df) rather than emitted as a
        for-loop.

        Triggers:
          - Array1DLiteral_N anywhere in the RHS (the per-element
            values aren't a single ``rhs[df_var]`` formula).
          - Identifier_N reference to a foldable constexpr array.
            With unrolling, those references resolve to literal
            values, which lets the compiler eliminate
            zero-coefficient terms gcc otherwise keeps per IEEE-754.
          - Identifier_N reference to a local array (registered in
            the active block's symbol table).  These appear in slice-LHS
            collisions like ``f.out[x,y,z|:] = fIn - tau_inv * (fIn -
            feq)`` where ``fIn`` and ``feq`` are temp arrays
            populated by an upstream_dfs read or an inlined
            equilibrium computation.  Unrolling lets the compiler
            keep each ``fIn[i]`` / ``feq[i]`` in a register instead
            of materialising 19-entry stack arrays per cell.
            Measured on TGV-3D BGK at N=128 1T: ~+10%
            (33.0 -> 36.5 MLUPS).

        The first two triggers are the perf-critical case for LBM
        equilibria -- ``eu[df] = EX[df]*ux + EY[df]*uy`` and the feq
        formula contain many zero-coefficient terms after constant
        folding.  The third is what makes BGK / MRT collisions
        themselves unroll, after the user-function inlining pass
        has rewritten ``Eq(...)`` into a local feq array.
        """
        from gelb.gelb_ast.ASTNodes import Node_N
        if not isinstance(expr, Node_N):
            return False
        if (isinstance(expr, IntrinsicFunctionCall_N)
                and expr.function_name == 'bounce_back_dfs'):
            return True
        if isinstance(expr, Array1DLiteral_N):
            return True
        if isinstance(expr, Identifier_N):
            if self._constant_vector(expr.name) is not None \
                    and self._constant_values(expr.name) is not None:
                return True
            if self._local_array_type(expr.name) is not None:
                return True
        for c in expr.get_children():
            if self._expr_should_unroll_slice(c):
                return True
        return False

    # Peephole folds for the literal tokens that constexpr-array
    # substitution exposes (``EX[3]`` -> ``-1.0``).  They apply only the
    # identities that hold bit for bit, as the midware's exact pass
    # does (``gelb.midware.ast_simplify``; a fold alters no value).  In real
    # arithmetic a zero has a sign: ``u * 0.0`` is -0 for u = -1,
    # ``u + 0.0`` is +0 for u = -0 and ``0.0 - u`` is +0 for u = +0, so
    # only ``x + (-0)``, ``x - (+0)`` and ``(-0) - x`` fold; ``integer``
    # (the operation's kind) allows every zero identity.  Two literals
    # fold in binary64 arithmetic, or as in-range int64 arithmetic inside
    # a singleton-axis scope.

    # A negative literal is emitted bare (``EX[3]`` -> ``-1.0``, a
    # negative ``-D`` value), so a minus put in front of it would read
    # ``--0.05``: a decrement to C++ and CUDA.

    @staticmethod
    def _negate(s: str, integer: bool = False) -> str:
        value = getattr(s, 'constant', None)
        if not integer and type(value) is float and math.copysign(1.0, value) < 0:
            return ConstantOperand(cpp_real(-value), -value)
        text = f'(-({s}))' if s.startswith('-') else f'(-{s})'
        # Normalize int64 negation, except the minimum whose negation overflows.
        # Parenthesized real and narrow-integer negations remain runtime operands.
        if type(value) is int and getattr(s, 'int64', False) and value > -(1 << 63):
            return ConstantOperand(int64_typed_literal(-value), -value, int64=True)
        return text

    def _constant_binop(self, expr, a, b, kind):
        """Apply width-aware identities without interpreting C++ source text."""
        va, vb = getattr(a, 'constant', None), getattr(b, 'constant', None)
        integer = (kind is not None and kind.startswith('int')) or (
            kind is None and type(va) is int and type(vb) is int)
        op = '+' if isinstance(expr, Add_N) else '-' if isinstance(expr, Sub_N) else '*'
        written = f'({a} {op} {b})'
        if kind == 'real32' or any(numeric_kind(getattr(node, 'inferred_type', None)) == 'real32'
                                   for node in (expr.left, expr.right)):
            return written

        if (kind == 'int64' and self._axis_bindings
                and type(va) is int and type(vb) is int
                and getattr(a, 'int64', False) and getattr(b, 'int64', False)):
            value = {'+': lambda: va + vb, '-': lambda: va - vb,
                     '*': lambda: va * vb}[op]()
            if -(1 << 63) <= value < (1 << 63):
                return ConstantOperand(int64_typed_literal(value), value, int64=True)
            return written

        def zero(value, negative):
            if integer:
                return type(value) is int and value == 0
            return (type(value) is float and value == 0.0
                    and (math.copysign(1.0, value) < 0) == negative)

        if op == '+':
            if zero(va, True):
                return b
            if zero(vb, True):
                return a
        elif op == '-':
            if zero(vb, False):
                return a
            if zero(va, True):
                return self._negate(b, integer)
        else:
            if integer and (zero(va, False) or zero(vb, False)) and is_pure(expr):
                return ConstantOperand('0LL' if kind == 'int64' else '0', 0, int64=kind == 'int64')
            required = int if integer else float
            if type(va) is required and va == 1:
                return b
            if type(vb) is required and vb == 1:
                return a
            if type(va) is required and va == -1:
                return self._negate(b, integer)
            if type(vb) is required and vb == -1:
                return self._negate(a, integer)
        if not integer and type(va) is float and type(vb) is float:
            try:
                value = {'+': ev_add, '-': ev_sub, '*': ev_mul}[op](va, vb)
                if math.isfinite(value):
                    return ConstantOperand(cpp_real(value), value)
            except (OverflowError, ValueError, ZeroDivisionError):
                pass
        return written

    @staticmethod
    def _operand_for_coeff(coef, runtime_expr: str):
        """Decide how to render an operand whose coefficient ``coef``
        we know at codegen time:
          - None -> runtime; return None (caller falls back to the
                   raw multiplicative form).
          - +/-1 -> return ('+', None) / ('-', None) sentinel -- caller
                 emits the raw operand without a multiplicative term.
          - 0 -> ('+', '0.0'): the term is kept, so an Inf or NaN in
                 the runtime operand propagates (every term counts).
          - other -> return ('+', '<lit> * <runtime>') as a flat
                    multiplicative form.
        Output: tuple ``(sign, multiplicative_part_or_None)`` -- the
        caller composes this with the other operand's tuple."""
        if coef is None:
            return None
        if coef == 1.0:
            return ('+', None)
        if coef == -1.0:
            return ('-', None)
        return (('+' if coef >= 0 else '-'), str(abs(coef)))

    def _merge_signed_product(self, lhs_op, rhs_op, raw_a, raw_b):
        """Merge two operand descriptions (from ``_operand_for_coeff``)
        into a single ``(sign, body)`` term where ``body`` is the C++
        expression to add (or subtract) to the running sum."""
        # Either lhs_op or rhs_op (or both) is non-None.
        sa, ma = lhs_op if lhs_op is not None else ('+', None)
        sb, mb = rhs_op if rhs_op is not None else ('+', None)
        # XOR of signs.
        sign = '-' if (sa == '-') != (sb == '-') else '+'
        if lhs_op is None:
            # b is constexpr; emit ``[lit *] raw_a``
            body = raw_a if mb is None else f'{mb} * {raw_a}'
        elif rhs_op is None:
            body = raw_b if ma is None else f'{ma} * {raw_b}'
        else:
            # Both constexpr -- fold further.
            if ma is None and mb is None:
                # Pure +/-1 * +/-1 -- no operand at all.  This can't happen
                # in dot_prod (the operand IS the term); guard anyway.
                body = '1.0'
            elif ma is None:
                body = mb
            elif mb is None:
                body = ma
            else:
                body = f'{ma} * {mb}'
        return (sign, body)

    def _join_signed_terms(self, terms):
        """Compose a list of ``(sign, body)`` tuples into a single
        ``a + b - c + d`` expression, leading sign suppressed.  A
        leading negative term is negated: in the SIMD body with
        ``hn::Neg`` (Highway's vector type has no unary minus), which
        like ``-x`` keeps the sign of a zero (``0 - x`` would give +0
        for x = +0; user manual, Numerical semantics: Special
        values)."""
        if not terms:
            return '0.0'
        out = []
        for i, (sign, body) in enumerate(terms):
            if i == 0:
                if sign == '+':
                    out.append(body)
                elif self._simd_mode == 'vec8d':
                    out.append(f'hn::Neg({body})')
                else:
                    out.append(f'-{body}')
            else:
                out.append(f' {sign} {body}')
        return ''.join(out)

    def _emit_matmul_into_array(self, name: str, n: int,
                                call: IntrinsicFunctionCall_N) -> None:
        """Emit per-element initialisation of ``out[0..n-1]`` from
        ``out = matmul(M, v)`` where M is a 2-D array constant of
        shape (n, k) and v is a 1-D local/constant of size k.

        We unroll across both axes so the emitted code is
        ``out[i] = M[i][0]*v[0] + M[i][1]*v[1] + ... ;`` for each i.
        At the assembly level this is the same as a loop the compiler
        would unroll anyway, but emitting it unrolled means the slice
        outer loop's optimiser sees concrete adds and folds zero-rows
        of sparse stencils (D2Q9 M is sparse)."""
        if len(call.arguments) != 2:
            raise NotImplementedError(
                f"matmul: 2 arguments expected, got {len(call.arguments)}.")
        Marg, varg = call.arguments
        if not isinstance(Marg, Identifier_N) or \
                not isinstance(varg, Identifier_N):
            raise NotImplementedError(
                "matmul: both arguments must be bare identifiers.")
        matrix = self.backend_context.global_constants.get(Marg.name)
        if matrix is None or len(matrix.dims) != 2:
            raise NotImplementedError(
                f"matmul: first argument {Marg.name} must be a 2-D "
                f"array constant.")
        nrows, ncols = matrix.dims
        if nrows != n:
            raise NotImplementedError(
                f"matmul: M has {nrows} rows but output array "
                f"{name} declared with {n} elements.")
        # Resolve v's length.
        v_len = self._array_size(varg.name)
        if v_len != ncols:
            raise NotImplementedError(
                f"matmul: M has {ncols} cols but vector {varg.name} "
                f"has {v_len} elements.")
        Mg = _uname(Marg.name)
        vg = _uname(varg.name)
        # Per-row coefficient pruning + multi-accumulator helper call,
        # mirroring the dot_prod path: when M's row has all-+/-1 nonzero
        # coefficients with at least one positive AND one negative,
        # emit ``gelb::gelb_signed_sum``; for general numeric
        # coefficients emit ``gelb::gelb_dot_prod_const``.  Both
        # helpers are 4-accumulator templates (the standard parallel-
        # reduction pattern that breaks a serial dependency chain into
        # k independent streams) so each row's reduction parallelises
        # across the FP unit instead of forming a single 19-deep
        # ``vfmadd`` chain.  The constexpr index/coefficient arrays are
        # registered in ``_deferred_constexpr_decls`` and hoisted to
        # the top of ``main()`` (de-duped by content), so the
        # generated source is one helper-call per row regardless of
        # how many dispatch sites the matmul appears in.
        simd = (self._simd_mode == 'vec8d')
        call_dtype = call.canonical_type.dtype
        acc_cpp = _TYPE_MAP[call_dtype]
        m_cpp = _TYPE_MAP[Marg.canonical_type.dtype]
        v_cpp = _TYPE_MAP[varg.canonical_type.dtype]

        def vector_entry(j):
            value = f'{vg}[{j}]'
            return (value if simd or v_cpp == acc_cpp
                    else f'static_cast<{acc_cpp}>({value})')

        def narrow_row(value):
            return (f'static_cast<{acc_cpp}>({value})'
                    if not simd and acc_cpp in ('int8_t', 'int16_t') else value)

        M_vals = matrix.matrix
        if M_vals is None:
            # Fold-failure fallback: keep the original ``M[i][j]*v[j]``
            # ``+``-chain.  This still relies on gcc to const-propagate
            # through ``g_M[i][j]``, which it does for
            # ``static constexpr`` 2-D arrays.
            for i in range(n):
                terms = []
                for j in range(ncols):
                    entry = f'{Mg}[{i}][{j}]'
                    if simd:
                        entry = f'hn::Set(d, {entry})'
                    elif m_cpp != acc_cpp:
                        entry = f'static_cast<{acc_cpp}>({entry})'
                    terms.append(f'{entry} * {vector_entry(j)}')
                self._emit(f'{name}[{i}] = {narrow_row(" + ".join(terms))};')
            return
        # Matmul row dispatch -- DELIBERATELY keeps the inline ``+``
        # chain here, NOT the multi-acc helpers.
        #
        # Why: in MRT examples the codegen emits 2 matmuls per cell
        # (forward M = 9 rows, inverse M_INV = 9 rows), each with
        # a 9-deep dot-product per row.  Routing those 18 calls
        # per cell through ``gelb_dot_prod_const`` costs ~5pp on
        # TGV-2D MRT N=512 in a paired interleaved bench.
        # The helpers also (correctly) cause TGV-3D BGK and RB-2D
        # BGK to *gain* 4-5pp -- those routes are kept on multi-acc
        # via ``_emit_intrinsic_call`` for ``sum`` / ``dot_prod``.
        #
        # The matmul-specific loss is unexplained at the
        # codegen level (assembly insn-counts and code-size look
        # comparable).  Leaving the matmul dispatch on the inline
        # ``+`` chain keeps MRT inside the +/-5 % bar without giving
        # up the BGK / multi-lattice wins.
        for i in range(n):
            row = M_vals[i]
            survived = [(c, j) for j, c in enumerate(row) if c != 0]
            if not survived:
                if simd:
                    self._emit(f'{name}[{i}] = hn::Zero(d);')
                else:
                    zero = {'double': '0.0', 'float': '0.0f', 'int64_t': '0LL'}.get(
                        acc_cpp, f'static_cast<{acc_cpp}>(0)')
                    self._emit(f'{name}[{i}] = {zero};')
                continue
            pos_idx = [j for c, j in survived
                       if c > 0 and abs(c) == 1.0]
            neg_idx = [j for c, j in survived
                       if c < 0 and abs(c) == 1.0]
            all_unit = (len(pos_idx) + len(neg_idx)
                        == len(survived))
            if all_unit and pos_idx and neg_idx:
                pos_terms = ' + '.join(vector_entry(j) for j in pos_idx)
                neg_terms = ' + '.join(vector_entry(j) for j in neg_idx)
                row_text = narrow_row(f'(({pos_terms}) - ({neg_terms}))')
                self._emit(f'{name}[{i}] = {row_text};')
            else:
                # General case (non-+/-1 coefficients OR all-positive
                # +/-1 OR all-negative +/-1): inline coeff*v products
                # (with scalar-broadcast in SIMD mode).  An integer
                # matrix's entries are spelled exactly.
                if simd:
                    terms = ' + '.join(
                        f'hn::Set(d, {self._matrix_entry_text(c)}) * {vg}[{j}]'
                        for c, j in survived)
                else:
                    terms = ' + '.join(
                        f'{self._matrix_entry_text(c, call_dtype)} * {vector_entry(j)}'
                        for c, j in survived)
                row_text = narrow_row(f'({terms})')
                self._emit(f'{name}[{i}] = {row_text};')

    @staticmethod
    def _matrix_entry_text(c, dtype=None) -> str:
        """Spell a coefficient in the product width, with one conversion."""
        if dtype is None:  # Preserve the established double SIMD spelling.
            return (int64_typed_literal(c) if isinstance(c, int)
                    else cpp_real(float(c)))
        cpp_type = _TYPE_MAP[dtype]
        if cpp_type in ('double', 'float'):
            return cpp_real(convert_plain(c, dtype), cpp_type)
        if cpp_type == 'int64_t':
            return int64_typed_literal(int(c))
        return f'static_cast<{cpp_type}>({int(c)})'

    def _emit_upstream_dfs(self, name: str, n: int,
                           call: IntrinsicFunctionCall_N) -> None:
        """Emit per-direction reads for `array[real, q] var = upstream_dfs(...)`.

        Signatures (resolved at codegen time):
            1-D: upstream_dfs(f, x, EX)
            2-D: upstream_dfs(f, x, y, {EX, EY})  -- last arg is a 2-elem List_N

        EX/EY must be array constants whose values are known at codegen
        time so we can fold per-direction offsets to literals.
        """
        args = call.arguments
        d = self._d
        # Expected arg shapes:
        #   1-D: f, x, EX
        #   2-D: f, x, y, {EX, EY}
        #   3-D: f, x, y, z, {EX, EY, EZ}
        expected_args = d + 2
        if len(args) != expected_args:
            raise NotImplementedError(
                f"upstream_dfs ({d}-D) expects {expected_args} args; "
                f"got {len(args)}.")
        lat_id = args[0]
        coord_nodes = list(args[1:1 + d])
        if d == 1:
            ex_nodes = [args[2]]
        else:
            ev_node = args[1 + d]
            elems = (ev_node.elements
                     if isinstance(ev_node, List_N)
                     else getattr(ev_node, 'value', None))
            if elems is None or len(elems) != d:
                raise NotImplementedError(
                    f"upstream_dfs ({d}-D): velocity-set argument must "
                    f"be a {d}-element list, e.g. "
                    f"{'{EX, EY, EZ}' if d == 3 else '{EX, EY}'}.")
            ex_nodes = list(elems)
        if not isinstance(lat_id, Identifier_N):
            raise NotImplementedError(
                "upstream_dfs's lattice argument must be a bare identifier.")
        for ex_node in ex_nodes:
            if not isinstance(ex_node, Identifier_N):
                raise NotImplementedError(
                    "upstream_dfs's velocity-set entries must be bare "
                    "identifiers referring to array constants "
                    "(e.g. EX, EY).")
        ev_values_list = []
        for ex_node in ex_nodes:
            vals = self._constant_values(ex_node.name)
            if vals is None or len(vals) != n:
                raise NotImplementedError(
                    f"upstream_dfs needs {ex_node.name} declared as a "
                    f"{n}-element array constant.")
            ev_values_list.append(vals)
        lname = lat_id.name
        sizes = self._grid_sizes()
        for i in range(n):
            # Fold each axis offset for direction i to an integer literal.
            offsets = []
            for vals, ex_node in zip(ev_values_list, ex_nodes):
                try:
                    offsets.append(int(vals[i]))
                except Exception:
                    raise NotImplementedError(
                        f"upstream_dfs: could not fold "
                        f"{ex_node.name}[{i}] to a constant integer.")
            src_coords = [self._coordinate(c, axis, -off, subtract=True)
                          for axis, (c, off) in enumerate(zip(coord_nodes, offsets))]
            # SIMD-CBT: stencil reads at x +/- 1 cross tile boundaries.
            # Emit valignq of (prev_tile, curr_tile) or (curr_tile,
            # next_tile) instead of a single load.  Same-tile reads
            # (off_x == 0) use ``Vec8d.load_a`` directly.
            if (self._simd_mode == 'vec8d'
                    and self._use_cbt.get(lname, False)):
                # offsets[0] is the x-offset (positive = read from x-off
                # i.e. EX[i] > 0 -> off > 0 -> src_x = curr_x - off -> tile
                # below).  src_coords[0] already has the offset baked
                # in; we need to know off_x for the valignq decision.
                off_x = offsets[0]
                # Build CBT address for the source cell of lane 0.
                # When off_x == 0, src_coords[0] equals coord_exprs[0],
                # which is g_x.  storage_x = g_x + 1 = tile-aligned.
                # When off_x = +1, source storage_x = g_x.
                # When off_x = -1, source storage_x = g_x + 2.
                # In ALL cases, the source range [src_x..src_x+7] crosses
                # at most one tile boundary; we load both tiles and
                # valignq with imm = (src_storage_x % TILE).
                # But we don't know g_x_tile / etc. at codegen time --
                # we compute (g_x + 1 - off) / TILE and % TILE in C++.
                if off_x == 0:
                    # Aligned same-tile load.  CBT storage is
                    # 64-byte aligned at every tile-row start, so
                    # ``hn::Load`` (aligned variant) is safe here
                    # and gives the compiler a stronger alignment
                    # hint than ``hn::LoadU``.
                    coord_idx_cbt = self._storage_subscript(
                        src_coords, df_idx_str=str(i), lattice_name=lname,
                        aligned_tile_start=True)
                    addr = (f'{_lname(lname)}_storage[{_lname(lname)}_old]'
                            f'{coord_idx_cbt}')
                    self._emit(f'{name}[{i}] = '
                               f'hn::Load(d, &{addr});')
                else:
                    # Cross-tile lane shift.  Under tile-aligned iteration
                    # (``g_x = g_x_tile * TILE - 1``):
                    #   src_storage_x = (g_x + 1) - off_x = g_x_tile*TILE - off_x
                    #   src_tile_lo   = floor(src_storage_x / TILE)
                    #                 = g_x_tile - 1 (off_x > 0)
                    #                   or g_x_tile (off_x < 0)
                    #   src_tile_hi   = src_tile_lo + 1
                    #   imm           = src_storage_x % TILE = (-off_x) mod TILE
                    # ``imm`` is a compile-time constant per direction.
                    imm_const = (-off_x) % _CBT_TILE
                    if off_x > 0:
                        tile_lo_expr = '(g_x_tile - 1)'
                        tile_hi_expr = 'g_x_tile'
                    else:  # off_x < 0
                        tile_lo_expr = 'g_x_tile'
                        tile_hi_expr = '(g_x_tile + 1)'
                    non_x_spatial = spatial_subscript(src_coords[1:])
                    addr_lo = (f'{_lname(lname)}_storage[{_lname(lname)}_old]'
                               f'{non_x_spatial}[{tile_lo_expr}][{i}][0]')
                    addr_hi = (f'{_lname(lname)}_storage[{_lname(lname)}_old]'
                               f'{non_x_spatial}[{tile_hi_expr}][{i}][0]')
                    # Concat-shift across two tiles by ``imm`` lanes.
                    #
                    # Highway's natural-looking
                    # ``hn::CombineShiftRightLanes<kAmt>`` is
                    # restricted to per-128-bit-block shifts
                    # (``kAmt < N / kFactor`` = {0, 1} on
                    # Vec512<double>), so it can't span the full
                    # vector at TILE=8.
                    #
                    # Substitute: ``hn::TwoTablesLookupLanes
                    # (d, lo, hi, idx)`` with
                    # ``idx = {imm, imm+1, ..., imm+N-1}``.  A
                    # single permute on AVX-512 (lowers to
                    # ``vpermt2pd``, ~3-cycle latency, 1/cycle
                    # throughput).  An earlier fallback
                    # used ``hn::Or(hn::SlideDownLanes,
                    # hn::SlideUpLanes)`` which lowered to 2x
                    # ``valignq``-via-zero + 1x ``vpord`` =
                    # 3 instructions and showed +5 perm
                    # instructions/body at TGV-2D BGK N=512.
                    # Verified bit-equivalent to the SlideUp/
                    # Down/Or fallback by ``/tmp/ttll_test.cpp``
                    # at imm in {1, 4, 7}.
                    #
                    # Index arrays are ``int64_t`` (matches the
                    # descriptor's lane width on Vec512<double>)
                    # and hoisted via ``_register_constexpr_array``
                    # so multiple cross-tile reads at the same
                    # imm share one ``static constexpr`` decl.
                    blend_indices = tuple(imm_const + k
                                          for k in range(_CBT_TILE))
                    idx_arr_name = self._register_constexpr_array(
                        'gelb_cbt_idx', 'int64_t', blend_indices)
                    self._emit(
                        f'{{ V _t_lo = hn::Load(d, &{addr_lo}); '
                        f'V _t_hi = hn::Load(d, &{addr_hi}); '
                        f'{name}[{i}] = hn::TwoTablesLookupLanes('
                        f'd, _t_lo, _t_hi, '
                        f'hn::SetTableIndices(d, {idx_arr_name})); }}')
                continue

            coord_idx = self._storage_subscript(
                src_coords, df_idx_str=str(i), lattice_name=lname)
            addr = f'{_lname(lname)}_storage[{_lname(lname)}_old]{coord_idx}'
            if self._simd_mode == 'vec8d':
                # Stencil reads at x +/- 1 are not 64-byte aligned in
                # general -- use ``hn::LoadU`` (unaligned).  Highway
                # docs Sec. "Loads/Stores" note ``LoadU`` lowers to a
                # zero-cost aligned load when the runtime address
                # happens to be aligned, so this is safe everywhere.
                self._emit(f'{name}[{i}] = hn::LoadU(d, &{addr});')
            else:
                self._emit(f'{name}[{i}] = {addr};')

    def _emit_statement(self, stmt, context: str) -> None:
        """Emit C++ for one block statement.

        Pure dispatch on the statement kind -- the per-kind emission
        lives in the ``_emit_*_stmt`` helpers below.
        """
        if isinstance(stmt, AssignmentStmt_N):
            self._emit_assignment_stmt(stmt, context)
        elif isinstance(stmt, VariableDeclarationStmt_N):
            self._emit_variable_decl_stmt(stmt, context)
        else:
            raise NotImplementedError(
                f"cpu_highway: unsupported statement: {type(stmt).__name__}")

    def _emit_assignment_stmt(self, stmt: AssignmentStmt_N,
                              context: str) -> None:
        """Assignment statement: dispatch on the LHS shape."""
        lhs = stmt.lhs
        if isinstance(lhs, RectSelOfLatticeOutDFs_N):
            self._emit_lattice_slice_assignment(stmt, lhs, context)
        elif isinstance(lhs, Identifier_N):
            self._emit_identifier_assignment(stmt, lhs, context)
        else:
            raise NotImplementedError(
                f"cpu_highway: unsupported LHS in assignment: "
                f"{type(lhs).__name__}")

    def _emit_lattice_slice_assignment(
            self, stmt: AssignmentStmt_N,
            lhs: RectSelOfLatticeOutDFs_N, context: str) -> None:
        """``f.out[... | dfs] = expr`` -- single-DF store or
        DF-slice loop, scalar or SIMD.  A selection the type pass made
        an array takes the loop, also when it holds one DF (``| :`` on a
        q = 1 lattice is ``array[real, 1]``)."""
        df_lo, df_hi = self._df_range(lhs)
        if df_lo == df_hi and not _is_array_typed(lhs):
            lhs_addr = self._emit_lattice_out_lhs(lhs, context)
            rhs_expr = self._emit_expression(
                stmt.rhs, df_var=(str(df_lo) if
                    self._block_has_bounce_back(stmt.rhs) else None))
            if self._simd_mode == 'vec8d':
                # Dispatch the store call on the active
                # layout's alignment / NT decision --
                # ``StoreU`` for SoA, ``Store`` (aligned)
                # for CBT-no-NT, ``Stream`` (NT) for
                # CBT+NT.  See ``_emit_simd_store``.
                # Scalar RHS broadcast (Highway has no
                # implicit double->V conversion).
                if not self._yields_simd_vector(stmt.rhs):
                    rhs_expr = f'hn::Set(d, {rhs_expr})'
                self._emit(f'{{ V gelb_v = {rhs_expr}; '
                           f'{self._emit_simd_store("gelb_v", lhs_addr)}; }}')
            else:
                self._emit(f'{lhs_addr} = {rhs_expr};')
        else:
            # Slice-DF assignment: emit a `for (int df = lo; df <= hi)` loop
            # and substitute the DF index with the loop variable inside
            # both LHS and RHS expressions.
            # Mirror the Identifier_N case below: when the RHS
            # references a foldable array constant (e.g. EX,
            # EY, EZ, W in BGK ``f.out[x,y,z|:] = f.in - 1/tau
            # * (f.in - Eq(...))``), unroll the slice loop
            # into one statement per direction.  Per-direction
            # substitution constant-folds the EX[i]/EY[i]
            # references to literals, eliminating dead zero-
            # coefficient terms gcc otherwise keeps per
            # IEEE-754, and lets the compiler keep the
            # per-direction f.in / feq values in registers
            # instead of materialising 19-entry stack arrays.
            # Measured win on TGV-3D BGK at N=128 1T: ~+10%
            # (33.0 -> 36.5 MLUPS).  Patterns without foldable
            # constants keep the rolled emit, where the extra
            # code size would otherwise regress perf.
            #
            # The Q >= 16 gate restricts unrolling to large
            # stencils (D3Q19, D3Q27, D2Q21, ...) where the
            # register-keeping benefit dominates the
            # I-cache cost of the larger emitted body.
            # On D2Q9 (Q=9) the same change measured
            # **-7 %** on TGV-2D N=1024 because gcc was
            # already hoisting 9-direction temp arrays into
            # registers, and unrolling just bloats the
            # multi-NC peeled emit's code footprint.
            # (Measured 2026-04-30 with hidden-halo storage:
            # lowering to Q=9 regresses single-NC
            # programs, e.g. TGV-2D BGK N=128 16T 1198 ->
            # 1105 (-7.8 %), N=128 1T 397 -> 360 (-9.3 %),
            # though LDC-2D is unchanged.  The I-cache
            # cost dominates on simple kernels even after
            # peel collapse.  Keep at Q>=16.)
            n_slice = df_hi - df_lo + 1
            should_unroll = (
                self._block_has_bounce_back(stmt.rhs) or
                (n_slice >= 16
                 and self._expr_should_unroll_slice(stmt.rhs)))
            if should_unroll:
                for df in range(0, n_slice):
                    lhs_addr = self._emit_lattice_out_lhs(
                        lhs, context, df_var=str(df))
                    rhs_expr = self._emit_expression(
                        stmt.rhs, df_var=str(df))
                    if self._simd_mode == 'vec8d':
                        # Same scalar-broadcast guard +
                        # layout-aware store dispatch as the
                        # single-DF site above.
                        if not self._yields_simd_vector(
                                stmt.rhs):
                            rhs_expr = f'hn::Set(d, {rhs_expr})'
                        self._emit(f'{{ V gelb_v = '
                                   f'{rhs_expr}; '
                                   f'{self._emit_simd_store("gelb_v", lhs_addr)}; }}')
                    else:
                        self._emit(f'{lhs_addr} = '
                                   f'{rhs_expr};')
            else:
                self._emit(f'for (int gelb_df = 0; '
                           f'gelb_df <= {n_slice - 1}; ++gelb_df) {{')
                self._indent += 1
                lhs_addr = self._emit_lattice_out_lhs(
                    lhs, context, df_var='gelb_df')
                rhs_expr = self._emit_expression(stmt.rhs,
                                                 df_var='gelb_df')
                if self._simd_mode == 'vec8d':
                    if not self._yields_simd_vector(stmt.rhs):
                        rhs_expr = f'hn::Set(d, {rhs_expr})'
                    self._emit(f'V gelb_v = {rhs_expr};')
                    self._emit(
                        f'{self._emit_simd_store("gelb_v", lhs_addr)};')
                else:
                    self._emit(f'{lhs_addr} = {rhs_expr};')
                self._indent -= 1
                self._emit('}')

    def _emit_identifier_assignment(
            self, stmt: AssignmentStmt_N,
            lhs: Identifier_N, context: str) -> None:
        """``name = expr`` -- scalar local or whole-array
        assignment (Fortran-style element-wise semantics)."""
        lname = _uname(lhs.name)
        # Whole-array assignment: rebroadcast the RHS over a
        # per-element loop, like Fortran's array-assignment
        # semantics.  Detect array-typed LHS via the local-array
        # registry.
        if self._local_array_type(lhs.name) is not None:
            n = self._array_size(lhs.name)
            # If the RHS *contains* an Array1DLiteral_N
            # anywhere -- either as the whole RHS (``meq =
            # {a, b, c, ...}``) or embedded in an arithmetic
            # expression (``moments = moments + {0, 0, 0,
            # 0.5*G, ...}``) -- unroll element-wise.  Each
            # iteration substitutes a literal int index into
            # the RHS, which lets _emit_expression for
            # Array1DLiteral_N pick the corresponding element
            # directly (see the digit-df_var short-circuit
            # there).
            lhs_is_vec = (
                self._simd_mode == 'vec8d'
                and self._simd_int_locals.get(lhs.name)
                    == 'vec8d')
            if self._expr_should_unroll_slice(stmt.rhs):
                for i in range(n):
                    elem_str = self._emit_expression(
                        stmt.rhs, df_var=str(i))
                    if lhs_is_vec and not \
                            self._unrolled_element_yields_simd_vector(
                                stmt.rhs, i):
                        elem_str = f'hn::Set(d, {elem_str})'
                    self._emit(f'{lname}[{i}] = {elem_str};')
            else:
                self._emit(f'for (int gelb_df = 0; gelb_df < {n};'
                           f' ++gelb_df) {{')
                self._indent += 1
                rhs_expr = self._emit_expression(stmt.rhs,
                                                 df_var='gelb_df')
                # The rolled-loop path can't pick a specific
                # element per-i; use the whole-RHS predicate.
                # Array1DLiteral_N RHSs trip
                # ``_expr_should_unroll_slice`` and route to the
                # unrolled branch above, so this rolled path
                # never sees mixed-V-ness elements.
                if lhs_is_vec and not \
                        self._yields_simd_vector(stmt.rhs):
                    rhs_expr = f'hn::Set(d, {rhs_expr})'
                self._emit(f'{lname}[gelb_df] = {rhs_expr};')
                self._indent -= 1
                self._emit('}')
        else:
            rhs_expr = self._emit_expression(stmt.rhs)
            if (self._simd_mode == 'vec8d'
                    and self._simd_int_locals.get(lhs.name) == 'mask'):
                rhs_expr = self._broadcast_simd_bool(stmt.rhs, rhs_expr)
            # Scalar-LHS assignment to a SIMD-V-retyped local
            # (``_simd_int_locals[name] == 'vec8d'``) needs
            # to broadcast a scalar RHS into V -- Highway has
            # no implicit ``V::operator=(double)``.
            if (self._simd_mode == 'vec8d'
                    and self._simd_int_locals.get(lhs.name) == 'vec8d'
                    and not self._yields_simd_vector(stmt.rhs)):
                rhs_expr = f'hn::Set(d, {rhs_expr})'
            self._emit(f'{lname} = {rhs_expr};')

    def _emit_variable_decl_stmt(
            self, stmt: VariableDeclarationStmt_N,
            context: str) -> None:
        """Local declaration (scalar or array), including the
        SIMD V-retyping rules and the array-initialiser forms
        (upstream_dfs / matmul / literal / rolled loop)."""
        kind = stmt.data_type.canonical_type
        arr_size = kind.dims[0] if kind.rank == 1 else None
        cpp_type = self._decl_cpp_type(stmt)
        # In SIMD mode, retype real-valued *scalar* locals as
        # ``V`` so subsequent arithmetic with V-typed lattice
        # loads / intrinsic results works.  Highway has no
        # implicit ``V(double)`` constructor, so any scalar RHS
        # must be explicitly broadcast via ``hn::Set(d, ...)`` --
        # handled at the init-emit site below and at scalar-LHS
        # assignment sites in the AssignmentStmt_N branch.
        #
        # Track the retype in ``_simd_int_locals`` (historic
        # name; now covers all SIMD-retyped locals -- real + int)
        # so the V-yielding predicate (``_yields_simd_vector``)
        # propagates V-ness through downstream references.
        #
        # Real-valued *array* locals retype to V[] only when
        # their initialiser yields V (e.g. ``upstream_dfs``,
        # ``EX * ux + EY * uy`` with V ``ux``).  Pure-scalar
        # array initialisers (``{0.1, 0.2, ...}``) stay
        # double[] -- there's no scalar->V conversion for
        # element-wise list initialisation.
        if (self._simd_mode == 'vec8d'
                and arr_size is None and cpp_type == 'bool'):
            # A bool local holds one value per lane, including when its
            # first assignment is scalar or comes after its declaration.
            cpp_type = 'hn::Mask<D>'
            self._simd_int_locals[stmt.name.name] = 'mask'
        elif self._simd_mode == 'vec8d' \
                and arr_size is None \
                and cpp_type in ('double', 'float'):
            cpp_type = 'V'
            self._simd_int_locals[stmt.name.name] = 'vec8d'
        elif (self._simd_mode == 'vec8d'
                and arr_size is not None
                and cpp_type in ('double', 'float')):
            # Real-typed array locals always retype to V[] in
            # SIMD mode.  An "init yields V?" flow analysis is
            # not enough -- uninitialised arrays (e.g. ``array
            # [real, 9] feq;`` then ``feq[i] = ...``) often
            # receive V values from later assignments.  The
            # cost of the slightly-wasteful V[] for purely-
            # scalar arrays is offset by gcc's ability to
            # constant-fold ``hn::Set`` when the inputs are
            # literals.  Per-element init paths broadcast
            # scalar RHS values via the new ``_simd_broadcast_str``
            # helper; downstream reads of ``arr[i]`` carry the
            # V-ness through ``_yields_simd_vector``'s
            # RectSelOfArrayElems_N branch.
            cpp_type = 'V'
            self._simd_int_locals[stmt.name.name] = 'vec8d'
        # Int-typed scalar locals whose RHS is a SIMD-vector-
        # producing expression (e.g. ``int dx = x - N/2;`` where
        # ``x`` is the SIMD-promoted spatial coord) must also
        # retype, otherwise a Highway vector value won't type-
        # check against an ``int64_t`` declaration.
        elif (self._simd_mode == 'vec8d'
                and arr_size is None
                and cpp_type in ('int8_t', 'int16_t', 'int32_t', 'int64_t')
                and stmt.initial_value is not None):
            vec_kind = self._rhs_simd_vec_kind(stmt.initial_value)
            if vec_kind == 'vec8d':
                cpp_type = 'V'
                self._simd_int_locals[stmt.name.name] = 'vec8d'
            elif vec_kind == 'vec8q':
                # Integer SIMD arithmetic support is narrower than
                # real-valued SIMD today; emit the type spelling
                # here and keep arithmetic fixups localized to the
                # operations that need them.
                cpp_type = 'hn::Vec<hn::CappedTag<int64_t, 8>>'
                self._simd_int_locals[stmt.name.name] = 'vec8q'
        name = _uname(stmt.name.name)
        if arr_size is None:
            # Scalar: T name = (init expr or 0);
            if stmt.initial_value is not None:
                init_expr = self._emit_expression(stmt.initial_value)
                if cpp_type == 'hn::Mask<D>':
                    init_expr = self._broadcast_simd_bool(
                        stmt.initial_value, init_expr)
                # If the local was retyped to V (Highway vector)
                # but the init expression evaluates to a scalar,
                # broadcast explicitly -- Highway has no implicit
                # scalar->V conversion.  When the RHS is a
                # comparison or other mask-producing expression
                # (e.g. ``int seed = ((dx*dx + dy*dy) < SEED_R2);``
                # in fd/2d/fisher_kpp_rk2, fd/2d/gray_scott_2d),
                # ``hn::Set(d, mask)`` is ill-typed (Highway's
                # ``Mask<D>`` is opaque, ``Set`` only accepts a
                # scalar) -- route through ``_emit_simd_aware_cast``
                # which lowers the mask via ``IfThenElse`` to
                # an ``hn::Vec<D>`` of 1.0 / 0.0.
                if cpp_type == 'V' \
                        and self._simd_mode == 'vec8d' \
                        and not self._yields_simd_vector(
                            stmt.initial_value):
                    if self._produces_simd_bool_mask(
                            stmt.initial_value):
                        init_expr = self._emit_simd_aware_cast(
                            init_expr, stmt.initial_value, 'double')
                    else:
                        init_expr = f'hn::Set(d, {init_expr})'
                self._emit(f'{cpp_type} {name} = {init_expr};')
            elif cpp_type == 'hn::Mask<D>':
                self._emit(f'{cpp_type} {name} = hn::FirstN(d, 0);')
            elif cpp_type == 'V':
                # Highway's V is opaque -- ``V x = 0;`` won't
                # compile.  Use ``hn::Zero(d)`` to broadcast zero
                # into all lanes.
                self._emit(f'{cpp_type} {name} = hn::Zero(d);')
            else:
                self._emit(f'{cpp_type} {name} = 0;')
        else:
            # Array: T name[N];  followed by per-element init if any.
            self._emit(f'{cpp_type} {name}[{arr_size}];')
            init = stmt.initial_value
            # Unwrap a TypePromotionNode_N wrapper so that the
            # dispatch below sees the actual initializer node
            # (e.g. ``IntrinsicFunctionCall_N(upstream_dfs)`` rather
            # than ``TypePromotionNode_N(IntrinsicFunctionCall_N(...))``).
            # Such wrappers appear when an ``array[real32, q]`` decl
            # is initialized with a default-real64-typed call.
            while isinstance(init, TypePromotionNode_N):
                init = init.expr
            if init is None:
                pass  # uninitialised
            elif isinstance(init, IntrinsicFunctionCall_N) \
                    and init.function_name in ('upstream_dfs', 'matmul'):
                self._emit_intrinsic_into_array(name, arr_size, init)
            elif isinstance(init, Array1DLiteral_N):
                # ``array[real, n] x = {a, b, c, ...};`` -- unroll
                # element-wise to keep the per-element type
                # consistent (matters in SIMD mode where each
                # element may itself be V-typed).
                elements = init.value.elements
                if len(elements) != arr_size:
                    raise NotImplementedError(
                        f"array literal length {len(elements)}"
                        f" != array {stmt.name.name} size "
                        f"{arr_size}")
                for i, e in enumerate(elements):
                    elem_str = self._emit_expression(e)
                    # When the array was retyped to V[] (real
                    # array in SIMD mode), pure-scalar element
                    # values need an explicit ``hn::Set(d, ...)``
                    # broadcast; Highway's V has no implicit
                    # ``V::operator=(double)``.
                    if cpp_type == 'V' \
                            and self._simd_mode == 'vec8d' \
                            and not self._yields_simd_vector(e):
                        elem_str = f'hn::Set(d, {elem_str})'
                    self._emit(f'{name}[{i}] = {elem_str};')
            elif isinstance(init, Identifier_N) and (
                    self._local_array_type(init.name) is not None
                    or self._constant_vector(init.name) is not None):
                # Array-to-array copy.  When the destination is
                # V[] but the source is a scalar compound-literal array
                # global constant, broadcast each element.
                src = _uname(init.name)
                src_is_vec = (
                    self._simd_mode == 'vec8d'
                    and self._simd_int_locals.get(init.name)
                        == 'vec8d')
                if cpp_type == 'V' and not src_is_vec:
                    rhs = f'hn::Set(d, {src}[gelb_df])'
                else:
                    rhs = f'{src}[gelb_df]'
                self._emit(f'for (int gelb_df = 0; gelb_df < {arr_size};'
                           f' ++gelb_df) {{ {name}[gelb_df] = '
                           f'{rhs}; }}')
            elif self._expr_should_unroll_slice(init):
                # Init expression references a constexpr array
                # (e.g. ``eu = EX*ux + EY*uy``).  Unroll so each
                # ``EX[i]`` / ``EY[i]`` resolves to its literal
                # value, letting the compiler fold zero terms.
                for i in range(arr_size):
                    elem_str = self._emit_expression(init, df_var=str(i))
                    if cpp_type == 'V' \
                            and self._simd_mode == 'vec8d' \
                            and not \
                            self._unrolled_element_yields_simd_vector(
                                init, i):
                        elem_str = f'hn::Set(d, {elem_str})'
                    self._emit(f'{name}[{i}] = {elem_str};')
            else:
                # Array-valued expression (broadcast op, slice, etc.):
                # emit a per-element init loop, substituting the DF
                # index into any array-typed sub-expression.
                self._emit(f'for (int gelb_df = 0; gelb_df < {arr_size};'
                           f' ++gelb_df) {{')
                self._indent += 1
                init_expr = self._emit_expression(init, df_var='gelb_df')
                if cpp_type == 'V' \
                        and self._simd_mode == 'vec8d' \
                        and not self._yields_simd_vector(init):
                    init_expr = f'hn::Set(d, {init_expr})'
                self._emit(f'{name}[gelb_df] = {init_expr};')
                self._indent -= 1
                self._emit('}')

    def _decode_lattice_sel(self, sel) -> tuple[list, object]:
        """Return ``(spatial_ranges, df_range)`` from a RectSel.

        ``element_ranges`` is a list whose last element is the DF range
        and whose earlier elements are spatial coordinate ranges.
        Each element is typically a ``Range_N`` with ``.low`` and
        ``.high`` (which may both be the same scalar for ``f[x | 3]``
        sugar).
        """
        ers = sel.element_ranges
        return ers[:-1], ers[-1]

    def _range_scalar(self, r) -> object:
        """If a Range_N's low and high are the same expr, return that
        expr (single index).  Otherwise raise (not yet supported)."""
        if isinstance(r, Range_N):
            if r.low is None or r.high is None or r.low is not r.high:
                # Still allow if low==high by structural equality (e.g.
                # both IntLiteral with same value).
                if (isinstance(r.low, IntLiteral_N)
                        and isinstance(r.high, IntLiteral_N)
                        and r.low.value == r.high.value):
                    return r.low
                if (isinstance(r.low, Identifier_N)
                        and isinstance(r.high, Identifier_N)
                        and r.low.name == r.high.name):
                    return r.low
                raise NotImplementedError(
                    "cpu_highway only supports single-index lattice access "
                    "(low==high in each range; got distinct low/high).")
            return r.low
        return r

    def _emit_lattice_out_lhs(self, sel: RectSelOfLatticeOutDFs_N,
                              context: str, df_var: str | None = None) -> LatticeAddress:
        lname = sel.lattice_name.name
        spatial, df = self._decode_lattice_sel(sel)
        if len(spatial) != self._d:
            raise NotImplementedError(
                f"cpu_highway: lattice access has {len(spatial)} spatial "
                f"dimensions but lattice is {self._d}-D.")
        df_idx_str = self._df_index_str(df, df_var)
        coord_strs = self._emit_lattice_coord_strs(spatial, for_write=True)
        if context == 'dynamic':
            buf = f'{_lname(lname)}_new'
        else:  # initializer or gauge -> both target f_old's logical slot
            buf = f'{_lname(lname)}_old'
        # SoA: g_f_storage[buf][df][y][x] (x innermost -- contiguous).
        # AoS: g_f_storage[buf][y][x][df] (DF innermost -- co-located).
        return self._lattice_address(lname, buf, coord_strs, df_idx_str)

    def _emit_coord_scalar(self, node, df_var=None) -> str:
        """Emit a coord expression as a scalar (int) regardless of
        ``self._simd_mode``.  Used at lattice-array index positions
        (the inner dimensions of g_f_storage[...]), where the per-lane
        Vec8d gelb_xv would not type-check as an integer subscript."""
        old = self._simd_mode
        old_index = getattr(self, '_in_coord_scalar', False)
        self._simd_mode = 'scalar'
        # An index keeps its literals bare (``_emit_operand``).
        self._in_coord_scalar = True
        try:
            return self._emit_expression(node, df_var)
        finally:
            self._simd_mode = old
            self._in_coord_scalar = old_index

    def _split_axis_offset(self, expr):
        """Parse a coord expression that is one axis's coordinate plus
        a constant (``x``, ``x - 1``, ``2 + x``, ``(x + 1) + 1``) into
        ``(axis_name, offset)``.  Returns None for any other shape so
        the caller can fall back to plain emission."""
        form = affine_index(expr)
        if form is None or len(form[0]) != 1:
            return None
        (axis_name, coefficient), = form[0].items()
        if coefficient != 1:
            return None
        return (axis_name, form[1])

    def _coordinate(self, node, axis_idx, offset=0, *, for_write=False,
                    subtract=False, bounce=False):
        """Resolve an affine coordinate without parsing its emitted spelling."""
        parsed = self._split_axis_offset(node)
        size = self._grid_sizes()[axis_idx]
        periodic = is_periodic(self._lattice_info, axis_idx)
        if parsed is not None and parsed[0] == self._axis(axis_idx):
            axis, base_offset = parsed
            total = base_offset + offset
            policy = 'plain'
            if total and axis_idx not in self._wrap_safe_axes:
                if periodic and (for_write or abs(total) > 1):
                    policy = 'wrap'
                elif not periodic and not for_write and not bounce:
                    policy = 'clamp'
            coord = AxisOffset(axis, total, size, periodic, policy, subtract)
            # Even a wrap-safe bound read is resolved by the same rule.
            if axis in self._axis_bindings and not periodic and not for_write and not bounce:
                coord = AxisOffset(axis, total, size, False, 'clamp', subtract)
            return coord.resolve(self._axis_bindings)
        text = self._emit_coord_scalar(node)
        if offset:
            text = f'({text} - ({-offset}))' if subtract else f'({text} + ({offset}))'
        return ExprCoord(text)

    def _emit_lattice_coord_strs(self, spatial, for_write=False):
        return [self._coordinate(self._range_scalar(node), i, for_write=for_write)
                for i, node in enumerate(spatial)]

    def _x_offset_of_spatial(self, spatial) -> int | None:
        """Return the integer x-offset of a lattice spatial selector,
        or ``None`` if axis 0 doesn't fit the ``x +/- k`` shape (e.g. a
        literal index or a complex expression).  Used by
        ``_emit_simd_lattice_load`` to decide whether the CBT
        cross-tile permute path applies."""
        if not spatial:
            return None
        scalar = self._range_scalar(spatial[0])
        parsed = self._split_axis_offset(scalar)
        if parsed is None:
            return None
        axis_name, off = parsed
        if axis_name != self._axis(0):
            return None
        return off

    def _emit_lattice_in(self, sel: RectSelOfLatticeInDFs_N,
                         df_var: str | None = None) -> str:
        lname = sel.lattice_name.name
        spatial, df = self._decode_lattice_sel(sel)
        if len(spatial) != self._d:
            raise NotImplementedError(
                f"cpu_highway: lattice access has {len(spatial)} spatial "
                f"dimensions but lattice is {self._d}-D.")
        df_idx_str = self._df_index_str(df, df_var)
        coord_strs = self._emit_lattice_coord_strs(spatial)
        x_offset = self._x_offset_of_spatial(spatial)
        return self._emit_simd_lattice_load(
            lname, coord_strs, df_idx_str, x_offset)

    def _df_index_str(self, df_node, df_var: str | None) -> str:
        """Resolve the DF index portion of a lattice access.

        - If ``df_var`` is set, the caller is inside a ``for-df`` loop
          and any df range maps to the loop variable.  ``df_var`` counts
          from the start of the slice being assigned, so a slice with a
          nonzero lower bound (``f.in[x, y | 2:5]``) adds it: element
          ``i`` of that slice is DF ``2 + i``.
        - Otherwise the df range must be a single literal int.
        """
        if df_var is not None:
            # A single DF (``| k``) keeps its own index inside the loop:
            # it is a scalar operand, broadcast over the slice.
            single = self._single_df_literal(df_node)
            if single is not None:
                return str(single)
            lo = self._slice_low(df_node)
            if lo == 0:
                return df_var
            if df_var.lstrip('-').isdigit():
                return str(int(df_var) + lo)
            return f'({df_var} + {lo})'
        df_scalar = self._range_scalar(df_node)
        if isinstance(df_scalar, IntLiteral_N):
            return str(df_scalar.value)
        raise NotImplementedError(
            "cpu_highway: DF index must be a literal int outside a slice loop.")

    def _opp_var_name(self, key) -> str:
        return 'gelb_opp_' + '_'.join(key)

    def _emit_bounce_back_dfs_tables(self) -> None:
        keys = self.backend_context.opp_tables
        if not keys:
            return
        for key in sorted(keys):
            opp = self.backend_context.opp_tables[key]
            var = self._opp_var_name(key)
            n = len(opp)
            self._emit(f'// Opposite-direction lookup for {{{", ".join(key)}}}')
            self._emit(f'static constexpr int {var}[{n}] = '
                       f'{{ {", ".join(str(j) for j in opp)} }};')
