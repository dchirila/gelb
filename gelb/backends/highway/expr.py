"""Expression and intrinsic-call emission for cpu_highway.

The recursive expression dispatcher and the intrinsic lowering
(sum / dot_prod / matmul / bounce_back_dfs / random / math intrinsics),
in both scalar and SIMD modes.
"""

from __future__ import annotations

from gelb.backends.real_literals import cpp_real

from gelb.backends.highway.common import (
    _TYPE_MAP,
    _uname,
)

from gelb.frontend.intrinsic_functions import CAST_INTRINSIC_NAMES
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
    NotEqual_N,
    NotExpr_N,
    Or_N,
    Pow_N,
    RealLiteral_N,
    RectSelOfArrayElems_N,
    RectSelOfLatticeInDFs_N,
    Sub_N,
    TypePromotionNode_N,
    UnaryMinusExpr_N,
    VariableDeclarationStmt_N,
)
from gelb.midware.ast_eval import eval_const_expr, is_periodic
from gelb.midware.ast_simplify import is_pure, numeric_kind


# ----------------------------------------------------------------------
# Intrinsic lookup tables
# ----------------------------------------------------------------------

# Scalar math intrinsics.  In scalar mode we use ``std::`` for
# explicitness and to avoid <math.h> macro hazards; in SIMD mode we
# route to Highway's contrib math via ``hn::Sin(d, v)`` etc.
# (free-function form, NOT a member / ADL hook -- Highway's ``Vec<D>``
# is opaque).  The contrib header is included by the runtime header.
_UNARY_MATH_SET = {'sin', 'cos', 'tan', 'tanh', 'sqrt',
                   'exp', 'log', 'abs'}

# Highway splits unary math across two surfaces:
#   * ``hn::Sqrt(V)`` and ``hn::Abs(V)`` are CORE ops with a
#     single-arg ``(V)`` signature -- no descriptor.  They live
#     in ``hwy/ops/<isa>-inl.h``.
#   * ``hn::Sin(d, V)`` / ``hn::Cos(d, V)`` / etc. are contrib
#     math ops with the two-arg ``(D, V)`` signature, defined
#     in ``hwy/contrib/math/math-inl.h``.
# The per-name dispatch below picks the right shape.
_UNARY_SIMD_SPELLING = {
    'sin':  'hn::Sin',
    'cos':  'hn::Cos',
    'tan':  'hn::Tan',
    'tanh': 'hn::Tanh',
    'sqrt': 'hn::Sqrt',
    'exp':  'hn::Exp',
    'log':  'hn::Log',
    'abs':  'hn::Abs',
}
_UNARY_SIMD_TAKES_DESCRIPTOR = {
    'sin', 'cos', 'tan', 'tanh', 'exp', 'log',
}
# The library functions with one implementation per path on cpu_highway
# (cpu_highway_runtime.hpp's gelb_<name>; user manual, Numerical
# semantics: Library functions).
_LIBRARY_FUNCTIONS = frozenset({'sin', 'cos', 'tan', 'tanh', 'exp', 'log'})

# Binary scalar math.  ``min`` / ``max`` / ``mod`` are GeLB's runtime
# helpers (cpp_runtime_common.hpp; user manual, Numerical semantics:
# Types and promotion): one definition on every path, with the call's
# C++ type given explicitly so an ``int`` literal beside an ``int64_t``
# operand converts instead of failing template deduction.  In SIMD mode
# ``min`` / ``max`` on a vector operand call the vector overloads in
# cpu_highway_runtime.hpp (the same IEEE minimum / maximum); a ``mod``
# or ``atan2`` on a vector has no vector form, so such a block takes
# the scalar path (``_block_has_scalar_only_intrinsic``).  ``atan2`` is
# a library function, one implementation per backend: the platform's
# ``std::atan2`` at the call's width.
_BINARY_MATH_SCALAR = {
    'min': 'gelb::gelb_min', 'max': 'gelb::gelb_max',
    'atan2': 'std::atan2', 'mod': 'gelb::gelb_mod',
}
_BINARY_MATH_TYPED = frozenset({'min', 'max', 'mod'})


class ExpressionEmitMixin:
    """Mixin: see module docstring.  Assembled into
    ``HighwayCodeGenerator`` (stage3_backend_cpu_highway).
    """

    def _emit_expression(self, expr, df_var: str | None = None) -> str:
        if isinstance(expr, IntLiteral_N):
            # A decimal literal takes the first of int, long, long long
            # that holds it, so every int64 value but the minimum is
            # spelled bare; the minimum's magnitude is not a signed
            # literal (clang reads it as unsigned and the negation
            # keeps the wrong sign), so it is the negative maximum
            # minus one; a native literal must express its GeLB value.
            if expr.value == -2 ** 63:
                return '(-9223372036854775807LL - 1LL)'
            return str(expr.value)
        if isinstance(expr, RealLiteral_N):
            kind = getattr(getattr(expr, 'inferred_type', None), 'element_dtype', None)
            cpp_type = 'float' if kind in ('real16', 'real32') else 'double'
            return cpp_real(expr.value, cpp_type)
        if isinstance(expr, BoolLiteral_N):
            return 'true' if expr.value in (True, 'true') else 'false'
        if isinstance(expr, Identifier_N):
            # `t` and `Nx`/`Ny`/`Nz` are GeLB `int`, int64; their C++
            # carriers are `int` (NetCDF and loop bounds want them so):
            # widened where a user expression reads them.
            tag = getattr(expr, 'symbol_tag', None)
            if tag == "implicit timestep variable":
                return 'static_cast<int64_t>(gelb_timestep)'
            if tag == "implicit dimension constant":
                # The size parameters are `g__nx` etc.; `_uname('Nx')`
                # would name an undeclared `g_Nx`.
                return f'static_cast<int64_t>(g__n{expr.name[1].lower()})'
            if expr.name in ('x', 'y', 'z'):
                # In SIMD mode, the x coordinate varies across the 8
                # vector lanes; emit the pre-computed lane vector
                # (declared at the top of each SIMD iteration).  y and
                # z are still scalar -- they're constant within one SIMD
                # iteration of the inner x-loop.
                if expr.name == 'x' and self._simd_mode == 'vec8d':
                    return 'gelb_xv'
                return f'g_{expr.name}'
            # Array variables -- local or global -- referenced inside a
            # for-df slice loop become element accesses.  Outside such a
            # loop, bare-name access is only allowed for scalars; an
            # array-typed identifier here would be a whole-array
            # operation (e.g. sum(EX) -- handled at the IntrinsicFunctionCall
            # level, never reached here as a bare identifier).
            base = _uname(expr.name)
            is_array = (expr.name in self._array_locals
                        or expr.name in self._array_constants)
            if is_array and df_var is not None:
                # Constant-fold accesses into a constexpr array
                # constant when the index is a literal integer.
                # Without this, ``EX[3]`` (with EX = {..., -1.0, ...})
                # emits as ``g_EX[3]`` and gcc keeps ``g_EX[3] * x``
                # as a multiplication even though the value is -1
                # (IEEE-754 strictness).  Inlining the literal lets
                # the compiler see ``-1.0 * x`` and fold it to ``-x``.
                if (df_var.lstrip('-').isdigit()
                        and expr.name in self._array_constants):
                    vals = self._fold_array_constants(expr.name)
                    if vals is not None:
                        idx = int(df_var)
                        if 0 <= idx < len(vals):
                            return (cpp_real(vals[idx], _TYPE_MAP.get(
                                getattr(expr.inferred_type, 'element_dtype', 'real'), 'double'))
                                if isinstance(vals[idx], float) else repr(vals[idx]))
                return f'{base}[{df_var}]'
            return base
        if isinstance(expr, (Add_N, Sub_N, Mul_N)):
            # The zero peepholes depend on the operation's kind: a real
            # zero has a sign, which a fold must keep.
            kind = numeric_kind(getattr(expr, 'inferred_type', None))
            integer = kind is not None and kind.startswith('int')
            # An integer product with zero folds to 0 only when the
            # dropped operand makes no call to random().
            if integer and isinstance(expr, Mul_N) and not is_pure(expr):
                integer = False
            a, b = self._broadcast_for_binop(expr.left, expr.right, df_var)
            fold = (self._fold_add if isinstance(expr, Add_N) else
                    self._fold_sub if isinstance(expr, Sub_N) else
                    self._fold_mul)
            return fold(a, b, integer)
        if isinstance(expr, Div_N):
            a, b = self._broadcast_for_binop(expr.left, expr.right, df_var)
            return f'({a} / {b})'
        if isinstance(expr, Pow_N):
            base = self._emit_expression(expr.left, df_var)
            # Small non-negative integer exponents -> unrolled multiplication.
            # The exponent may be a bare IntLiteral_N or a TypePromotionNode_N
            # wrapping one (the latter happens when the type-inference
            # visitor promotes the int literal to match the base's real
            # type, e.g. for `u^2` where u is real).
            int_exp_node = expr.right
            if isinstance(int_exp_node, TypePromotionNode_N):
                int_exp_node = int_exp_node.expr
            if isinstance(int_exp_node, IntLiteral_N):
                k = int_exp_node.value
                if 0 <= k <= 8:
                    if k == 0:
                        # ``1`` is a scalar literal; if it gets consumed
                        # in a V-context the surrounding binop will
                        # broadcast it via the ``_broadcast_for_binop``
                        # path.
                        return '1'
                    if k == 1:
                        return base
                    return '(' + ' * '.join([base] * k) + ')'
            exp_e = self._emit_expression(expr.right, df_var)
            kind = getattr(getattr(expr, 'inferred_type', None), 'element_dtype', None)
            if kind is not None and kind.startswith('int'):
                # An integer raised to an integer is exact integer
                # arithmetic with Fortran's negative-exponent rule (user
                # manual, Numerical semantics: Types and promotion), not
                # a double pow.
                return f'gelb::gelb_ipow<{_TYPE_MAP[kind]}>({base}, {exp_e})'
            # A real base: backend-defined; the platform's pow.
            return f'std::pow({base}, {exp_e})'
        if isinstance(expr, UnaryMinusExpr_N):
            inner = self._emit_expression(expr.value, df_var)
            if self._simd_mode == 'vec8d' \
                    and self._yields_simd_vector(expr.value):
                # Highway has no unary ``operator-`` overload on V --
                # use ``hn::Neg`` for explicit lane-wise negation.
                return f'hn::Neg({inner})'
            return f'(-{inner})'
        if isinstance(expr, RectSelOfLatticeInDFs_N):
            return self._emit_lattice_in(expr, df_var)
        if isinstance(expr, RectSelOfArrayElems_N):
            # Indexing into a 1-D local/constant array (e.g.
            # ``moments[3]``).  PR scope: single integer index;
            # multi-D array element selection is not used yet.
            arr_name = expr.array_name.name \
                if hasattr(expr.array_name, 'name') \
                else str(expr.array_name)
            ranges = expr.element_ranges
            if len(ranges) != 1:
                raise NotImplementedError(
                    f"cpu_highway: only 1-D array element selection "
                    f"is supported (got {len(ranges)}-D for "
                    f"{arr_name}).")
            idx_scalar = self._range_scalar(ranges[0])
            idx_str = self._emit_expression(idx_scalar, df_var)
            return f'{_uname(arr_name)}[{idx_str}]'
        if isinstance(expr, Array1DLiteral_N):
            elements = expr.value.elements
            # Common case: caller is unrolling a whole-array
            # assignment and passes a literal index string ('0', '1',
            # ...).  Just return the corresponding element directly --
            # this also avoids the SIMD-mode trap where a compound
            # literal of Vec8d-typed values doesn't type-check.
            if df_var is not None and df_var.lstrip('-').isdigit():
                idx = int(df_var)
                if 0 <= idx < len(elements):
                    return self._emit_expression(elements[idx])
            elem_strs = [self._emit_expression(e, df_var)
                         for e in elements]
            if df_var is None:
                # Bare-literal use outside a slice loop -- typical for
                # ``meq = {a, b, c, ...}`` whose surrounding statement
                # branch unrolls element-wise.  We don't expect to be
                # called here.
                raise NotImplementedError(
                    "cpu_highway: Array1DLiteral_N as a free-standing "
                    "expression is unsupported; use it as the RHS of "
                    "a whole-array assignment.")
            # Inside a per-element loop: emit a C99 compound literal
            # indexed at df_var.  GCC/Clang accept this in C++ as an
            # extension and the optimiser hoists constant elements.
            # NOTE: in SIMD mode, this only works when every element
            # is a plain scalar -- which is why the whole-array assign
            # path falls back to per-element unrolling whenever the
            # RHS contains an Array1DLiteral_N (see _emit_statement).
            return ('((double[]){ '
                    + ', '.join(elem_strs)
                    + ' })[' + df_var + ']')
        if isinstance(expr, BroadcastNode_N):
            return self._emit_expression(expr.scalar_expr, df_var)
        if isinstance(expr, IntrinsicFunctionCall_N):
            return self._emit_intrinsic_call(expr, df_var)
        if isinstance(expr, TypePromotionNode_N):
            # Promote with an explicit static_cast (or SIMD-aware
            # equivalent -- see ``_emit_simd_aware_cast`` for the
            # special cases involving Vec8db / Vec8q operands).
            tgt = expr.target_type
            tgt_elem = (getattr(tgt, 'element_dtype', None)
                        or getattr(tgt, 'name', 'double'))
            cpp_tgt = _TYPE_MAP.get(tgt_elem, 'double')
            inner = self._emit_expression(expr.expr, df_var)
            return self._emit_simd_aware_cast(inner, expr.expr, cpp_tgt)
        # Comparison operators -- in scalar mode produce a C++ bool
        # (implicitly convertible to int / double in arithmetic
        # contexts); in SIMD mode lower to Highway's free-function
        # comparison ops which return ``hn::Mask<D>``.  Highway has
        # no comparison ``operator<`` / ``operator==`` etc. on V
        # (verified: only the ``Vec128<XXX, N>`` overloads exist for
        # 8/16/32-bit unsigned-int lanes), so the function form is
        # the only portable shape.
        _CMP_HWY = {
            'Equal_N':        'hn::Eq',
            'NotEqual_N':     'hn::Ne',
            'Less_N':         'hn::Lt',
            'LessEqual_N':    'hn::Le',
            'Greater_N':      'hn::Gt',
            'GreaterEqual_N': 'hn::Ge',
        }
        _CMP_OP = {
            'Equal_N':        '==',
            'NotEqual_N':     '!=',
            'Less_N':         '<',
            'LessEqual_N':    '<=',
            'Greater_N':      '>',
            'GreaterEqual_N': '>=',
        }
        cmp_kind = type(expr).__name__
        if cmp_kind in _CMP_OP:
            a, b = self._broadcast_for_binop(
                expr.left, expr.right, df_var)
            if self._simd_mode == 'vec8d' and (
                    self._yields_simd_vector(expr.left)
                    or self._yields_simd_vector(expr.right)):
                return f'{_CMP_HWY[cmp_kind]}({a}, {b})'
            return f'({a} {_CMP_OP[cmp_kind]} {b})'
        # Boolean ops on masks -> ``hn::And`` / ``hn::Or`` /
        # ``hn::Not``.  In scalar mode these stay as ``&&`` / ``||``.
        # A uniform scalar operand (for example a comparison of t)
        # broadcasts when combined with a per-lane boolean.
        if isinstance(expr, NotExpr_N):
            value = self._emit_expression(expr.value, df_var)
            if (self._simd_mode == 'vec8d'
                    and self._produces_simd_bool_mask(expr.value)):
                return f'hn::Not({value})'
            return f'(!{value})'
        if isinstance(expr, And_N):
            a = self._emit_expression(expr.left, df_var)
            b = self._emit_expression(expr.right, df_var)
            if self._simd_mode == 'vec8d' and (
                    self._produces_simd_bool_mask(expr.left)
                    or self._produces_simd_bool_mask(expr.right)):
                a = self._broadcast_simd_bool(expr.left, a)
                b = self._broadcast_simd_bool(expr.right, b)
                return f'hn::And({a}, {b})'
            return f'({a} && {b})'
        if isinstance(expr, Or_N):
            a = self._emit_expression(expr.left, df_var)
            b = self._emit_expression(expr.right, df_var)
            if self._simd_mode == 'vec8d' and (
                    self._produces_simd_bool_mask(expr.left)
                    or self._produces_simd_bool_mask(expr.right)):
                a = self._broadcast_simd_bool(expr.left, a)
                b = self._broadcast_simd_bool(expr.right, b)
                return f'hn::Or({a}, {b})'
            return f'({a} || {b})'
        raise NotImplementedError(
            f"cpu_highway: unsupported expression: {type(expr).__name__} "
            f"(grow this method as more constructs are added).")

    def _emit_intrinsic_call(self, call: IntrinsicFunctionCall_N,
                             df_var: str | None) -> str:
        """Emit C++ for an intrinsic-function call expression.

        Pure dispatch -- each intrinsic family has a dedicated
        ``_emit_intrinsic_*`` helper below.
        """
        fname = call.function_name
        if fname == 'sum':
            return self._emit_intrinsic_sum(call, df_var)
        if fname == 'random':
            return self._emit_intrinsic_random(call)
        if fname in CAST_INTRINSIC_NAMES:
            return self._emit_intrinsic_cast(call, df_var)
        if fname in _UNARY_MATH_SET:
            return self._emit_intrinsic_unary_math(call, df_var)
        if fname in _BINARY_MATH_SCALAR:
            return self._emit_intrinsic_binary_math(call, df_var)
        if fname == 'dot_prod':
            return self._emit_intrinsic_dot_prod(call)
        if fname == 'bounce_back_dfs':
            return self._emit_intrinsic_bounce_back_dfs(call, df_var)
        if fname == 'upstream_dfs':
            # upstream_dfs as an *expression* would mean its result is
            # used in-place (e.g. f.out[x|:] = upstream_dfs(...) + ...).
            # The backend handles only the explicit-temporary case
            # (`array[real, q] var = upstream_dfs(...)`).  Emit a clear
            # error here -- the alternative is a substantial refactor.
            raise NotImplementedError(
                "cpu_highway: upstream_dfs(...) only supported as the "
                "right-hand side of a local array declaration "
                "(`array[real, q] var = upstream_dfs(...);`).  "
                "Wrap it in a temporary if needed.")
        if fname == 'matmul':
            return self._emit_intrinsic_matmul(call, df_var)
        raise NotImplementedError(
            f"cpu_highway: intrinsic function '{fname}' not yet supported.")

    def _emit_intrinsic_sum(self, call: IntrinsicFunctionCall_N,
                        df_var: str | None) -> str:
        # sum(array) -- emit a call to ``gelb::gelb_sum(arr)``.  The
        # runtime helper is a 4-accumulator template (see
        # cpu_highway_runtime.hpp), implementing the multi-
        # accumulator parallel-reduction pattern.  This breaks the
        # otherwise 19-deep ``vaddpd`` dependency chain into 4
        # parallel streams, recovering ~2-4x of FP throughput on
        # long reductions.  Compiler fully inlines + unrolls at
        # -O3.
        #
        # Falls back to the inline ``+``-chain for the
        # ``f.in[x|:]`` lattice-slice form, where there's no named
        # C-array to pass: lifting 19 ``Vec8d().load(...)`` reads
        # into a temp array would defeat the compactness goal and
        # rarely fires on hot paths (it's typically a gauge
        # expression, not in dynamics).
        if len(call.arguments) != 1:
            raise NotImplementedError(
                "cpu_highway: sum() expects 1 argument.")
        arg = call.arguments[0]
        if isinstance(arg, Identifier_N):
            # Route to the multi-acc helper in
            # cpu_highway_runtime.hpp.  Descriptor ``d`` is the
            # first arg in SIMD mode (the V overload); there is no
            # descriptor in scalar mode (the double overload).  The
            # helper is templated on the array size so the 4-way
            # unroll is constexpr.
            base = _uname(arg.name)
            if self._simd_mode == 'vec8d':
                return f'gelb::gelb_sum(d, {base})'
            return f'gelb::gelb_sum({base})'
        if isinstance(arg, RectSelOfLatticeInDFs_N):
            # sum(f.in[x | :]) -- sum over DF slice.  Routes
            # through ``_emit_simd_lattice_load`` so explicit-offset
            # reads (e.g. ``sum(f.in[x +/- 1, y +/- 1 | :])`` in
            # Shan-Chen) take the CBT cross-tile permute path
            # instead of a stride-broken ``hn::LoadU``.
            spatial, df = self._decode_lattice_sel(arg)
            df_lo, df_hi = self._df_range(arg)
            if len(spatial) != self._d:
                raise NotImplementedError(
                    f"sum(): lattice access has {len(spatial)} spatial "
                    f"dims but lattice is {self._d}-D.")
            lname = arg.lattice_name.name
            coord_strs = self._emit_lattice_coord_strs(spatial)
            x_offset = self._x_offset_of_spatial(spatial)
            terms = [
                self._emit_simd_lattice_load(
                    lname, coord_strs, str(df), x_offset)
                for df in range(df_lo, df_hi + 1)]
            return '(' + ' + '.join(terms) + ')'
        raise NotImplementedError(
            f"cpu_highway: sum() of expression type {type(arg).__name__} "
            f"not supported (Identifier or lattice-slice only).")

    def _emit_intrinsic_random(self, call: IntrinsicFunctionCall_N) -> str:
        # Uniform double in [0, 1).  Scalar mode -> single lane
        # extracted from a fresh V draw; SIMD mode -> V of 8
        # independent uniform-[0,1) doubles, one per lane.  Both
        # are wrappers around Highway's ``VectorXoshiro`` (see
        # cpu_highway_runtime.hpp).
        if call.arguments and len(call.arguments) > 0:
            raise NotImplementedError(
                "random(): no arguments expected.")
        if self._simd_mode == 'vec8d':
            return 'gelb::gelb_random_vec()'
        return 'gelb::gelb_random()'

    def _emit_intrinsic_cast(self, call: IntrinsicFunctionCall_N,
                             df_var: str | None) -> str:
        """A cast intrinsic, ``real(x)``, ``int(x)``, ``real32(x)``,
        ``int8(x)`` ...: ``static_cast<T>(x)`` with the C++ type of the
        target width (user manual, Numerical semantics: Types and
        promotion: an integer to a narrower integer wraps, a real to an
        integer truncates).  In SIMD mode when x is already
        a ``V`` (double-typed) and the target is double, the cast is a
        no-op; a width-specific cast on a vector has no vector form, so
        such a block takes the scalar path
        (``_block_has_scalar_only_intrinsic``)."""
        fname = call.function_name
        target = _TYPE_MAP[fname]
        if len(call.arguments) != 1:
            raise NotImplementedError(
                f"{fname}(): 1 argument expected.")
        arg_node = call.arguments[0]
        inner = self._emit_expression(arg_node, df_var)
        return self._emit_simd_aware_cast(inner, arg_node, target)

    def _emit_intrinsic_unary_math(self, call: IntrinsicFunctionCall_N,
                               df_var: str | None) -> str:
        fname = call.function_name
        unary_simd_spelling = _UNARY_SIMD_SPELLING
        unary_simd_takes_descriptor = _UNARY_SIMD_TAKES_DESCRIPTOR
        if len(call.arguments) != 1:
            raise NotImplementedError(
                f"cpu_highway: {fname}() expects 1 argument.")
        arg_node = call.arguments[0]
        inner = self._emit_expression(arg_node, df_var)
        vector_arg = (self._simd_mode == 'vec8d'
                      and self._yields_simd_vector(arg_node))
        if fname in _LIBRARY_FUNCTIONS and self.backend_name == 'cpu_highway' \
                and self._cpp_type_of(arg_node) == 'double':
            # One implementation per function on this backend, in every
            # path (user manual, Numerical semantics: Library functions):
            # the runtime header's gelb_sin & co. apply Highway's math to
            # a V in the SIMD body and to a one-lane vector in the scalar
            # tail and the edge cells, with the platform's function
            # outside Highway's valid range (chosen lane by lane from the
            # value) and for tan, which Highway lacks.  Overloaded on V
            # and double.  A real32 argument keeps the platform's
            # function (no SIMD path for it).
            return f'gelb::gelb_{fname}({inner})'
        # sqrt and abs are core ops, exact on every path; CUDA and a
        # real32 argument use the platform's library, one implementation
        # on that backend.
        if vector_arg:
            if fname in unary_simd_takes_descriptor:
                return f'{unary_simd_spelling[fname]}(d, {inner})'
            return f'{unary_simd_spelling[fname]}({inner})'
        return f'std::{fname}({inner})'

    def _emit_intrinsic_binary_math(self, call: IntrinsicFunctionCall_N,
                                df_var: str | None) -> str:
        fname = call.function_name
        binary_map_scalar = _BINARY_MATH_SCALAR
        if len(call.arguments) != 2:
            raise NotImplementedError(
                f"cpu_highway: {fname}() expects 2 arguments.")
        a_node, b_node = call.arguments[0], call.arguments[1]
        a = self._emit_expression(a_node, df_var)
        b = self._emit_expression(b_node, df_var)
        if self._simd_mode == 'vec8d' and fname in ('min', 'max'):
            # The vector overloads are lane-wise on V; only take the
            # SIMD path when at least one arg is V.  Pure scalar/scalar
            # still goes to the scalar helper even in SIMD mode.
            a_vec = self._yields_simd_vector(a_node)
            b_vec = self._yields_simd_vector(b_node)
            if a_vec or b_vec:
                if a_vec and not b_vec:
                    b = f'hn::Set(d, {b})'
                elif b_vec and not a_vec:
                    a = f'hn::Set(d, {a})'
                return f'{binary_map_scalar[fname]}({a}, {b})'
        if fname in _BINARY_MATH_TYPED:
            return f'{binary_map_scalar[fname]}<{self._cpp_type_of(call)}>({a}, {b})'
        return f'{binary_map_scalar[fname]}({a}, {b})'

    @staticmethod
    def _cpp_type_of(node) -> str:
        """The C++ type of ``node``'s inferred GeLB type (user manual,
        Numerical semantics: Types and promotion), ``double`` when
        unknown."""
        dtype = getattr(getattr(node, 'inferred_type', None), 'element_dtype', None)
        return _TYPE_MAP.get(dtype, 'double')

    def _emit_intrinsic_dot_prod(self, call: IntrinsicFunctionCall_N) -> str:
        # dot_prod(a, b) -- sum_i a[i] * b[i].  At codegen time we have
        # access to one operand as folded constants (typically EX
        # / EY / EZ -- D2Q9/D3Q19 stencil velocities) and the other
        # as a runtime local array (typically the upstream_dfs
        # result).  Every term counts (user manual, Numerical semantics:
        # Reproducibility): a zero coefficient is kept, so an Inf or NaN
        # in that direction propagates (skipping such terms is allowed
        # only under an opt-in relaxation flag of a later version).  The
        # +/-1 special case is recognised.
        #
        # When all coefficients are exactly +/-1 (the
        # common case for LBM moments), we emit a call to
        # ``gelb::gelb_signed_sum<T, Mp, Mn>(arr, pos_idx, neg_idx)``
        # which uses two parallel accumulators (positive and
        # negative streams) and a final binary subtract -- the
        # multi-accumulator parallel-reduction pattern that breaks
        # the otherwise depth-N dependency chain.
        #
        # When some coefficient is not +/-1, we emit a call to
        # ``gelb_dot_prod_const`` (4-acc generic dot product
        # with a constexpr coefficient array).  When no coefficient
        # is foldable (both operands runtime), we keep the inline
        # ``+``-chain emit.
        if len(call.arguments) != 2:
            raise NotImplementedError(
                "cpu_highway: dot_prod() expects 2 arguments.")
        a, b = call.arguments
        if not (isinstance(a, Identifier_N)
                and isinstance(b, Identifier_N)):
            raise NotImplementedError(
                "cpu_highway: dot_prod() arguments must be bare identifiers.")
        n_a = (len(self._array_constants[a.name])
               if a.name in self._array_constants
               else self._lookup_local_array_size(a.name))
        n_b = (len(self._array_constants[b.name])
               if b.name in self._array_constants
               else self._lookup_local_array_size(b.name))
        if n_a != n_b:
            raise NotImplementedError(
                f"cpu_highway: dot_prod() length mismatch "
                f"({a.name}: {n_a} vs {b.name}: {n_b}).")
        n = n_a
        ba, bb = _uname(a.name), _uname(b.name)
        a_vals = self._fold_array_constants(a.name)
        b_vals = self._fold_array_constants(b.name)
        # Helper-friendly path: exactly one operand is a foldable
        # array constant.  Identify which is the "coefficient"
        # side and which is the "runtime array" side.
        coeff_vals = None
        runtime_arr = None
        if a_vals is not None and b_vals is None:
            coeff_vals, runtime_arr = a_vals, bb
        elif a_vals is None and b_vals is not None:
            coeff_vals, runtime_arr = b_vals, ba
        elif a_vals is not None and b_vals is not None \
                and all(v is not None for v in a_vals):
            # Both operands are constant arrays (the folder folds the
            # global-constant case in the expression's width; a local
            # constant reaches here): the scalar helper multiplies and
            # adds in the arrays' C++ type (every operation rounds to
            # its type), rather than an inline chain of binary64
            # literals.
            coeff_name = self._register_constexpr_array(
                'gelb_dp_coeff', 'double', tuple(float(v) for v in a_vals))
            idx_name = self._register_constexpr_array(
                'gelb_dp_idx', 'int', tuple(range(n)))
            scalar = f'gelb::gelb_dot_prod_const({coeff_name}, {bb}, {idx_name})'
            if self._simd_mode == 'vec8d':
                # a dot_prod is taken to yield V in the SIMD body
                return f'hn::Set(d, {scalar})'
            return scalar
        if coeff_vals is not None:
            survived = [(float(coeff_vals[i]), i) for i in range(n)
                        if coeff_vals[i] is not None]   # every term, zeros included
            if not survived:
                return '0.0'
            pos_idx = [i for c, i in survived
                       if c > 0 and abs(c) == 1.0]
            neg_idx = [i for c, i in survived
                       if c < 0 and abs(c) == 1.0]
            all_unit = (len(pos_idx) + len(neg_idx)
                        == len(survived))
            # Common +/-1 case (D2Q9/D3Q19 momentum reductions):
            # both pos_idx and neg_idx non-empty, all coefficients
            # are +/-1.  Fall through to the inline emit when one
            # side is empty (the helper signature requires Mp >= 1
            # and Mn >= 1 -- zero-size template-array params are
            # awkward).  This is fine: most LBM stencils have
            # both signs in the moment vectors.
            ds_arg = 'd, ' if self._simd_mode == 'vec8d' else ''
            if all_unit and pos_idx and neg_idx:
                # Route to the descriptor-aware multi-acc helper.
                # Four independent accumulators on each side
                # (pos + neg); final ``hn::Sub``.
                pos_name = self._register_constexpr_array(
                    'gelb_dp_pos', 'int', tuple(pos_idx))
                neg_name = self._register_constexpr_array(
                    'gelb_dp_neg', 'int', tuple(neg_idx))
                return (f'gelb::gelb_signed_sum({ds_arg}{runtime_arr}, '
                        f'{pos_name}, {neg_name})')
            # General (some non-+/-1 coefficient, or all-positive /
            # all-negative): use ``gelb_dot_prod_const`` --
            # 4-way multi-acc with FMA per stream.
            if not all_unit:
                coeff_name = self._register_constexpr_array(
                    'gelb_dp_coeff', 'double',
                    tuple(c for c, _ in survived))
                idx_name = self._register_constexpr_array(
                    'gelb_dp_idx', 'int',
                    tuple(i for _, i in survived))
                return (f'gelb::gelb_dot_prod_const({ds_arg}'
                        f'{coeff_name}, {runtime_arr}, '
                        f'{idx_name})')
            # All-positive +/-1 or all-negative +/-1: fall through to
            # the inline emit for now (rare in LBM).
        # Fallback: both runtime, both foldable, or all-positive /
        # all-negative +/-1.  Keep the original inline emit, every term
        # included (a zero coefficient is a ``0.0 * x`` term).
        terms = []
        for i in range(n):
            ca = a_vals[i] if a_vals is not None else None
            cb = b_vals[i] if b_vals is not None else None
            lhs = self._operand_for_coeff(ca, f'{ba}[{i}]')
            rhs = self._operand_for_coeff(cb, f'{bb}[{i}]')
            if lhs is None and rhs is None:
                terms.append(('+', f'{ba}[{i}] * {bb}[{i}]'))
            else:
                sign, body = self._merge_signed_product(lhs, rhs,
                                                         f'{ba}[{i}]',
                                                         f'{bb}[{i}]')
                terms.append((sign, body))
        if not terms:
            return '0.0'
        return '(' + self._join_signed_terms(terms) + ')'

    def _emit_intrinsic_bounce_back_dfs(self, call, df_var):
        """Read +c_i, opp(i), falling back to the entire current cell.

        Slice and array emission unroll this intrinsic so offsets and
        opposite indices are compile-time integers. SIMD peels unsafe
        x lanes; y/z guards are uniform across a vector. CUDA inherits
        the scalar path and its short-circuit conditional loads.
        """
        if df_var is None or not df_var.isdigit():
            raise NotImplementedError("bounce_back_dfs needs an unrolled DF index")
        i = int(df_var)
        args = call.arguments
        vel = args[-1]
        if self._d == 1:
            key = (vel.name,)
        else:
            elems = vel.elements if isinstance(vel, List_N) else vel.value
            key = tuple(e.name for e in elems)
        offsets = [int(eval_const_expr(self._array_constants[name][i],
                                       ast=self.ast,
                                       lattice_info=self._lattice_info))
                   for name in key]
        opposite = self._opp_tables[key][1][i]
        coords = [self._emit_coord_scalar(c) for c in args[1:-1]]
        targets, guards = [], []
        for axis, (coord, off, size) in enumerate(
                zip(coords, offsets, self._grid_sizes())):
            target = f'({coord} + ({off}))' if off else coord
            if off and is_periodic(self._lattice_info, axis):
                if abs(off) > 1 and axis not in self._wrap_safe_axes:
                    target = f'(({target} % {size} + {size}) % {size})'
            elif off and not (axis == 0 and self._simd_mode == 'vec8d'):
                guards.append(f'({target} >= 0 && {target} < {size})')
            targets.append(target)
        lname = args[0].name
        neighbour = self._emit_simd_lattice_load(
            lname, targets, df_idx_str=str(opposite), x_offset=offsets[0])
        if not guards:
            return neighbour
        local = self._emit_simd_lattice_load(
            lname, coords, df_idx_str=str(opposite), x_offset=0)
        return f'(({" && ".join(guards)}) ? {neighbour} : {local})'

    def _emit_intrinsic_matmul(self, call: IntrinsicFunctionCall_N,
                           df_var: str | None) -> str:
        # matmul appearing inside a slice-DF expression -- i.e.
        # the user wrote ``f.out[x,y|:] = matmul(M, v)`` (or used
        # ``matmul(M, v)`` as a sub-expression in a slice loop).
        # In that context the slice emitter has bound df_var to
        # ``gelb_df`` and we want this call to evaluate to the
        # df_var-th element of the matmul result, i.e.
        #   sum_j M[gelb_df][j] * v[j]
        # Outside a slice loop, matmul-as-expression isn't
        # supported (use the ``array[real, n] var = matmul(...)``
        # form instead, which routes through
        # _emit_matmul_into_array).
        if df_var is None:
            raise NotImplementedError(
                "matmul as a bare expression is only supported "
                "inside a slice-DF assignment (where the row "
                "index is the gelb_df loop counter).  For other "
                "uses, lift it into a temporary: "
                "`array[real, n] tmp = matmul(M, v);`.")
        if len(call.arguments) != 2:
            raise NotImplementedError(
                f"matmul: 2 args expected, got {len(call.arguments)}.")
        Marg, varg = call.arguments
        if not isinstance(Marg, Identifier_N) or \
                not isinstance(varg, Identifier_N):
            raise NotImplementedError(
                "matmul: both args must be bare identifiers.")
        if Marg.name not in self._array_constants_2d:
            raise NotImplementedError(
                f"matmul: first argument {Marg.name} must be a "
                f"2-D array constant.")
        _, ncols = self._array_constants_2d[Marg.name]
        if varg.name in self._array_locals:
            v_len = self._lookup_local_array_size(varg.name)
        elif varg.name in self._array_constants:
            v_len = len(self._array_constants[varg.name])
        else:
            raise NotImplementedError(
                f"matmul: unknown vector argument '{varg.name}'.")
        if v_len != ncols:
            raise NotImplementedError(
                f"matmul: M cols ({ncols}) != v len ({v_len}).")
        Mg = _uname(Marg.name)
        vg = _uname(varg.name)
        # ``M`` is a global constexpr 2-D array (double[][]); in
        # SIMD mode the user vector ``v`` is V[], so each
        # ``M[i][j] * v[j]`` mixes scalar * V -- wrap M with
        # ``hn::Set(d, ...)`` so Highway's V*V operator overload
        # resolves.
        if self._simd_mode == 'vec8d':
            terms = ' + '.join(
                f'hn::Set(d, {Mg}[{df_var}][{j}]) * {vg}[{j}]'
                for j in range(ncols))
        else:
            terms = ' + '.join(
                f'{Mg}[{df_var}][{j}] * {vg}[{j}]'
                for j in range(ncols))
        return f'({terms})'

    def _lookup_local_array_size(self, name: str) -> int:
        """Walk the AST to find the array size of a local declaration.
        Used when emitting ``sum(name)`` and we need to know how many
        terms to unroll.
        """
        # Runtime-injected temps (e.g. matmul lifts) are recorded
        # directly in _local_array_sizes -- check that first since
        # they're not in the AST.
        if name in self._local_array_sizes:
            return self._local_array_sizes[name]
        for block_list in (self.ast.initializers, self.ast.dynamics,
                           self.ast.gauges):
            if block_list is None:
                continue
            for block in block_list:
                for stmt in block.stmts:
                    if (isinstance(stmt, VariableDeclarationStmt_N)
                            and stmt.name.name == name):
                        sz = self._array_decl_size(stmt)
                        if sz is not None:
                            return sz
        raise NotImplementedError(
            f"cpu_highway: could not determine size of local array '{name}'.")
