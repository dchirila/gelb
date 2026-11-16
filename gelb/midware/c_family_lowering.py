"""Prepare a separate, typed AST for C-family code generation."""

import copy
import itertools

from gelb.gelb_ast import ASTNodes as A
from gelb.frontend.ASTInvariantValidator import (
    canonicalize_types, check_c_lowering, check_stage2,
    c_value_edges, c_global_matrices, c_literal_context,
)
from gelb.midware.BlockMutationHelper import declare_temp, fresh_name
from gelb.midware.ast_eval import collect_lattice_info
from gelb.utils.exceptions import GeLBExTypeError, GeLBInternalInvariantError


def _replace(parent, key, value):
    if isinstance(parent, list):
        parent[key] = value
    else:
        setattr(parent, key, value)


def _scalar_type(node):
    return A.ArrayDataType_N(node.code_range, node.canonical_type.dtype, A.List_N(node.code_range))


def _element(array, index, dtype):
    cr = array.code_range
    bounds = A.Range_N(cr, A.IntLiteral_N(cr, index), A.IntLiteral_N(cr, index))
    result = A.RectSelOfArrayElems_N(cr, copy.deepcopy(array), [bounds])
    result.inferred_type = A.ArrayDataType_N(cr, dtype, A.List_N(cr))
    return result


def desugar_local_array_slices(ast):
    """Turn resolved one-dimensional value slices into typed element lists."""
    for group in (ast.initializers, ast.dynamics, ast.gauges):
        for block in group or ():
            stack = list(c_value_edges(block.stmts))
            while stack:
                parent, key, node = stack.pop()
                if isinstance(node, A.RectSelOfArrayElems_N) and len(node.element_ranges) == 1:
                    bounds = node.element_ranges[0]
                    if (isinstance(bounds.low, A.IntLiteral_N)
                            and isinstance(bounds.high, A.IntLiteral_N)
                            and 0 <= bounds.low.value < bounds.high.value):
                        lo, hi = bounds.low.value, bounds.high.value
                        cr, dtype = node.code_range, node.canonical_type.dtype
                        values = A.List_N(cr)
                        values.elements = [_element(node.array_name, i, dtype) for i in range(lo, hi + 1)]
                        node = A.Array1DLiteral_N(cr, values)
                        node.inferred_type = A.ArrayDataType_N(cr, dtype, A.IntLiteral_N(cr, hi - lo + 1))
                        _replace(parent, key, node)
                stack.extend(reversed(list(c_value_edges(node))))


def _df_bounds(selection, lattices):
    bounds = selection.element_ranges[-1]
    lo = bounds.low.value if isinstance(bounds.low, A.IntLiteral_N) else 0
    hi = (bounds.high.value if isinstance(bounds.high, A.IntLiteral_N)
          else lattices[selection.lattice_name.name]['q'] - 1)
    return lo, hi


def _narrow_df(node, index):
    cr = node.code_range
    node.element_ranges[-1] = A.Range_N(cr, A.IntLiteral_N(cr, index), A.IntLiteral_N(cr, index))
    node.inferred_type = _scalar_type(node)


def _scalarize_literal_store(root, offset, lattices):
    """Select one direction, retaining scalar reductions and singleton conversions."""
    result = [root]
    stack = [(result, 0, root)]
    while stack:
        parent, key, node = stack.pop()
        if isinstance(node, A.TypePromotionNode_N) and node.is_singleton_coercion():
            continue
        if isinstance(node, A.IntrinsicFunctionCall_N) and node.function_name in ('sum', 'dot_prod', 'determinant'):
            continue
        if isinstance(node, (A.BroadcastNode_N, A.Array1DLiteral_N)):
            replacement = (node.scalar_expr if isinstance(node, A.BroadcastNode_N)
                           else node.value[offset])
            _replace(parent, key, replacement)
            stack.append((parent, key, replacement))
            continue
        if isinstance(node, A.RectSelOfArrayElems_N):
            continue
        canonical = node.canonical_type
        if canonical is not None and canonical.is_array:
            if isinstance(node, A.Identifier_N) and len(canonical.dims) == 1:
                _replace(parent, key, _element(node, offset, canonical.dtype))
                continue
            if isinstance(node, A.RectSelOfLatticeInDFs_N):
                lo, _ = _df_bounds(node, lattices)
                _narrow_df(node, lo + offset)
                continue
            scalar_type = _scalar_type(node)
            node.inferred_type = scalar_type
            if isinstance(node, A.TypePromotionNode_N):
                node.target_type = scalar_type
        stack.extend(reversed(list(c_value_edges(node))))
    return result[0]


def _hoist_store_intrinsics(stmt, block, counter, matrices):
    declarations = []
    stack = [(stmt, 'rhs', stmt.rhs, False)]
    while stack:
        parent, key, node, visited = stack.pop()
        if not visited:
            stack.append((parent, key, node, True))
            stack.extend((p, k, c, False) for p, k, c in reversed(list(c_value_edges(node))))
            continue
        if not (isinstance(node, A.IntrinsicFunctionCall_N)
                and node.canonical_type is not None and len(node.canonical_type.dims) == 1):
            continue
        supported = node.function_name == 'bounce_back_dfs'
        if node.function_name == 'matmul':
            matrix, vector = node.arguments
            supported = (isinstance(matrix, A.Identifier_N) and matrix.name in matrices
                         and isinstance(vector, A.Identifier_N))
        if not supported:
            continue
        cr = node.code_range
        dtype = A.ArrayDataType_N(cr, node.canonical_type.dtype,
                                 A.IntLiteral_N(cr, node.canonical_type.dims[0]))
        reference = A.Identifier_N(cr, fresh_name(block, 'gelb_tmp_', counter))
        reference.inferred_type = copy.deepcopy(dtype)
        reference.symbol_tag = 'variable declaration'
        declaration = A.VariableDeclarationStmt_N(cr, dtype, copy.deepcopy(reference), node)
        declare_temp(block, declaration)
        declarations.append(declaration)
        _replace(parent, key, reference)
    return declarations


def expand_literal_slice_stores(ast):
    """Hoist supported array calls and emit a typed scalar store per direction."""
    matrices = c_global_matrices(ast)
    lattices = collect_lattice_info(ast) if ast.lattices is not None else {}
    for group in (ast.initializers, ast.dynamics, ast.gauges):
        for block in group or ():
            counter = itertools.count(0)
            statements = []
            for stmt in block.stmts or ():
                literal, invalid = c_literal_context(stmt, matrices)
                if literal is not None and invalid is not None:
                    raise GeLBExTypeError(invalid,
                        'This inline array expression is not supported by the C-family backends.',
                        'Bind the expression to a local array[...] variable first, then use that variable.')
                if (literal is None or not isinstance(stmt, A.LatticeOutSelectionAssignmentStmt_N)
                        or not isinstance(stmt.lhs, A.RectSelOfLatticeOutDFs_N)
                        or stmt.lhs.canonical_type is None or not stmt.lhs.canonical_type.is_array):
                    statements.append(stmt)
                    continue
                statements.extend(_hoist_store_intrinsics(stmt, block, counter, matrices))
                lo, hi = _df_bounds(stmt.lhs, lattices)
                for i in range(hi - lo + 1):
                    lhs = copy.deepcopy(stmt.lhs)
                    _narrow_df(lhs, lo + i)
                    rhs = _scalarize_literal_store(copy.deepcopy(stmt.rhs), i, lattices)
                    statements.append(A.LatticeOutSelectionAssignmentStmt_N(stmt.code_range, lhs, rhs))
            if block.stmts is not None:
                block.stmts.elements = statements


def lift_matmul_args(ast):
    """Hoist vector expressions in dependency order, numbering each block anew."""
    for group in (ast.initializers, ast.dynamics, ast.gauges):
        for block in group or ():
            counter = itertools.count(0)
            statements = []
            for stmt in block.stmts or ():
                stack = [(stmt, False)]
                while stack:
                    node, visited = stack.pop()
                    if not isinstance(node, A.Node_N):
                        continue
                    if not visited:
                        stack.append((node, True))
                        stack.extend((child, False) for child in reversed(node.get_children()))
                        continue
                    if not (isinstance(node, A.IntrinsicFunctionCall_N)
                            and node.function_name == 'matmul' and len(node.arguments) == 2):
                        continue
                    arg = node.arguments[1]
                    if (isinstance(arg, A.Identifier_N) or arg.canonical_type is None
                            or len(arg.canonical_type.dims) != 1):
                        continue
                    name = fresh_name(block, 'gelb_matmul_in_', counter)
                    decl_type = copy.deepcopy(arg.inferred_type)
                    # Inferred slice shapes may be lists; declarations use a
                    # scalar extent for a one-dimensional array.
                    decl_type.shape = A.IntLiteral_N(arg.code_range, arg.canonical_type.dims[0])
                    reference = A.Identifier_N(arg.code_range, name)
                    reference.inferred_type = copy.deepcopy(decl_type)
                    reference.canonical_type = arg.canonical_type
                    reference.symbol_tag = 'variable declaration'
                    decl = A.VariableDeclarationStmt_N(
                        arg.code_range, decl_type,
                        copy.deepcopy(reference), initial_value=arg)
                    declare_temp(block, decl)
                    statements.append(decl)
                    node.arguments[1] = reference
                statements.append(stmt)
            if block.stmts is not None:
                block.stmts.elements = statements


def prepare_c_family_ast(ast, *, capture_ast=None, strict_invariants=True):
    """Copy Stage 2, prepare array expressions, and check the C-family boundary."""
    c_ast = copy.deepcopy(ast)
    desugar_local_array_slices(c_ast)
    lift_matmul_args(c_ast)
    expand_literal_slice_stores(c_ast)
    canonicalize_types(c_ast)
    if capture_ast is not None:
        capture_ast(c_ast, 'c_lowering')
    for check in (check_c_lowering, check_stage2):
        try:
            check(c_ast)
        except GeLBInternalInvariantError as error:
            if strict_invariants:
                raise
            from gelb.utils.output_to_terminal import warning_with_hint_to_term
            warning_with_hint_to_term(
                f'(internal) {error}', 'Please report this compiler invariant violation.', None)
    return c_ast
