"""
Midware pass: inline all user-defined function calls.

GeLB user-defined functions are pure (no side effects, no lattice access),
so inlining is always safe and semantically equivalent.  Benefits:

* Eliminates device-function call overhead on GPU backends.
* Allows the host compiler to optimise across the (now straight-line)
  code.

The pass replaces every ``UserFunctionCall_N`` (single-output, used as an
expression) and every ``DestructuringAssignmentStmt_N`` (multi-output) with
the function body, alpha-renaming local/output variables and substituting
input parameters with the actual arguments.

After this pass ``ast.functions`` is set to ``None`` so that backends skip
emitting separate function/subroutine definitions.
"""

import copy

from gelb.midware.BlockMutationHelper import declare_temp

from gelb.gelb_ast.ASTNodes import (
    Array1DLiteral_N,
    BinaryExpr_N,
    BoolLiteral_N,
    BroadcastNode_N,
    ConstantDefinitionStmt_N,
    DestructuringAssignmentStmt_N,
    FunctionBlock_N,
    Identifier_N,
    IntLiteral_N,
    IntrinsicFunctionCall_N,
    LatticeOutSelectionAssignmentStmt_N,
    List_N,
    Node_N,
    RealLiteral_N,
    RectSelOfArrayElems_N,
    StringLiteral_N,
    TypePromotionNode_N,
    UnaryExpr_N,
    UserFunctionCall_N,
    VariableAssignmentStmt_N,
    VariableDeclarationStmt_N,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def inline_functions(ast):
    """Inline all user-defined function calls and remove function blocks.

    This is an AST-to-AST transformation.  After this pass every
    ``UserFunctionCall_N`` and ``DestructuringAssignmentStmt_N`` that
    referenced a user function has been replaced by the function's body
    statements (with appropriate variable renaming).

    Parameters
    ----------
    ast : Program_N
        The GeLB AST (after type inference and constant folding).

    Returns
    -------
    Program_N
        The transformed AST with ``ast.functions`` set to ``None``.
    """
    if ast.functions is None or len(ast.functions.elements) == 0:
        return ast

    # Build lookup: function_name -> FunctionBlock_N
    func_map = {func.name.name: func for func in ast.functions}

    call_args = {}

    # Finish each program block against the original function bodies so
    # nested calls get flat prefixes, independent of declaration order.
    for block_list in (ast.initializers, ast.dynamics, ast.gauges):
        for block in block_list or ():
            _inline_owner(block, func_map, call_args, in_blocks=True)

    # Retain synchronized bodies for geometry evaluation. Callees must
    # be complete before their callers copy them.
    functions = _callee_order(func_map)
    for func in functions:
        _inline_owner(func, func_map, call_args, in_blocks=False)

    ast._inlined_functions = tuple(functions)
    ast.functions = None
    ast.inline_call_args = call_args

    return ast


def _inline_owner(owner, func_map, call_args, *, in_blocks):
    if owner.stmts is None:
        return
    taken = _names_in(owner)
    table = owner.symbol_defs
    while table is not None:
        taken.update(symbol.name for symbol in table)
        table = table.parent_table
    # Capture user names only once: synthesized destructuring targets
    # must not be mistaken for caller variables on subsequent rounds.
    state = _State(taken, call_args)
    state.in_blocks = in_blocks
    owner.stmts.elements = _inline_block_stmts(
        owner.stmts.elements, func_map, state, owner)
    _inline_until_done([owner], func_map, state)


def _callee_order(func_map):
    """Callees before callers, with alphabetical ties and cycle fallback."""
    pending = {}
    for name, func in func_map.items():
        calls, stack = set(), [func.stmts]
        while stack:
            node = stack.pop()
            if isinstance(node, UserFunctionCall_N):
                calls.add(node.function_name.name)
            if isinstance(node, Node_N):
                stack.extend(node.get_children())
        pending[name] = calls & func_map.keys()
    ordered = []
    while pending:
        ready = sorted(name for name, calls in pending.items() if not calls)
        if not ready:
            ordered.extend(sorted(pending))
            break
        name = ready[0]
        ordered.append(name)
        del pending[name]
        for calls in pending.values():
            calls.discard(name)
    return [func_map[name] for name in ordered]


def _inline_until_done(owners, func_map, counter):
    """Inline the calls in the statements of *owners* (functions or
    blocks) again while a call is left and the last pass inlined one.
    Recursion is rejected by the frontend, so this ends whatever the
    order of the definitions; a call no pass inlines (in the DF selector
    or a spatial index of a lattice store) is left to the checks that
    follow, which report it."""
    while any(_contains_call(owner.stmts, func_map) for owner in owners):
        inlined = counter[0]          # the prefixes given out so far
        for owner in owners:
            owner.stmts.elements = _inline_block_stmts(
                owner.stmts.elements, func_map, counter, owner)
        if counter[0] == inlined:
            return


class _Counter(list):
    """The owner's prefix counter (``counter[0]``) and original visible names,
    which no prefix may start (a user may write ``__F_0_a``)."""

    def __init__(self, taken):
        super().__init__([0])
        self.taken = taken

    def fresh_prefix(self, fname):
        while True:
            prefix = f"__{fname}_{self[0]}"
            self[0] += 1
            if not any(name.startswith(prefix + "_") for name in self.taken):
                return prefix


class _State(_Counter):
    """The owner's prefix counter and names (``_Counter``); the
    calls inlined, each with the sources of its arguments (recorded on
    the program as ``inline_call_args``, for the folder that runs after
    inlining to tell whether the call is a call of constants: only the
    folder decides that); the calls the statement being inlined itself
    comes from, innermost first; and whether the statements being
    inlined are a program block's (a function body's otherwise)."""

    def __init__(self, taken, call_args):
        super().__init__(taken)
        self.call_args = call_args
        self.chain = ()
        self.in_blocks = True

    def new_call(self, fname, code_range):
        """A new call: (function name, code range, id)."""
        k = len(self.call_args)
        self.call_args[k] = []
        return (fname, code_range, k)

    def argument(self, call, source):
        """Record an argument source of *call*: ``('expr', node)`` for an
        argument substituted for its parameter, ``(role, name)`` for one
        bound to a temporary (``'argument'``, or ``'param'`` when the
        body stores into it)."""
        self.call_args[call[2]].append(source)


def _bound(decl, role, call):
    """``decl``, a declaration of a name only inlined code holds, with
    its binding ``decl.inline_binding = (role, call)``: the role
    (``'argument'``, ``'param'`` for a parameter the body stores into,
    ``'local'``, ``'output'``) and the call (function name, code range,
    id).  The folder that runs after inlining carries an argument's
    constant into its uses, and a local's or an output's only when the
    call is a call of constants, which it decides from the arguments'
    values (gelb.midware.ConstantFoldingVisitor)."""
    decl.inline_binding = (role, call)
    return decl


def _bound_copy(body_stmt, subst, locals_, call, state, remap):
    """A body statement copied for a call: a declaration of one of the
    call's locals (``locals_``) is bound as such; one that an earlier
    inlining into the body had bound keeps its role, for a copy of that
    inner call whose argument sources are renamed as the body is
    (``remap``: inner call -> its copy)."""
    stmt = _subst_stmt(body_stmt, subst)
    chain = tuple(_remapped(c, subst, state, remap)
                  for c in getattr(body_stmt, 'inline_calls', ()))
    stmt.inline_calls = chain
    if isinstance(stmt, VariableDeclarationStmt_N) and \
            getattr(body_stmt.name, 'name', None) in locals_:
        earlier = getattr(body_stmt, 'inline_binding', None)
        if earlier is None:
            _bound(stmt, 'local', call)
        else:
            role, inner = earlier
            _bound(stmt, role, _remapped(inner, subst, state, remap))
    return stmt


def _remapped(call, subst, state, remap):
    """The copy of an inner call, made once per copy of the body that
    holds it, its argument sources renamed by *subst*."""
    fname, code_range, k = call
    if k not in remap:
        copied = state.new_call(fname, code_range)
        for kind, source in state.call_args[k]:
            if kind == 'expr':
                state.argument(copied, (kind, _subst_expr(source, subst)))
            else:
                renamed = subst.get(source)
                state.argument(copied, (kind, renamed.name
                                        if isinstance(renamed, Identifier_N) else source))
        remap[k] = copied
    return remap[k]


def _tagged(stmt, chain):
    """``stmt``, recording the calls it was inlined from, innermost
    first, as ``stmt.inline_calls``: ((function name, code range of the
    call), ...).  Diagnostics found in inlined code name these calls."""
    stmt.inline_calls = chain
    return stmt


def call_chain_text(chain):
    """``", in the call Sq(3037000500) on line 7"`` for each call of
    ``chain`` (``stmt.inline_calls``), innermost first; empty for code
    that was not inlined."""
    return "".join(f", in the call {_call_text(fname, code_range)}"
                   f" on line {code_range.start_line}"
                   for fname, code_range, *_ in chain if code_range is not None)


def value_of_call_text(node):
    """``", the value of the call Sq(0) on line 7"`` when ``node`` (a
    literal, under any conversions) is the constant value the folder
    carried out of an inlined call (``inlined_from_call``); else empty."""
    while isinstance(node, TypePromotionNode_N):
        node = node.expr
    origin = getattr(node, 'inlined_from_call', None)
    if origin is None:
        return ""
    return call_chain_text((origin,)).replace(
        ", in the call", ", the value of the call", 1)


def _call_text(fname, code_range):
    """The call as written, when it is on one line of the source."""
    import gelb.utils.config
    source = getattr(gelb.utils.config, 'GELB_SRC_RAW', None)
    if source and code_range.start_line == code_range.stop_line:
        lines = source.splitlines()
        if 0 < code_range.start_line <= len(lines):
            text = lines[code_range.start_line - 1][
                code_range.start_col:code_range.stop_col + 1]
            if text.startswith(fname) and text.endswith(")"):
                return text
    return f"{fname}(...)"


# ---------------------------------------------------------------------------
# Statement-level inlining
# ---------------------------------------------------------------------------

def _inline_block_stmts(stmts, func_map, counter, block=None):
    """Process a list of statements, inlining function calls.

    Returns a new list of statements.
    """
    result = []
    original = {id(stmt) for stmt in stmts}
    for stmt in stmts:
        _inline_one_stmt(stmt, func_map, counter, result)
    for stmt in result:
        if isinstance(stmt, VariableDeclarationStmt_N) and id(stmt) not in original:
            declare_temp(block, stmt)
    return result


def _inline_one_stmt(stmt, func_map, counter, out):
    """Inline function calls in *stmt* and append resulting statements to *out*.

    For a ``DestructuringAssignmentStmt_N`` the entire statement is replaced
    by the inlined function body.  For other statements, any embedded
    ``UserFunctionCall_N`` expressions are inlined (prefix statements are
    emitted before the original statement, and the call expression is
    replaced by a reference to the inlined output variable).
    """
    counter.chain = getattr(stmt, 'inline_calls', ())
    # --- Destructuring: {a, b, c} = Func(args...) ---
    if isinstance(stmt, DestructuringAssignmentStmt_N):
        rhs = stmt.rhs
        if isinstance(rhs, UserFunctionCall_N) and rhs.function_name.name in func_map:
            fname = rhs.function_name.name
            func = func_map[fname]
            prefix = counter.fresh_prefix(fname)
            site = counter.chain                  # the call's own statement
            call = counter.new_call(fname, rhs.code_range)
            body_chain = (call,) + site

            # Inputs -> actual arguments, a call in an argument inlined
            # first
            subst = {}
            stored = _stored_names(func.stmts)
            arg_names = set()
            for param, arg in zip(func.inputs.elements, rhs.arguments):
                prefix_stmts = []
                arg = _transform_expr(arg, func_map, counter, prefix_stmts)
                out.extend(prefix_stmts)
                arg_names |= _names_in(arg)
                _bind_argument(param, arg, stored, prefix, call, site,
                               counter, subst, out)

            # Outputs -> destructuring targets.  An output is stored in its
            # target after the body, in the targets' order, as assignments
            # store them, with the conversion the frontend recorded
            # (``output_stores``).  The body writes the target itself only
            # where that is the same and nothing the folder decides can
            # depend on it: the target is a variable of the caller's block
            # (a user variable, which the folder never carries; not a name
            # of a function body or of the inliner, which a call of
            # constants carries), the output has the target's type, no
            # argument reads the target (``{w, q} = Two(w)`` must not see
            # ``w`` change halfway through the body), no other output goes
            # to it, and the body does not read it.  Otherwise the output
            # is the call's own name, which the folder carries when the
            # call is a call of constants (only the folder decides that).
            stores = (getattr(stmt, 'output_stores', None)
                      or [None] * len(stmt.targets))
            reads = _read_names(func.stmts)
            final_stores = []
            repeated = {t.name for t in stmt.targets
                        if [u.name for u in stmt.targets].count(t.name) > 1}
            for out_param, target, store in zip(
                    func.outputs.elements, stmt.targets, stores):
                out_name = out_param.name.name
                if counter.in_blocks and target.name in counter.taken \
                        and store is None and target.name not in arg_names \
                        and target.name not in repeated and out_name not in reads:
                    subst[out_name] = Identifier_N(None, target.name)
                    continue
                temp_name = f"{prefix}_{out_name}"
                subst[out_name] = Identifier_N(None, temp_name)
                out.append(_tagged(_bound(VariableDeclarationStmt_N(
                    None, _copy_tree(out_param.data_type),
                    Identifier_N(None, temp_name), None),
                    'output', call), site))
                value = Identifier_N(None, temp_name)
                _copy_inferred_type(out_param.name, value)
                if store is not None:
                    value = _subst_expr(store, {out_name: value})
                target_id = Identifier_N(target.code_range, target.name)
                _copy_inferred_type(target, target_id)
                final_stores.append(_tagged(VariableAssignmentStmt_N(
                    stmt.code_range, target_id, value), site))

            _emit_body(func, subst, prefix, call, body_chain, counter, out)
            out.extend(final_stores)
            return

    # --- All other statement types: inline calls in expressions ---
    prefix_stmts = []
    new_stmt = _transform_stmt(stmt, func_map, counter, prefix_stmts)
    out.extend(prefix_stmts)
    out.append(new_stmt)


def _bind_argument(param, arg, stored, prefix, call, site, counter, subst, out):
    """Bind *param* of *call* to *arg* in *subst*: a simple argument the
    body does not store into is substituted for the parameter; any other
    is stored in a variable of the call's own, declared in *out* (the
    caller's variable is never written through a parameter).  The
    argument's source is recorded for the folder."""
    pname = param.name.name
    if _is_simple_expr(arg) and pname not in stored:
        subst[pname] = arg
        counter.argument(call, ('expr', arg))
        return
    temp_name = f"{prefix}_{pname}"
    role = 'param' if pname in stored else 'argument'
    out.append(_tagged(_bound(VariableDeclarationStmt_N(
        None, copy.deepcopy(param.data_type),
        Identifier_N(None, temp_name), arg), role, call), site))
    counter.argument(call, (role, temp_name))
    subst[pname] = Identifier_N(None, temp_name)


def _emit_body(func, subst, prefix, call, body_chain, counter, out):
    """Copy the body of *func* into *out* with the caller's names:
    *subst* maps the parameters and outputs, each local is renamed with
    the call's *prefix*, and each statement records the calls it comes
    from (*body_chain*, innermost first)."""
    locals_ = set()
    for body_stmt in func.stmts:
        if isinstance(body_stmt, (VariableDeclarationStmt_N,
                                  ConstantDefinitionStmt_N)):
            vname = body_stmt.name.name
            if vname not in subst:
                subst[vname] = Identifier_N(None, f"{prefix}_{vname}")
                locals_.add(vname)
    remap = {}
    for body_stmt in func.stmts:
        copied = _bound_copy(body_stmt, subst, locals_, call, counter, remap)
        out.append(_tagged(copied, copied.inline_calls + body_chain))


# ---------------------------------------------------------------------------
# Statement transformation (shallow - delegates to expression transform)
# ---------------------------------------------------------------------------

def _transform_stmt(stmt, func_map, counter, prefix_stmts):
    """Transform a statement by inlining any function calls in its
    sub-expressions.  Prefix statements (inlined function bodies) are
    appended to *prefix_stmts*.  Returns the (possibly modified) statement.
    """
    if isinstance(stmt, LatticeOutSelectionAssignmentStmt_N):
        new_rhs = _transform_expr(stmt.rhs, func_map, counter, prefix_stmts)
        stmt.rhs = new_rhs
        return stmt

    if isinstance(stmt, VariableAssignmentStmt_N):
        new_rhs = _transform_expr(stmt.rhs, func_map, counter, prefix_stmts)
        stmt.rhs = new_rhs
        return stmt

    if isinstance(stmt, VariableDeclarationStmt_N):
        if stmt.initial_value is not None:
            new_val = _transform_expr(stmt.initial_value, func_map,
                                      counter, prefix_stmts)
            stmt.initial_value = new_val
        return stmt

    if isinstance(stmt, ConstantDefinitionStmt_N):
        new_val = _transform_expr(stmt.value, func_map, counter,
                                  prefix_stmts)
        stmt.value = new_val
        return stmt

    # Every other statement (an element store ``a[1] = F(x);``, a
    # destructuring from an array): a call anywhere in it is inlined.
    _transform_fields(stmt, func_map, counter, prefix_stmts)
    return stmt


# ---------------------------------------------------------------------------
# Expression transformation - the core inlining logic
# ---------------------------------------------------------------------------

def _transform_expr(expr, func_map, counter, prefix_stmts):
    """Recursively transform an expression, inlining any
    ``UserFunctionCall_N`` found within.

    Inlined function bodies are appended to *prefix_stmts*.  The call
    expression is replaced by an ``Identifier_N`` referencing the
    (alpha-renamed) output variable.

    Returns the transformed expression.
    """
    if expr is None:
        return None

    # --- User function call: inline it ---
    if isinstance(expr, UserFunctionCall_N):
        fname = expr.function_name.name
        if fname in func_map:
            func = func_map[fname]

            # First, recursively transform arguments
            new_args = []
            for arg in expr.arguments:
                new_args.append(
                    _transform_expr(arg, func_map, counter, prefix_stmts))

            prefix = counter.fresh_prefix(fname)
            site = counter.chain                  # the call's own statement
            call = counter.new_call(fname, expr.code_range)
            body_chain = (call,) + site

            subst = {}
            stored = _stored_names(func.stmts)
            for param, arg in zip(func.inputs.elements, new_args):
                _bind_argument(param, arg, stored, prefix, call, site,
                               counter, subst, prefix_stmts)

            # The output: a variable of the call's own
            assert len(func.outputs.elements) == 1, \
                f"Single-output function expected, got {len(func.outputs.elements)} outputs for '{fname}'"
            out_param = func.outputs.elements[0]
            out_new_name = f"{prefix}_{out_param.name.name}"
            subst[out_param.name.name] = Identifier_N(None, out_new_name)
            prefix_stmts.append(_tagged(_bound(VariableDeclarationStmt_N(
                None, copy.deepcopy(out_param.data_type),
                Identifier_N(None, out_new_name), None),
                'output', call), site))

            _emit_body(func, subst, prefix, call, body_chain, counter,
                       prefix_stmts)

            # Return a reference to the output variable, at the call
            result_id = Identifier_N(expr.code_range, out_new_name)
            # Preserve the inferred type from the original call
            if hasattr(expr, 'inferred_type') and expr.inferred_type is not None:
                result_id.inferred_type = expr.inferred_type
            return result_id

    # --- Recurse into sub-expressions ---
    if isinstance(expr, BinaryExpr_N):
        expr.left = _transform_expr(expr.left, func_map, counter,
                                    prefix_stmts)
        expr.right = _transform_expr(expr.right, func_map, counter,
                                     prefix_stmts)
        return expr

    if isinstance(expr, UnaryExpr_N):
        expr.value = _transform_expr(expr.value, func_map, counter,
                                     prefix_stmts)
        return expr

    if isinstance(expr, TypePromotionNode_N):
        expr.expr = _transform_expr(expr.expr, func_map, counter,
                                    prefix_stmts)
        return expr

    if isinstance(expr, BroadcastNode_N):
        expr.scalar_expr = _transform_expr(expr.scalar_expr, func_map,
                                           counter, prefix_stmts)
        return expr

    if isinstance(expr, IntrinsicFunctionCall_N):
        new_elems = []
        for arg in expr.arguments:
            new_elems.append(
                _transform_expr(arg, func_map, counter, prefix_stmts))
        expr.arguments.elements = new_elems
        return expr

    if isinstance(expr, Array1DLiteral_N):
        new_elems = []
        for elem in expr.value:
            new_elems.append(
                _transform_expr(elem, func_map, counter, prefix_stmts))
        expr.value.elements = new_elems
        return expr

    # Any other node: a call in any of its values is inlined (identifiers
    # and literals have none)
    _transform_fields(expr, func_map, counter, prefix_stmts)
    return expr


def _transform_fields(node, func_map, counter, prefix_stmts):
    """Inline the calls in every value of *node*, in place, in the
    order of its fields."""
    if isinstance(node, List_N):
        node.elements = [_transform_expr(e, func_map, counter, prefix_stmts)
                         if isinstance(e, Node_N) else e
                         for e in node.elements]
        return
    done = {}           # a node shared by two fields (``w[k]``'s range) is one
    for field in _value_fields(node):
        child = getattr(node, field)
        if id(child) not in done:
            done[id(child)] = _transform_expr(child, func_map, counter, prefix_stmts)
        setattr(node, field, done[id(child)])


# ---------------------------------------------------------------------------
# AST substitution (deep-copy with identifier replacement)
# ---------------------------------------------------------------------------

def _subst_stmt(stmt, subst):
    """Copy a statement of a function body, replacing identifiers per
    *subst* (``str`` -> ``Identifier_N`` or argument expression) in every
    value it holds: a declaration's name and value, an assignment's two
    sides, the targets and arguments of a destructuring call, the array
    and value of an element store.  No kind of statement is copied with
    the function's own names, which do not exist where it is inlined.
    """
    if isinstance(stmt, ConstantDefinitionStmt_N):
        # Inline as a VariableDeclarationStmt_N (not a Fortran parameter:
        # the backends emit it as an assignment)
        return VariableDeclarationStmt_N(
            stmt.code_range, _copy_tree(stmt.data_type),
            _subst_expr(stmt.name, subst), _subst_expr(stmt.value, subst))
    return _subst_expr(stmt, subst)


def _subst_expr(expr, subst):
    """Copy an expression (or any node), replacing identifiers per
    *subst* in every value position."""
    if expr is None:
        return None
    if isinstance(expr, Identifier_N):
        return _subst_identifier(expr, subst)
    result = _copy_tree(expr)
    _rename_fields(result, subst)
    return result


# Fields that hold no value of the function body: the name of the
# function called, and types (a shape names constants, never a
# parameter).  Metadata (``inferred_type``, ``function_block``, ...) is
# not a field (``Node_N.get_children_names``).
_NOT_VALUES = frozenset({'function_name', 'data_type', 'target_type',
                         'target_array_type'})


def _value_fields(node):
    """The fields of *node* that hold a value node, in field order."""
    return [f for f in node.get_children_names()
            if f not in _NOT_VALUES and isinstance(getattr(node, f), Node_N)]


def _copy_tree(node, memo=None):
    """A copy of *node* and of every node below it, a node shared below
    it shared in the copy too; the metadata it carries (its type, a
    call's function block) is shared with the original."""
    if not isinstance(node, Node_N):
        return node
    memo = {} if memo is None else memo
    if id(node) in memo:
        return memo[id(node)]
    result = memo[id(node)] = copy.copy(node)
    for field, value in vars(result).items():
        if field in ('inferred_type', 'function_block'):
            continue
        if isinstance(value, Node_N):
            setattr(result, field, _copy_tree(value, memo))
        elif isinstance(value, list):
            setattr(result, field, [_copy_tree(v, memo) for v in value])
    return result


def _rename_fields(node, subst, seen=None):
    """Replace, in place, every identifier in a value position below
    *node* per *subst* (a node shared by two fields once)."""
    seen = set() if seen is None else seen
    if id(node) in seen:
        return
    seen.add(id(node))
    if isinstance(node, List_N):
        # one pass: a substituted argument is the caller's, never renamed
        for i, e in enumerate(node.elements):
            if isinstance(e, Identifier_N):
                node.elements[i] = _subst_identifier(e, subst)
            elif isinstance(e, Node_N):
                _rename_fields(e, subst, seen)
        return
    for field in _value_fields(node):
        child = getattr(node, field)
        if isinstance(child, Identifier_N):
            setattr(node, field, _subst_identifier(child, subst))
        else:
            _rename_fields(child, subst, seen)


def _subst_identifier(node, subst):
    """Substitute an Identifier_N per the *subst* map.

    The substitution value may be an ``Identifier_N`` (for alpha-renames)
    or any expression node (for input parameter substitution with an
    actual argument like a literal or complex expression).
    """
    if node.name in subst:
        replacement = subst[node.name]
        if isinstance(replacement, Identifier_N):
            result = Identifier_N(node.code_range, replacement.name)
            if hasattr(node, 'inferred_type'):
                result.inferred_type = node.inferred_type
            return result
        # Non-identifier replacement (literal, expression, etc.)
        result = copy.deepcopy(replacement)
        if hasattr(node, 'inferred_type') and not hasattr(result, 'inferred_type'):
            result.inferred_type = node.inferred_type
        return result
    # Not in map -- copy
    result = Identifier_N(node.code_range, node.name)
    if hasattr(node, 'inferred_type'):
        result.inferred_type = node.inferred_type
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _contains_call(node, func_map):
    """True when a call of a user function is left below *node*."""
    if isinstance(node, UserFunctionCall_N) and node.function_name.name in func_map:
        return True
    if isinstance(node, List_N):
        children = node.elements
    elif isinstance(node, Node_N):
        children = [getattr(node, f) for f in _value_fields(node)]
    else:
        return False
    return any(_contains_call(c, func_map) for c in children if isinstance(c, Node_N))


def _names_in(node):
    """The names read or written below *node*."""
    if isinstance(node, Identifier_N):
        return {node.name}
    if isinstance(node, List_N):
        children = node.elements
    elif isinstance(node, Node_N):
        children = [getattr(node, f) for f in _value_fields(node)]
    else:
        return set()
    names = set()
    for c in children:
        if isinstance(c, Node_N):
            names |= _names_in(c)
    return names


def _read_names(stmts):
    """The names a function body reads (a store's target is not read;
    the indices of an element store are)."""
    read = set()
    for stmt in stmts:
        if isinstance(stmt, VariableDeclarationStmt_N):
            read |= _names_in(stmt.initial_value) if stmt.initial_value is not None else set()
        elif isinstance(stmt, ConstantDefinitionStmt_N):
            read |= _names_in(stmt.value)
        elif isinstance(stmt, DestructuringAssignmentStmt_N):
            read |= _names_in(stmt.rhs)
        elif hasattr(stmt, 'lhs') and hasattr(stmt, 'rhs'):
            target = stmt.lhs
            if isinstance(target, RectSelOfArrayElems_N):
                read |= _names_in(target) - _names_in(target.array_name)
            elif not isinstance(target, Identifier_N):
                read |= _names_in(target)
            read |= _names_in(stmt.rhs)
        else:
            read |= _names_in(stmt)
    return read


def _stored_names(stmts):
    """The names a function body stores into: assignment targets, the
    arrays of element stores, destructuring targets."""
    stored = set()
    for stmt in stmts:
        if isinstance(stmt, DestructuringAssignmentStmt_N):
            stored |= {t.name for t in stmt.targets}
            continue
        target = getattr(stmt, 'lhs', None)
        if isinstance(target, Identifier_N):
            stored.add(target.name)
        elif isinstance(target, RectSelOfArrayElems_N):
            stored |= _names_in(target.array_name)
    return stored


def _is_simple_expr(expr):
    """Check if an expression is simple enough to substitute directly
    (no redundant re-evaluation concern)."""
    return isinstance(expr, (Identifier_N, IntLiteral_N, RealLiteral_N,
                             BoolLiteral_N, StringLiteral_N))


def _copy_inferred_type(src, dst):
    """Copy inferred_type from *src* to *dst* if present."""
    if hasattr(src, 'inferred_type'):
        dst.inferred_type = src.inferred_type
