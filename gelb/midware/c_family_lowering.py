"""Prepare a separate, typed AST for C-family code generation."""

import copy
import itertools

from gelb.gelb_ast import ASTNodes as A
from gelb.frontend.ASTInvariantValidator import (
    canonicalize_types, check_c_lowering, check_stage2,
)
from gelb.midware.BlockMutationHelper import declare_temp, fresh_name
from gelb.utils.exceptions import GeLBInternalInvariantError


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
    """Copy Stage 2, lift matmul vectors, and check the C-family boundary."""
    c_ast = copy.deepcopy(ast)
    lift_matmul_args(c_ast)
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
