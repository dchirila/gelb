"""Expression and intrinsic-call emission for cpu_highway.

The recursive expression dispatcher and the intrinsic lowering
(sum / dot_prod / matmul / bounce_back_dfs / random / math intrinsics),
in both scalar and SIMD modes.
"""

from __future__ import annotations

from gelb.backends.highway.addressing import ConstCoord
from gelb.backends.highway.simd_types import EmittedValue, ScalarFallbackRequired

from gelb.type_table import UnifiedTypeTable as Types

import math

from gelb.backends.real_literals import cpp_real

from gelb.backends.highway.common import (
    _TYPE_MAP,
    _uname,
    int64_literal,
    int64_typed_literal,
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
    Node_N,
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
from gelb.midware.ast_eval import is_periodic
from gelb.midware.ast_simplify import is_pure, numeric_kind


class ConstantOperand(str):
    """Rendered scalar operand retaining its exact, already typed value."""

    def __new__(cls, text, value, *, int64=False):
        assert type(value) in (int, float)
        result = super().__new__(cls, text)
        result.constant = value if type(value) is int or math.isfinite(value) else None
        result.int64 = int64
        return result


def _int_to_binary32(n: int) -> float:
    """The binary32 value nearest the integer ``n``, ties to even."""
    m = abs(n)
    shift = m.bit_length() - 24
    if shift <= 0:
        return float(n)
    q, r = divmod(m, 1 << shift)
    half = 1 << (shift - 1)
    if r > half or (r == half and q & 1):
        q += 1
    return math.copysign(float(q << shift), n)


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
# or ``atan2`` has no vector form, so such a block takes the scalar
# path (``_emit_intrinsic_call``).  ``atan2`` is
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

    def _local_array_type(self, name):
        block = self._current_block
        sdef = block.symbol_defs.get_symbol_definition_local(name) if block is not None else None
        kind = sdef.canonical_type if sdef is not None else None
        return kind if kind is not None and kind.is_array else None

    def _constant_vector(self, name):
        constant = self.backend_context.global_constants.get(name)
        return constant if constant is not None and len(constant.dims) == 1 else None

    def _constant_values(self, name):
        constant = self._constant_vector(name)
        return constant.folded if constant is not None else None

    def _array_size(self, name):
        local = self._local_array_type(name)
        if local is not None and local.rank == 1:
            return local.dims[0]
        constant = self._constant_vector(name)
        if constant is not None:
            return constant.dims[0]
        raise NotImplementedError(f"cpu_highway: no one-dimensional array '{name}' in this scope.")

    def _emit_implicit_timestep(self) -> str:
        """The implicit ``t`` as an ``int64`` operand: the host's step
        counter.  A backend whose counter lives elsewhere overrides
        this."""
        return 'static_cast<int64_t>(gelb_timestep)'

    def _emit_expression(self, expr, df_var: str | None = None) -> str:
        """The C++ source of ``expr`` alone, for callers outside block
        bodies (global constants, indices, CUDA)."""
        return self._emit_typed_expr(expr, df_var).code

    def _value(self, node, code, lane_kind='scalar', vec_int_origin=None) -> EmittedValue:
        dtype = getattr(getattr(node, 'inferred_type', None), 'element_dtype', None)
        return EmittedValue(code, dtype, _TYPE_MAP.get(dtype, 'double'),
                            lane_kind, vec_int_origin)

    @staticmethod
    def _coerce_to_vec(value: EmittedValue) -> str:
        """``value`` as a ``V``: Highway converts neither a scalar nor a
        mask to a vector implicitly."""
        if value.lane_kind == 'vec':
            return value.code
        if value.lane_kind == 'mask':
            return f'hn::IfThenElse({value.code}, hn::Set(d, 1.0), hn::Set(d, 0.0))'
        return f'hn::Set(d, {value.code})'

    @staticmethod
    def _coerce_to_mask(value: EmittedValue) -> str:
        """``value`` as an ``hn::Mask<D>``: a scalar bool is the same in
        every lane."""
        if value.lane_kind == 'mask':
            return value.code
        return f'hn::FirstN(d, ({value.code}) ? hn::Lanes(d) : 0)'

    def _require_wide(self, node) -> None:
        """A vector body holds binary64 lanes only: a value of a narrow
        width sends the block to the scalar path, where every operation
        rounds to its width (user manual, Numerical semantics: Types and
        promotion)."""
        dtype = getattr(getattr(node, 'inferred_type', None), 'element_dtype', None)
        if self._simd_mode == 'vec8d' and dtype in Types.narrow_array_types:
            raise ScalarFallbackRequired(f'a {dtype} value has no vector form')

    def _require_vector_reduction(self, *arrays) -> None:
        """``sum``, ``dot_prod`` and ``matmul`` have exact vector helpers
        for real arrays and for global constant integer arrays (an
        integer velocity set); an integer array local to the block has
        scalar helpers only."""
        if self._simd_mode != 'vec8d':
            return
        for array in arrays:
            self._require_wide(array)
            local = (self._local_array_type(array.name)
                     if isinstance(array, Identifier_N) else None)
            if local is not None and local.dtype in Types.integer_types:
                raise ScalarFallbackRequired(
                    f"a reduction over the integer array '{array.name}' has no vector form")

    def _has_integer_division(self, expr) -> bool:
        """True iff ``expr`` holds an integer ``/``: evaluating it stops
        the program when the divisor is zero."""
        dtype = getattr(getattr(expr, 'inferred_type', None), 'element_dtype', None)
        if isinstance(expr, Div_N) and dtype in Types.integer_types:
            return True
        return (isinstance(expr, Node_N)
                and any(self._has_integer_division(c) for c in expr.get_children()))

    def _emit_typed_expr(self, expr, df_var: str | None = None) -> EmittedValue:
        """Emit ``expr`` once, with the way its value is held.

        In a vector body the result says whether the C++ value is one
        scalar for the whole iteration, a ``V`` or a mask, and the forms
        with no vector equivalent raise ``ScalarFallbackRequired``: a
        narrow width, and an integer that varies from cell to cell other
        than the two a ``V`` holds exactly (a reference to x or to an
        ``int`` local declared from it, and the integer of a per-cell
        truth value).  An integer computed as a double would round where
        its type says exact (user manual, Numerical semantics: Types and
        promotion)."""
        value = self._emit_typed_node(expr, df_var)
        if self._simd_mode == 'vec8d':
            self._require_wide(expr)
            dtype = getattr(getattr(expr, 'inferred_type', None), 'element_dtype', None)
            exact = (isinstance(expr, Identifier_N)
                     or (isinstance(expr, (TypePromotionNode_N, IntrinsicFunctionCall_N))
                         and value.vec_int_origin == 'bool_int_cast'))
            if (value.lane_kind != 'scalar' and dtype in Types.integer_types
                    and not exact):
                raise ScalarFallbackRequired(
                    'an integer that varies from cell to cell has no vector form')
        return value

    def _emit_typed_operand(self, expr, df_var: str | None = None, *,
                            int64_op: bool = False) -> EmittedValue:
        """An operand of an expression.  For an operand of an ``int64``
        operation (``int64_op``: ``+ - * /``, ``^``, unary minus,
        ``abs``) an integer literal, also broadcast over a slice or taken
        from an array literal, is written with the operation's int64
        width (``2147483647LL``), whatever its own type (a folded
        ``int32`` constant passed to an ``int`` parameter is an int64
        operand there): a bare C++ literal is a 32-bit ``int``, and
        an operation with two of them is computed in 32 bits where GeLB
        computes in int64 (user manual, Numerical semantics: Types and
        promotion).  With every literal operand so written, every
        ``int64`` operation has 64-bit operands, whatever the folds keep
        or combine.  An index (``_emit_coord_scalar``) keeps its literals
        bare."""
        node = expr
        while isinstance(node, BroadcastNode_N):
            node = node.scalar_expr
        if (isinstance(node, Array1DLiteral_N) and df_var is not None
                and df_var.lstrip('-').isdigit()):
            elements = node.value.elements
            if 0 <= int(df_var) < len(elements):
                node = elements[int(df_var)]
        if (int64_op and not self._in_coord_scalar
                and isinstance(node, IntLiteral_N)):
            return self._value(node, ConstantOperand(
                int64_typed_literal(int(node.value)), int(node.value), int64=True))
        return self._emit_typed_expr(expr, df_var)

    def _emit_typed_identifier(self, expr, df_var) -> EmittedValue:
        # `t` and `Nx`/`Ny`/`Nz` are GeLB `int`, int64; their C++
        # carriers are `int` (NetCDF and loop bounds want them so):
        # widened where a user expression reads them.
        tag = getattr(expr, 'symbol_tag', None)
        if tag == "implicit timestep variable":
            return self._value(expr, self._emit_implicit_timestep())
        if tag == "implicit dimension constant":
            # The size parameters are `g__nx` etc.; `_uname('Nx')`
            # would name an undeclared `g_Nx`.
            return self._value(expr, f'static_cast<int64_t>(g__n{expr.name[1].lower()})')
        vector = self._simd_mode == 'vec8d'
        if expr.name in ('x', 'y', 'z'):
            # In a vector body the x coordinate varies across the lanes:
            # the lane vector declared at the top of each iteration.  y
            # and z are constant within one iteration of the inner
            # x-loop.
            if expr.name == 'x' and vector:
                return self._value(expr, 'gelb_xv', 'vec', 'coord_x')
            if expr.name in self._axis_bindings:
                return self._value(expr, ConstantOperand(
                    int64_typed_literal(self._axis_bindings[expr.name]),
                    self._axis_bindings[expr.name], int64=True))
            return self._value(expr, f'g_{expr.name}')
        # Array variables -- local or global -- referenced inside a
        # for-df slice loop become element accesses.  Outside such a
        # loop, bare-name access is only allowed for scalars; an
        # array-typed identifier here would be a whole-array
        # operation (e.g. sum(EX) -- handled at the IntrinsicFunctionCall
        # level, never reached here as a bare identifier).
        base = _uname(expr.name)
        carrier = self._simd_env.carrier(expr.name) if vector else None
        lane_kind = {'vec': 'vec', 'vec_int': 'vec', 'mask': 'mask'}.get(carrier, 'scalar')
        is_array = (self._local_array_type(expr.name) is not None
                    or self._constant_vector(expr.name) is not None)
        if is_array and df_var is not None:
            # Constant-fold accesses into a constexpr array
            # constant when the index is a literal integer.
            # Without this, ``EX[3]`` (with EX = {..., -1.0, ...})
            # emits as ``g_EX[3]`` and gcc keeps ``g_EX[3] * x``
            # as a multiplication even though the value is -1
            # (IEEE-754 strictness).  Inlining the literal lets
            # the compiler see ``-1.0 * x`` and fold it to ``-x``.
            # An integer array's element is its exact value (an
            # int64 above 2^53 keeps its low bits), carrying its
            # int64 width into the expression; a real one is a
            # literal of the array's width.
            if (df_var.lstrip('-').isdigit()
                    and self._constant_vector(expr.name) is not None):
                vals = self._constant_values(expr.name)
                if vals is not None:
                    idx = int(df_var)
                    if 0 <= idx < len(vals):
                        value = vals[idx]
                        cpp = _TYPE_MAP.get(getattr(expr.inferred_type, 'element_dtype', 'real'), 'double')
                        text = (cpp_real(value, cpp) if type(value) is float
                                else int64_typed_literal(value))
                        return self._value(expr, ConstantOperand(text, value, int64=type(value) is int)
                                           if type(value) is int or cpp == 'double' else text)
            return self._value(expr, f'{base}[{df_var}]', lane_kind)
        return self._value(expr, base, lane_kind,
                           'local' if carrier == 'vec_int' else None)

    def _emit_typed_node(self, expr, df_var) -> EmittedValue:
        vector = self._simd_mode == 'vec8d'
        if isinstance(expr, IntLiteral_N):
            return self._value(expr, ConstantOperand(int64_literal(expr.value), int(expr.value)))
        if isinstance(expr, RealLiteral_N):
            kind = getattr(getattr(expr, 'inferred_type', None), 'element_dtype', None)
            cpp_type = Types.cpp.get(kind, 'double')
            text = cpp_real(expr.value, cpp_type)
            return self._value(expr, ConstantOperand(text, float(expr.value))
                               if cpp_type == 'double' else text)
        if isinstance(expr, BoolLiteral_N):
            return self._value(expr, 'true' if expr.value in (True, 'true') else 'false')
        if isinstance(expr, Identifier_N):
            return self._emit_typed_identifier(expr, df_var)
        if isinstance(expr, (Add_N, Sub_N, Mul_N, Div_N)):
            kind = numeric_kind(getattr(expr, 'inferred_type', None))
            a = self._emit_typed_operand(expr.left, df_var, int64_op=kind == 'int64')
            b = self._emit_typed_operand(expr.right, df_var, int64_op=kind == 'int64')
            op = {Add_N: '+', Sub_N: '-', Mul_N: '*', Div_N: '/'}[type(expr)]
            if a.lane_kind == b.lane_kind == 'scalar':
                # Two scalars: the exact identities and folds apply.
                if isinstance(expr, Div_N):
                    return self._value(expr, f'({a.code} / {b.code})')
                return self._value(expr, self._constant_binop(expr, a.code, b.code, kind))
            # A vector operand: the other one is broadcast first, and the
            # operation stays written (an identity such as ``1.0 * v`` is
            # not applied across a vector).
            return self._value(
                expr, f'({self._coerce_to_vec(a)} {op} {self._coerce_to_vec(b)})', 'vec')
        if isinstance(expr, Pow_N):
            base = self._emit_typed_operand(
                expr.left, df_var, int64_op=numeric_kind(
                    getattr(expr, 'inferred_type', None)) == 'int64')
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
                        # One, in the power's own type: a scalar that a
                        # consuming vector operation broadcasts.  The bare
                        # C++ literal ``1`` is a 32-bit ``int``: a quotient
                        # of such powers was an integer division, and a
                        # product with ``int`` literals wrapped at 2^31
                        # (user manual, Numerical semantics: Types and
                        # promotion).  An integer one is a cast to the
                        # power's own width (``int32(k)^0`` is int32).
                        kind0 = getattr(getattr(expr, 'inferred_type', None),
                                        'element_dtype', None)
                        cpp0 = _TYPE_MAP.get(kind0)
                        if cpp0 == 'double':
                            return self._value(expr, ConstantOperand('1.0', 1.0))
                        if cpp0 == 'float':
                            return self._value(expr, '1.0f')
                        if base.lane_kind != 'scalar':
                            # An integer power of a per-cell value is
                            # integer arithmetic on it, whatever the
                            # exponent.
                            raise ScalarFallbackRequired(
                                'an integer power of a per-cell value has no vector form')
                        return self._value(expr, f'static_cast<{cpp0 or "int64_t"}>(1)')
                    if k == 1:
                        return base
                    return self._value(expr, '(' + ' * '.join([base.code] * k) + ')',
                                       base.lane_kind)
            if vector:
                raise ScalarFallbackRequired('a power that is not unrolled has no vector form')
            exp_e = self._emit_expression(expr.right, df_var)
            kind = getattr(getattr(expr, 'inferred_type', None), 'element_dtype', None)
            if kind is not None and kind.startswith('int'):
                # An integer raised to an integer is exact integer
                # arithmetic with Fortran's negative-exponent rule (user
                # manual, Numerical semantics: Types and promotion), not
                # a double pow.
                return self._value(expr, f'gelb::gelb_ipow<{_TYPE_MAP[kind]}>({base.code}, {exp_e})')
            # A real base: backend-defined; the platform's pow.
            return self._value(expr, f'std::pow({base.code}, {exp_e})')
        if isinstance(expr, UnaryMinusExpr_N):
            kind = numeric_kind(getattr(expr, 'inferred_type', None))
            inner = self._emit_typed_operand(expr.value, df_var, int64_op=kind == 'int64')
            if inner.lane_kind == 'vec':
                # Highway has no unary ``operator-`` overload on V --
                # use ``hn::Neg`` for explicit lane-wise negation.
                return self._value(expr, f'hn::Neg({inner.code})', 'vec')
            return self._value(
                expr, self._negate(inner.code, kind is not None and kind.startswith('int')),
                inner.lane_kind)
        if isinstance(expr, RectSelOfLatticeInDFs_N):
            return self._value(expr, self._emit_lattice_in(expr, df_var),
                               'vec' if vector else 'scalar')
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
            # A real local array is a ``V[]`` in a vector body; an
            # integer or bool one and a global constant hold scalars.
            held = vector and self._simd_env.carrier(arr_name) == 'vec'
            return self._value(expr, f'{_uname(arr_name)}[{idx_str}]',
                               'vec' if held else 'scalar')
        if isinstance(expr, Array1DLiteral_N):
            elements = expr.value.elements
            # The caller is unrolling a whole-array operation and passes
            # a literal index string ('0', '1', ...): the corresponding
            # element, emitted by itself, with its own lane kind.
            if df_var is not None and df_var.lstrip('-').isdigit():
                idx = int(df_var)
                if 0 <= idx < len(elements):
                    return self._emit_typed_expr(elements[idx])
            raise NotImplementedError(
                "cpu_highway: array literals require a constant element index; "
                "prepare the C-family AST before code generation.")
        if isinstance(expr, BroadcastNode_N):
            return self._emit_typed_expr(expr.scalar_expr, df_var)
        if isinstance(expr, IntrinsicFunctionCall_N):
            return self._emit_intrinsic_call(expr, df_var)
        if isinstance(expr, TypePromotionNode_N):
            tgt = expr.target_type
            tgt_elem = (getattr(tgt, 'element_dtype', None)
                        or getattr(tgt, 'name', 'double'))
            cpp_tgt = _TYPE_MAP.get(tgt_elem, 'double')
            inner_df = '0' if expr.is_singleton_coercion() else df_var
            return self._cast_value(expr, self._emit_typed_expr(expr.expr, inner_df), cpp_tgt)
        # Comparison operators -- on scalars a C++ bool (implicitly
        # convertible to int / double in arithmetic contexts); on a
        # vector Highway's free-function comparison ops, which return
        # ``hn::Mask<D>``.  Highway has no comparison ``operator<`` /
        # ``operator==`` etc. on V (only the ``Vec128<XXX, N>`` overloads
        # exist for 8/16/32-bit unsigned-int lanes), so the function form
        # is the only portable shape.
        _CMP_HWY = {
            'Equal_N':        'hn::Eq',
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
            a = self._emit_typed_expr(expr.left, df_var)
            b = self._emit_typed_expr(expr.right, df_var)
            if 'mask' in (a.lane_kind, b.lane_kind):
                # ``==`` / ``!=`` between per-cell bools (the frontend
                # rejects an order on bool): both sides are masks, a
                # uniform scalar bool broadcasts.  Highway has no
                # ``Eq`` / ``Ne`` on masks; ``Xor`` is ``!=``.
                differ = f'hn::Xor({self._coerce_to_mask(a)}, {self._coerce_to_mask(b)})'
                return self._value(
                    expr, differ if cmp_kind == 'NotEqual_N' else f'hn::Not({differ})', 'mask')
            if 'vec' in (a.lane_kind, b.lane_kind):
                a_code, b_code = self._coerce_to_vec(a), self._coerce_to_vec(b)
                if cmp_kind == 'NotEqual_N':
                    # ``hn::Ne`` is the *ordered* comparison with
                    # AVX2 or AVX-512 (``_CMP_NEQ_OQ``): false when a
                    # lane is NaN, where IEEE 754, the scalar path,
                    # Fortran, NEON and SSE say true.  ``Not(Eq)`` is
                    # the unordered inequality on every target.
                    return self._value(expr, f'hn::Not(hn::Eq({a_code}, {b_code}))', 'mask')
                return self._value(expr, f'{_CMP_HWY[cmp_kind]}({a_code}, {b_code})', 'mask')
            return self._value(expr, f'({a.code} {_CMP_OP[cmp_kind]} {b.code})')
        # Boolean ops on masks -> ``hn::And`` / ``hn::Or`` / ``hn::Not``;
        # on scalars ``&&`` / ``||`` / ``!``.  A uniform scalar operand
        # (for example a comparison of t) broadcasts when the other
        # operand is a mask, for ``&&`` and ``||`` as for ``==`` and
        # ``!=``.  ``hn::And`` and ``hn::Or`` evaluate both operands, and
        # ``&&`` and ``||`` do not evaluate the right one when the left
        # one decides: a right operand with an integer division, which
        # the left one may guard (``t > 0 && 10 / t > 2``), has no vector
        # form.
        if isinstance(expr, NotExpr_N):
            value = self._emit_typed_expr(expr.value, df_var)
            if value.lane_kind == 'mask':
                return self._value(expr, f'hn::Not({value.code})', 'mask')
            return self._value(expr, f'(!{value.code})')
        if isinstance(expr, (And_N, Or_N)):
            a = self._emit_typed_expr(expr.left, df_var)
            b = self._emit_typed_expr(expr.right, df_var)
            if 'mask' in (a.lane_kind, b.lane_kind):
                if self._has_integer_division(expr.right):
                    raise ScalarFallbackRequired(
                        'the right operand of && or || holds an integer division')
                name = 'hn::And' if isinstance(expr, And_N) else 'hn::Or'
                return self._value(
                    expr, f'{name}({self._coerce_to_mask(a)}, {self._coerce_to_mask(b)})', 'mask')
            op = '&&' if isinstance(expr, And_N) else '||'
            return self._value(expr, f'({a.code} {op} {b.code})')
        raise NotImplementedError(
            f"cpu_highway: unsupported expression: {type(expr).__name__} "
            f"(grow this method as more constructs are added).")

    def _cast_value(self, node, inner: EmittedValue, cpp_target: str) -> EmittedValue:
        """``inner`` converted to ``cpp_target``, the type of ``node`` (a
        promotion or a cast intrinsic).

        A scalar is a ``static_cast``.  In a vector body a binary64
        vector is its own conversion to ``real``, and a mask becomes 1.0
        or 0.0 per lane, for ``real`` and for ``int``: every consumer of
        such an integer promotes it back to double, Highway has no
        implicit promotion between an int64 and a double vector, and the
        round trip of 0 and 1 is exact.  Every other conversion of a
        per-cell value (to an integer, to a narrow width) has no vector
        form."""
        if inner.lane_kind == 'scalar':
            return self._value(node, f'static_cast<{cpp_target}>({inner.code})')
        if inner.lane_kind == 'mask' and cpp_target in ('double', 'int64_t'):
            return self._value(
                node, f'hn::IfThenElse({inner.code}, hn::Set(d, 1.0), hn::Set(d, 0.0))',
                'vec', 'bool_int_cast' if cpp_target == 'int64_t' else None)
        if inner.lane_kind == 'vec' and cpp_target == 'double':
            return self._value(node, inner.code, 'vec')
        raise ScalarFallbackRequired(
            f'a per-cell value has no vector conversion to {cpp_target}')

    def _emit_intrinsic_call(self, call: IntrinsicFunctionCall_N,
                             df_var: str | None) -> EmittedValue:
        """Emit C++ for an intrinsic-function call expression.

        Pure dispatch -- each intrinsic family has a dedicated
        ``_emit_intrinsic_*`` helper below.  ``mod``, ``atan2`` and the
        width-specific casts have no vector form: such a call sends the
        block to the scalar path, so that every cell takes the same one
        (user manual, Numerical semantics: Types and promotion, Library
        functions).  A reduction, a streamed read and ``random()`` are
        vectors in a vector body whatever their arguments.
        """
        fname = call.function_name
        vector = self._simd_mode == 'vec8d'
        if vector and (fname in ('mod', 'atan2') or fname in Types.width_casts):
            raise ScalarFallbackRequired(f'{fname}() has no vector form')
        lane_kind = 'vec' if vector else 'scalar'
        if fname == 'sum':
            return self._value(call, self._emit_intrinsic_sum(call, df_var), lane_kind)
        if fname == 'random':
            return self._value(call, self._emit_intrinsic_random(call), lane_kind)
        if fname in CAST_INTRINSIC_NAMES:
            return self._emit_intrinsic_cast(call, df_var)
        if fname in _UNARY_MATH_SET:
            return self._emit_intrinsic_unary_math(call, df_var)
        if fname in _BINARY_MATH_SCALAR:
            return self._emit_intrinsic_binary_math(call, df_var)
        if fname == 'dot_prod':
            return self._value(call, self._emit_intrinsic_dot_prod(call), lane_kind)
        if fname == 'bounce_back_dfs':
            return self._value(call, self._emit_intrinsic_bounce_back_dfs(call, df_var),
                               lane_kind)
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
            return self._value(call, self._emit_intrinsic_matmul(call, df_var), lane_kind)
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
        self._require_vector_reduction(arg)
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
                             df_var: str | None) -> EmittedValue:
        """A cast intrinsic, ``real(x)``, ``int(x)``, ``real32(x)``,
        ``int8(x)`` ...: ``static_cast<T>(x)`` with the C++ type of the
        target width (user manual, Numerical semantics: Types and
        promotion: an integer to a narrower integer wraps, a real to an
        integer truncates).  The conversions of a per-cell value are
        ``_cast_value``'s."""
        fname = call.function_name
        target = _TYPE_MAP[fname]
        if len(call.arguments) != 1:
            raise NotImplementedError(
                f"{fname}(): 1 argument expected.")
        return self._cast_value(
            call, self._emit_typed_expr(call.arguments[0], df_var), target)

    def _emit_intrinsic_unary_math(self, call: IntrinsicFunctionCall_N,
                                   df_var: str | None) -> EmittedValue:
        fname = call.function_name
        unary_simd_spelling = _UNARY_SIMD_SPELLING
        unary_simd_takes_descriptor = _UNARY_SIMD_TAKES_DESCRIPTOR
        if len(call.arguments) != 1:
            raise NotImplementedError(
                f"cpu_highway: {fname}() expects 1 argument.")
        arg_node = call.arguments[0]
        inner = self._emit_typed_operand(
            arg_node, df_var, int64_op=fname == 'abs' and numeric_kind(
                getattr(call, 'inferred_type', None)) == 'int64')
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
            return self._value(call, f'gelb::gelb_{fname}({inner.code})', inner.lane_kind)
        # sqrt and abs are core ops, exact on every path; CUDA and a
        # real32 argument use the platform's library, one implementation
        # on that backend.
        if inner.lane_kind == 'vec':
            if fname in unary_simd_takes_descriptor:
                return self._value(call, f'{unary_simd_spelling[fname]}(d, {inner.code})', 'vec')
            return self._value(call, f'{unary_simd_spelling[fname]}({inner.code})', 'vec')
        return self._value(call, f'std::{fname}({inner.code})')

    def _emit_intrinsic_binary_math(self, call: IntrinsicFunctionCall_N,
                                    df_var: str | None) -> EmittedValue:
        fname = call.function_name
        binary_map_scalar = _BINARY_MATH_SCALAR
        if len(call.arguments) != 2:
            raise NotImplementedError(
                f"cpu_highway: {fname}() expects 2 arguments.")
        a = self._emit_typed_expr(call.arguments[0], df_var)
        b = self._emit_typed_expr(call.arguments[1], df_var)
        if 'vec' in (a.lane_kind, b.lane_kind):
            # ``min`` / ``max`` with a vector operand: the lane-wise
            # overloads on V, the other operand broadcast.  Two scalars
            # go to the scalar helper, also in a vector body.
            return self._value(
                call, f'{binary_map_scalar[fname]}({self._coerce_to_vec(a)}, '
                      f'{self._coerce_to_vec(b)})', 'vec')
        if fname in _BINARY_MATH_TYPED:
            return self._value(
                call, f'{binary_map_scalar[fname]}<{self._cpp_type_of(call)}>({a.code}, {b.code})')
        return self._value(call, f'{binary_map_scalar[fname]}({a.code}, {b.code})')

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
        # ``+``-chain emit.  A constant real array with an integer
        # array, in either order, is written out as well
        # (``_emit_dot_prod_real_coeffs_int_array``): the helpers would
        # compute in the integer type or convert through binary64.
        #
        # A constant ``real`` array with a per-cell ``real32`` array has
        # a ``real`` result, and each element converts before it is
        # multiplied (user manual, Numerical semantics: Types and
        # promotion).  The two helpers above take their type from the
        # array they read, so this case names the result's type through
        # ``gelb_signed_sum_as`` / ``gelb_dot_prod_const_as``, which add
        # in the same order, and the written-out chain converts each
        # element.  Operands of one width keep the deducing helpers.
        if len(call.arguments) != 2:
            raise NotImplementedError(
                "cpu_highway: dot_prod() expects 2 arguments.")
        a, b = call.arguments
        if not (isinstance(a, Identifier_N)
                and isinstance(b, Identifier_N)):
            raise NotImplementedError(
                "cpu_highway: dot_prod() arguments must be bare identifiers.")
        self._require_vector_reduction(a, b)
        n_a = self._array_size(a.name)
        n_b = self._array_size(b.name)
        if n_a != n_b:
            raise NotImplementedError(
                f"cpu_highway: dot_prod() length mismatch "
                f"({a.name}: {n_a} vs {b.name}: {n_b}).")
        n = n_a
        ba, bb = _uname(a.name), _uname(b.name)
        a_vals = self._constant_values(a.name)
        b_vals = self._constant_values(b.name)
        mixed = self._emit_dot_prod_real_coeffs_int_array(
            call, a, b, a_vals, b_vals, n)
        if mixed is not None:
            return mixed
        integer = self._emit_dot_prod_integer(call, a, b, a_vals, b_vals, n)
        if integer is not None:
            return integer
        # Helper-friendly path: exactly one operand is a foldable
        # array constant.  Identify which is the "coefficient"
        # side and which is the "runtime array" side.
        coeff_vals = None
        runtime_arr = None
        runtime_node = None
        if a_vals is not None and b_vals is None:
            coeff_vals, runtime_arr, runtime_node = a_vals, bb, b
            coeff_vals = self._dot_prod_coefficients(call, a, coeff_vals)
        elif a_vals is None and b_vals is not None:
            coeff_vals, runtime_arr, runtime_node = b_vals, ba, a
            coeff_vals = self._dot_prod_coefficients(call, b, coeff_vals)
        # The result's C++ type where the per-cell array is narrower
        # (``real`` coefficients with a ``real32`` array), else None.
        widened_to = None
        if coeff_vals is not None:
            acc_cpp = _TYPE_MAP.get(
                getattr(call.inferred_type, 'element_dtype', None))
            arr_cpp = _TYPE_MAP.get(
                getattr(runtime_node.inferred_type, 'element_dtype', None))
            if acc_cpp is not None and arr_cpp is not None and acc_cpp != arr_cpp:
                widened_to = acc_cpp
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
                if widened_to is not None:
                    return (f'gelb::gelb_signed_sum_as<{widened_to}>('
                            f'{runtime_arr}, {pos_name}, {neg_name})')
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
                if widened_to is not None:
                    return (f'gelb::gelb_dot_prod_const_as<{widened_to}>('
                            f'{coeff_name}, {runtime_arr}, {idx_name})')
                return (f'gelb::gelb_dot_prod_const({ds_arg}'
                        f'{coeff_name}, {runtime_arr}, '
                        f'{idx_name})')
            # All-positive +/-1 or all-negative +/-1: fall through to
            # the inline emit for now (rare in LBM).
        # Fallback: both runtime, both foldable, or all-positive /
        # all-negative +/-1.  Keep the original inline emit, every term
        # included (a zero coefficient is a ``0.0 * x`` term).
        # A real result: an integer constant's coefficients are the
        # binary64 values the helper paths see.  A narrower per-cell
        # element converts to the result's type before it is negated or
        # added.
        terms = []
        for i in range(n):
            ca = float(a_vals[i]) if a_vals is not None else None
            cb = float(b_vals[i]) if b_vals is not None else None
            raw_a, raw_b = f'{ba}[{i}]', f'{bb}[{i}]'
            if widened_to is not None and runtime_node is a:
                raw_a = f'static_cast<{widened_to}>({raw_a})'
            elif widened_to is not None:
                raw_b = f'static_cast<{widened_to}>({raw_b})'
            lhs = self._operand_for_coeff(ca, raw_a)
            rhs = self._operand_for_coeff(cb, raw_b)
            if lhs is None and rhs is None:
                terms.append(('+', f'{ba}[{i}] * {bb}[{i}]'))
            else:
                sign, body = self._merge_signed_product(lhs, rhs,
                                                         raw_a, raw_b)
                terms.append((sign, body))
        if not terms:
            return '0.0'
        return '(' + self._join_signed_terms(terms) + ')'

    def _dot_prod_coefficients(self, call, operand, values):
        """The folded coefficients of a ``dot_prod`` as the helper must
        see them: binary64 values, which it converts to the result's
        C++ type.  Integer coefficients with a ``real32`` result convert
        to binary32 directly (user manual, Numerical semantics: Types and
        promotion); one above 2^53 is already rounded in binary64, so it
        is rounded to binary32 from its exact value instead.  Every other
        value is returned as it is."""
        if (_TYPE_MAP.get(getattr(call.inferred_type, 'element_dtype',
                                  None)) != 'float'
                or _TYPE_MAP.get(getattr(operand.inferred_type,
                                         'element_dtype', None))
                not in ('int8_t', 'int16_t', 'int32_t', 'int64_t')):
            return values
        constant = self.backend_context.global_constants[operand.name]
        exact = [e.converted_value if e.converted_value is not None else e.raw_value
                 for e in constant.elements]
        return [_int_to_binary32(int(e))
                if isinstance(e, int) and float(e) != e else v
                for e, v in zip(exact, values)]

    _INTEGER_CPP_TYPES = ('int8_t', 'int16_t', 'int32_t', 'int64_t')

    def _emit_dot_prod_integer(self, call, a, b, a_vals, b_vals, n):
        """``dot_prod`` with an integer result on the scalar path,
        computed in the result's type, or None for any other call.

        Each element and each coefficient converts to the result's
        type before it is multiplied, and the products and sums are
        exact integer operations in it, never a fused multiply-add
        (user manual, Numerical semantics: Types and promotion,
        Reproducibility).  The deducing helpers would compute in the
        array's own type (an int8 array wraps at 127 under int64
        coefficients), take the coefficients as binary64 (an int64 above
        2^53 loses its low bits) and, from the fifth term, go through
        ``std::fma``, which converts to double; the typed overloads
        (``gelb_signed_sum_as``, ``gelb_dot_prod_const_as``) take the
        result's type and the coefficients exactly, so every case with a
        constant operand uses one of them.  Two per-cell arrays are
        written out as the helpers compute: each element converted to
        ``int64_t``, the products and sums in it, and one conversion of
        the sum to the result's type, which wraps a narrow result as a
        conversion after every operation would (the bare chain would
        compute two int8 elements in ``int`` and never narrow, so
        ``real(dot_prod(a8, b8))`` would see 130 where Fortran gives
        -126).  The SIMD body is left as it is: an integer array does
        not build there yet.
        """
        if self._simd_mode == 'vec8d':
            return None
        result = _TYPE_MAP.get(
            getattr(call.inferred_type, 'element_dtype', None))
        if result not in self._INTEGER_CPP_TYPES:
            return None
        ba, bb = _uname(a.name), _uname(b.name)
        if a_vals is not None:
            coeffs, array = a_vals, bb
        elif b_vals is not None:
            coeffs, array = b_vals, ba
        else:
            terms = [('+', f'static_cast<int64_t>({ba}[{i}])'
                           f' * static_cast<int64_t>({bb}[{i}])')
                     for i in range(n)]
            return (f'static_cast<{result}>('
                    + self._join_signed_terms(terms) + ')')
        pos_idx = [i for i, c in enumerate(coeffs) if c == 1]
        neg_idx = [i for i, c in enumerate(coeffs) if c == -1]
        if pos_idx and neg_idx and len(pos_idx) + len(neg_idx) == n:
            pos_name = self._register_constexpr_array(
                'gelb_dp_pos', 'int', tuple(pos_idx))
            neg_name = self._register_constexpr_array(
                'gelb_dp_neg', 'int', tuple(neg_idx))
            return (f'gelb::gelb_signed_sum_as<{result}>({array}, '
                    f'{pos_name}, {neg_name})')
        coeff_name = self._register_constexpr_array(
            'gelb_dp_coeff', 'int64_t', tuple(int(c) for c in coeffs))
        idx_name = self._register_constexpr_array(
            'gelb_dp_idx', 'int', tuple(range(n)))
        return (f'gelb::gelb_dot_prod_const_as<{result}>({coeff_name}, '
                f'{array}, {idx_name})')

    def _emit_dot_prod_real_coeffs_int_array(self, call, a, b, a_vals,
                                             b_vals, n):
        """``dot_prod`` of a constant real array with an integer array,
        in either order, or None for any other operands.

        The result is real and each integer element converts to its
        width (user manual, Numerical semantics: Types and promotion).
        The helpers take their C++ type from the array they read: with
        the integer array they would compute in it (other coefficients
        are truncated; with coefficients of +/-1 a narrow integer wraps
        and a ``real32`` sum is an exact integer sum), and with the
        integer array as their coefficients they would convert it
        through binary64.  The products are written out instead, each
        integer element converted to the result's width (a +/-1
        coefficient is the sign alone), and added in index order; GeLB
        fuses none of them.  The SIMD body is left as it is: an integer
        array does not build there yet.
        """
        if self._simd_mode == 'vec8d':
            return None
        result = _TYPE_MAP.get(
            getattr(call.inferred_type, 'element_dtype', None))
        if result not in ('double', 'float'):
            return None
        reals = ('double', 'float')
        ints = ('int8_t', 'int16_t', 'int32_t', 'int64_t')
        ta, tb = (_TYPE_MAP.get(getattr(op.inferred_type, 'element_dtype',
                                        None)) for op in (a, b))
        if ta in reals and tb in ints:
            coeffs, array = a_vals, b
        elif tb in reals and ta in ints:
            coeffs, array = b_vals, a
        else:
            return None
        # A real array computed per cell keeps the helper or the inline
        # chain, both in its own type.
        if coeffs is None or any(v is None for v in coeffs):
            return None
        name = _uname(array.name)
        terms = []
        for i in range(n):
            coeff = float(coeffs[i])
            value = f'static_cast<{result}>({name}[{i}])'
            terms.append(('-' if math.copysign(1.0, coeff) < 0 else '+',
                          value if abs(coeff) == 1.0
                          else f'{cpp_real(abs(coeff), result)} * {value}'))
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
            elems = [vel]
        else:
            elems = vel.elements if isinstance(vel, List_N) else vel.value
        for elem in elems:
            self._require_wide(elem)
        key = tuple(e.name for e in elems)
        offsets = [int(self.backend_context.global_constants[name].folded[i]) for name in key]
        opposite = self.backend_context.opp_tables[key][i]
        coords = [self._coordinate(c, axis, bounce=True)
                  for axis, c in enumerate(args[1:-1])]
        targets, guards = [], []
        lname = args[0].name
        for axis, (coord, node, off, size) in enumerate(
                zip(coords, args[1:-1], offsets, self._grid_sizes())):
            target = self._coordinate(node, axis, off, bounce=True)
            if isinstance(target, ConstCoord):
                if not 0 <= target.value < size:
                    return self._emit_simd_lattice_load(
                        lname, coords, df_idx_str=str(opposite), x_offset=0)
            elif off and not is_periodic(self._lattice_info, axis) and not (
                    axis == 0 and self._simd_mode == 'vec8d'):
                guards.append(f'({target} >= 0 && {target} < {size})')
            targets.append(target)
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
        self._require_vector_reduction(Marg, varg)
        matrix = self.backend_context.global_constants.get(Marg.name)
        if matrix is None or len(matrix.dims) != 2:
            raise NotImplementedError(
                f"matmul: first argument {Marg.name} must be a "
                f"2-D array constant.")
        _, ncols = matrix.dims
        v_len = self._array_size(varg.name)
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
        acc_cpp = _TYPE_MAP[call.canonical_type.dtype]
        if self._simd_mode != 'vec8d' and acc_cpp in ('int8_t', 'int16_t'):
            return f'static_cast<{acc_cpp}>({terms})'
        return f'({terms})'
