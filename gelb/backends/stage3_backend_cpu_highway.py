#!/usr/bin/env python3

"""
Stage 3: CPU C++ / Google Highway Backend.

Generates a standalone C++17 program from a GeLB AST that has
passed through the frontend and midware stages.  Targets the same
lattice abstractions as the Fortran backend, but emits portable
SIMD via Google Highway (vendored at ``third_party/highway/``),
which dispatches to AVX-512 / AVX-2 / NEON automatically per the
compile-host ISA.

Entry point: ``generate_cpu_highway(ast, ...)`` returns a string
containing the full ``.cpp`` source.
"""

from __future__ import annotations

import math
import os

from gelb.backends.real_literals import cpp_real
from gelb.gelb_ast.ASTNodes import (
    Add_N,
    And_N,
    Array1DLiteral_N,
    Array2DLiteral_N,
    ArrayDataType_N,
    AssignmentStmt_N,
    BoolLiteral_N,
    BroadcastNode_N,
    ConstantDefinitionStmt_N,
    Div_N,
    DynamicBlock_N,
    Equal_N,
    GaugeBlock_N,
    Greater_N,
    GreaterEqual_N,
    Identifier_N,
    InitializerBlock_N,
    IntLiteral_N,
    IntrinsicFunctionCall_N,
    LatticeInstaStmt_N,
    Less_N,
    LessEqual_N,
    List_N,
    Mul_N,
    Node_N,
    NotEqual_N,
    Or_N,
    PaintNodesStmt_N,
    Pow_N,
    Range_N,
    RectSelOfArrayElems_N,
    RealLiteral_N,
    RectSelOfLatticeInDFs_N,
    RectSelOfLatticeOutDFs_N,
    Sub_N,
    TypePromotionNode_N,
    UnaryMinusExpr_N,
    VariableDeclarationStmt_N,
)

from gelb.midware.ast_eval import (
    collect_lattice_info,
    eval_const_expr,
    get_grid_size,
    get_grid_sizes,
    get_max_dim,
    is_periodic,
)
from gelb.midware.geometry import resolve_geometry

from gelb.backends.highway.expr import ExpressionEmitMixin
from gelb.backends.highway.layout import StorageLayoutMixin
from gelb.backends.highway.output import OutputEmitMixin
from gelb.backends.highway.simd import SimdEmitMixin
from gelb.backends.highway.statements import StatementEmitMixin
from gelb.backends.highway.common import (
    _lname,
    _CBT_TILE,
    _NETCDF_TYPE_MAP,
    _NT_STORE_THRESHOLD_BYTES,
    _TYPE_MAP,
    _cbt_addr_to_tile_start,
    _detect_avx512_available,
    _uname,
)


# ----------------------------------------------------------------------
# Generator
# ----------------------------------------------------------------------


class HighwayCodeGenerator(
        ExpressionEmitMixin,
        StatementEmitMixin,
        SimdEmitMixin,
        StorageLayoutMixin,
        OutputEmitMixin,
):
    backend_name = 'cpu_highway'
    runtime_header = 'cpu_highway_runtime.hpp'
    wrap_main_with_highway = True

    def __init__(self, ast, num_timesteps=1, output_filename='output.nc',
                 write_every=1, use_openmp=False, random_seed=None,
                 source_file='', storage_layout='auto',
                 resolved_geometry=None, backend_context=None,
                 poison_uninit=False, strict_fp=False):
        if backend_context is not None and backend_context.ast is not ast:
            raise ValueError(
                "BackendContext AST does not match the AST passed to "
                "HighwayCodeGenerator.")

        self.ast = ast
        self.num_timesteps = int(num_timesteps)
        self.output_filename = output_filename
        self.write_every = int(write_every)
        self.use_openmp = bool(use_openmp)
        self.random_seed = random_seed
        self.source_file = source_file
        self._storage_layout_override = storage_layout
        # ``--poison-uninit``: fill lattice allocations with 0xFF (every
        # uninitialized double reads as NaN) instead of zeros, so reads
        # of unwritten lattice cells surface as NaN in the output rather
        # than hiding behind benign zeros.  Debugging aid.
        self._poison_uninit = bool(poison_uninit)
        # Strict build (user manual, Numerical semantics: Build modes):
        # the generated source defines ``GELB_STRICT_FP`` before
        # including the runtime header, whose helpers then fuse nothing
        # (``gelb_mul_add``).
        self._strict_fp = bool(strict_fp)

        self._lines: list[str] = []
        self._indent = 0

        # Singleton-axis literal-substitution state.  When a 1-cell
        # axis sub-region is opened via ``_emit_axis_loop_open`` with
        # ``lo == hi``, we register ``g_<axis> -> str(lo)`` here; the
        # ``_emit`` method substitutes those identifiers in subsequent
        # body lines and folds simple integer arithmetic.  The stack
        # tracks open scopes so close-pop restores the outer binding.
        self._axis_substitutions: dict[str, str] = {}
        self._axis_subst_stack: list = []

        # Reuse midware: lattice info + geometry resolution.  The
        # compiler driver passes a BackendContext built from the canonical
        # pipeline; direct backend calls still compute these facts here to
        # preserve the public generator behavior.
        if backend_context is not None:
            self._lattice_info = backend_context.lattice_info
            self._geom = backend_context.geometry
            self._stencils = backend_context.stencils
        else:
            self._lattice_info = collect_lattice_info(ast)
            self._geom = (
                resolved_geometry
                if resolved_geometry is not None
                else resolve_geometry(ast)
            )
            self._stencils = None

        # Per-lattice storage-layout decision: True => AoS, False => SoA.
        # Driven by ``--storage-layout`` and the periodicity flags on
        # each lattice declaration.  Consulted by ``_storage_subscript``
        # and the storage-allocation emit.
        self._use_aos: dict[str, bool] = self._decide_storage_layout()
        # Parallel map for CBT (cell-block-tiled) opt-in.  Mutually
        # exclusive with AoS.  When True, storage is shaped
        # [buf][y_pad][x_tile][df][x_within_tile] with x_within_tile = 8.
        self._use_cbt: dict[str, bool] = self._decide_storage_layout_cbt()
        # Validate: AoS and CBT are mutually exclusive per-lattice.
        for ln in self._lattice_info:
            if self._use_aos[ln] and self._use_cbt[ln]:
                raise ValueError(
                    f"lattice {ln!r}: AoS and CBT layouts are mutually "
                    "exclusive (got both True)")

        # Constant + variable tracking.
        # _array_constants[name] = list of folded scalar values (for EX, EY, W
        #   etc).  Lets us fold EX[i] to a literal when emitting upstream_dfs.
        # _array_locals = set of variable names that are array-typed in the
        #   current emit scope.  Used when an Identifier appears inside a
        #   for-df loop: array -> name[gelb_df]; scalar -> name.
        self._array_constants: dict[str, list] = {}
        # 2-D constants: name -> (nrows, ncols).  Used by matmul to
        # fold the inner dimension at codegen time.
        self._array_constants_2d: dict[str, tuple[int, int]] = {}
        # Folded values for 2-D constants -- populated alongside
        # ``_array_constants_2d`` when we successfully fold every
        # entry to a numeric.  Indexed as ``[row][col]``.  Used by
        # the matmul emit to prune zero coefficients and recognise
        # the +/-1 case per row.
        self._array_constants_2d_values: dict[
            str, list[list[float]]] = {}
        self._array_locals: set[str] = set()
        # Tracks user-level int-typed scalar locals that have been
        # retyped to a SIMD vector in the currently-emitting block
        # because their RHS evaluates to a Vec-typed expression
        # (e.g. ``int dx = x - N/2;`` in the SIMD body becomes
        # ``V g_dx = ...``).  Maps user-name -> 'vec8d' or 'vec8q'.
        # Consulted by ``_emit_simd_aware_cast`` so that downstream
        # casts of these locals (e.g. an implicit promote to
        # ``double`` for a lattice-out store) emit the right Highway
        # spelling rather than a compile-failing ``static_cast``.
        self._simd_int_locals: dict[str, str] = {}
        # Sizes of runtime-lifted temp arrays (e.g. matmul second-arg
        # lifts).  Consulted by _lookup_local_array_size before
        # falling back to the AST walk.
        self._local_array_sizes: dict[str, int] = {}
        # Counter for unique matmul temp names.
        self._matmul_temp_counter: int = 0

        # Registry for ``static constexpr`` index/coefficient arrays
        # that the dot_prod / matmul emit needs.  Hoisted to the top
        # of ``main()`` and de-duplicated by content so repeated calls
        # to ``dot_prod(EX, fIn)`` across many dispatch sites share a
        # single declaration.  Filled in lazily by
        # ``_register_constexpr_array``; emitted into the saved
        # position ``_main_body_start_idx`` at the end of ``generate``.
        self._deferred_constexpr_decls: list[str] = []
        self._deferred_constexpr_dedup: dict[
            tuple[str, tuple], str] = {}
        self._deferred_constexpr_counter: int = 0
        self._main_body_start_idx: int = -1

        # bounce_back_dfs table cache: (ex_name,) or (ex_name, ey_name) ->
        # (var_name, opp_indices_list).  Filled on first reference; the
        # constexpr table is emitted alongside the lattice constants.
        self._opp_tables: dict[tuple[str, ...], tuple[str, list[int]]] = {}

        # SIMD emission mode toggled by the time-loop emitter.  When
        # 'vec8d', leaf emitters (_emit_lattice_in, the slice-assign
        # branch of _emit_statement, var-decl emit, bounce_back_dfs in
        # _emit_intrinsic_call) emit Vec8d code instead of scalar.
        self._simd_mode: str = 'scalar'
        # Width of the SIMD vector we emit for.  Vec8d (8 doubles)
        # is the AVX-512 native width; Highway's ``CappedTag`` /
        # target dispatch handles narrower ISAs (AVX-2, NEON)
        # transparently.
        self._simd_vw: int = 8
        # Set of axis indices for which the current loop bounds make
        # periodic wrap impossible.  upstream_dfs consults this to skip
        # the modulo arithmetic on safe axes, leaving wrap math in
        # place on unsafe ones.  e.g. inside the y-body of a 2-D SIMD
        # emit, both {0, 1} are safe; inside y-head, only {0} (x) is
        # safe along the x-interior since y still wraps.
        self._wrap_safe_axes: set[int] = set()

        # Backend scope checks - fail loudly on anything we don't
        # support yet.
        self._enforce_backend_scope()

    # ------------------------------------------------------------------
    # Scope enforcement
    # ------------------------------------------------------------------

    def _enforce_backend_scope(self) -> None:
        d = get_max_dim(self._lattice_info)
        if d not in (1, 2, 3):
            raise NotImplementedError(
                f"cpu_highway supports 1-D, 2-D, and 3-D lattices "
                f"(this program is {d}-D).")
        # Multi-lattice is supported.
        # Masked node classes: their dyn/init/gauge are all None, so
        # the per-NC dispatch in the time loop already skips them.
        # The gauge buffer cells at those positions are NaN-filled
        # before each per-NC gauge fill (see _emit_gauge_nan_init).
        if self.ast.functions and len(self.ast.functions) > 0:
            raise NotImplementedError(
                "cpu_highway: user-defined functions are not yet "
                "supported.")

    # ------------------------------------------------------------------
    # Convenience emit
    # ------------------------------------------------------------------

    def _emit(self, line: str = '') -> None:
        if line and self._axis_substitutions:
            line = self._apply_axis_substitutions(line)
        if line:
            self._lines.append('  ' * self._indent + line)
        else:
            self._lines.append('')

    def _apply_axis_substitutions(self, line: str) -> str:
        """Apply singleton-axis substitutions ``g_<axis> -> literal``
        followed by integer-arithmetic folding to a single emit line.
        Replaces e.g. ``g_z`` with ``0`` and folds wrap-modulo
        expressions like ``((g_z - 1 + 64) % 64)`` to ``63`` at
        codegen time so the generated source reads as concrete
        literal coordinates at axis-singleton sub-regions instead of
        symbolic ``g_<axis>`` references that the C++ compiler would
        only fold at compile time.

        Word-boundary substitution avoids hitting other identifiers
        that share the prefix (e.g. ``g_z_storage`` is left alone)."""
        import re
        for k, v in self._axis_substitutions.items():
            line = re.sub(rf'\b{re.escape(k)}\b', v, line)
        return self._fold_int_arith(line)

    @staticmethod
    def _fold_int_arith(s: str) -> str:
        """Fold purely-numeric paren-wrapped arithmetic in a string.

        Recognises two patterns and applies them iteratively until
        the string stabilises:

          * ``(N)`` (single integer in parens) -> ``N``
          * ``(N op M op K op ...)`` (a chain of integers and the
            operators ``+ - * %``) -> the evaluated result, when the
            entire chain is purely numeric.

        Used by ``_apply_axis_substitutions`` to clean up wrap-modulo
        expressions after axis-singleton substitution.  Sanitisation
        guarantees only digit / op / whitespace tokens reach
        ``eval``; identifiers, function calls, etc. are rejected and
        left untouched.  Python's ``%`` semantics agree with C's for
        non-negative operands, which is the case here (the wrap form
        is always ``(... + N) % N`` with the inner sum >= 0)."""
        import re
        int_pat = r'-?\d+(?:LL)?'
        # Negative lookbehind ``(?<!>)`` skips parens immediately
        # preceded by ``>`` -- those are part of ``static_cast<TYPE>(N)``
        # where the parens are required syntax, not a redundant wrap.
        parens_int = re.compile(rf'(?<!>)\(\s*({int_pat})\s*\)')
        chain_pat = re.compile(
            rf'(?<!>)\(\s*({int_pat}(?:\s*[+\-*%]\s*{int_pat})+)\s*\)')
        sanitiser = re.compile(
            rf'\s*{int_pat}(\s*[+\-*%]\s*{int_pat})*\s*')

        def eval_chain(m):
            expr = m.group(1)
            if not sanitiser.fullmatch(expr):
                return m.group(0)
            suffix = 'LL' if 'LL' in expr else ''
            try:
                result = eval(expr.replace('LL', ''), {'__builtins__': {}}, {})
            except Exception:
                return m.group(0)
            if isinstance(result, int):
                return f'{result}{suffix}'
            return m.group(0)

        while True:
            new = parens_int.sub(lambda m: m.group(1), s)
            new = chain_pat.sub(eval_chain, new)
            if new == s:
                return s
            s = new

    def _omp_firstprivate_clause(self) -> str:
        """Return the ``firstprivate(...)`` clause listing every lattice's
        per-step buffer-index variables.

        Why: ``g_<lname>_old`` and ``g_<lname>_new`` are mutable ints
        in ``main()`` that select the source/destination slot of the
        ping-pong storage.  Without ``firstprivate``, OpenMP captures
        them by reference through the parallel-region struct, which
        forces gcc to reload them through indirection on every
        iteration AND recompute the multi-dim array stride
        (``imul $0x244824, ...``) on every load/store.  With
        ``firstprivate`` each thread gets a register-allocated private
        copy initialised once at parallel-region entry, eliminating
        ~7+ imul-stride ops and ~10 movslq reloads per inner-loop
        iteration.  Empirically worth +5-6 % MLUPS on LDC-2D N=512.
        """
        names = []
        for lname in self._lattice_info:
            names.append(f'{_lname(lname)}_old')
            names.append(f'{_lname(lname)}_new')
        if not names:
            return ''
        return f'firstprivate({", ".join(names)})'

    @property
    def _lattice_name(self) -> str:
        return next(iter(self._lattice_info))

    def _lattice(self):
        return self._lattice_info[self._lattice_name]

    def _grid_n(self) -> int:
        return get_grid_size(self._lattice_info, 0, ast=self.ast)

    @property
    def _d(self) -> int:
        return get_max_dim(self._lattice_info)

    def _grid_sizes(self) -> tuple[int, ...]:
        return get_grid_sizes(self._lattice_info, ast=self.ast)

    @staticmethod
    def _axis(i: int) -> str:
        return ('x', 'y', 'z')[i]

    # ------------------------------------------------------------------
    # Top-level
    # ------------------------------------------------------------------

    def generate(self) -> str:
        self._emit_header_comment()
        self._emit_includes()
        self._emit_main_header()

        self._emit_grid_constants()
        self._emit_lattice_declarations()
        self._emit_aux_variables()
        self._emit_netcdf_setup()
        self._emit('')

        self._emit_simulation_body()

        # Splice the deferred ``static constexpr`` index / coefficient
        # arrays at the recorded main-body start position so they're
        # declared once at the top of ``main()`` (instead of being
        # re-emitted at every call site).  Keeps the per-call-site
        # source compact: each dot_prod / matmul-row call is a single
        # expression referencing the hoisted name.
        if self._deferred_constexpr_decls and self._main_body_start_idx >= 0:
            indent_prefix = '  ' * 1  # main()'s body indent
            decls_with_indent = [
                indent_prefix + d for d in self._deferred_constexpr_decls
            ]
            self._lines[self._main_body_start_idx
                        :self._main_body_start_idx] = decls_with_indent

        return '\n'.join(self._lines) + '\n'

    def _emit_simulation_body(self) -> None:
        self._emit_masked_lattice_zero_init()
        self._emit_initialiser_loops()
        self._emit_gauge_at_t0()
        self._emit('')

        self._emit_time_loop()
        self._emit('')

        self._emit_mlups_report()
        self._emit_netcdf_close()
        self._emit_main_footer()

    # ------------------------------------------------------------------
    # Header / boilerplate
    # ------------------------------------------------------------------

    def _emit_header_comment(self) -> None:
        src = os.path.basename(self.source_file) if self.source_file else '<unknown>'
        self._emit('// Generated by GeLB (Generic Lattice Boltzmann DSL)')
        self._emit(f'// Source: {src}')
        self._emit(f'// Backend: {self.backend_name}')
        self._emit('//')
        self._emit('// Naming conventions:')
        self._emit('//   g_<name>  -- user-defined identifier')
        self._emit('//   gelb_*    -- compiler-internal')
        self._emit('')

    def _emit_includes(self) -> None:
        if self._strict_fp:
            # Must precede the include: the runtime header selects its
            # unfused helpers on this macro (user manual, Numerical
            # semantics: Build modes).
            self._emit('#define GELB_STRICT_FP 1')
        self._emit(f'#include "{self.runtime_header}"')
        self._emit('')
        self._emit('using namespace gelb;')
        self._emit('')

    def _emit_main_header(self) -> None:
        if self.wrap_main_with_highway:
            # Highway requires that any function calling SIMD intrinsics
            # (``hn::Set``, ``hn::LoadU``, ``hn::Sin``, ...) be inside the
            # ``HWY_BEFORE_NAMESPACE() / HWY_AFTER_NAMESPACE()`` brackets.
            # Wrapping ``int main()`` directly is OK -- these macros emit
            # ``#pragma GCC push_options`` / ``pop_options`` rather than
            # opening a new namespace, so ``main`` stays at global scope.
            self._emit('HWY_BEFORE_NAMESPACE();')
        self._emit('int main() {')
        self._indent += 1
        # Mark the position where deferred ``static constexpr`` index
        # / coefficient arrays will be spliced in by ``generate()``
        # after all dyn / gauge emit has completed.  Storing the
        # current ``len(self._lines)`` lets us insert without scanning
        # the buffer or using a placeholder string.
        self._main_body_start_idx = len(self._lines)

    def _register_constexpr_array(self, prefix: str, ctype: str,
                                   values: tuple) -> str:
        """Register a ``static constexpr <ctype> NAME[] = {...};`` decl
        to be hoisted to the top of ``main()``.  De-duplicates by
        ``(ctype, values)`` so repeated calls with the same content
        share a single declaration.  Returns the array's name.

        Used by ``dot_prod`` (index arrays) and ``_emit_matmul_into_array``
        (coefficient arrays) to keep per-call-site emit compact: each
        call references a hoisted name instead of re-declaring the
        constants at every dispatch site."""
        key = (ctype, tuple(values))
        if key in self._deferred_constexpr_dedup:
            return self._deferred_constexpr_dedup[key]
        self._deferred_constexpr_counter += 1
        name = f'{prefix}_{self._deferred_constexpr_counter}'
        if ctype in ('int', 'int8_t', 'int16_t', 'int32_t', 'int64_t',
                     'uint8_t', 'uint16_t', 'uint32_t', 'uint64_t'):
            value_str = ', '.join(str(int(v)) for v in values)
        else:
            value_str = ', '.join(cpp_real(float(v), ctype) for v in values)
        decl = (f'static constexpr {ctype} {name}[] = '
                f'{{ {value_str} }};')
        self._deferred_constexpr_decls.append(decl)
        self._deferred_constexpr_dedup[key] = name
        return name

    def _emit_main_footer(self) -> None:
        self._emit('return 0;')
        self._indent -= 1
        self._emit('}')
        if self.wrap_main_with_highway:
            # Pair with the ``HWY_BEFORE_NAMESPACE()`` emitted in
            # ``_emit_main_header``: pops the pragma stack so subsequent
            # TUs (none, here) build with default target attributes.
            self._emit('HWY_AFTER_NAMESPACE();')

    # ------------------------------------------------------------------
    # Declarations
    # ------------------------------------------------------------------

    def _emit_grid_constants(self) -> None:
        sizes = self._grid_sizes()
        self._emit('// Grid parameters')
        for i, n in enumerate(sizes):
            self._emit(f'constexpr int g__n{self._axis(i)} = {n};')
        # Emit user-declared global constants (if present).
        if self.ast.global_constants is not None:
            self._emit('')
            self._emit('// Global constants')
            for stmt in self.ast.global_constants.stmts:
                if isinstance(stmt, ConstantDefinitionStmt_N):
                    self._emit_global_constant(stmt)
        # Emit opposite-DF tables (one per unique (EX[, EY]) stencil).
        self._emit_bounce_back_dfs_tables()
        self._emit('')

    _NARROW_ELEMENT_WIDTHS = ('real32', 'real16', 'int8', 'int16', 'int32')

    def _constant_elements_in_width(self, elements, elem):
        """The literal elements of a constant array of a narrow element
        width ``elem``, each replaced by a literal of the value that
        width stores (user manual, Numerical semantics: Types and
        promotion; through the one evaluator: an integer wraps, a real
        rounds), so that the declaration, the element reads and the
        folds agree.  An element the width cannot hold (a real past its
        range) and a non-constant element are kept as written and
        converted where the declaration is emitted (an infinity at run
        time; a constant expression never writes one).  A constant array
        is emitted in its declared width; a wide width holds each element
        as written, so wide widths keep their nodes."""
        if elem not in self._NARROW_ELEMENT_WIDTHS:
            return list(elements)
        from gelb.midware.ast_eval import convert_plain
        out = []
        for e in elements:
            try:
                value = eval_const_expr(e, ast=self.ast,
                                        lattice_info=self._lattice_info)
                converted = convert_plain(value, elem)
            except Exception:
                out.append(e)
                continue
            if isinstance(converted, bool) or not isinstance(converted, (int, float)):
                out.append(e)
                continue
            cr = e.code_range
            if isinstance(converted, int):
                lit = IntLiteral_N(cr, int(converted))
            else:
                lit = RealLiteral_N(cr, float(converted))
            lit.inferred_type = ArrayDataType_N(cr, elem, List_N(cr))
            out.append(lit)
        return out

    def _constant_element_text(self, e, elem, cpp_type):
        """The C++ spelling of one element of a constant array: a literal
        of the declared width as is; an element the width cannot hold
        (``1.0e300``, ``real32(1.0e300)``, ``1.0e300 * 1.0e300`` in a
        ``real32`` array) as the IEEE 754 value the conversion or the
        operation gives at run time (user manual, Numerical semantics:
        Special values), ``std::numeric_limits<float>::infinity()``,
        which is a constant expression on every compiler where a cast of
        an overflowing product is not (nvcc rejects it in a ``__device__
        constexpr`` array); anything else of a narrow width through an
        explicit conversion."""
        text = self._emit_expression(e)
        if elem not in self._NARROW_ELEMENT_WIDTHS:
            return text
        kind = getattr(getattr(e, 'inferred_type', None), 'element_dtype', None)
        if isinstance(e, (IntLiteral_N, RealLiteral_N)) and kind == elem:
            return text
        special = self._ieee_special_value(e, elem)
        if special is not None:
            return cpp_real(special, cpp_type)
        return f'static_cast<{cpp_type}>({text})'

    def _ieee_special_value(self, e, elem):
        """The non-finite value a constant element has in the width
        ``elem`` under IEEE 754 (an infinity, a NaN), or None when it is
        finite or not a constant."""
        from gelb.midware.ast_eval import convert_plain, ieee_special_values
        try:
            with ieee_special_values():
                value = float(convert_plain(
                    eval_const_expr(e, ast=self.ast, lattice_info=self._lattice_info),
                    elem))
        except Exception:
            return None
        return None if math.isfinite(value) else value

    def _emit_global_constant(self, stmt: ConstantDefinitionStmt_N) -> None:
        dtype = stmt.data_type
        # All declarations carry an ArrayDataType_N in modern GeLB.
        # Scalars have shape = empty List_N; arrays have shape = IntLiteral_N
        # (1-D) or List_N of IntLiterals (multi-D).
        shape = getattr(dtype, 'shape', None)
        elem = (getattr(dtype, 'element_dtype', None)
                or getattr(dtype, 'name', 'real'))
        cpp_type = _TYPE_MAP.get(elem, 'double')
        is_array = (shape is not None
                    and not (isinstance(shape, List_N) and len(shape) == 0))

        if not is_array:
            value_expr = self._emit_expression(stmt.value)
            self._emit(f'static constexpr {cpp_type} '
                       f'{_uname(stmt.name.name)} = {value_expr};')
            return

        # Array constant.  Two shapes supported:
        #   1-D: shape is IntLiteral_N (q)
        #   2-D: shape is Array1DLiteral_N (rows, cols) -- used by MRT
        #        transformation matrices (M, M_inv).
        if isinstance(shape, IntLiteral_N):
            n = shape.value
            # The frontend wraps the initializer in a
            # ``TypePromotionNode_N`` when an explicit ``array[real32, ...]``
            # declaration coerces a literal whose default type is real64.
            # Unwrap it here so the underlying ``Array1DLiteral_N``
            # element list is reachable.
            value_node = stmt.value
            while isinstance(value_node, TypePromotionNode_N):
                value_node = value_node.expr
            if not hasattr(value_node, 'value'):
                raise NotImplementedError(
                    f"unexpected 1-D array constant initialiser "
                    f"({type(value_node).__name__}) for {stmt.name.name}.")
            elements = value_node.value.elements
            if len(elements) != n:
                raise NotImplementedError(
                    f"Array constant {stmt.name.name}: shape {n} != "
                    f"{len(elements)} elements")
            elements = self._constant_elements_in_width(elements, elem)
            value_node.value.elements = elements
            emitted_elems = [self._constant_element_text(e, elem, cpp_type)
                             for e in elements]
            self._emit(f'static constexpr {cpp_type} '
                       f'{_uname(stmt.name.name)}[{n}] = '
                       f'{{ {", ".join(emitted_elems)} }};')
            # Record for later folding (e.g. when emitting upstream_dfs).
            self._array_constants[stmt.name.name] = list(elements)
            return
        # 2-D array constant -- extract rows and cols from the shape
        # literal (Array1DLiteral_N or List_N of two IntLiterals).
        nrows = ncols = None
        if isinstance(shape, Array1DLiteral_N):
            shape_elems = shape.value.elements
        elif isinstance(shape, List_N):
            shape_elems = shape.elements
        else:
            shape_elems = None
        if shape_elems is not None and len(shape_elems) == 2 \
                and all(isinstance(e, IntLiteral_N) for e in shape_elems):
            nrows, ncols = shape_elems[0].value, shape_elems[1].value
        if nrows is None:
            raise NotImplementedError(
                f"cpu_highway: only 1-D and 2-D array constants are "
                f"supported (got shape {type(shape).__name__} "
                f"for {stmt.name.name}).")
        # Same TypePromotionNode_N unwrap as the 1-D path: the frontend
        # wraps the literal when the declared element type forces a
        # promotion (e.g. ``array[real32, ...]`` initialised from a
        # default-real64 literal).
        value_node = stmt.value
        while isinstance(value_node, TypePromotionNode_N):
            value_node = value_node.expr
        if not isinstance(value_node, Array2DLiteral_N):
            raise NotImplementedError(
                f"2-D array constant {stmt.name.name}: expected "
                f"Array2DLiteral_N initialiser, got "
                f"{type(value_node).__name__}.")
        rows = value_node.value.elements  # List_N of Array1DLiteral_N
        if len(rows) != nrows:
            raise NotImplementedError(
                f"Array constant {stmt.name.name}: declared {nrows} "
                f"rows, got {len(rows)}.")
        # Emit row-major C++ literal (row-major matches both the
        # source-text order in `{{...}, {...}}` and the natural C++
        # layout of `T[nrows][ncols]`).
        out_lines = []
        for r in rows:
            row_elems = r.value.elements
            if len(row_elems) != ncols:
                raise NotImplementedError(
                    f"Array constant {stmt.name.name}: row width "
                    f"{len(row_elems)} != declared {ncols}.")
            row_elems = self._constant_elements_in_width(row_elems, elem)
            r.value.elements = row_elems
            out_lines.append('{ '
                             + ', '.join(self._constant_element_text(e, elem, cpp_type)
                                         for e in row_elems)
                             + ' }')
        self._emit(f'static constexpr {cpp_type} '
                   f'{_uname(stmt.name.name)}[{nrows}][{ncols}] = '
                   f'{{ {", ".join(out_lines)} }};')
        # Track 2-D constants separately from 1-D for matmul lookups.
        self._array_constants_2d[stmt.name.name] = (nrows, ncols)
        # Try to fold every (row, col) to a numeric.  If all entries
        # fold, cache them so the matmul emit can prune zero
        # coefficients and recognise the +/-1 case per row.  If any
        # entry fails to fold (rare -- typically every M / M_inv in
        # MRT examples is a literal numeric matrix), fall back: the
        # matmul emit will skip the helper path and use the original
        # 19-term ``+`` chain.
        try:
            folded = []
            for r in rows:
                folded_row = []
                for e in r.value.elements:
                    folded_row.append(float(eval_const_expr(
                        e, ast=self.ast,
                        lattice_info=self._lattice_info)))
                folded.append(folded_row)
            self._array_constants_2d_values[stmt.name.name] = folded
        except Exception:
            pass  # leave unset; matmul emit will fall back

    def _emit_aux_variables(self) -> None:
        # MLUPS timer + NetCDF state come from the runtime header.
        self._emit_mlups_timer_setup()
        self._emit_timestep_counters()
        # PRNG seeding -- Highway's ``VectorXoshiro`` (parallel-stream
        # xoshiro256+) is wrapped by ``gelb_seed_prng`` /
        # ``gelb_random_vec`` / ``gelb_random`` in the runtime
        # header.  The seed-storage global is shared across OpenMP
        # threads; each thread's first touch of its thread_local
        # rng instance reads this seed + its own thread_id offset.
        # No bit-equivalence with cpu_fortran_serial (different
        # algorithm -- Mersenne Twister).  --seed gives bit-
        # reproducibility within the cpu_highway backend itself.
        if self.random_seed is not None:
            self._emit(f'gelb::gelb_seed_prng({int(self.random_seed)}'
                       f'ULL);')
        else:
            self._emit('// PRNG seeded from system clock (default).')
            self._emit('gelb::gelb_seed_prng(static_cast<uint64_t>(')
            self._emit('    std::chrono::steady_clock::now()'
                       '.time_since_epoch().count()));')
        self._emit('')

    def _emit_mlups_timer_setup(self) -> None:
        self._emit('// MLUPS timer')
        self._emit('MlupsTimer gelb_timer;')
        self._emit(f'gelb_timer.total_nodes = {self._total_nodes_expr()};')
        self._emit(f'gelb_timer.num_timesteps = {self.num_timesteps};')
        self._emit('')

    def _emit_timestep_counters(self) -> None:
        self._emit('int gelb_timestep = 0;')
        self._emit('int gelb_write_count = 0;')

    def _total_nodes_expr(self) -> str:
        return ' * '.join(
            f'static_cast<double>(g__n{self._axis(i)})'
            for i in range(self._d))

    # ------------------------------------------------------------------
    # NetCDF setup
    # ------------------------------------------------------------------

    def _gauge_output_layout(self):
        from gelb.backends.gauge_outputs import collect_gauge_outputs
        return collect_gauge_outputs(
            self._find_block(self.ast.gauges, info.gauge)
            if info.gauge is not None else None
            for info in self._geom.nc_info.values())

    def _find_block(self, container, name: str):
        # ``container`` is a List_N for ast.initializers / .dynamics /
        # .gauges / .functions, which iterates over ``.elements``.
        if container is None:
            return None
        for stmt in container:
            if hasattr(stmt, 'name') and stmt.name.name == name:
                return stmt
        return None

    # ------------------------------------------------------------------
    # Initialiser
    # ------------------------------------------------------------------

    def _emit_initialiser_loops(self) -> None:
        self._emit('// ========== Initialiser ==========')
        for nc_name, info in self._geom.nc_info.items():
            if info.initializer is None:
                continue
            iblock = self._find_block(self.ast.initializers, info.initializer)
            if iblock is None:
                continue
            for rect_info, is_synth in self._iter_dispatch_rects(info):
                rect_suffix = (f' [rect bbox={rect_info.bbox}]'
                               if is_synth else '')
                if self._block_simd_eligible(iblock, rect_info):
                    self._emit(f'// Initialiser: {info.initializer} '
                               f'({nc_name}) -- SIMD{rect_suffix}')
                    self._emit_block_simd(iblock, rect_info,
                                          context='initializer')
                else:
                    self._emit(f'// Initialiser: {info.initializer} '
                               f'({nc_name}){rect_suffix}')
                    self._emit_spatial_loop_open(rect_info)
                    self._emit_block_body(iblock, context='initializer')
                    self._emit_spatial_loop_close()
        # 2nd-buffer init: NCs without a dynamic are never written by the
        # time-loop's collide-and-stream pass, so their f_new slot stays
        # uninitialised and becomes garbage after the first ping-pong
        # swap.  Mirror the Fortran backend by re-running the initialiser
        # for static-only NCs into f_new as well.
        had_2nd = False
        for nc_name, info in self._geom.nc_info.items():
            if info.initializer is None or info.dynamic is not None:
                continue
            iblock = self._find_block(self.ast.initializers, info.initializer)
            if iblock is None:
                continue
            if not had_2nd:
                self._emit('')
                self._emit('// 2nd-buffer init for static-only NCs')
                had_2nd = True
            for rect_info, is_synth in self._iter_dispatch_rects(info):
                rect_suffix = (f' [rect bbox={rect_info.bbox}]'
                               if is_synth else '')
                if self._block_simd_eligible(iblock, rect_info):
                    self._emit(f'// Init (2nd buffer): {info.initializer} '
                               f'({nc_name}) -- SIMD{rect_suffix}')
                    self._emit_block_simd(iblock, rect_info,
                                          context='initializer_2nd_buffer')
                else:
                    self._emit(f'// Init (2nd buffer): {info.initializer} '
                               f'({nc_name}){rect_suffix}')
                    self._emit_spatial_loop_open(rect_info)
                    self._emit_block_body(iblock,
                                           context='initializer_2nd_buffer')
                    self._emit_spatial_loop_close()
        self._emit('')

    def _any_masked_nc(self) -> bool:
        return any(info.masked for info in self._geom.nc_info.values())

    def _emit_masked_lattice_zero_init(self) -> None:
        """Zero the DFs of every masked-NC cell (both ping-pong
        buffers, all lattices) before the initialisers run.

        Language guarantee: masked cells hold zero DFs (see
        LANGUAGE_DESIGN.md).  Masked NCs have no initializer, yet
        neighbouring cells may read their DFs (e.g. a bounce-back
        WALL ring around a masked SOLID obstacle gathers them via
        ``bounce_back_dfs``) -- the fullway-bounce-back convention from
        Palabos/OpenLB, where zero populations contribute zero mass.
        The explicit write makes the guarantee independent of the
        allocation fill, so ``--poison-uninit`` only flags reads
        that are *genuinely* undefined.
        """
        if not self._any_masked_nc():
            return
        self._emit('// ========== Masked-cell DF zero-init =========='
                   '')
        self._emit('// Language guarantee: masked cells hold zero DFs'
                   ' in both buffers.')
        for nc_name, info in self._geom.nc_info.items():
            if not info.masked:
                continue
            for rect_info, is_synth in self._iter_dispatch_rects(info):
                rect_suffix = (f' [rect bbox={rect_info.bbox}]'
                               if is_synth else '')
                self._emit(f'// Masked zero-init: {nc_name}'
                           f'{rect_suffix}')
                self._emit_spatial_loop_open(rect_info)
                coord_strs = [f'g_{self._axis(i)}'
                              for i in range(self._d)]
                for lname, linfo in self._lattice_info.items():
                    q = linfo['q']
                    subs = self._storage_subscript(
                        coord_strs, 'gelb_df', lname)
                    self._emit(f'for (int gelb_buf = 0; gelb_buf < 2;'
                               f' ++gelb_buf) {{')
                    self._indent += 1
                    self._emit(f'for (int gelb_df = 0; gelb_df < {q};'
                               f' ++gelb_df) {{')
                    self._indent += 1
                    self._emit(f'{_lname(lname)}_storage[gelb_buf]{subs}'
                               f' = 0.0;')
                    self._indent -= 1
                    self._emit('}')
                    self._indent -= 1
                    self._emit('}')
                self._emit_spatial_loop_close()
        self._emit('')

    # ------------------------------------------------------------------
    # Time loop
    # ------------------------------------------------------------------

    def _emit_gauge_halo_updates(self) -> None:
        """Refresh the ghost cells a gauge reads.  The time loop updates
        the halo before the dynamics only; gauges run after the swap and
        at t=0, so a gauge reading a neighbour across a periodic axis
        needs its own refresh.  Without stencil information every
        periodic lattice is refreshed."""
        wanted = (self._stencils.gauge_halo_lattices()
                  if self._stencils is not None else set(self._lattice_info))
        for lname, info in self._lattice_info.items():
            if lname in wanted and any(is_periodic(self._lattice_info, i)
                                       for i in range(info['d'])):
                self._emit(f'halo_update_{lname}({_lname(lname)}_old);')

    def _emit_time_loop(self) -> None:
        self._emit('// ========== Time loop ==========')
        self._emit('gelb_timer.wall_start();')
        self._emit(f'for (gelb_timestep = 1; gelb_timestep <= '
                   f'{self.num_timesteps}; ++gelb_timestep) {{')
        self._indent += 1

        # Halo update: refresh ghost cells on the input buffer for every
        # periodic-axis lattice before the dynamic kernel reads them.
        for lname, info in self._lattice_info.items():
            if any(is_periodic(self._lattice_info, i)
                   for i in range(info['d'])):
                self._emit(f'halo_update_{lname}({_lname(lname)}_old);')

        # Dynamic blocks
        self._emit('gelb_timer.dyn_start();')
        for nc_name, info in self._geom.nc_info.items():
            if info.dynamic is None:
                continue
            dblock = self._find_block(self.ast.dynamics, info.dynamic)
            if dblock is None:
                continue
            for rect_info, is_synth in self._iter_dispatch_rects(info):
                rect_suffix = (f' [rect bbox={rect_info.bbox}]'
                               if is_synth else '')
                if self._block_simd_eligible(dblock, rect_info):
                    self._emit(f'// Dynamic: {info.dynamic} '
                               f'({nc_name}) -- SIMD{rect_suffix}')
                    self._emit_block_simd(dblock, rect_info,
                                          context='dynamic')
                else:
                    self._emit(f'// Dynamic: {info.dynamic} '
                               f'({nc_name}){rect_suffix}')
                    self._emit_spatial_loop_open(rect_info)
                    self._emit_block_body(dblock, context='dynamic')
                    self._emit_spatial_loop_close()
        self._emit('gelb_timer.dyn_stop();')

        # NT-store fence.  ``hn::Stream`` writes through the
        # write-combining buffer and can be reordered with respect
        # to other stores; ``gelb::gelb_sfence()`` guarantees
        # global visibility before subsequent loads (gauge sweep,
        # next-timestep halo update, next-timestep dynamic).  The
        # helper expands to ``_mm_sfence`` on x86 and to a NEON
        # data-memory-barrier (``dmb ishst``) on ARM -- see
        # ``cpu_highway_runtime.hpp`` for the per-target dispatch.
        # Only emitted when at least one CBT lattice uses NT stores
        # -- otherwise the fence is wasted overhead.
        if self._should_use_nt_stores():
            self._emit('// NT-store fence: makes ``hn::Stream`` '
                       'writes globally visible')
            self._emit('gelb::gelb_sfence();')

        # Buffer swap
        for lname in self._lattice_info:
            self._emit(f'std::swap({_lname(lname)}_old, {_lname(lname)}_new);')

        # Gauge sweep (with --write-every guard)
        gauge = self._gauge_output_layout()
        if gauge is not None:
            need_guard = self.write_every > 1
            if need_guard:
                self._emit(f'if (gelb_timestep % {self.write_every} == 0 '
                           f'|| gelb_timestep == {self.num_timesteps}) {{')
                self._indent += 1
            self._emit('gelb_write_count += 1;')
            self._emit_gauge_halo_updates()
            self._emit_gauge_nan_init(gauge)
            for nc_name, info in self._geom.nc_info.items():
                if info.gauge is None:
                    continue
                gblock = self._find_block(self.ast.gauges, info.gauge)
                for rect_info, is_synth in self._iter_dispatch_rects(info):
                    rect_suffix = (f' [rect bbox={rect_info.bbox}]'
                                   if is_synth else '')
                    if self._block_simd_eligible(gblock, rect_info):
                        self._emit(f'// Gauge: {info.gauge} ({nc_name}) '
                                   f'-- SIMD{rect_suffix}')
                        self._emit_block_simd(gblock, rect_info,
                                              context='gauge')
                    else:
                        self._emit(f'// Gauge: {info.gauge} '
                                   f'({nc_name}){rect_suffix}')
                        self._emit_spatial_loop_open(rect_info)
                        self._emit_block_body(gblock, context='gauge')
                        self._emit_spatial_loop_close()
            self._emit_gauge_netcdf_write(gauge)
            if need_guard:
                self._indent -= 1
                self._emit('}')

        self._indent -= 1
        self._emit('}')
        self._emit('gelb_timer.wall_stop();')

    # ------------------------------------------------------------------
    # Rectangle decomposition.
    # Non-dense NCs (e.g. LDC's WALL = three lines + corners) get
    # split into a list of dense rectangles, each of which can flow
    # through the SIMD-eligibility check and emit pipeline like a
    # normal dense bbox.  This is what enables boundary-row walls to
    # vectorise even though the parent NC isn't a single rectangle.
    # ------------------------------------------------------------------

    def _decompose_into_rectangles(self, nc_id, bbox):
        """Greedy maximal-rectangle (or rectangular-cuboid in 3-D)
        decomposition of cells with the given ``nc_id`` within
        ``bbox``.  Each output rectangle is dense (every cell inside
        it has the requested nc_id) and together they tile the
        matching cells exactly once.  Order is deterministic
        (outermost-axis-major, innermost-axis-minor scan)."""
        import numpy as np
        nc_map = self._geom.nc_map
        rects = []
        if self._d == 1:
            x_lo, x_hi = bbox[0]
            x = x_lo
            while x <= x_hi:
                if int(nc_map[x]) != nc_id:
                    x += 1
                    continue
                x_end = x
                while x_end + 1 <= x_hi \
                        and int(nc_map[x_end + 1]) == nc_id:
                    x_end += 1
                rects.append([(x, x_end)])
                x = x_end + 1
            return rects
        if self._d == 2:
            x_lo, x_hi = bbox[0]
            y_lo, y_hi = bbox[1]
            nx_local = x_hi - x_lo + 1
            ny_local = y_hi - y_lo + 1
            visited = np.zeros((nx_local, ny_local), dtype=bool)
            for j in range(ny_local):
                y = y_lo + j
                for i in range(nx_local):
                    x = x_lo + i
                    if visited[i, j] or int(nc_map[x, y]) != nc_id:
                        continue
                    i_end = i
                    while (i_end + 1 < nx_local
                           and not visited[i_end + 1, j]
                           and int(nc_map[x_lo + i_end + 1, y]) == nc_id):
                        i_end += 1
                    j_end = j
                    while j_end + 1 < ny_local:
                        row_y = y_lo + j_end + 1
                        can_extend = True
                        for ii in range(i, i_end + 1):
                            if visited[ii, j_end + 1] or \
                                    int(nc_map[x_lo + ii, row_y]) != nc_id:
                                can_extend = False
                                break
                        if not can_extend:
                            break
                        j_end += 1
                    visited[i:i_end + 1, j:j_end + 1] = True
                    rects.append([(x, x_lo + i_end),
                                  (y, y_lo + j_end)])
            return rects
        # 3-D: extend the same greedy strategy to cuboids.  Scan order:
        # k (z) outermost, then j (y), then i (x).  At each unvisited
        # matching cell, extend along x, then along y (if the whole
        # x-row at the next y matches), then along z.
        x_lo, x_hi = bbox[0]
        y_lo, y_hi = bbox[1]
        z_lo, z_hi = bbox[2]
        nx_local = x_hi - x_lo + 1
        ny_local = y_hi - y_lo + 1
        nz_local = z_hi - z_lo + 1
        visited = np.zeros((nx_local, ny_local, nz_local), dtype=bool)
        for k in range(nz_local):
            z = z_lo + k
            for j in range(ny_local):
                y = y_lo + j
                for i in range(nx_local):
                    x = x_lo + i
                    if visited[i, j, k] \
                            or int(nc_map[x, y, z]) != nc_id:
                        continue
                    # Extend x.
                    i_end = i
                    while (i_end + 1 < nx_local
                           and not visited[i_end + 1, j, k]
                           and int(nc_map[x_lo + i_end + 1, y, z])
                               == nc_id):
                        i_end += 1
                    # Extend y.
                    j_end = j
                    while j_end + 1 < ny_local:
                        row_y = y_lo + j_end + 1
                        can_extend = True
                        for ii in range(i, i_end + 1):
                            if visited[ii, j_end + 1, k] or \
                                    int(nc_map[x_lo + ii, row_y, z]) \
                                        != nc_id:
                                can_extend = False
                                break
                        if not can_extend:
                            break
                        j_end += 1
                    # Extend z.
                    k_end = k
                    while k_end + 1 < nz_local:
                        slab_z = z_lo + k_end + 1
                        can_extend = True
                        for jj in range(j, j_end + 1):
                            row_y = y_lo + jj
                            if not can_extend:
                                break
                            for ii in range(i, i_end + 1):
                                if visited[ii, jj, k_end + 1] or \
                                        int(nc_map[x_lo + ii, row_y,
                                                   slab_z]) != nc_id:
                                    can_extend = False
                                    break
                        if not can_extend:
                            break
                        k_end += 1
                    visited[i:i_end + 1, j:j_end + 1,
                            k:k_end + 1] = True
                    rects.append([(x, x_lo + i_end),
                                  (y, y_lo + j_end),
                                  (z, z_lo + k_end)])
        return rects

    def _iter_dispatch_rects(self, info):
        """Yield (rect_info, is_synth) per rectangle of an NC's
        painted region.  Dense NCs yield exactly one ``(info, False)``;
        non-dense NCs yield one synthetic dense-bbox info per rectangle
        from the greedy decomposition.  All emit paths (init, dynamic,
        gauge) iterate through this so that boundary kernels can hit
        the SIMD path on a per-rectangle basis."""
        from dataclasses import replace
        if info.bbox is None or info.bbox_dense:
            yield info, False
            return
        rects = self._decompose_into_rectangles(info.nc_id, info.bbox)
        for rect in rects:
            yield replace(info, bbox=rect, bbox_dense=True), True

    # ------------------------------------------------------------------
    # SIMD path (Vec8d) -- PR B.2 generalised for bulk-with-stencil.
    # Eligible blocks may read at constant offsets via upstream_dfs;
    # the emitter splits each periodic axis whose bbox covers the
    # boundary into [head, interior, tail], runs scalar code on the
    # head/tail (where periodic wrap is needed), and Vec8d on the
    # interior (where reads at x +/- off stay in range).
    # ------------------------------------------------------------------

    def _periodic_reach(self) -> int:
        """The largest |offset| of any access along a periodic axis.
        Reads within one cell use the halo; paths that cannot wrap an
        index themselves (CBT cross-tile loads, CUDA shared tiles) are
        only taken when this is at most 1."""
        stencils = self._stencils
        if stencils is None:
            from gelb.midware.stage2_midware import extract_stencils
            stencils = extract_stencils(self.ast)
        return stencils.periodic_reach()

    def _write_reach(self) -> int:
        """The largest |offset| of any lattice write (0 when every write
        is local).  Paths that store only at the cell they compute (the
        CBT layout's aligned and streaming stores, the CUDA shared tiles)
        are only taken when this is 0."""
        stencils = self._stencils
        if stencils is None:
            from gelb.midware.stage2_midware import extract_stencils
            stencils = extract_stencils(self.ast)
        return stencils.write_reach()

    def _compute_write_offsets(self, block):
        """Per-axis ``(max_neg_off, max_pos_off)`` over every lattice
        *write* of ``block`` (``f.out[x +/- k, ...]``).  A push needs the
        full reach peeled at a periodic edge, since the halo cannot
        absorb a write; see ``_emit_block_simd``."""
        from gelb.gelb_ast.ASTNodes import Node_N
        d = self._d
        max_neg = [0] * d
        max_pos = [0] * d

        def walk(n):
            if not isinstance(n, Node_N):
                return
            if isinstance(n, RectSelOfLatticeOutDFs_N):
                spatial = n.element_ranges[:-1]
                for axis_idx, sr in enumerate(spatial):
                    parsed = self._split_axis_offset(self._range_scalar(sr))
                    if parsed is None:
                        continue
                    _, off = parsed
                    if off > 0:
                        max_pos[axis_idx] = max(max_pos[axis_idx], off)
                    elif off < 0:
                        max_neg[axis_idx] = max(max_neg[axis_idx], -off)
            for c in n.get_children():
                walk(c)
        walk(block)
        return list(zip(max_neg, max_pos))

    def _compute_stencil_offsets(self, dblock):
        """Walk a dynamic block and return per-axis ``(max_neg_off,
        max_pos_off)`` covering every neighbour-cell read it does:
          * upstream_dfs calls (offsets folded from EX/EY constants);
          * direct ``f.in[x +/- k, y +/- k | df]`` reads parsed from the
            spatial coord expressions.
        The two together let _emit_dynamic_simd compute correct
        head/body/tail bounds even for examples that use both styles
        (e.g. poiseuille_flow_2d_mrt's BounceBack walls)."""
        from gelb.gelb_ast.ASTNodes import Node_N
        d = self._d
        max_neg = [0] * d
        max_pos = [0] * d

        def bump(axis, off):
            if off > 0:
                max_pos[axis] = max(max_pos[axis], off)
            elif off < 0:
                max_neg[axis] = max(max_neg[axis], -off)

        def walk(n):
            if not isinstance(n, Node_N):
                return
            if isinstance(n, IntrinsicFunctionCall_N) \
                    and n.function_name in ('upstream_dfs', 'bounce_back_dfs'):
                args = n.arguments
                expected = d + 2
                ev_lists = []
                if len(args) == expected:
                    if d == 1:
                        ev_lists = [(args[2], 0)]
                    else:
                        ev = args[1 + d]
                        elems = (ev.elements
                                 if isinstance(ev, List_N)
                                 else getattr(ev, 'value', None))
                        if elems is not None and len(elems) == d:
                            ev_lists = [(elems[axis], axis)
                                        for axis in range(d)]
                for ev_id, axis in ev_lists:
                    if not isinstance(ev_id, Identifier_N):
                        continue
                    vals = self._array_constants.get(ev_id.name)
                    if vals is None:
                        continue
                    for v in vals:
                        try:
                            off_val = int(eval_const_expr(
                                v, ast=self.ast,
                                lattice_info=self._lattice_info))
                        except Exception:
                            continue
                        # upstream_dfs at direction i reads the
                        # *upstream* cell (- offset).
                        bump(axis, off_val if n.function_name ==
                             'bounce_back_dfs' else -off_val)
            elif isinstance(n, RectSelOfLatticeInDFs_N):
                # Direct stencil read: parse each spatial coord.
                spatial = n.element_ranges[:-1]
                for axis_idx, sr in enumerate(spatial):
                    scalar = self._range_scalar(sr)
                    parsed = self._split_axis_offset(scalar)
                    if parsed is not None:
                        _, off_val = parsed
                        bump(axis_idx, off_val)
            for c in n.get_children():
                walk(c)
        walk(dblock)
        return list(zip(max_neg, max_pos))

    # Back-compat alias for any external caller / test that used the
    # dyn-specific name.
    _dyn_block_simd_eligible = SimdEmitMixin._block_simd_eligible

    # Back-compat alias for any external caller that used the
    # dyn-specific name.
    _emit_dynamic_simd = SimdEmitMixin._emit_block_simd

    # ------------------------------------------------------------------
    # Spatial loops
    # ------------------------------------------------------------------

    def _emit_axis_loop_open(self, axis: str, lo: int, hi: int,
                              *, label: str = None,
                              omp: bool = False) -> None:
        """Emit a loop opener for ``g_<axis>`` over the inclusive
        range ``[lo, hi]``.  Two forms:

          * When ``lo == hi``, the loop is a single-iteration loop
            and collapses to a brace-scoped declaration::

                // <label>
                { int g_axis = lo;

            **And** the binding ``g_<axis> = lo`` is pushed onto
            ``_axis_substitutions``: subsequent body emits replace
            every ``\\bg_<axis>\\b`` with the literal ``lo`` and fold
            simple integer arithmetic at codegen time (so e.g.
            cross-axis reads at the boundary like
            ``((g_y - 1 + 64) % 64)`` collapse to ``63``).  The push
            happens *after* the declaration line is emitted so the
            decl itself keeps the ``g_<axis>`` identifier (otherwise
            we'd produce ``int 0 = 0;``).

          * Otherwise, a normal ``for (...; ...; ++...)`` loop with
            an optional ``#pragma omp parallel for`` directive
            preceding it (suppressed in the collapsed case, where
            there's no parallelism available).

        ``label`` is an optional comment line emitted just before
        the loop opener -- used by the dyn / gauge / initialiser emit
        to label region roles like ``'scalar head (x wrap)'``,
        ``'SIMD body (Vec8d x 8 cells/iter)'``, ``'y = first'``."""
        if label:
            self._emit(f'// {label}')
        # A coordinate is a GeLB `int`, int64: `x + 2147483647` must
        # not overflow.
        if lo == hi:
            self._emit(f'{{ int64_t g_{axis} = {lo};')
            key = f'g_{axis}'
            prior = self._axis_substitutions.get(key)
            # The literal is an int64, `LL`, so that arithmetic on the
            # collapsed coordinate stays 64-bit, as on a loop coordinate;
            # the folder below understands the suffix.
            self._axis_substitutions[key] = f'{lo}LL'
            self._axis_subst_stack.append(('singleton', key, prior))
        else:
            if omp:
                fp = self._omp_firstprivate_clause()
                self._emit(f'#pragma omp parallel for '
                           f'schedule(static){" " + fp if fp else ""}')
            self._emit(f'for (int64_t g_{axis} = {lo}; '
                       f'g_{axis} <= {hi}; ++g_{axis}) {{')
            self._axis_subst_stack.append(('loop',))
        self._indent += 1

    def _emit_axis_loop_close(self) -> None:
        """Close a loop or singleton-brace block opened by
        ``_emit_axis_loop_open``.  Pops any singleton binding from
        ``_axis_substitutions`` so subsequent emits see the outer
        scope's bindings again.  Symmetric: one ``}`` either way."""
        entry = self._axis_subst_stack.pop()
        if entry[0] == 'singleton':
            _, key, prior = entry
            if prior is None:
                del self._axis_substitutions[key]
            else:
                self._axis_substitutions[key] = prior
        self._indent -= 1
        self._emit('}')

    def _emit_spatial_loop_open(self, info) -> None:
        # Use the bounding box from ResolvedGeometry.nc_info[NC].
        # bbox is a list of (lo, hi) pairs, one per spatial dimension.
        d = self._d
        sizes = self._grid_sizes()
        # Loop nesting follows Fortran's column-major convention so the
        # innermost loop varies the contiguous (x) axis: y outer, x inner
        # for 2-D.  This matches the gauge-buffer layout buf[ny][nx].
        self._spatial_loop_depth = 0
        outer = True
        for i in reversed(range(d)):
            ax = self._axis(i)
            if info.bbox is None:
                lo, hi = 0, sizes[i] - 1
            else:
                lo, hi = info.bbox[i]
            self._emit_axis_loop_open(
                ax, lo, hi,
                omp=outer and self.use_openmp and d >= 2
                    and (hi - lo + 1) >= 2)
            self._spatial_loop_depth += 1
            outer = False
        # Every NC reaches this point with bbox_dense=True because
        # ``_iter_rect_decomposition`` rewrites non-dense NCs into a
        # sequence of dense synthetic-bbox sub-rectangles upstream.
        # The assertion guards against a future regression where some
        # emit path forgets to route through the decomposition.
        #
        # NOTE for future irregular-geometry support (porous media,
        # CT-scanned rock geometries, etc.) where rect decomposition
        # would explode in count: an alternate dispatch path could emit
        # a per-cell ``gelb_nc_map`` lookup gated on a rect-count
        # threshold (switch to map-based dispatch when rect count
        # exceeds, say, 64).  See git history pre-Lever-D for the
        # earlier wiring (``_emit_nc_map`` + ``if (gelb_nc_map[...] ==
        # nc_id) { ... }``).  That code was always-emitted-but-never-
        # read; reviving it would need the threshold logic above plus a
        # benchmark of the crossover point for irregular geometries.
        assert info.bbox is None or info.bbox_dense, (
            f"NC {info.nc_id} reached spatial-loop emit with "
            f"non-dense bbox; expected rect decomposition upstream")

    def _emit_spatial_loop_close(self) -> None:
        # No-op now that the per-cell gelb_nc_map guard has been
        # removed.  Kept for symmetry with _emit_spatial_loops_open in
        # case a future dispatch variant re-introduces a guard scope.
        pass
        # Close via _emit_axis_loop_close (not raw brace emit) so any
        # axis-singleton bindings pushed by _emit_spatial_loop_open
        # are popped.  Otherwise bindings would leak across
        # consecutive dispatch sites at the same nesting level
        # (e.g. WALL_TOP at y=N-1 followed by BULK at y=[0..N-2]),
        # corrupting subsequent for-loop declarations like
        # ``for (int g_y = 0; ...)`` with the stale binding's literal.
        for _ in range(self._spatial_loop_depth):
            self._emit_axis_loop_close()
        self._spatial_loop_depth = 0

    # ------------------------------------------------------------------
    # Block body
    # ------------------------------------------------------------------

    @staticmethod
    def _decl_cpp_type(decl: VariableDeclarationStmt_N) -> str:
        """Resolve a VariableDeclarationStmt_N's element type to a
        C++ scalar spelling.  Most declarations carry an
        ``ArrayDataType_N`` even for scalars (with an empty ``shape``);
        the actual element type lives at ``data_type.element_dtype``.
        Plain ``ScalarDataType_N`` carries it at ``.name``."""
        dt = decl.data_type
        elem = getattr(dt, 'element_dtype', None) or getattr(dt, 'name', 'real')
        return _TYPE_MAP.get(elem, 'double')

    @staticmethod
    def _try_parse_lit(s: str):
        """If ``s`` is a literal-looking C++ float (no operators or
        identifiers, just a number), return its float value;
        otherwise return None.  Used by the arithmetic-folding
        helpers below to recognise pre-evaluated constexpr-array
        substitutions (e.g. ``EX[3]`` -> ``-1.0``)."""
        try:
            return float(s)
        except (ValueError, TypeError):
            return None


# ----------------------------------------------------------------------
# Module entry point
# ----------------------------------------------------------------------


def generate_cpu_highway(ast, num_timesteps=1, output_filename='output.nc',
                    write_every=1, use_openmp=False, random_seed=None,
                    source_file='', storage_layout='auto',
                    resolved_geometry=None, backend_context=None,
                    poison_uninit=False, strict_fp=False):
    """Generate C++17 + Google Highway code from a GeLB AST.

    ``storage_layout``: per-lattice memory layout policy.  ``'auto'``
    picks AoS (``[buf][...y][x][df]``) for lattices with no periodic
    axis (LDC, channel-with-obstacle), SoA (``[buf][df][...y][x]``)
    otherwise.  ``'soa'`` / ``'aos'`` force the choice for every
    lattice.  Both layouts produce bit-identical output.

    ``backend_context`` may be supplied by the compiler driver to reuse
    facts already produced by the canonical compiler pipeline.
    ``resolved_geometry`` is retained for direct-call compatibility.

    Returns a string with the full ``.cpp`` source.  Raises
    :class:`NotImplementedError` with a precise message if the program
    uses constructs not supported by the cpu_highway backend.
    """
    gen = HighwayCodeGenerator(ast, num_timesteps=num_timesteps,
                              output_filename=output_filename,
                              write_every=write_every,
                              use_openmp=use_openmp,
                              random_seed=random_seed,
                              source_file=source_file,
                              storage_layout=storage_layout,
                              resolved_geometry=resolved_geometry,
                              backend_context=backend_context,
                              poison_uninit=poison_uninit,
                              strict_fp=strict_fp)
    return gen.generate()
