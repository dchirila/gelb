"""Structural CSE pass for scalar variable assignment runs.

Companion to ``SliceDFExpansionVisitor`` (which CSEs the Q sibling
expressions of one Q-element-array statement).  This pass operates on
the **scalar prelude** of a block -- runs of consecutive
``VariableDeclarationStmt_N`` / ``VariableAssignmentStmt_N`` whose
RHSs share subexpressions across statements.

The motivating case is the LBM ``Macro()`` pattern:

    rho = sum(fIn)
    ux  = signed_sum(fIn, EX_pos, EX_neg) / rho
    uy  = signed_sum(fIn, EY_pos, EY_neg) / rho

Two divisions share the same divisor.  Without this pass, nvcc emits
two separate FP64-DDIV ops (each ~10-15 DFMA refinement steps via
``MUFU.RCP64H`` + Newton-Raphson on consumer Ada -- see
the source for the SASS-level analysis).
The pass shares the identical *ordered* subtrees of a run's
right-hand sides as hoisted temporaries
(``ast_simplify.hoist_common_subtrees``).  Two divisions by ``rho``
stay two divisions, as written: the earlier SymPy version rewrote
them into a reciprocal and two products, which the source does not
say and which rounds differently (user manual, Numerical semantics:
What the optimizer promises).

Pipeline position: AFTER ``hoist_intrinsic_args`` and
``collinearity_rewrite``, BEFORE ``expand_slice_dfs``.  Runs on the
scalar prelude only; ``SliceDFExpansionVisitor`` then handles the
Q-element body separately.

Bit-equivalence: exact against the unhoisted form; a shared value is
computed once, in the same order.  ``--no-scalar-cse`` disables the
pass.

Run boundaries: within a run every name has one value, so identical
subtrees are identical values.  Only scalar statements join a run; a
subtree containing ``random()`` is never shared (``ast_simplify``).
  * Stop the run at any non-scalar-assignment statement (e.g.,
    ``LatticeOutSelectionAssignmentStmt_N``, ``ExpressionStmt_N``).
  * Stop before an assignment to a name the run has already defined or
    *read*: in ``a = v*v; v = 2.0; b = v*v`` the two products are
    different values; a subtree is shared only while every name it
    reads has one value.  A statement that reads
    the name it assigns (``v = v*v``) ends its run: what follows reads
    the new value.  The pass would otherwise need SSA renaming; LBM
    kernels don't re-assign in the scalar prelude in practice.
  * Skip runs of length < 2 (no CSE opportunity).

Topology: the temps come in dependency order (inner first).  Each
temp is emitted at the earliest position in the run where (a) all of
its run-defined free-symbol inputs are already defined AND (b) all
prior temps it transitively depends on are already emitted.
"""


from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.frontend.visitor_mixins import ProgramTraversalMixin
from gelb.gelb_ast.ASTNodes import (
    ArrayDataType_N,
    Identifier_N,
    List_N,
    Node_N,
    VariableAssignmentStmt_N,
    VariableDeclarationStmt_N,
)
from gelb.midware.ast_simplify import (
    hoist_common_subtrees,
    scalar_type_of,
)


class ScalarBlockCSEVisitor(ASTBaseVisitor, ProgramTraversalMixin):
    """Block-level scalar-prelude CSE.  Hoists shared subexpressions
    across consecutive scalar variable assignments.
    """

    def __init__(self):
        super().__init__()
        # Program-unique CSE temp counter.  Names: ``_gelb_pre_cse_<n>``
        # (the ``pre_cse`` prefix is distinct from ``SliceDFExpansion
        # Visitor``'s ``_gelb_pre_cse_<n>``, which starts its own counter
        # at 0 per program).  Without the distinct prefix, scalar-
        # prelude temps and slice-DF Q-array temps would collide
        # within the same emitted block -- both passes generate names
        # like ``_gelb_pre_cse_2``, but with different shapes and scopes.
        self._cse_counter = 0
        self.runs_processed = 0
        self.temps_hoisted = 0

    # --- Generic dispatch -------------------------------------------

    def visit(self, node, ast_root_node):
        if node is None:
            return None
        method_name = f"visit{type(node).__name__}"
        method = getattr(self, method_name, None)
        if method is not None:
            return method(node, ast_root_node)
        if isinstance(node, List_N):
            node.elements = [self.visit(e, ast_root_node)
                             for e in node.elements]
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

    # --- Program / block entry points -------------------------------

    def visitProgram_N(self, node, ast_root_node):
        self.traverse_program_blocks(node, ast_root_node)
        return node

    def visitInitializerBlock_N(self, node, ast_root_node):
        return self._process_block(node)

    def visitDynamicBlock_N(self, node, ast_root_node):
        return self._process_block(node)

    def visitGaugeBlock_N(self, node, ast_root_node):
        return self._process_block(node)

    # --- Block processing -------------------------------------------

    def _process_block(self, block):
        if not hasattr(block, 'stmts') or block.stmts is None:
            return block
        elements = block.stmts.elements
        new_elements = []
        run = []
        for stmt in elements:
            if not self._is_scalar_assign(stmt):
                new_elements.extend(self._flush_run(run))
                run = []
                new_elements.append(stmt)
                continue
            if self._changes_value_seen_by_run(stmt, run):
                # The run so far saw the old value: flush it without
                # this stmt, which starts a fresh run.
                new_elements.extend(self._flush_run(run))
                run = []
            run.append(stmt)
            if self._reads_own_target(stmt):
                new_elements.extend(self._flush_run(run))
                run = []
        new_elements.extend(self._flush_run(run))
        block.stmts.elements = new_elements
        return block

    # --- Run detection / flush --------------------------------------

    def _is_scalar_assign(self, stmt):
        """True if ``stmt`` is a scalar VariableDeclaration with an
        initialiser, or a scalar VariableAssignment.

        Decl-only statements (no ``initial_value``) are excluded --
        they carry no expression to CSE, and including them would
        force a bail-out (or, worse, get them merged into a run
        whose CSE is then dropped).  When such a stmt appears
        mid-block, it just breaks the run and passes through
        verbatim.

        Q-element-array statements are handled by
        ``SliceDFExpansionVisitor``; we leave them alone."""
        if isinstance(stmt, VariableDeclarationStmt_N):
            if stmt.initial_value is None:
                return False
            return self._is_scalar_data_type(stmt.data_type)
        if isinstance(stmt, VariableAssignmentStmt_N):
            # Only Identifier_N LHSs (the most common scalar-assign
            # case).  RectSelOfArrayElems_N etc. fall outside scope.
            # And only a scalar one: a whole-array assignment
            # (``a = u.in[x | :] * u.in[x | :]``) belongs to the slice
            # path, and its value cannot be held in a scalar temporary;
            # whole-array assignments never enter this pass.
            if not isinstance(stmt.lhs, Identifier_N):
                return False
            dtype = (getattr(stmt.lhs, 'inferred_type', None)
                     or getattr(stmt.rhs, 'inferred_type', None))
            return self._is_scalar_data_type(dtype)
        return False

    def _is_scalar_data_type(self, dt):
        """Return True if ``dt`` represents a scalar (False when it is
        unknown).

        ``ArrayDataType_N`` carries its rank-and-extent in ``shape``:
          * ``shape = None``                -- scalar;
          * ``shape = List_N(elements=[])`` -- scalar (rank-0 array);
          * ``shape = IntLiteral_N(N)``     -- Q-element 1-D array;
          * ``shape = List_N(elements=[...])`` -- multi-dim array.

        Only the first two cases are scalars.  The fallback default
        of ``getattr(shape, 'elements', [])`` would erroneously treat
        ``IntLiteral_N(N)`` as scalar (no ``elements`` attr -> empty
        list -> ``len([]) == 0``).  Check explicitly for ``List_N``."""
        if dt is None:
            return False
        if isinstance(dt, ArrayDataType_N):
            shape = getattr(dt, 'shape', None)
            if shape is None:
                return True
            if isinstance(shape, List_N):
                return len(shape.elements) == 0
            # IntLiteral_N (Q-array) or anything else: not scalar.
            return False
        # Plain non-array types (rare but possible): scalar by
        # definition.
        return True

    def _changes_value_seen_by_run(self, stmt, run):
        """True if ``stmt`` assigns a name that a statement of the
        current run defines or reads: after it, the name has another
        value than the one the run's expressions saw."""
        name = self._lhs_name(stmt)
        if name is None:
            return False
        return any(self._lhs_name(prior) == name
                   or name in self._collect_identifier_names(
                       self._stmt_rhs(prior), {name})
                   for prior in run)

    def _reads_own_target(self, stmt):
        """True if ``stmt`` (``v = v*v``) reads the name it assigns."""
        name = self._lhs_name(stmt)
        return name is not None and name in self._collect_identifier_names(
            self._stmt_rhs(stmt), {name})

    def _lhs_name(self, stmt):
        if isinstance(stmt, VariableDeclarationStmt_N):
            n = getattr(stmt, 'name', None)
            return n.name if n is not None and hasattr(n, 'name') else None
        if isinstance(stmt, VariableAssignmentStmt_N):
            if isinstance(stmt.lhs, Identifier_N):
                return stmt.lhs.name
        return None

    def _stmt_rhs(self, stmt):
        """RHS of a scalar assign -- ``initial_value`` for declarations,
        ``rhs`` for plain assignments.  May be ``None`` for declarations
        without an initialiser."""
        if isinstance(stmt, VariableDeclarationStmt_N):
            return stmt.initial_value
        if isinstance(stmt, VariableAssignmentStmt_N):
            return stmt.rhs
        return None

    def _flush_run(self, run):
        """Share the identical ordered subtrees of ``run``'s right-hand
        sides (``hoist_common_subtrees``).  Return the replacement
        statement list, hoisted temps interleaved in dependency order,
        or ``run`` unchanged when nothing is shared."""
        if len(run) < 2:
            return list(run)
        # A declaration without a value has nothing to share.
        if any(self._stmt_rhs(s) is None for s in run):
            return list(run)
        start = self._cse_counter
        temps, rewritten = hoist_common_subtrees(
            [self._stmt_rhs(s) for s in run],
            lambda i: f'_gelb_pre_cse_{start + i}')
        if not temps:
            return list(run)
        self._cse_counter = start + len(temps)
        self.temps_hoisted += len(temps)
        self.runs_processed += 1
        return self._emit_with_temps(run, temps, rewritten)

    # --- Topological emit ------------------------------------------

    def _emit_with_temps(self, run, temps, rewritten):
        """Emit the run's statements with the hoisted temps interleaved.

        A temp is declared at the earliest position where every
        run-defined name its body reads (inside opaque sub-trees such
        as ``cos(K*zc)`` too) and every temp it depends on is already
        defined, and no later than the first statement reading it."""
        run_def_pos = {self._lhs_name(s): k for k, s in enumerate(run)
                       if self._lhs_name(s) is not None}
        run_lhs_names = set(run_def_pos)
        temp_names = {name for name, _ in temps}
        temp_first_use = {}
        for k, expr in enumerate(rewritten):
            for name in self._collect_identifier_names(expr, temp_names):
                temp_first_use.setdefault(name, k)
        temp_emit_pos = {}
        for name, body in temps:      # inner temps come first
            min_pos = 0
            for ref in self._collect_identifier_names(body, run_lhs_names):
                min_pos = max(min_pos, run_def_pos[ref] + 1)
            for dep in self._collect_identifier_names(body, temp_names):
                if dep in temp_emit_pos:
                    min_pos = max(min_pos, temp_emit_pos[dep])
            temp_emit_pos[name] = min(min_pos, temp_first_use.get(name, len(run)))

        output, emitted = [], set()

        def _emit_at(pos, ref_stmt):
            for name, body in temps:
                if name not in emitted and temp_emit_pos[name] == pos:
                    output.append(self._build_temp_decl(name, body, ref_stmt))
                    emitted.add(name)

        _emit_at(0, run[0])
        for k, stmt in enumerate(run):
            output.append(self._rewrite_stmt(stmt, rewritten[k]))
            _emit_at(k + 1, stmt)
        return output

    def _collect_identifier_names(self, node, target_names):
        """Recursively walk ``node`` and return the subset of
        ``target_names`` that appear as ``Identifier_N`` references."""
        from collections import deque
        found = set()
        stack = deque([node])
        while stack:
            n = stack.popleft()
            if n is None:
                continue
            if isinstance(n, Identifier_N):
                if n.name in target_names:
                    found.add(n.name)
                continue
            if isinstance(n, List_N):
                stack.extend(n.elements)
                continue
            if isinstance(n, Node_N):
                for child_name in n.get_children_names():
                    stack.append(getattr(n, child_name))
        return found

    # --- Statement / temp builders ---------------------------------

    def _rewrite_stmt(self, stmt, new_rhs):
        if isinstance(stmt, VariableDeclarationStmt_N):
            return VariableDeclarationStmt_N(
                stmt.code_range, stmt.data_type, stmt.name,
                initial_value=new_rhs)
        if isinstance(stmt, VariableAssignmentStmt_N):
            return VariableAssignmentStmt_N(
                stmt.code_range, stmt.lhs, new_rhs)
        return stmt

    def _build_temp_decl(self, name, body, ref_stmt):
        """``<dtype> _gelb_pre_cse_<n> = <body>;`` for a hoisted temp,
        typed like the subtree it holds (else like ``ref_stmt``)."""
        cr = ref_stmt.code_range
        dtype = scalar_type_of(body, self._scalar_dtype_for(ref_stmt))
        name_id = Identifier_N(cr, name)
        if dtype is not None:
            name_id.inferred_type = dtype
        return VariableDeclarationStmt_N(
            cr, dtype, name_id, initial_value=body)

    def _scalar_dtype_for(self, ref_stmt):
        """Best-effort scalar dtype for a hoisted CSE temp.  Use the
        reference statement's declared type when it's a Decl; fall
        back to the RHS's ``inferred_type`` otherwise."""
        if isinstance(ref_stmt, VariableDeclarationStmt_N):
            if ref_stmt.data_type is not None:
                return ref_stmt.data_type
        rhs = self._stmt_rhs(ref_stmt)
        if rhs is not None:
            it = getattr(rhs, 'inferred_type', None)
            if it is not None:
                return it
        return None


def cse_scalar_blocks(ast):
    """Run scalar-block CSE over ``ast`` (a ``Program_N``).  Mutates
    and returns the AST.  Counts of processed runs and hoisted temps
    are stashed on the AST as ``ast.scalar_cse_runs`` and
    ``ast.scalar_cse_temps`` (for diagnostics / tests)."""
    visitor = ScalarBlockCSEVisitor()
    visitor.visit(ast, ast)
    ast.scalar_cse_runs = visitor.runs_processed
    ast.scalar_cse_temps = visitor.temps_hoisted
    return ast
