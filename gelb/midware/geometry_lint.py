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
    out.extend(warn_disconnected_nc_regions(geo))
    out.extend(warn_unreachable_fluid_pockets(geo))
    return out
