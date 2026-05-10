"""Slice-DF expansion midware pass.

After ``inline_functions`` the BGK polynomial is hoisted into Q-element
array variables (e.g.  ``__Eq_1_eu = EX*ux + EY*uy``,
``__Eq_1_feq = W*rho*(1 + 3*__Eq_1_eu + 4.5*__Eq_1_eu^2 - 1.5*__Eq_1_usq)``).
The lattice-out slice statement only references the resulting array.
This pass walks each block's statement list, identifies Q-element array
statements (Q >= 9), expands each into Q scalar statements with literal-
indexed array constants substituted (W[i], EX[i], ...) and per-direction
exact simplification (``ast_simplify.simplify_exact``).

Per-direction substitution rules (in ``_subst_for_direction``):

* ``Identifier_N(name)`` where ``name`` is a constexpr global Q-element
  array (W, EX, EY, EZ, ...)            -> literal ``RealLiteral_N`` /
                                         ``IntLiteral_N`` for value at i.
* ``Identifier_N(name)`` where ``name`` is a local Q-element array we
  already expanded                    -> ``Identifier_N(per_dir[i])``.
* ``Identifier_N(name)`` where ``name`` is a Q-element array we did NOT
  expand (e.g. ``fIn = upstream_dfs(...)``) -> ``RectSelOfArrayElems_N``
                                              indexed at literal i.
* Bare ``RectSelOfArrayElems_N(name, [Range(L,L)])`` with literal L and
  ``name`` a constexpr global array  -> literal substitution.
* Otherwise (scalar identifier, etc.) -> unchanged.

A statement triggers expansion when:

* ``LatticeOutSelectionAssignmentStmt_N`` whose LHS DF range is a slice
  of length Q >= 9.
* ``VariableDeclarationStmt_N`` whose ``data_type.shape`` is
  ``IntLiteral_N(Q)`` with Q >= 9, EXCEPT when ``initial_value`` is a
  bare ``IntrinsicFunctionCall_N`` (e.g. ``upstream_dfs(...)``) -- those
  stay as a single Q-element array.
* ``VariableAssignmentStmt_N`` whose LHS Identifier was previously
  expanded (i.e. is in the visitor's ``local_array_to_scalars`` map).

Bit-equivalence: bit-exact against the unexpanded form.  Only the
identities IEEE arithmetic makes exact are applied, literal-only
subtrees are folded in their own width, and identical *ordered*
subtrees are shared; nothing is re-associated (user manual, Numerical
semantics: What the optimizer promises).
``--no-slice-simplify`` disables the pass.

Common-subexpression elimination (``ast_simplify.hoist_common_subtrees``)
is gated by the ``enable_cse`` flag.
"""

import copy


from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.frontend.visitor_mixins import ProgramTraversalMixin
from gelb.gelb_ast.ASTNodes import (
    Array1DLiteral_N,
    ArrayDataType_N,
    BroadcastNode_N,
    ConstantDefinitionStmt_N,
    DynamicBlock_N,
    GaugeBlock_N,
    Identifier_N,
    InitializerBlock_N,
    IntLiteral_N,
    IntrinsicFunctionCall_N,
    LatticeOutSelectionAssignmentStmt_N,
    List_N,
    Node_N,
    Range_N,
    RealLiteral_N,
    RectSelOfArrayElems_N,
    RectSelOfLatticeInDFs_N,
    RectSelOfLatticeOutDFs_N,
    TypePromotionNode_N,
    UnaryMinusExpr_N,
    VariableAssignmentStmt_N,
    VariableDeclarationStmt_N,
)
from gelb.midware.ast_eval import collect_lattice_info
from gelb.midware.ast_simplify import (
    hoist_common_subtrees,
    real_width,
    scalar_type_of,
    simplify_exact,
)


_Q_GATE = 9   # D2Q9 minimum -- smaller stencils don't justify the AST blow-up


# Intrinsics that return a Q-element array whose semantics the
# cpu_highway backend specialises per-direction at codegen time
# (inside its slice-DF unroll path).  When such an intrinsic appears
# anywhere in a Q-element-array statement's RHS, this pass leaves the
# statement alone -- expanding would produce Q stmts each carrying the
# array-typed intrinsic in scalar context, which the backend cannot
# lower.
_KNOWN_ARRAY_INTRINSICS = {'upstream_dfs', 'bounce_back_dfs', 'matmul',
                           'transpose', 'inverse'}


class SliceDFExpansionVisitor(ASTBaseVisitor, ProgramTraversalMixin):
    """Visitor that expands Q-element-array statements per direction
    and applies the exact simplification to the resulting scalar expressions.

    The visitor maintains per-block scope tracking the local Q-element
    arrays it has expanded into scalar names.  Each block (initializer,
    dynamic, gauge) starts with a fresh scope so per-direction scalars
    introduced in one block can't leak into another.
    """

    def __init__(self, lattice_info: dict, array_constants: dict,
                 enable_cse: bool = True):
        super().__init__()
        self.lattice_info = lattice_info
        self.array_constants = array_constants  # name -> [Python values]
        self.enable_cse = enable_cse
        # Telemetry counters.
        self.expansions_applied = 0
        self.cse_temps_emitted = 0
        # Program-unique CSE temp index.
        self._cse_counter = 0
        # Per-block scope reset by each block-entry visitor.
        self._scope = None

    # --- Dispatcher --------------------------------------------------

    def visit(self, node, ast_root_node):
        """Generic-fallback dispatcher: recurse into children when no
        explicit visitor method exists.  Mirrors
        ``CollinearityRewriteVisitor.visit``."""
        if node is None:
            return None
        method_name = f"visit{type(node).__name__}"
        method = getattr(self, method_name, None)
        if method is not None:
            return method(node, ast_root_node)
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

    # --- Program / block entry points --------------------------------

    def visitProgram_N(self, node, ast_root_node):
        self.traverse_program_blocks(node, ast_root_node)
        return node

    def visitInitializerBlock_N(self, node, ast_root_node):
        return self._process_block(node, ast_root_node)

    def visitDynamicBlock_N(self, node, ast_root_node):
        return self._process_block(node, ast_root_node)

    def visitGaugeBlock_N(self, node, ast_root_node):
        return self._process_block(node, ast_root_node)

    def _process_block(self, block, ast_root_node):
        """Process one block -- fresh scope, walk its statement list,
        expand triggering statements 1:Q in-place."""
        # Pre-scan: identify Q-element-array names referenced by stmts
        # that the visitor will NOT expand (whole-array ops kept as-is).
        # These arrays must remain as whole arrays -- expanding them
        # would leave dangling references in the unexpanded stmts.
        forced_whole = _scan_forced_whole(block.stmts.elements)
        self._scope = _BlockScope(forced_whole=forced_whole)
        new_elements = []
        for stmt in block.stmts.elements:
            replacement = self._maybe_expand_stmt(stmt)
            if replacement is None:
                new_elements.append(stmt)
            else:
                new_elements.extend(replacement)
        block.stmts.elements = new_elements
        self._scope = None
        return block

    # --- Per-statement dispatch --------------------------------------

    def _maybe_expand_stmt(self, stmt):
        """Return a list of replacement statements, or ``None`` to keep
        ``stmt`` as-is."""
        if isinstance(stmt, VariableDeclarationStmt_N):
            return self._maybe_expand_var_decl(stmt)
        if isinstance(stmt, VariableAssignmentStmt_N):
            return self._maybe_expand_var_assign(stmt)
        if isinstance(stmt, LatticeOutSelectionAssignmentStmt_N):
            return self._maybe_expand_lattice_out(stmt)
        return None

    # --- VariableDeclarationStmt_N -----------------------------------

    def _maybe_expand_var_decl(self, stmt: VariableDeclarationStmt_N):
        q = _q_from_data_type(stmt.data_type)
        if q is None or q < _Q_GATE:
            return None
        name = stmt.name.name
        # Forced-whole (pre-scan): some downstream stmt references this
        # array as a whole-array operand and won't be per-direction
        # expanded.  Keep this decl whole too so the references resolve.
        if name in self._scope.forced_whole:
            self._scope.unexpanded_arrays.add(name)
            return None
        # Opaque-only initial value (e.g. fIn = upstream_dfs(...)) -- leave
        # the array as-is; subsequent stmts referencing this array will
        # resolve via ``RectSelOfArrayElems_N`` indexing.
        if stmt.initial_value is not None and \
                _is_opaque_only(stmt.initial_value):
            self._scope.unexpanded_arrays.add(name)
            return None
        # RHS contains a Q-element-array intrinsic whose semantics the
        # backend specialises per-direction (e.g. ``upstream_dfs(...) +
        # correction``) -- expanding here would break the backend's
        # specialisation.  Leave as-is.
        if stmt.initial_value is not None and \
                _contains_known_array_intrinsic(stmt.initial_value):
            self._scope.unexpanded_arrays.add(name)
            return None
        # Generate Q per-direction scalar names.
        scalar_names = [f"{name}_{i}" for i in range(q)]
        self._scope.array_to_scalars[name] = scalar_names

        cr = stmt.code_range
        scalar_dtype = _scalar_dtype_for(stmt.data_type)
        self._scope.remember_dtype(name, scalar_dtype)

        if stmt.initial_value is None:
            # Decl without init -- emit Q scalar decls, no CSE pass.
            result = []
            for i in range(q):
                name_id = Identifier_N(cr, scalar_names[i])
                name_id.inferred_type = scalar_dtype
                result.append(VariableDeclarationStmt_N(
                    cr, scalar_dtype, name_id, initial_value=None))
            self.expansions_applied += 1
            return result

        # Decl with init -- expand to Q per-direction RHS ASTs, in the
        # RHS's own arithmetic type, stored in the declared one.
        core, arith_dtype = _arithmetic_core(stmt.initial_value, cr)
        cse_temp_decls, ast_per_dir = self._build_q_simplified(
            core, q, arith_dtype, cr)
        result = list(cse_temp_decls)
        for i in range(q):
            name_id = Identifier_N(cr, scalar_names[i])
            name_id.inferred_type = scalar_dtype
            decl = VariableDeclarationStmt_N(
                cr, scalar_dtype, name_id,
                initial_value=_stored(ast_per_dir[i], scalar_dtype, cr))
            result.append(decl)
        self.expansions_applied += 1
        return result

    # --- VariableAssignmentStmt_N ------------------------------------

    def _maybe_expand_var_assign(self, stmt: VariableAssignmentStmt_N):
        if not isinstance(stmt.lhs, Identifier_N):
            return None
        name = stmt.lhs.name
        scalar_names = self._scope.array_to_scalars.get(name)
        if scalar_names is None:
            # The LHS array wasn't expanded by a prior decl -- leave as-is.
            return None
        # Defensive: if the assignment RHS contains a known array
        # intrinsic, the backend would need the array form to specialise
        # -- but the LHS scalars need scalar values.  Skip the expansion
        # in this corner case (rare; usually the prior decl was already
        # left unexpanded by the same check).
        if _contains_known_array_intrinsic(stmt.rhs):
            return None
        q = len(scalar_names)
        cr = stmt.code_range
        scalar_dtype = _scalar_dtype_for_name_in_scope(
            self._scope, name)
        core, arith_dtype = _arithmetic_core(stmt.rhs, cr)
        cse_temp_decls, ast_per_dir = self._build_q_simplified(
            core, q, arith_dtype, cr)
        result = list(cse_temp_decls)
        for i in range(q):
            new_lhs = Identifier_N(cr, scalar_names[i])
            new_lhs.inferred_type = scalar_dtype
            result.append(VariableAssignmentStmt_N(
                cr, new_lhs, _stored(ast_per_dir[i], scalar_dtype, cr)))
        self.expansions_applied += 1
        return result

    # --- LatticeOutSelectionAssignmentStmt_N -------------------------

    def _maybe_expand_lattice_out(
            self, stmt: LatticeOutSelectionAssignmentStmt_N):
        if not isinstance(stmt.lhs, RectSelOfLatticeOutDFs_N):
            return None
        df_range = stmt.lhs.element_ranges[-1]
        df_lo, df_hi = self._resolve_df_range(stmt.lhs, df_range)
        if df_lo is None or df_hi is None:
            return None
        if df_lo == df_hi:
            return None  # already single-direction
        if (df_hi - df_lo + 1) < _Q_GATE:
            return None
        # Opaque-only RHS (e.g. ``f.out[x,y|:] = bounce_back_dfs(...)``):
        # let the backend's existing per-DF loop handle it -- expanding
        # would produce Q identical scalar statements with array-typed
        # RHSs the backend cannot lower at scalar context.
        if _is_opaque_only(stmt.rhs):
            return None
        # RHS contains a Q-element-array intrinsic anywhere (e.g. the
        # MovingLid pattern ``bounce_back_dfs(...) + 6*W*EX*0.1``) -- the
        # backend has special handling for these in its slice-DF unroll
        # path.  Skip.
        if _contains_known_array_intrinsic(stmt.rhs):
            return None
        # The slice df range covers [df_lo, df_hi].  Build Q new
        # single-DF statements (plus optional CSE temps).
        cr = stmt.code_range
        q = df_hi - df_lo + 1
        # The store type is the RHS's type after the promotion the type
        # pass placed at the store; the arithmetic is rebuilt in the
        # type under that promotion and converted per direction, so a
        # `real` literal times a real32 read stays a double product
        # rounded once at the store, as in the unexpanded form.
        rhs_inferred = getattr(stmt.rhs, 'inferred_type', None)
        scalar_dtype = _scalar_inferred_type(rhs_inferred, cr)
        core, arith_dtype = _arithmetic_core(stmt.rhs, cr)
        # ``_build_q_simplified`` always produces indices [0, Q) -- for a
        # ``[df_lo, df_hi]`` slice we need to map back: temporarily
        # adjust the visitor's per-direction substitution to use the
        # actual df-index.  Since slice df ranges always start at 0 in
        # practice (D2Q9 / D3Q19 share this convention), assert and
        # forward.
        assert df_lo == 0, \
            f"non-zero slice low {df_lo} is not supported"
        cse_temp_decls, ast_per_dir = self._build_q_simplified(
            core, q, arith_dtype, cr)
        result = list(cse_temp_decls)
        for i in range(df_lo, df_hi + 1):
            new_lhs = self._build_single_df_lhs(stmt.lhs, i)
            result.append(LatticeOutSelectionAssignmentStmt_N(
                cr, new_lhs, _stored(ast_per_dir[i - df_lo], scalar_dtype, cr)))
        self.expansions_applied += 1
        return result

    def _resolve_df_range(self, lhs: RectSelOfLatticeOutDFs_N,
                          df_range: Range_N):
        """Return ``(df_lo, df_hi)`` integers for the DF range, or
        ``(None, None)`` if the range cannot be resolved here."""
        if df_range.low is None and df_range.high is None:
            # Bare ``:`` slice -- covers [0, Q-1] from the lattice meta.
            lattice_name = lhs.lattice_name.name \
                if isinstance(lhs.lattice_name, Identifier_N) \
                else str(lhs.lattice_name)
            info = self.lattice_info.get(lattice_name)
            if info is None:
                return None, None
            return 0, info['q'] - 1
        if isinstance(df_range.low, IntLiteral_N) and \
                isinstance(df_range.high, IntLiteral_N):
            return df_range.low.value, df_range.high.value
        return None, None

    def _build_single_df_lhs(
            self, lhs: RectSelOfLatticeOutDFs_N, i: int):
        """Build a single-DF LHS at index ``i`` by deep-copying the
        original LHS and replacing its DF range."""
        cr = lhs.code_range
        new_lhs = copy.deepcopy(lhs)
        # Replace the last element_range with a singleton ``Range(i, i)``.
        idx_lit_low = IntLiteral_N(cr, i)
        idx_lit_high = IntLiteral_N(cr, i)
        new_lhs.element_ranges[-1] = Range_N(cr, idx_lit_low, idx_lit_high)
        return new_lhs

    # --- Per-direction expansion core --------------------------------

    def _prepare_per_direction_ast(self, rhs, i: int):
        """Deep-copy ``rhs`` and apply per-direction substitution
        (literal-indexed arrays, lattice-in slice narrowing, local
        expanded-array refs).  The per-direction expression before
        simplification."""
        # Top-level Array1DLiteral_N: select element i directly (the
        # whole literal would otherwise be one opaque operand --
        # wrong for per-direction expansion).
        if isinstance(rhs, Array1DLiteral_N):
            elements = rhs.value.elements
            if i < len(elements):
                rhs_i = copy.deepcopy(elements[i])
            else:
                rhs_i = copy.deepcopy(rhs)
        else:
            rhs_i = copy.deepcopy(rhs)
        return self._subst_for_direction(rhs_i, i)

    def _build_q_simplified(self, rhs, q: int, scalar_dtype, code_range):
        """Return ``(cse_temp_decls, [ast_per_direction])``.

        Builds the Q per-direction expressions, applies the exact
        identities and the folding of literal-only subtrees
        (``simplify_exact``) and, optionally, shares their identical
        ordered subtrees as scalar temporaries declared before the Q
        expanded statements (``hoist_common_subtrees``).  Nothing here
        re-associates or rounds differently from the unexpanded form
        (user manual, Numerical semantics: What the optimizer promises).
        """
        per_dir = [simplify_exact(self._prepare_per_direction_ast(rhs, i))
                   for i in range(q)]
        cse_temp_decls, per_dir = self._maybe_apply_cse(
            per_dir, code_range, scalar_dtype)
        return cse_temp_decls, per_dir

    def _maybe_apply_cse(self, exprs, code_range, scalar_dtype):
        """Share the identical ordered subtrees of ``exprs`` (the Q
        per-direction expressions).  Return ``(temp_decls, exprs)``:
        scalar ``VariableDeclarationStmt_N`` with program-unique names
        for the hoisted subtrees, and the expressions reading them."""
        if not self.enable_cse or len(exprs) < 2:
            return [], exprs
        start = self._cse_counter
        temps, rewritten = hoist_common_subtrees(
            exprs, lambda i: f'_gelb_cse_{start + i}')
        if not temps:
            return [], exprs
        self._cse_counter = start + len(temps)
        self.cse_temps_emitted += len(temps)
        decls = [self._build_temp_decl(name, body, code_range,
                                       scalar_type_of(body, scalar_dtype))
                 for name, body in temps]
        return decls, rewritten

    def _build_temp_decl(self, name, ast_rhs, code_range,
                         scalar_dtype) -> 'VariableDeclarationStmt_N':
        """Build a scalar ``VariableDeclarationStmt_N`` for a CSE temp,
        typed like the subtree it holds."""
        name_id = Identifier_N(code_range, name)
        name_id.inferred_type = scalar_dtype
        return VariableDeclarationStmt_N(
            code_range, scalar_dtype, name_id, initial_value=ast_rhs)

    def _subst_for_direction(self, node, i: int):
        """Walk an AST sub-tree and substitute Q-element references with
        per-direction values for index ``i``.  Returns the (possibly
        new) root node.

        Opaque sub-trees (``IntrinsicFunctionCall_N``) are NOT recursed
        into -- their arguments may contain Q-element-array identifiers
        that should stay as whole-array references (e.g.
        ``bounce_back_dfs(f, x, y, [EX, EY])`` -- substituting EX -> 0 inside
        would silently break the intrinsic semantics).
        ``RectSelOfLatticeInDFs_N`` with a slice DF range gets its DF
        range narrowed to ``[i, i]`` so the bridge sees a single-DF
        opaque sub-tree (distinct per direction via structural-key
        interning).
        """
        # Identifier_N: the most common case -- references to W, EX, EY,
        # local array variables, etc.
        if isinstance(node, Identifier_N):
            return self._subst_identifier(node, i)
        # RectSelOfArrayElems_N(name, [Range(L,L)]): explicit array
        # element access (rare post-inlining but possible).
        if isinstance(node, RectSelOfArrayElems_N):
            return self._subst_array_elems(node, i)
        # f.in[x,y|:] (or f.in[x,y|0:8]) inside an expanded RHS:
        # narrow the DF range to the per-direction index.
        if isinstance(node, RectSelOfLatticeInDFs_N):
            return self._subst_lattice_in(node, i)
        # Opaque leaf-tree -- leave its internal structure intact.
        if isinstance(node, IntrinsicFunctionCall_N):
            return node
        # Lists: mutate elements in place.
        if isinstance(node, List_N):
            for k, elem in enumerate(node.elements):
                node.elements[k] = self._subst_for_direction(elem, i)
            return node
        # Generic AST node: walk named children.
        if isinstance(node, Node_N):
            for child_name in node.get_children_names():
                child = getattr(node, child_name)
                if isinstance(child, (Node_N, List_N)):
                    setattr(node, child_name,
                            self._subst_for_direction(child, i))
            return node
        return node

    def _subst_identifier(self, node: Identifier_N, i: int):
        """Substitute a bare identifier for direction ``i`` -- see the
        rules in the module docstring."""
        name = node.name
        cr = node.code_range
        # Constexpr global Q-element array: literal at index i.
        if name in self.array_constants:
            values = self.array_constants[name]
            if i < len(values):
                return _make_literal_for_value(values[i], cr,
                                               getattr(node, 'inferred_type', None))
        # Local array we expanded: substitute the per-direction scalar.
        scalar_names = self._scope.array_to_scalars.get(name)
        if scalar_names is not None and i < len(scalar_names):
            new_id = Identifier_N(cr, scalar_names[i])
            new_id.inferred_type = self._scope.scalar_dtype_for(name)
            return new_id
        # Local array we did NOT expand: emit indexed access.
        if name in self._scope.unexpanded_arrays:
            sel = RectSelOfArrayElems_N(
                cr,
                Identifier_N(cr, name),
                [Range_N(cr, IntLiteral_N(cr, i), IntLiteral_N(cr, i))])
            return sel
        return node

    def _subst_lattice_in(self, node: RectSelOfLatticeInDFs_N, i: int):
        """Narrow the DF range of a lattice-in selection to direction
        ``i`` so per-direction expansion yields scalar single-DF reads
        (the bridge interns each as a distinct opaque sub-tree)."""
        if not node.element_ranges:
            return node
        df_range = node.element_ranges[-1]
        is_slice = (df_range.low is None or (
            isinstance(df_range.low, IntLiteral_N) and
            isinstance(df_range.high, IntLiteral_N) and
            df_range.low.value != df_range.high.value))
        if not is_slice:
            return node
        cr = node.code_range
        node.element_ranges[-1] = Range_N(
            cr, IntLiteral_N(cr, i), IntLiteral_N(cr, i))
        return node

    def _subst_array_elems(self, node: RectSelOfArrayElems_N, i: int):
        """Substitute ``RectSelOfArrayElems_N(name, [Range(L,L)])``.

        Two cases handled (``i`` is the outer per-direction index, not
        used for the inner literal lookup which uses ``L.value``):

        * ``name`` is a constexpr global array (W, EX, EY, ...) -- replace
          with the literal value at index ``L``.
        * ``name`` is a local Q-element array we already expanded --
          replace with the per-direction scalar identifier
          ``Identifier_N(local_array_to_scalars[name][L])``.
        """
        name = _name_of(node.array_name)
        if len(node.element_ranges) != 1:
            return node
        r = node.element_ranges[0]
        if not (isinstance(r.low, IntLiteral_N) and
                isinstance(r.high, IntLiteral_N) and
                r.low.value == r.high.value):
            return node
        idx = r.low.value
        cr = node.code_range
        # Constexpr global array.
        if name in self.array_constants:
            values = self.array_constants[name]
            if 0 <= idx < len(values):
                return _make_literal_for_value(
                    values[idx], cr,
                    getattr(node, 'inferred_type', None))
        # Local Q-element array we expanded into scalars.
        scalar_names = self._scope.array_to_scalars.get(name)
        if scalar_names is not None and 0 <= idx < len(scalar_names):
            new_id = Identifier_N(cr, scalar_names[idx])
            new_id.inferred_type = self._scope.scalar_dtype_for(name)
            return new_id
        return node


# --- Block-scoped state ---------------------------------------------


class _BlockScope:
    """Per-block tracking of expanded local arrays."""

    def __init__(self, forced_whole: set | None = None):
        # name -> [scalar_name_per_dir]
        self.array_to_scalars: dict[str, list[str]] = {}
        # name -> ArrayDataType_N (scalar) -- to retag substituted ids
        self._scalar_dtypes: dict[str, ArrayDataType_N] = {}
        # Names of Q-element local arrays we did NOT expand (opaque
        # initial_value); references resolve via RectSelOfArrayElems_N.
        self.unexpanded_arrays: set[str] = set()
        # Names that must NOT be expanded because some downstream stmt
        # references them as whole arrays (pre-scan determined).
        self.forced_whole: set[str] = forced_whole or set()

    def remember_dtype(self, name, scalar_dtype):
        self._scalar_dtypes[name] = scalar_dtype

    def scalar_dtype_for(self, name):
        return self._scalar_dtypes.get(name)


# --- Free-floating helpers ------------------------------------------


def _q_from_data_type(data_type) -> int | None:
    """Return Q for a Q-element 1-D array data type, else ``None``."""
    if not isinstance(data_type, ArrayDataType_N):
        return None
    shape = data_type.shape
    if isinstance(shape, IntLiteral_N):
        return shape.value
    return None


def _scalar_dtype_for(data_type: ArrayDataType_N) -> ArrayDataType_N:
    """Construct a scalar (0-D) ``ArrayDataType_N`` matching the element
    dtype of ``data_type``."""
    cr = data_type.code_range
    return ArrayDataType_N(cr, data_type.element_dtype, List_N(cr))


def _scalar_dtype_for_name_in_scope(scope: _BlockScope, name: str):
    """Look up the scalar dtype for an array variable previously
    registered in ``scope``.  Falls back to a default real64 if the
    dtype was not recorded."""
    dtype = scope.scalar_dtype_for(name)
    if dtype is not None:
        return dtype
    # Default to real64 scalar -- this path is hit only if the visitor
    # somehow lost track of a registered array (shouldn't happen in
    # practice).
    cr = None
    return ArrayDataType_N(cr, 'real64', List_N(cr))


def _arithmetic_core(rhs, cr):
    """``(core, scalar type)``: the expression under the promotion(s)
    the type pass placed at the store, and its own scalar type.  The
    expansion rebuilds the arithmetic in that type: a real32 temporary
    stays real32."""
    core = rhs
    while True:
        if isinstance(core, BroadcastNode_N):
            core = core.scalar_expr
        elif isinstance(core, TypePromotionNode_N) and \
                real_width(core.target_type) is not None and \
                real_width(getattr(core.expr, 'inferred_type', None)) is not None:
            # a store promotion between real widths, re-applied per
            # direction by _stored; a conversion from another kind
            # (bool or integer to real) stays part of the core
            core = core.expr
        else:
            break
    return core, _scalar_inferred_type(
        getattr(core, 'inferred_type', None), cr)


def _stored(expr, store_dtype, cr):
    """``expr`` converted to ``store_dtype`` when its real width differs:
    the store promotion, re-applied per direction."""
    if real_width(store_dtype) is None:
        return expr
    if real_width(getattr(expr, 'inferred_type', None)) in (None, real_width(store_dtype)):
        return expr
    return TypePromotionNode_N(cr, expr, copy.deepcopy(store_dtype))


def _scalar_inferred_type(inferred, cr):
    """For lattice-out slice statements: derive a scalar inferred_type
    from the array-typed RHS inferred_type.  Falls back to real64 if
    inferred_type is missing."""
    if isinstance(inferred, ArrayDataType_N):
        return ArrayDataType_N(
            inferred.code_range, inferred.element_dtype, List_N(cr))
    return ArrayDataType_N(cr, 'real64', List_N(cr))


def _scan_forced_whole(stmts) -> set:
    """Pre-scan a block's statement list to identify Q-element-array
    names that MUST remain whole arrays.

    An array is "forced whole" if any stmt that will NOT be per-direction
    expanded references it as a bare ``Identifier_N`` -- expanding such an
    array would leave dangling whole-array references in the unexpanded
    stmt.  Iterates to a fixed point because forcing one array whole can
    propagate to its dependencies (e.g. ``fluidMeq = __FluidEq_meq``
    forces both names whole when ``fluidMeq`` is forced whole by a
    downstream whole-array op).
    """
    qarr_names: set[str] = set()
    base_cant_expand: set[str] = set()

    # Sub-pass 1: collect Q-element array LHS names and identify
    # decls that simply cannot be expanded regardless of forced-whole
    # status (opaque-only or contain known array intrinsic).
    for stmt in stmts:
        if isinstance(stmt, VariableDeclarationStmt_N):
            q = _q_from_data_type(stmt.data_type)
            if q is None or q < _Q_GATE:
                continue
            name = stmt.name.name
            qarr_names.add(name)
            if stmt.initial_value is not None and (
                    _is_opaque_only(stmt.initial_value) or
                    _contains_known_array_intrinsic(stmt.initial_value)):
                base_cant_expand.add(name)

    # Sub-pass 2: iterate to fixed point.  Every stmt that won't be
    # per-direction-expanded contributes its whole-array references to
    # ``forced``.  This includes scalar stmts (e.g.  ``rho = sum(fIn)``,
    # ``k_20 = dot_prod(f_in, cx*cx)``), unexpandable Q-element-array
    # stmts, and lattice-out stmts with opaque/known-array-intrinsic
    # RHSs.
    forced: set[str] = set()
    while True:
        cant_expand = base_cant_expand | forced
        new_forced = set(forced)
        for stmt in stmts:
            will_expand = False
            sources_to_scan = []
            if isinstance(stmt, VariableDeclarationStmt_N):
                q = _q_from_data_type(stmt.data_type)
                if q is not None and q >= _Q_GATE \
                        and stmt.name.name not in cant_expand:
                    will_expand = True
                elif stmt.initial_value is not None:
                    sources_to_scan.append(stmt.initial_value)
            elif isinstance(stmt, VariableAssignmentStmt_N):
                lhs_is_qarr = isinstance(stmt.lhs, Identifier_N) \
                    and stmt.lhs.name in qarr_names
                if lhs_is_qarr and stmt.lhs.name not in cant_expand \
                        and not _contains_known_array_intrinsic(stmt.rhs):
                    will_expand = True
                else:
                    sources_to_scan.append(stmt.rhs)
            elif isinstance(stmt, LatticeOutSelectionAssignmentStmt_N):
                if isinstance(stmt.lhs, RectSelOfLatticeOutDFs_N):
                    df_range = stmt.lhs.element_ranges[-1]
                    is_slice = (df_range.low is None or (
                        isinstance(df_range.low, IntLiteral_N) and
                        isinstance(df_range.high, IntLiteral_N) and
                        df_range.low.value != df_range.high.value))
                    if is_slice and not _is_opaque_only(stmt.rhs) \
                            and not _contains_known_array_intrinsic(
                                stmt.rhs):
                        will_expand = True
                if not will_expand:
                    sources_to_scan.append(stmt.rhs)
            else:
                # Any other stmt type -- scan whatever RHS-shaped
                # attribute it has.
                rhs = getattr(stmt, 'rhs', None) \
                    or getattr(stmt, 'initial_value', None)
                if rhs is not None:
                    sources_to_scan.append(rhs)
            if not will_expand:
                for src in sources_to_scan:
                    for ref in _whole_array_refs(src, qarr_names):
                        new_forced.add(ref)
        if new_forced == forced:
            break
        forced = new_forced
    return forced


def _whole_array_refs(node, qarr_names: set) -> set:
    """Return the set of Q-element-array names referenced as bare
    ``Identifier_N`` anywhere in ``node`` (including inside intrinsic
    calls)."""
    out: set[str] = set()
    _whole_array_refs_walk(node, qarr_names, out)
    return out


def _whole_array_refs_walk(node, qarr_names, out):
    if node is None:
        return
    if isinstance(node, Identifier_N):
        if node.name in qarr_names:
            out.add(node.name)
        return
    if isinstance(node, List_N):
        for elem in node.elements:
            _whole_array_refs_walk(elem, qarr_names, out)
        return
    if isinstance(node, Node_N):
        for nm in node.get_children_names():
            child = getattr(node, nm)
            _whole_array_refs_walk(child, qarr_names, out)


def _contains_known_array_intrinsic(node) -> bool:
    """Recursively check whether ``node`` contains an
    ``IntrinsicFunctionCall_N`` whose ``function_name`` is in
    ``_KNOWN_ARRAY_INTRINSICS`` (i.e. a Q-element-array-returning
    intrinsic with backend-side per-direction specialisation)."""
    if isinstance(node, IntrinsicFunctionCall_N):
        if node.function_name in _KNOWN_ARRAY_INTRINSICS:
            return True
        # Recurse into arguments -- a known intrinsic may be nested
        # inside another intrinsic call (rare but possible).
        for arg in node.arguments:
            if _contains_known_array_intrinsic(arg):
                return True
        return False
    if isinstance(node, List_N):
        return any(_contains_known_array_intrinsic(e)
                   for e in node.elements)
    if isinstance(node, Node_N):
        for nm in node.get_children_names():
            child = getattr(node, nm)
            if child is not None and \
                    _contains_known_array_intrinsic(child):
                return True
    return False


def _is_opaque_only(node) -> bool:
    """Return True iff ``node`` is a single bare opaque-leaf expression
    that cannot be decomposed per direction.

    A ``RectSelOfLatticeInDFs_N`` whose DF range is a slice (e.g.
    ``f.in[x, y | :]``) IS decomposable: ``_subst_lattice_in`` narrows
    it per-direction into a singleton ``f.in[x, y | i]``.  Treating
    such slices as opaque preserves a per-direction loop in init/gauge
    bodies and blocks downstream SIMD vectorisation -- return False for
    those.  Same logic applies to ``RectSelOfArrayElems_N`` with a
    slice element range."""
    while isinstance(node, TypePromotionNode_N):
        node = node.expr
    while isinstance(node, BroadcastNode_N):
        node = node.scalar_expr
    if isinstance(node, IntrinsicFunctionCall_N):
        return True
    if isinstance(node, RectSelOfLatticeInDFs_N):
        if not node.element_ranges:
            return True
        df_range = node.element_ranges[-1]
        if df_range.low is None and df_range.high is None:
            return False  # bare ``:`` slice -- decomposable
        if (isinstance(df_range.low, IntLiteral_N) and
                isinstance(df_range.high, IntLiteral_N) and
                df_range.low.value != df_range.high.value):
            return False  # explicit slice -- decomposable
        return True  # singleton or unresolvable -- keep opaque
    if isinstance(node, RectSelOfArrayElems_N):
        if len(node.element_ranges) != 1:
            return True
        r = node.element_ranges[0]
        if r.low is None and r.high is None:
            return False
        if (isinstance(r.low, IntLiteral_N) and
                isinstance(r.high, IntLiteral_N) and
                r.low.value != r.high.value):
            return False
        return True
    return False


def _name_of(node):
    """Identifier_N -> str; bare str -> str; else None."""
    if isinstance(node, Identifier_N):
        return node.name
    if isinstance(node, str):
        return node
    return None


def _make_literal_for_value(value, code_range, inferred_type):
    """Construct an AST literal node for a Python value (int or float).

    Negative values emit ``UnaryMinusExpr_N`` wrapping the positive
    literal -- matches the canonical form GeLB's lexer produces."""
    if isinstance(value, bool):
        lit = IntLiteral_N(code_range, 1 if value else 0)
        if inferred_type is not None:
            lit.inferred_type = inferred_type
        return lit
    if isinstance(value, int):
        if value < 0:
            inner = IntLiteral_N(code_range, -value)
            if inferred_type is not None:
                inner.inferred_type = inferred_type
            neg = UnaryMinusExpr_N(code_range, inner)
            if inferred_type is not None:
                neg.inferred_type = inferred_type
            return neg
        lit = IntLiteral_N(code_range, value)
        if inferred_type is not None:
            lit.inferred_type = inferred_type
        return lit
    # Float fallback.
    if value < 0:
        inner = RealLiteral_N(code_range, float(-value))
        if inferred_type is not None:
            inner.inferred_type = inferred_type
        neg = UnaryMinusExpr_N(code_range, inner)
        if inferred_type is not None:
            neg.inferred_type = inferred_type
        return neg
    lit = RealLiteral_N(code_range, float(value))
    if inferred_type is not None:
        lit.inferred_type = inferred_type
    return lit


# --- Constexpr-array harvesting -------------------------------------


# Element widths whose declared type converts a written element: the
# real widths (an integer element becomes a real, a narrow one rounds)
# and the narrow integer widths (wrap).  `int` and `bool` elements are
# already what they say.
_CONVERTED_ELEMENT_WIDTHS = frozenset(
    ('real', 'real16', 'real32', 'real64', 'int8', 'int16', 'int32'))


def _collect_constexpr_arrays(ast) -> dict:
    """Extract Q-element constexpr global arrays from the AST as
    ``{name: [python_values]}``.  After constant folding, the array
    literal elements are pure ``IntLiteral_N`` / ``RealLiteral_N`` /
    ``UnaryMinusExpr_N`` nodes -- directly evaluable with
    ``ast_eval.eval_const_expr``.

    Explicit-precision array constants (``array[real32, q] EX = {...}``)
    have their ``Array1DLiteral_N`` wrapped in ``TypePromotionNode_N``
    by the frontend's promotion pass to record the implicit narrowing
    of the (default-real64) element literals to real32.  Strip the
    wrapper(s) so fp32 array constants populate ``array_constants``
    the same way as fp64 ones -- otherwise per-direction substitution
    misses the lookup and the bare-array identifier survives to
    codegen, which fails to compile (whole-array * scalar)."""
    from gelb.midware.ast_eval import eval_const_expr, convert_plain
    out = {}
    if ast.global_constants is None:
        return out
    for stmt in ast.global_constants.stmts.elements:
        if not isinstance(stmt, ConstantDefinitionStmt_N):
            continue
        value = stmt.value
        while isinstance(value, (TypePromotionNode_N, BroadcastNode_N)):
            value = value.expr if isinstance(value, TypePromotionNode_N) \
                else value.scalar_expr
        if not isinstance(value, Array1DLiteral_N):
            continue
        elements = value.value.elements
        try:
            vals = [eval_const_expr(e, ast=ast) for e in elements]
            # plain Python values: a narrow-width element would be a
            # NumPy scalar, which the literal printers do not take
            vals = [v.item() if hasattr(v, 'item') else v for v in vals]
        except (ValueError, TypeError, OverflowError):
            # an element that overflows (``1.0e300 * 1.0e300``,
            # ``real32(1.0e300)``) has no literal to substitute
            continue
        # The elements as the array stores them: a real32 array's 4.0/9.0
        # is the binary32 value and its 16777217 is the real 16777216.0,
        # the declared width, not the initializer's; the promotion just
        # stripped is the conversion applied here.
        dtype = getattr(getattr(stmt, 'data_type', None), 'element_dtype', None)
        if dtype in _CONVERTED_ELEMENT_WIDTHS:
            try:
                vals = [convert_plain(v, dtype) for v in vals]
            except (OverflowError, ValueError):
                # an element the width cannot hold (``1.0e300`` in a
                # real32 array) has no literal to substitute; the
                # array keeps its name and the backend's declaration
                # converts it at run time, to an infinity (user manual,
                # Numerical semantics: Special values)
                continue
        out[stmt.name.name] = vals
    return out


# --- Module entry point ---------------------------------------------


def expand_slice_dfs(ast, enable_cse: bool = True):
    """Run the slice-DF expansion pass over ``ast`` (a ``Program_N``).
    Returns the (mutated) AST.  Counts of applied expansions and CSE
    temps are stashed on the AST as ``ast.slice_df_expansions`` and
    ``ast.cse_temps_emitted`` respectively."""
    lattice_info = collect_lattice_info(ast)
    array_constants = _collect_constexpr_arrays(ast)
    visitor = SliceDFExpansionVisitor(
        lattice_info, array_constants, enable_cse=enable_cse)
    visitor.visit(ast, ast)
    setattr(ast, 'slice_df_expansions', visitor.expansions_applied)
    setattr(ast, 'cse_temps_emitted', visitor.cse_temps_emitted)
    return ast
