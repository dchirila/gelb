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

    # Monotonically increasing counter for unique alpha-rename prefixes
    counter = [0]

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
    # call other functions).  Repeat until no calls remain.
    changed = True
    while changed:
        changed = False
        for func in ast.functions:
            old_len = len(func.stmts.elements)
            func.stmts.elements = _inline_block_stmts(
                func.stmts.elements, func_map, counter)
            if len(func.stmts.elements) != old_len:
                changed = True

    # Re-process program blocks (function bodies may have expanded)
    for block_list in (ast.initializers, ast.dynamics, ast.gauges):
        if block_list is None:
            continue
        for block in block_list:
            if block.stmts is None:
                continue
            block.stmts.elements = _inline_block_stmts(
                block.stmts.elements, func_map, counter)

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
            prefix = f"__{rhs.function_name.name}_{counter[0]}"
            counter[0] += 1

            # Build substitution map
            subst = {}

            # Inputs -> actual arguments (with temps for complex exprs)
            for param, arg in zip(func.inputs.elements, rhs.arguments):
                # First, inline any calls inside the argument itself
                prefix_stmts = []
                arg = _transform_expr(arg, func_map, counter, prefix_stmts)
                out.extend(prefix_stmts)

                pname = param.name.name
                if _is_simple_expr(arg):
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

            # Outputs -> destructuring targets (direct mapping)
            for out_param, target in zip(func.outputs.elements, stmt.targets):
                subst[out_param.name.name] = Identifier_N(None, target.name)

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

    # DestructuringAssignmentStmt_N with non-user-func RHS (shouldn't
    # happen, but pass through unchanged)
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

            prefix = f"__{fname}_{counter[0]}"
            counter[0] += 1

            subst = {}

            # Inputs -> actual arguments
            for param, arg in zip(func.inputs.elements, new_args):
                pname = param.name.name
                if _is_simple_expr(arg):
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

    if isinstance(expr, RectSelOfArrayElems_N):
        # Array selection like arr[i] -- transform the array expr and indices
        expr.array_name = _transform_expr(expr.array_name, func_map,
                                          counter, prefix_stmts)
        return expr

    # Leaf nodes: Identifier_N, literals -- return as-is
    return expr


# ---------------------------------------------------------------------------
# AST substitution (deep-copy with identifier replacement)
# ---------------------------------------------------------------------------

def _subst_stmt(stmt, subst):
    """Deep-copy a statement, replacing identifiers per *subst* map.

    *subst* maps ``str`` (variable name) -> ``Identifier_N`` (replacement).
    """
    if isinstance(stmt, VariableDeclarationStmt_N):
        new_name_id = _subst_identifier(stmt.name, subst)
        new_init = (_subst_expr(stmt.initial_value, subst)
                    if stmt.initial_value is not None else None)
        result = VariableDeclarationStmt_N(
            stmt.code_range, copy.deepcopy(stmt.data_type),
            new_name_id, new_init)
        return result

    if isinstance(stmt, ConstantDefinitionStmt_N):
        # Inline as a VariableDeclarationStmt_N (not a Fortran parameter:
        # the backends emit it as an assignment)
        new_name_id = _subst_identifier(stmt.name, subst)
        new_value = _subst_expr(stmt.value, subst)
        result = VariableDeclarationStmt_N(
            stmt.code_range, copy.deepcopy(stmt.data_type),
            new_name_id, new_value)
        return result

    if isinstance(stmt, VariableAssignmentStmt_N):
        new_lhs = _subst_expr(stmt.lhs, subst)
        new_rhs = _subst_expr(stmt.rhs, subst)
        return VariableAssignmentStmt_N(stmt.code_range, new_lhs, new_rhs)

    # Fallback: deep copy (shouldn't normally be reached for function bodies)
    return copy.deepcopy(stmt)


def _subst_expr(expr, subst):
    """Deep-copy an expression, replacing identifiers per *subst* map."""
    if expr is None:
        return None

    if isinstance(expr, Identifier_N):
        return _subst_identifier(expr, subst)

    if isinstance(expr, (IntLiteral_N, RealLiteral_N, BoolLiteral_N,
                         StringLiteral_N)):
        return copy.deepcopy(expr)

    if isinstance(expr, BinaryExpr_N):
        result = copy.copy(expr)
        result.left = _subst_expr(expr.left, subst)
        result.right = _subst_expr(expr.right, subst)
        return result

    if isinstance(expr, UnaryExpr_N):
        result = copy.copy(expr)
        result.value = _subst_expr(expr.value, subst)
        return result

    if isinstance(expr, IntrinsicFunctionCall_N):
        result = copy.copy(expr)
        new_args = List_N(expr.arguments.code_range)
        for arg in expr.arguments:
            new_args.append(_subst_expr(arg, subst))
        result.arguments = new_args
        return result

    if isinstance(expr, UserFunctionCall_N):
        # A call inside a function body passes the body's names on
        # (``Inner(p)`` in ``Outer``): substitute its arguments, so
        # that the later inlining of this call sees the caller's
        # values and not a parameter name, which does not exist after
        # inlining.
        result = copy.copy(expr)
        new_args = List_N(expr.arguments.code_range)
        for arg in expr.arguments:
            new_args.append(_subst_expr(arg, subst))
        result.arguments = new_args
        return result

    if isinstance(expr, Array1DLiteral_N):
        result = copy.copy(expr)
        new_elems = List_N(expr.value.code_range)
        for elem in expr.value:
            new_elems.append(_subst_expr(elem, subst))
        result.value = new_elems
        return result

    if isinstance(expr, TypePromotionNode_N):
        result = copy.copy(expr)
        result.expr = _subst_expr(expr.expr, subst)
        return result

    if isinstance(expr, BroadcastNode_N):
        result = copy.copy(expr)
        result.scalar_expr = _subst_expr(expr.scalar_expr, subst)
        return result

    if isinstance(expr, RectSelOfArrayElems_N):
        result = copy.copy(expr)
        result.array_name = _subst_expr(expr.array_name, subst)
        return result

    # Fallback: deep copy
    return copy.deepcopy(expr)


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

def _is_simple_expr(expr):
    """Check if an expression is simple enough to substitute directly
    (no redundant re-evaluation concern)."""
    return isinstance(expr, (Identifier_N, IntLiteral_N, RealLiteral_N,
                             BoolLiteral_N, StringLiteral_N))


def _copy_inferred_type(src, dst):
    """Copy inferred_type from *src* to *dst* if present."""
    if hasattr(src, 'inferred_type'):
        dst.inferred_type = src.inferred_type
