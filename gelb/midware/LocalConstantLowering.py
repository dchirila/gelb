#!/usr/bin/env python3
"""Lower block-local constants to typed declarations.

A ``const`` inside an initializer, dynamic, gauge or function block is a
``ConstantDefinitionStmt_N``.  The frontend has already enforced what
makes it a constant (no assignment to it, checked by
``ConstantAssignmentValidationVisitor``), and the folder has substituted
its value into every use it could.  The statement itself still has to
be lowered, and no backend had a declaration for it: Fortran emitted
the assignment without a type, Highway and CUDA stopped with an
unsupported statement.

This pass rewrites every surviving block-local
``ConstantDefinitionStmt_N`` as a ``VariableDeclarationStmt_N`` with the
same type, name, value and source range, so that the backends see one
kind of typed local declaration.  Global constants are untouched: they
have their own emission (``parameter`` in Fortran, ``constexpr`` or an
assigned global in C++).
"""

from gelb.gelb_ast.ASTNodes import (
    ConstantDefinitionStmt_N,
    VariableDeclarationStmt_N,
)


def lower_local_constants(ast):
    """Rewrite block-local constants as typed declarations, in place."""
    for block_list in (ast.initializers, ast.dynamics, ast.gauges,
                       ast.functions):
        if block_list is None:
            continue
        for block in block_list:
            stmts = getattr(block, 'stmts', None)
            if stmts is None:
                continue
            stmts.elements = [_lowered(stmt) for stmt in stmts.elements]
    return ast


def _lowered(stmt):
    if not isinstance(stmt, ConstantDefinitionStmt_N):
        return stmt
    decl = VariableDeclarationStmt_N(
        stmt.code_range, stmt.data_type, stmt.name, stmt.value)
    if hasattr(stmt, 'inferred_type'):
        decl.inferred_type = stmt.inferred_type
    return decl
