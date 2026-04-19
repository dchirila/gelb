"""Geometry resolution -- node-class map from paint statements.

Resolves the ``geometry`` block's paint statements into a concrete
per-cell node-class map.  This is a pure analysis pass: it reads
the AST and produces a ``ResolvedGeometry`` data structure, without
emitting any target-language code.

Used by:
- The Fortran backend (for loop bounds, IF guards, nc_map array)
- The geometry viewer (``gelb-view geo``)
- The boundary-access validator (``validate_boundary_access``)
"""

from __future__ import annotations

import functools
import itertools
import operator
from dataclasses import dataclass, field

import numpy as np

from gelb.gelb_ast.ASTNodes import (
    PaintNodesStmt_N, ConditionalPaintStmt_N, BorderStmt_N,
    NodeClassInstaStmt_N,
)
from gelb.midware.ast_eval import (
    collect_lattice_info, get_max_dim, get_grid_sizes,
    is_periodic, eval_const_expr,
)
from gelb.midware.stencil import source_line_of
from gelb.utils.exceptions import GeLBExStencilError


@dataclass
class NodeClassInfo:
    """Metadata for a single node class.  ``source_line`` is the 1-based
    line of its ``node_class`` statement (None if unknown)."""
    name: str
    nc_id: int
    initializer: str | None
    dynamic: str | None
    gauge: str | None
    masked: bool
    bbox: list[tuple[int, int]] | None = None
    bbox_dense: bool = False
    source_line: int | None = None


@dataclass
class ResolvedGeometry:
    """The fully resolved geometry of a GeLB program.

    Attributes
    ----------
    ndim : int
        Dimensionality (1, 2, or 3).
    grid_sizes : tuple[int, ...]
        Grid size per dimension.
    nc_map : np.ndarray
        Integer array of shape ``grid_sizes`` where each cell holds the
        1-based node-class ID.  The mapping from ID to name is in
        ``nc_order``.
    nc_order : list[str]
        Ordered list of node-class names.  ``nc_order[0]`` has ID 1,
        ``nc_order[1]`` has ID 2, etc.
    nc_info : dict[str, NodeClassInfo]
        Per-node-class metadata (initializer, dynamic, gauge, masked,
        bounding box).
    boundary_contacts : dict[str, dict[int, set[str]]]
        Which node classes touch which boundary faces.
        ``boundary_contacts[nc_name][dim_idx]`` is a set of
        ``{'low', 'high'}``.
    periodic : tuple[bool, ...]
        Periodicity flag per dimension.
    border_corrections : list[tuple[tuple[int, ...], str]]
        List of ``(coords, nc_name)`` for cells repainted by
        ``border()`` statements, in the order they were applied.
    paint_ops : list[tuple]
        The paint statements in source order, each as
        ``('rect', [(lo, hi), ...], nc_name)`` for a range or point
        paint, or ``('cells', [coords, ...], nc_name)`` for a ``where``
        paint (only the cells where the predicate held).  A backend
        that materializes the node-class map at run time replays
        these in this order, then ``border_corrections``; that is the
        only way to reproduce ``nc_map`` exactly, since later paints
        override earlier ones whatever their kind.
    source_line : int | None
        1-based line of the ``geometry`` block (None if unknown).
    """
    ndim: int
    grid_sizes: tuple[int, ...]
    nc_map: np.ndarray
    nc_order: list[str]
    nc_info: dict[str, NodeClassInfo]
    boundary_contacts: dict[str, dict[int, set[str]]]
    periodic: tuple[bool, ...]
    border_corrections: list[tuple[tuple[int, ...], str]] = field(
        default_factory=list)
    source_line: int | None = None
    paint_ops: list = field(default_factory=list)


def _evaluate_predicate(stmt, nc_name, coords, bindings, ast, lattice_info):
    """The value of a ``where`` predicate at one cell, or the diagnostic
    that explains why it has none."""
    try:
        hit = eval_const_expr(
            stmt.predicate, bindings, ast=ast, lattice_info=lattice_info)
    except GeLBExStencilError:
        raise
    except (ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
        raise GeLBExStencilError(
            f"The 'where' predicate painting '{nc_name}' could"
            f" not be evaluated at cell {coords}: {exc}",
            "A paint predicate is evaluated at compile time;"
            " it may use the coordinates, constants,"
            " arithmetic, comparisons, logical operators,"
            " numeric conversions, the scalar math intrinsics"
            " and pure single-output user functions.",
            source_line=stmt.code_range.start_line,
            source_end_line=stmt.code_range.stop_line,
        ) from exc
    if not isinstance(hit, (bool, np.bool_)):
        raise GeLBExStencilError(
            f"The 'where' predicate painting '{nc_name}'"
            f" evaluated to {hit!r} at cell {coords}, not to a"
            f" bool",
            "A paint predicate must be a bool expression.",
            source_line=stmt.code_range.start_line,
            source_end_line=stmt.code_range.stop_line,
        )
    return bool(hit)


def resolve_geometry(ast, validate_continuity: bool = True) -> ResolvedGeometry:
    """Resolve geometry paint statements into a per-cell node-class map.

    Runs the full paint -> conditional-paint -> border() pipeline and
    returns a ``ResolvedGeometry`` containing the integer NC map,
    per-NC metadata, and boundary contact information.

    Parameters
    ----------
    ast : Program_N
        The typed, constant-folded AST (after frontend + midware
        passes 1-3).
    validate_continuity : bool, default True
        Run :func:`~gelb.midware.geometry_validate.validate_periodic_continuity`
        on the resolved geometry before returning.  Disable only in
        unit tests that need to inspect a deliberately discontinuous
        ``nc_map``.

    Returns
    -------
    ResolvedGeometry
    """
    lattice_info = collect_lattice_info(ast)
    ndim = get_max_dim(lattice_info)
    sizes = get_grid_sizes(lattice_info, ast=ast)
    total = functools.reduce(operator.mul, sizes, 1)

    # Flat node-class map (later paints override earlier)
    nc_map_flat = [None] * total

    def _flat_index(coords):
        idx = 0
        for i, c in enumerate(coords):
            idx = idx * sizes[i] + c
        return idx

    def _coords_from_flat(flat_idx):
        coords = []
        rem = flat_idx
        for i in range(ndim):
            stride = functools.reduce(operator.mul, sizes[i + 1:], 1)
            coords.append(rem // stride)
            rem %= stride
        return tuple(coords)

    _DIM_LABELS = ('x', 'y', 'z')
    paint_ops = []

    # --- Phase 1: apply paint statements ---
    for stmt in ast.geometry.stmts:
        if isinstance(stmt, PaintNodesStmt_N):
            nc_name = stmt.rhs.name
            given = len(stmt.lhs.elements)
            if given != ndim:
                # One range per dimension: ``nodes[:] = B`` on a 2-D grid
                # is a diagnostic, not an index error in the resolver.
                wanted = ', '.join(':' for _ in range(ndim))
                raise GeLBExStencilError(
                    f"Geometry paint to '{nc_name}' gives {given} range"
                    f"{'s' if given != 1 else ''} for a {ndim}-D grid",
                    f"Write one range per dimension, e.g. nodes[{wanted}] = "
                    f"{nc_name};",
                    source_line=stmt.code_range.start_line,
                    source_end_line=stmt.code_range.stop_line)
            if ndim == 1:
                r = stmt.lhs[0]
                lo = int(eval_const_expr(
                    r.low, ast=ast, lattice_info=lattice_info))
                hi = int(eval_const_expr(
                    r.high, ast=ast, lattice_info=lattice_info))
                if lo < 0 or hi >= sizes[0]:
                    raise GeLBExStencilError(
                        f"Geometry paint to '{nc_name}' is out of "
                        f"bounds: x-range [{lo}, {hi}] extends outside "
                        f"[0, {sizes[0] - 1}]",
                        "GeLB paint ranges are INCLUSIVE on both ends.",
                        source_line=stmt.code_range.start_line,
                        source_end_line=stmt.code_range.stop_line)
                for i in range(lo, hi + 1):
                    nc_map_flat[i] = nc_name
                paint_ops.append(('rect', [(lo, hi)], nc_name))
            else:
                ranges = []
                for i in range(ndim):
                    r = stmt.lhs[i]
                    lo = int(eval_const_expr(
                        r.low, ast=ast, lattice_info=lattice_info))
                    hi = int(eval_const_expr(
                        r.high, ast=ast, lattice_info=lattice_info))
                    if lo < 0 or hi >= sizes[i]:
                        dim_label = (_DIM_LABELS[i]
                                     if i < len(_DIM_LABELS) else f'dim{i}')
                        raise GeLBExStencilError(
                            f"Geometry paint to '{nc_name}' is out of "
                            f"bounds: {dim_label}-range [{lo}, {hi}] "
                            f"extends outside [0, {sizes[i] - 1}]",
                            "GeLB paint ranges are INCLUSIVE on both ends.",
                            source_line=stmt.code_range.start_line,
                            source_end_line=stmt.code_range.stop_line)
                    ranges.append(range(lo, hi + 1))
                for coords in itertools.product(*ranges):
                    nc_map_flat[_flat_index(coords)] = nc_name
                paint_ops.append(
                    ('rect', [(r.start, r.stop - 1) for r in ranges],
                     nc_name))

        elif isinstance(stmt, ConditionalPaintStmt_N):
            # `nodes[where P] = C;`: P is evaluated once per cell with
            # the coordinates bound to that cell.  It has been checked
            # to be a scalar bool over coordinates, constants and pure
            # functions only (GeometryDependencyValidator), so a
            # failure here is an evaluator limitation, reported as such.
            nc_name = stmt.node_class.name
            hits = []
            coord_names = _DIM_LABELS[:ndim]
            # Narrow-width arithmetic overflows to inf or wraps, as it
            # does in the generated code; NumPy need not warn about it.
            with np.errstate(all='ignore'):
                for coords in itertools.product(*(range(s) for s in sizes)):
                    hit = _evaluate_predicate(
                        stmt, nc_name, coords, dict(zip(coord_names, coords)),
                        ast, lattice_info)
                    if hit:
                        nc_map_flat[_flat_index(coords)] = nc_name
                        hits.append(coords)
            paint_ops.append(('cells', hits, nc_name))

    # border() repaints are recorded separately, in application order.
    border_corrections = []

    # --- Phase 2: apply border() statements ---
    all_coords = list(itertools.product(*(range(s) for s in sizes)))
    periodic_flags = tuple(
        is_periodic(lattice_info, i) for i in range(ndim))
    # Full Chebyshev-distance-one neighbourhood: include diagonal links
    # even when a particular lattice uses only a subset of them.
    neighbour_offsets = [delta for delta in itertools.product((-1, 0, 1), repeat=ndim)
                         if any(delta)]
    for stmt in ast.geometry.stmts:
        if isinstance(stmt, BorderStmt_N):
            src = stmt.source.name
            tgt = stmt.target.name
            repaint = []
            for coords in all_coords:
                if nc_map_flat[_flat_index(coords)] != src:
                    continue
                for delta in neighbour_offsets:
                    neighbour = []
                    for dim, step in enumerate(delta):
                        c = coords[dim] + step
                        if periodic_flags[dim]:
                            c %= sizes[dim]
                        elif not 0 <= c < sizes[dim]:
                            break  # No neighbour outside a non-periodic axis.
                        neighbour.append(c)
                    else:
                        if nc_map_flat[_flat_index(neighbour)] != src:
                            repaint.append((_flat_index(coords), coords))
                            break
            # Each rule sees a snapshot; only the next rule sees its repaints.
            for flat_idx, coords in repaint:
                nc_map_flat[flat_idx] = tgt
                border_corrections.append((coords, tgt))

    # --- Phase 3: verify full coverage ---
    for idx in range(total):
        if nc_map_flat[idx] is None:
            coords = _coords_from_flat(idx)
            # Range-attach the whole geometry block: any cell being
            # uncovered is a fault of the paint statements as a set,
            # not of one in particular, so pointing at the block is
            # the tightest honest answer we can give. The CLI output
            # renders the full block via show_source_range; the
            # VSCode extension uses the range to jump to line 1 of
            # the block (click-to-navigate).
            geom_range = getattr(ast.geometry, 'code_range', None)
            raise GeLBExStencilError(
                f"Geometry does not cover node {coords}",
                ("Every cell in the domain must be assigned a node "
                 "class by the geometry block. Typically the fix is "
                 "adding a catch-all 'nodes[:, :] = BULK;' line "
                 "before the more specific paints."),
                source_line=(geom_range.start_line
                             if geom_range is not None else None),
                source_end_line=(geom_range.stop_line
                                 if geom_range is not None else None))

    # --- Phase 4: build ordered NC list and integer map ---
    seen = set()
    nc_order = []
    for stmt in ast.geometry.stmts:
        if isinstance(stmt, PaintNodesStmt_N):
            name = stmt.rhs.name
        elif isinstance(stmt, ConditionalPaintStmt_N):
            name = stmt.node_class.name
        elif isinstance(stmt, BorderStmt_N):
            name = stmt.target.name
        else:
            continue
        if name not in seen:
            nc_order.append(name)
            seen.add(name)

    nc_ids = {name: i + 1 for i, name in enumerate(nc_order)}

    # Build numpy integer map
    nc_map_int = np.array(
        [nc_ids[nc_map_flat[i]] for i in range(total)],
        dtype=np.int32).reshape(sizes)

    # --- Phase 5: per-NC metadata ---
    nc_info = {}
    for nc_name in nc_order:
        nc_stmt = _find_node_class(ast, nc_name)
        info = NodeClassInfo(
            name=nc_name,
            nc_id=nc_ids[nc_name],
            initializer=(nc_stmt.initializer.name
                         if nc_stmt.initializer else None),
            dynamic=(nc_stmt.dynamic.name
                     if nc_stmt.dynamic else None),
            gauge=(nc_stmt.gauge.name
                   if nc_stmt.gauge else None),
            masked=nc_stmt.masked,
            source_line=source_line_of(nc_stmt),
        )
        # Bounding box
        mask = (nc_map_int == nc_ids[nc_name])
        where = np.argwhere(mask)
        if len(where) > 0:
            lo = where.min(axis=0)
            hi = where.max(axis=0)
            info.bbox = [(int(lo[i]), int(hi[i])) for i in range(ndim)]
            expected_count = functools.reduce(
                operator.mul,
                (hi[i] - lo[i] + 1 for i in range(ndim)), 1)
            info.bbox_dense = (int(mask.sum()) == expected_count)
        nc_info[nc_name] = info

    # --- Phase 6: boundary contacts ---
    boundary_contacts: dict[str, dict[int, set[str]]] = {}
    for dim_idx in range(ndim):
        if is_periodic(lattice_info, dim_idx):
            continue
        for side_label, coord_val in (('low', 0),
                                       ('high', sizes[dim_idx] - 1)):
            face_ranges = [(range(sizes[i]) if i != dim_idx
                            else [coord_val])
                           for i in range(ndim)]
            for coords in itertools.product(*face_ranges):
                flat = _flat_index(coords)
                nc_name = nc_map_flat[flat]
                if nc_name is None:
                    continue
                (boundary_contacts
                 .setdefault(nc_name, {})
                 .setdefault(dim_idx, set())
                 .add(side_label))

    resolved = ResolvedGeometry(
        ndim=ndim,
        grid_sizes=sizes,
        nc_map=nc_map_int,
        nc_order=nc_order,
        nc_info=nc_info,
        boundary_contacts=boundary_contacts,
        periodic=periodic_flags,
        border_corrections=border_corrections,
        source_line=source_line_of(ast.geometry),
        paint_ops=paint_ops,
    )

    if validate_continuity:
        # Imported here (rather than at module top) to avoid a circular
        # import: geometry_validate.py imports ResolvedGeometry from
        # this module.
        from gelb.midware.geometry_validate import (
            validate_periodic_continuity)
        validate_periodic_continuity(resolved)

    return resolved


# --- Helpers ---

def _find_node_class(ast, name: str) -> NodeClassInstaStmt_N:
    for stmt in ast.node_classes.stmts:
        if isinstance(stmt, NodeClassInstaStmt_N) and stmt.name.name == name:
            return stmt
    raise ValueError(f"Node class '{name}' not found")
