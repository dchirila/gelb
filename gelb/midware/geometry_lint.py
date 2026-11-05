"""Geometry lint warnings.

Pure analysis pass over a ``ResolvedGeometry`` that catches common
geometry mistakes before the user runs the simulation.

Each lint function returns a list of ``(message, hint, source_line)``
tuples, matching the pattern used by ``warn_writeonly_dynamics`` and
``warn_unused_lattices`` in ``stage2_midware.py``; ``source_line`` is the
1-based line the warning is about (the ``node_class`` statement or the
``geometry`` block), or None.

The aggregator ``all_geometry_warnings(geo, stencils=None)`` runs
every check and returns the union.  The ``stencils`` argument is
accepted for compatibility with compiler/viewer call sites, but the
current checks are geometry-only.
"""

from __future__ import annotations

import numpy as np

from gelb.midware.geometry import ResolvedGeometry


def warn_empty_node_classes(
        geo: ResolvedGeometry) -> list[tuple[str, str, int | None]]:
    """Flag node classes that end up with no cells.

    Every paint of the class was overridden by a later one, its ``where``
    matched nothing, its range was reversed, or ``border()`` converted
    all of its cells.  The program is valid and the class's blocks never
    run, but it is almost always a mistake or a constant (``-D``) that
    made a region vanish.
    """
    warnings = []
    for name, info in geo.nc_info.items():
        if (geo.nc_map == info.nc_id).any():
            continue
        warnings.append((
            f"Node class '{name}' has no cells",
            "Every paint of it was overridden by a later paint or a "
            "border() rule, or matched no cell, so none of its blocks "
            "run.  Check the paint statements and the constants they "
            "use (a -D value, for example).",
            info.source_line))
    return warnings


def warn_reversed_paint_ranges(
        geo: ResolvedGeometry) -> list[tuple[str, str, int | None]]:
    """Flag range paints whose bounds run backwards on some axis.

    Paint ranges are inclusive and run from low to high, so
    ``nodes[40:30, :]`` paints nothing; it is never what was meant.
    """
    labels = ('x', 'y', 'z')
    warnings = []
    for kind, ranges, name in geo.paint_ops:
        if kind != 'rect':
            continue
        for axis, (lo, hi) in enumerate(ranges):
            if lo > hi:
                warnings.append((
                    f"A paint of '{name}' covers no cells: its "
                    f"{labels[axis]}-range {lo}:{hi} runs backwards",
                    f"Paint ranges are inclusive and run from low to high; "
                    f"write {hi}:{lo} to paint those cells.",
                    geo.source_line))
                break
    return warnings


def warn_disconnected_nc_regions(
        geo: ResolvedGeometry) -> list[tuple[str, str, int | None]]:
    """Flag NCs that have multiple disconnected regions on the grid.

    A node class painted in a single contiguous region is the common
    case.  Multiple disconnected components usually means: two
    independent obstacles, OR an unintended paint pattern that splits
    a region into pieces (e.g. periodic boundary that doesn't wrap as
    expected).

    Uses full (8/26-connectivity) so staircase boundaries on a circular
    obstacle don't get falsely split into many tiny pieces.

    Skips trivial NCs (<=2 cells) where "disconnected" is meaningless.
    Threshold for warning: more than 4 components (allows top/bottom
    walls + a couple of obstacles without crying wolf).
    """
    from scipy.ndimage import label, generate_binary_structure

    warnings = []
    # Full connectivity in N dims (rank=ndim, connectivity=ndim)
    structure = generate_binary_structure(geo.ndim, geo.ndim)
    for name, info in geo.nc_info.items():
        mask = (geo.nc_map == info.nc_id)
        n_cells = int(mask.sum())
        if n_cells <= 2:
            continue
        _, n_components = label(mask, structure=structure)
        if n_components > 4:
            msg = (
                f"Node class '{name}' has {n_components} disconnected "
                f"regions ({n_cells:,} cells total)"
            )
            hint = (
                "If this is intentional (multiple obstacles + channel "
                "walls), ignore.  Otherwise, check your paint statements "
                "for missing cells along the boundary that fragment what "
                "should be one connected region."
            )
            warnings.append((msg, hint, info.source_line))
    return warnings


def warn_unreachable_fluid_pockets(
        geo: ResolvedGeometry,
        fluid_nc_names: list[str] | None = None,
) -> list[tuple[str, str, int | None]]:
    """Flag fluid pockets that are isolated from the main fluid region.

    Builds a single "fluid mask" from all non-masked, non-static NCs
    (or from an explicit list), runs connected-component analysis,
    and warns if there's more than one component.

    A pocket of fluid surrounded by walls would not exchange mass or
    momentum with the rest of the simulation -- usually a geometry
    bug.
    """
    from scipy.ndimage import label

    if fluid_nc_names is None:
        fluid_nc_names = [
            name for name, info in geo.nc_info.items()
            if not info.masked and info.dynamic
        ]
    if not fluid_nc_names:
        return []

    fluid_mask = np.zeros_like(geo.nc_map, dtype=bool)
    for name in fluid_nc_names:
        nc_id = geo.nc_info[name].nc_id
        fluid_mask |= (geo.nc_map == nc_id)

    if not fluid_mask.any():
        return []

    _, n_components = label(fluid_mask)
    if n_components > 1:
        return [(
            f"Fluid region (NCs: {', '.join(fluid_nc_names)}) is split "
            f"into {n_components} disconnected pockets",
            "Fluid pockets surrounded by walls cannot exchange mass with "
            "the bulk — usually a geometry bug.  If intentional, ignore. "
            "Otherwise, check that walls don't fully enclose part of the "
            "fluid region.",
            geo.source_line,
        )]
    return []


def all_geometry_warnings(
        geo: ResolvedGeometry,
        stencils=None) -> list[tuple[str, str, int | None]]:
    """Run every geometry-lint check and return the union."""
    del stencils  # kept for source/backward compatibility
    out = []
    out.extend(warn_reversed_paint_ranges(geo))
    out.extend(warn_empty_node_classes(geo))
    out.extend(warn_disconnected_nc_regions(geo))
    out.extend(warn_unreachable_fluid_pockets(geo))
    return out
