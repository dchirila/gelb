#!/usr/bin/env python3
"""
Apply command-line constant overrides (-D NAME=VALUE) to the AST.

This module is called after ``build_symbols_tables`` and
``add_implicit_symbols`` but *before* ``resolve_all_constants``, so
that derived constants (``const real K = 2*PI/dble(N);``) are
automatically recomputed with the overridden values.
"""

import math

from gelb.gelb_ast.ASTNodes import (
    ArrayDataType_N,
    BoolLiteral_N,
    ConstantDefinitionStmt_N,
    IntLiteral_N,
    List_N,
    RealLiteral_N,
)
from gelb.utils.exceptions import GeLBException


_REAL_TYPES = frozenset({'real', 'real16', 'real32', 'real64'})
_INT_TYPES = frozenset({'int', 'int8', 'int16', 'int32', 'int64'})


def parse_overrides(define_tuple):
    """Parse ``('-D', 'N=512', '-D', 'TAU=0.8')``-style tuples.

    Parameters
    ----------
    define_tuple : tuple[str, ...]
        Each element is a ``NAME=VALUE`` string (Click already strips
        the ``-D`` flag).

    Returns
    -------
    dict[str, str]
        Mapping from constant name to raw string value.
    """
    overrides = {}
    for item in define_tuple:
        if '=' not in item:
            raise GeLBException(
                f"Invalid override format '{item}'.",
                "Expected NAME=VALUE (e.g. -D N=512)")
        name, _, raw_value = item.partition('=')
        name = name.strip()
        raw_value = raw_value.strip()
        if not name:
            raise GeLBException(
                f"Invalid override format '{item}': empty constant name.",
                "Use NAME=VALUE format.")
        if not raw_value:
            raise GeLBException(
                f"Invalid override format '{item}': empty value for '{name}'.",
                "Provide a value after '='.")
        overrides[name] = raw_value
    return overrides


def _parse_value_to_literal(raw_value, element_dtype, const_name):
    """Convert a CLI string value to the appropriate AST literal node.

    Parameters
    ----------
    raw_value : str
        The raw string from the command line.
    element_dtype : str
        The declared type of the constant (e.g. ``'int'``, ``'real'``).
    const_name : str
        Name of the constant (for error messages).

    Returns
    -------
    IntLiteral_N | RealLiteral_N | BoolLiteral_N
    """
    if element_dtype in _INT_TYPES:
        try:
            return IntLiteral_N(None, int(raw_value))
        except ValueError:
            raise GeLBException(
                f"Cannot parse '{raw_value}' as {element_dtype} for "
                f"constant '{const_name}'.",
                "Expected an integer value.")

    if element_dtype in _REAL_TYPES:
        try:
            value = float(raw_value)
        except ValueError:
            raise GeLBException(
                f"Cannot parse '{raw_value}' as {element_dtype} for "
                f"constant '{const_name}'.",
                "Expected a numeric value (e.g. 0.6, 1e-3).")
        if not math.isfinite(value):
            # the same rule as for a literal in the source: a value no
            # backend can spell is rejected here, not there
            raise GeLBException(
                f"Value '{raw_value}' for constant '{const_name}' is "
                f"outside the range of {element_dtype}.",
                "A real override must be a finite number (at most about "
                "1.8e308); 'inf' and 'nan' are not accepted.")
        return RealLiteral_N(None, value)

    if element_dtype == 'bool':
        low = raw_value.lower()
        if low == 'true':
            return BoolLiteral_N(None, True)
        if low == 'false':
            return BoolLiteral_N(None, False)
        raise GeLBException(
            f"Cannot parse '{raw_value}' as bool for constant "
            f"'{const_name}'.",
            "Expected 'true' or 'false'.")

    raise GeLBException(
        f"Unsupported type '{element_dtype}' for constant override "
        f"'{const_name}'.",
        "Only int, real, real32, real64, and bool constants can be overridden.")


def _is_scalar_type(data_type):
    """Check if an ArrayDataType_N represents a scalar (empty shape)."""
    shape = data_type.shape
    if isinstance(shape, List_N) and len(shape.elements) == 0:
        return True
    return False


def apply_constant_overrides(ast, overrides):
    """Replace constant values in the AST with CLI-provided overrides.

    Parameters
    ----------
    ast : Program_N
        The program AST (must have symbol tables built).
    overrides : dict[str, str]
        Mapping from constant name to raw string value.

    Returns
    -------
    Program_N
        The modified AST (mutated in place, also returned for chaining).
    """
    if not overrides:
        return ast

    if ast.global_constants is None:
        names = ', '.join(overrides.keys())
        raise GeLBException(
            f"Cannot override constants ({names}): this program has no "
            f"global_constants block.",
            "Add a global_constants {{ ... }} block to your program.")

    # Collect available constant names for error messages
    available = []
    for stmt in ast.global_constants.stmts:
        if isinstance(stmt, ConstantDefinitionStmt_N):
            available.append(stmt.name.name)

    for name, raw_value in overrides.items():
        # Find the ConstantDefinitionStmt_N in the statement list
        target_stmt = None
        for stmt in ast.global_constants.stmts:
            if isinstance(stmt, ConstantDefinitionStmt_N):
                if stmt.name.name == name:
                    target_stmt = stmt
                    break

        if target_stmt is None:
            raise GeLBException(
                f"Cannot override '{name}': not declared in "
                f"global_constants block.",
                f"Available constants: {', '.join(available)}")

        # Reject array constants
        if not _is_scalar_type(target_stmt.data_type):
            raise GeLBException(
                f"Cannot override array constant '{name}' from command "
                f"line.",
                "Only scalar constants can be overridden with -D.")

        element_dtype = target_stmt.data_type.element_dtype
        new_literal = _parse_value_to_literal(raw_value, element_dtype, name)
        target_stmt.value = new_literal

    return ast
