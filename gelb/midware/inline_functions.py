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

    # Monotonically increasing counter for unique alpha-rename prefixes;
    # a prefix no name of the program starts with
    counter = _Counter(_names_in(ast))

    # Process every block that can contain function calls
    for block_list in (ast.initializers, ast.dynamics, ast.gauges):
        if block_list is None:
            continue
        for block in block_list:
            if block.stmts is None:
                continue
            block.stmts.elements = _inline_block_stmts(
                block.stmts.elements, func_map, counter)

    # Also inline inside function bodies themselves (in case functions
    # call other functions), then again in the program blocks (the
    # bodies they copied held calls)
    _inline_until_done(ast.functions, func_map, counter)
    blocks = [block for block_list in (ast.initializers, ast.dynamics, ast.gauges)
              if block_list is not None for block in block_list
              if block.stmts is not None]
    _inline_until_done(blocks, func_map, counter)

    # Remove function definitions -- they are fully inlined
    ast.functions = None

    return ast


# ---------------------------------------------------------------------------
# Statement-level inlining
# ---------------------------------------------------------------------------

def _inline_block_stmts(stmts, func_map, counter):
    """Process a list of statements, inlining function calls.

    Returns a new list of statements.
    """
    result = []
    for stmt in stmts:
        _inline_one_stmt(stmt, func_map, counter, result)
    return result


def _inline_one_stmt(stmt, func_map, counter, out):
    """Inline function calls in *stmt* and append resulting statements to *out*.

    For a ``DestructuringAssignmentStmt_N`` the entire statement is replaced
    by the inlined function body.  For other statements, any embedded
    ``UserFunctionCall_N`` expressions are inlined (prefix statements are
    emitted before the original statement, and the call expression is
    replaced by a reference to the inlined output variable).
    """
    # --- Destructuring: {a, b, c} = Func(args...) ---
    if isinstance(stmt, DestructuringAssignmentStmt_N):
        rhs = stmt.rhs
        if isinstance(rhs, UserFunctionCall_N) and rhs.function_name.name in func_map:
            func = func_map[rhs.function_name.name]
            prefix = counter.fresh_prefix(rhs.function_name.name)

            # Build substitution map
            subst = {}
            stored = _stored_names(func.stmts)
            arg_names = set()

            # Inputs -> actual arguments (with temps for complex exprs)
            for param, arg in zip(func.inputs.elements, rhs.arguments):
                # First, inline any calls inside the argument itself
                prefix_stmts = []
                arg = _transform_expr(arg, func_map, counter, prefix_stmts)
                out.extend(prefix_stmts)
                arg_names |= _names_in(arg)

                pname = param.name.name
                if _is_simple_expr(arg) and pname not in stored:
                    subst[pname] = arg
                else:
                    # Create temp variable for complex argument
                    temp_name = f"{prefix}_{pname}"
                    temp_id = Identifier_N(None, temp_name)
                    _copy_inferred_type(param.name, temp_id)
                    temp_decl = VariableDeclarationStmt_N(
                        None, copy.deepcopy(param.data_type),
                        Identifier_N(None, temp_name), arg)
                    out.append(temp_decl)
                    subst[pname] = Identifier_N(None, temp_name)

            # Outputs -> destructuring targets.  An output is stored in its
            # target after the body, in the targets' order, as assignments
            # store them, with the conversion the frontend recorded
            # (``output_stores``); the body writes the target itself only
            # where that is the same: the output has the target's type, no
            # argument reads the target (``{w, q} = Two(w)`` must not see
            # ``w`` change halfway through the body) and no other output
            # goes to it
            stores = (getattr(stmt, 'output_stores', None)
                      or [None] * len(stmt.targets))
            final_stores = []
            repeated = {t.name for t in stmt.targets
                        if [u.name for u in stmt.targets].count(t.name) > 1}
            for out_param, target, store in zip(
                    func.outputs.elements, stmt.targets, stores):
                out_name = out_param.name.name
                if store is None and target.name not in arg_names \
                        and target.name not in repeated:
                    subst[out_name] = Identifier_N(None, target.name)
                    continue
                temp_name = f"{prefix}_{out_name}"
                subst[out_name] = Identifier_N(None, temp_name)
                out.append(VariableDeclarationStmt_N(
                    None, _copy_tree(out_param.data_type),
                    Identifier_N(None, temp_name), None))
                value = Identifier_N(None, temp_name)
                _copy_inferred_type(out_param.name, value)
                if store is not None:
                    value = _subst_expr(store, {out_name: value})
                target_id = Identifier_N(target.code_range, target.name)
                _copy_inferred_type(target, target_id)
                final_stores.append(VariableAssignmentStmt_N(
                    stmt.code_range, target_id, value))

            # Alpha-rename local variables
            for body_stmt in func.stmts:
                if isinstance(body_stmt, VariableDeclarationStmt_N):
                    vname = body_stmt.name.name
                    if vname not in subst:
                        new_name = f"{prefix}_{vname}"
                        subst[vname] = Identifier_N(None, new_name)
                elif isinstance(body_stmt, ConstantDefinitionStmt_N):
                    vname = body_stmt.name.name
                    if vname not in subst:
                        new_name = f"{prefix}_{vname}"
                        subst[vname] = Identifier_N(None, new_name)

            # Emit the (substituted) function body
            for body_stmt in func.stmts:
                out.append(_subst_stmt(body_stmt, subst))
            out.extend(final_stores)

            return

    # --- All other statement types: inline calls in expressions ---
    prefix_stmts = []
    new_stmt = _transform_stmt(stmt, func_map, counter, prefix_stmts)
    out.extend(prefix_stmts)
    out.append(new_stmt)


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

            subst = {}
            stored = _stored_names(func.stmts)

            # Inputs -> actual arguments: a parameter the body stores into
            # is a variable of its own, initialized with the argument (the
            # caller's variable is never written through it)
            for param, arg in zip(func.inputs.elements, new_args):
                pname = param.name.name
                if _is_simple_expr(arg) and pname not in stored:
                    subst[pname] = arg
                else:
                    temp_name = f"{prefix}_{pname}"
                    temp_id = Identifier_N(None, temp_name)
                    _copy_inferred_type(param.name, temp_id)
                    temp_decl = VariableDeclarationStmt_N(
                        None, copy.deepcopy(param.data_type),
                        Identifier_N(None, temp_name), arg)
                    prefix_stmts.append(temp_decl)
                    subst[pname] = Identifier_N(None, temp_name)

            # Alpha-rename outputs and emit their declarations
            assert len(func.outputs.elements) == 1, \
                f"Single-output function expected, got {len(func.outputs.elements)} outputs for '{fname}'"
            out_param = func.outputs.elements[0]
            out_new_name = f"{prefix}_{out_param.name.name}"
            subst[out_param.name.name] = Identifier_N(None, out_new_name)
            # Declare the output variable
            prefix_stmts.append(VariableDeclarationStmt_N(
                None, copy.deepcopy(out_param.data_type),
                Identifier_N(None, out_new_name), None))

            # Alpha-rename locals
            for body_stmt in func.stmts:
                if isinstance(body_stmt, VariableDeclarationStmt_N):
                    vname = body_stmt.name.name
                    if vname not in subst:
                        subst[vname] = Identifier_N(None,
                                                    f"{prefix}_{vname}")
                elif isinstance(body_stmt, ConstantDefinitionStmt_N):
                    vname = body_stmt.name.name
                    if vname not in subst:
                        subst[vname] = Identifier_N(None,
                                                    f"{prefix}_{vname}")

            # Emit substituted function body as prefix statements
            for body_stmt in func.stmts:
                prefix_stmts.append(_subst_stmt(body_stmt, subst))

            # Return a reference to the output variable
            result_id = Identifier_N(None, out_new_name)
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
                owner.stmts.elements, func_map, counter)
        if counter[0] == inlined:
            return


class _Counter(list):
    """The prefix counter (``counter[0]``) and the names of the program,
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
