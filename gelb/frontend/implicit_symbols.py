#!/usr/bin/env python3

from gelb.gelb_ast.ASTNodes import (
    Array1DLiteral_N,
    ConstantDefinitionStmt_N,
    DynamicBlock_N,
    FunctionBlock_N,
    GaugeBlock_N,
    GlobalConstantsBlock_N,
    GeometryBlock_N,
    Identifier_N,
    InitializerBlock_N,
    IntLiteral_N,
    LatticeInstaStmt_N,
    LatticesBlock_N,
    NodeClassesBlock_N,
    Program_N,
    UnaryMinusExpr_N,
)
from gelb.utils.exceptions import GeLBExTypeError


COORDINATE_SYMBOL_NAMES = ("x", "y", "z")
DIMENSION_CONSTANT_NAMES = ("Nx", "Ny", "Nz")
TIMESTEP_SYMBOL_NAME = "t"

RUNTIME_IMPLICIT_SYMBOL_NAMES = (
    *COORDINATE_SYMBOL_NAMES,
    TIMESTEP_SYMBOL_NAME,
)
ALL_IMPLICIT_SYMBOL_NAMES = (
    *COORDINATE_SYMBOL_NAMES,
    *DIMENSION_CONSTANT_NAMES,
    TIMESTEP_SYMBOL_NAME,
)


def active_coordinate_names(dimensionality):
    """Return the coordinate symbols that exist for a lattice dimensionality."""
    return _active_names(COORDINATE_SYMBOL_NAMES, dimensionality)


def active_dimension_names(dimensionality):
    """Return the dimension constants that exist for a lattice dimensionality."""
    return _active_names(DIMENSION_CONSTANT_NAMES, dimensionality)


def is_implicit_symbol(name):
    return name in ALL_IMPLICIT_SYMBOL_NAMES


def allows_runtime_coordinates(block):
    return isinstance(block, (InitializerBlock_N, DynamicBlock_N, GaugeBlock_N))


def allows_dimension_constants(block):
    return isinstance(
        block,
        (InitializerBlock_N, DynamicBlock_N, GaugeBlock_N, GeometryBlock_N),
    )


def allows_predicate_coordinates(block):
    """The geometry block sees the coordinates inside ``where`` predicates.

    They are predicate inputs, bound per cell at compile time, not
    run-time variables: a range or point paint may not use them
    (``GeometryDependencyValidator`` rejects that), and ``t`` never
    exists here.
    """
    return isinstance(block, GeometryBlock_N)


def implicit_symbols_for_block(block, dimensionality):
    """Return implicit symbols valid for unresolved references in a block."""
    names = []

    if allows_runtime_coordinates(block):
        names.extend(active_coordinate_names(dimensionality))
        names.append(TIMESTEP_SYMBOL_NAME)
    elif allows_predicate_coordinates(block):
        names.extend(active_coordinate_names(dimensionality))

    if allows_dimension_constants(block):
        names.extend(active_dimension_names(dimensionality))

    return tuple(names)


def reserved_definition_names_for_block(block):
    """
    Return implicit names that may not be defined in a block.

    Per-site blocks see coordinates, timestep, and dimension constants. Global
    definition contexts reserve all implicit names to keep public symbols from
    colliding with language-level names. Functions only inherit global
    dimension constants, so they may use x/y/z/t as ordinary local names.
    """
    if allows_runtime_coordinates(block):
        return (
            *COORDINATE_SYMBOL_NAMES,
            TIMESTEP_SYMBOL_NAME,
            *DIMENSION_CONSTANT_NAMES,
        )
    if isinstance(block, FunctionBlock_N):
        return DIMENSION_CONSTANT_NAMES
    if isinstance(
        block,
        (
            Program_N,
            GlobalConstantsBlock_N,
            LatticesBlock_N,
            NodeClassesBlock_N,
            GeometryBlock_N,
        ),
    ):
        return ALL_IMPLICIT_SYMBOL_NAMES
    return DIMENSION_CONSTANT_NAMES


def grid_dimensions_from_lattices(lattices_block):
    """
    Extract the first lattice's grid-size expressions.

    The implicit symbol injector uses the first lattice as the source of
    `Nx`/`Ny`/`Nz`. Keeping that extraction here lets early validation apply
    the same dimensionality policy before those symbols are inserted.
    """
    if lattices_block is None:
        return [IntLiteral_N(None, 1)]

    stmts = getattr(lattices_block, "stmts", None)
    elements = getattr(stmts, "elements", stmts)
    if not elements:
        return [IntLiteral_N(None, 1)]

    first_lattice = elements[0]
    if not isinstance(first_lattice, LatticeInstaStmt_N):
        return [IntLiteral_N(None, 1)]

    grid_size = getattr(first_lattice, "grid_size", None)
    if not grid_size:
        return [IntLiteral_N(None, 1)]

    if isinstance(grid_size, IntLiteral_N):
        return [grid_size]

    if isinstance(grid_size, Array1DLiteral_N):
        value = getattr(grid_size, "value", None)
        elements = getattr(value, "elements", value)
        if elements:
            return list(elements)

    return [grid_size]


def lattice_statements(lattices_block):
    """The ``LatticeInstaStmt_N`` nodes of a lattices block, in order."""
    stmts = getattr(lattices_block, "stmts", None)
    elements = getattr(stmts, "elements", stmts) or []
    return [s for s in elements if isinstance(s, LatticeInstaStmt_N)]


def resolve_int_constant(ast_root, expr):
    """
    Best-effort compile-time integer value of ``expr`` *before* the
    constants pass has run: integer literals, unary minus, and the names
    of global constants that are defined by such an expression.
    ``None`` when the value is not known this early.
    """
    if isinstance(expr, IntLiteral_N):
        return expr.value
    if isinstance(expr, UnaryMinusExpr_N):
        inner = resolve_int_constant(ast_root, expr.value)
        return -inner if inner is not None else None
    if isinstance(expr, Identifier_N) and isinstance(ast_root, Program_N):
        block = ast_root.global_constants
        stmts = getattr(block, "stmts", None)
        for stmt in getattr(stmts, "elements", stmts) or []:
            if (isinstance(stmt, ConstantDefinitionStmt_N)
                    and getattr(stmt.name, "name", stmt.name) == expr.name):
                return resolve_int_constant(ast_root, stmt.value)
    return None


def validate_grid_size_rank(lattice_stmt, ast_root):
    """
    Reject a ``grid_size`` whose rank does not match ``d`` at the
    declaration.

    The implicit coordinate symbols (``x``, ``y``, ``z``) are derived from
    the *shape* of ``grid_size``; without this check a scalar (or a single
    named constant) on a 2D/3D lattice silently makes the program 1D and
    the mismatch only surfaces at the first use of ``y`` as an unknown
    symbol.  Out-of-range ``d`` and values that are not known before the
    constants pass are left to that pass.
    """
    d_value = resolve_int_constant(ast_root, getattr(lattice_stmt, "d", None))
    grid_size = getattr(lattice_stmt, "grid_size", None)
    if d_value is None or grid_size is None or not (1 <= d_value <= 3):
        return
    if isinstance(grid_size, Array1DLiteral_N):
        value = getattr(grid_size, "value", None)
        n = len(getattr(value, "elements", value) or [])
        if n != d_value:
            raise GeLBExTypeError(
                grid_size,
                f"Grid size has {n} elements but d={d_value}",
                f"Grid size must have exactly {d_value} "
                f"element{'s' if d_value > 1 else ''} to match dimensionality"
            )
    elif d_value != 1:
        example = "{" + ", ".join(("NX", "NY", "NZ")[:d_value]) + "}"
        raise GeLBExTypeError(
            grid_size,
            f"Grid size scalar is invalid for d={d_value}",
            f"For d={d_value}, grid_size must be a {d_value}-element array, "
            f"not a scalar: write the array literal at the declaration, "
            f"e.g. {example} (the elements may be constants); a single "
            f"named constant is not accepted either"
        )


def dimensionality_from_program(ast_root, default=3):
    if not isinstance(ast_root, Program_N):
        return default
    return len(grid_dimensions_from_lattices(ast_root.lattices))


def _active_names(names, dimensionality):
    try:
        count = int(dimensionality)
    except (TypeError, ValueError):
        count = 0
    return names[:max(0, min(count, len(names)))]
