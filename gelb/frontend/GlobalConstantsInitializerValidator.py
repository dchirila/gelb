#!/usr/bin/env python3
"""What a global constant's initializer may call.

A global constant is a compile-time value: the resolver substitutes it
into its uses and the folder evaluates it.  Two calls the parser accepts
have no compile-time value and used to reach the native compiler as an
undefined function:

* ``random()``, which draws at run time (user manual, Numerical
  semantics: Random numbers);
* a user function, which the inliner expands only inside the
  initializer, dynamic, gauge and function blocks ("not in this
  version" for a global constant).

Both are reported here, at the call, before the constants are resolved.
"""

from gelb.frontend.intrinsic_functions import STATEFUL_INTRINSIC_NAMES
from gelb.gelb_ast.ASTNodes import (
    ConstantDefinitionStmt_N,
    IntrinsicFunctionCall_N,
    Node_N,
    UserFunctionCall_N,
)
from gelb.utils.exceptions import GeLBExTypeError


def validate_global_constant_initializers(ast):
    """Raise ``GeLBExTypeError`` at the first call a global constant's
    initializer may not make."""
    block = getattr(ast, 'global_constants', None)
    if block is None or block.stmts is None:
        return
    for stmt in block.stmts:
        if not isinstance(stmt, ConstantDefinitionStmt_N):
            continue
        const_name = getattr(stmt.name, 'name', stmt.name)
        for node in _walk(stmt.value):
            if isinstance(node, IntrinsicFunctionCall_N) \
                    and node.function_name in STATEFUL_INTRINSIC_NAMES:
                raise GeLBExTypeError(
                    node,
                    f"{node.function_name}() in the global constant "
                    f"'{const_name}'",
                    "A global constant is a compile-time value, and "
                    f"{node.function_name}() draws a new number at run "
                    "time, once per call.  Draw where the value is used: "
                    "in an initializer, a dynamic or a gauge."
                )
            if isinstance(node, UserFunctionCall_N):
                func_name = getattr(node.function_name, 'name',
                                    node.function_name)
                raise GeLBExTypeError(
                    node,
                    f"Function '{func_name}' called in the global constant "
                    f"'{const_name}'",
                    "A user function in a global constant is not in this "
                    "version: functions are expanded only inside "
                    "initializer, dynamic, gauge and function blocks.  "
                    "Write the constant's value as an expression of "
                    "literals, constants and intrinsics, or call the "
                    "function where the value is used."
                )


def _walk(node):
    """Every node of the subtree at ``node``, ``node`` first."""
    if node is None:
        return
    yield node
    if isinstance(node, Node_N):
        for child in node.get_children():
            if isinstance(child, Node_N):
                yield from _walk(child)
