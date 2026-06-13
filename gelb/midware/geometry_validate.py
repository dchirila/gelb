"""Geometry validation -- hard-error checks on resolved geometry.

Companion to :mod:`gelb.midware.geometry_lint`.  Lint functions
return advisory warnings; the checks here raise exceptions because
they protect against silent wrong results in the generated code.

Currently implements:

- :func:`validate_periodic_continuity` -- for every axis declared
  periodic in the lattice declaration, the node-class slice at
  coord 0 must equal the slice at coord ``N-1``.  Otherwise
  streaming would wrap distribution functions across a node-class
  boundary and silently corrupt the solution.
"""

from __future__ import annotations

import numpy as np

from gelb.midware.geometry import ResolvedGeometry
from gelb.utils.exceptions import GeLBExGeometryDiscontinuity


_AXIS_NAMES = ('x', 'y', 'z')


def validate_periodic_continuity(geo: ResolvedGeometry,
                                 periodicity_stmt=None) -> None:
    """Raise :class:`GeLBExGeometryDiscontinuity` if the painted
    geometry has a node-class discontinuity at the wrap edge of any
    periodic axis.  Silent pass otherwise.

    Parameters
    ----------
    geo : ResolvedGeometry
        The fully resolved geometry (post-paint, post-conditional-paint,
        post-border).
    periodicity_stmt : optional
        AST node associated with the lattice periodicity declaration,
        used to anchor the source-caret in the error display.  If
        ``None``, the error falls back to the default error+hint banner.
    """
    id_to_name = {i + 1: name for i, name in enumerate(geo.nc_order)}
    for axis, is_per in enumerate(geo.periodic):
        if not is_per:
            continue
        first_slice = geo.nc_map.take(0, axis=axis)
        last_slice = geo.nc_map.take(-1, axis=axis)
        if np.array_equal(first_slice, last_slice):
            continue
        # Locate the first mismatching coord deterministically (lowest
        # flat index along the remaining axes).  Cast to plain Python
        # ints -- numpy.int64's repr is "np.int64(N)", which uglifies
        # the error message.
        diff = (first_slice != last_slice)
        mis = np.unravel_index(int(np.argmax(diff)), diff.shape)
        coord_first = [int(c) for c in mis]
        coord_first.insert(axis, 0)
        coord_last = [int(c) for c in mis]
        coord_last.insert(axis, geo.nc_map.shape[axis] - 1)
        nc_id_first = int(first_slice[mis])
        nc_id_last = int(last_slice[mis])
        raise GeLBExGeometryDiscontinuity(
            axis_name=_AXIS_NAMES[axis],
            coord_first=tuple(coord_first),
            coord_last=tuple(coord_last),
            nc_first=id_to_name[nc_id_first],
            nc_last=id_to_name[nc_id_last],
            periodicity_stmt=periodicity_stmt,
        )
