#!/usr/bin/env python3
"""Tests for the periodic-continuity geometry validator.

The validator raises :class:`GeLBExGeometryDiscontinuity` when a
``.gelb`` program declares an axis periodic but the painted geometry
has a node-class discontinuity at that axis' wrap edge.  Without the
check, streaming would silently wrap distribution functions across
the discontinuity, producing wrong results.
"""

import pytest

from gelb.tests.test_utils import get_typed_ast
from gelb.midware.geometry import resolve_geometry
from gelb.utils.exceptions import GeLBExGeometryDiscontinuity


# ---------------------------------------------------------------------------
# Program builders -- keep each as small as possible so a failing test
# is reproducible from the test source alone.
# ---------------------------------------------------------------------------

def _make_1d_program(geometry: str, periodicity: str, nx: int = 10) -> str:
    return f"""
    simulation_description("1D continuity test");
    lattices {{
        lattice f(1, 1, int, {nx}, {periodicity});
    }}
    initializer InitB {{ f.out[x | 0] = 0; }}
    initializer InitW {{ f.out[x | 0] = 1; }}
    dynamic DynB {{ f.out[x | 0] = f.in[x | 0]; }}
    dynamic DynW {{ f.out[x | 0] = f.in[x | 0]; }}
    gauge OutB -> (int val) {{ val = f.in[x | 0]; }}
    gauge OutW -> (int val) {{ val = f.in[x | 0]; }}
    node_classes {{
        node_class BULK(InitB, DynB, OutB);
        node_class WALL(InitW, DynW, OutW);
    }}
    geometry {{
        nodes[:] = BULK;
        {geometry}
    }}
    """


def _make_2d_program(geometry: str, periodicity: str,
                     nx: int = 10, ny: int = 10) -> str:
    return f"""
    simulation_description("2D continuity test");
    lattices {{
        lattice f(2, 1, int, {{{nx}, {ny}}}, {periodicity});
    }}
    initializer InitB {{ f.out[x, y | 0] = 0; }}
    initializer InitW {{ f.out[x, y | 0] = 1; }}
    initializer InitS {{ f.out[x, y | 0] = 2; }}
    dynamic DynB {{ f.out[x, y | 0] = f.in[x, y | 0]; }}
    dynamic DynW {{ f.out[x, y | 0] = f.in[x, y | 0]; }}
    gauge OutB -> (int val) {{ val = f.in[x, y | 0]; }}
    gauge OutW -> (int val) {{ val = f.in[x, y | 0]; }}
    node_classes {{
        node_class BULK(InitB, DynB, OutB);
        node_class WALL(InitW, DynW, OutW);
        node_class SOLID(InitS) masked;
    }}
    geometry {{
        nodes[:, :] = BULK;
        {geometry}
    }}
    """


def _make_3d_program(geometry: str, periodicity: str,
                     nx: int = 6, ny: int = 6, nz: int = 6) -> str:
    return f"""
    simulation_description("3D continuity test");
    lattices {{
        lattice f(3, 1, int, {{{nx}, {ny}, {nz}}}, {periodicity});
    }}
    initializer InitB {{ f.out[x, y, z | 0] = 0; }}
    initializer InitW {{ f.out[x, y, z | 0] = 1; }}
    dynamic DynB {{ f.out[x, y, z | 0] = f.in[x, y, z | 0]; }}
    dynamic DynW {{ f.out[x, y, z | 0] = f.in[x, y, z | 0]; }}
    gauge OutB -> (int val) {{ val = f.in[x, y, z | 0]; }}
    gauge OutW -> (int val) {{ val = f.in[x, y, z | 0]; }}
    node_classes {{
        node_class BULK(InitB, DynB, OutB);
        node_class WALL(InitW, DynW, OutW);
    }}
    geometry {{
        nodes[:, :, :] = BULK;
        {geometry}
    }}
    """


# ---------------------------------------------------------------------------
# Cases that should RAISE
# ---------------------------------------------------------------------------

class TestDiscontinuityIsDetected:

    def test_2d_wall_on_left_edge_only(self):
        """Wall at x=0 but not at x=Nx-1 under x-periodic."""
        code = _make_2d_program(
            geometry="nodes[0:0, :] = WALL;",
            periodicity="{true, false}",
        )
        ast = get_typed_ast(code)
        with pytest.raises(GeLBExGeometryDiscontinuity) as exc:
            resolve_geometry(ast)
        assert exc.value.axis_name == 'x'
        assert exc.value.nc_first == 'WALL'
        assert exc.value.nc_last == 'BULK'

    def test_2d_wall_on_bottom_edge_only(self):
        """Wall at y=0 but not at y=Ny-1 under y-periodic."""
        code = _make_2d_program(
            geometry="nodes[:, 0:0] = WALL;",
            periodicity="{false, true}",
        )
        ast = get_typed_ast(code)
        with pytest.raises(GeLBExGeometryDiscontinuity) as exc:
            resolve_geometry(ast)
        assert exc.value.axis_name == 'y'

    def test_3d_wall_on_low_z_face_only(self):
        """Wall at z=0 but not at z=Nz-1 under z-periodic."""
        code = _make_3d_program(
            geometry="nodes[:, :, 0:0] = WALL;",
            periodicity="{false, false, true}",
        )
        ast = get_typed_ast(code)
        with pytest.raises(GeLBExGeometryDiscontinuity) as exc:
            resolve_geometry(ast)
        assert exc.value.axis_name == 'z'

    def test_1d_wall_at_origin_only(self):
        """Wall at x=0 but not at x=Nx-1 in a 1D x-periodic domain."""
        code = _make_1d_program(
            geometry="nodes[0:0] = WALL;",
            periodicity="true",
        )
        ast = get_typed_ast(code)
        with pytest.raises(GeLBExGeometryDiscontinuity) as exc:
            resolve_geometry(ast)
        assert exc.value.axis_name == 'x'


# ---------------------------------------------------------------------------
# Cases that should PASS silently
# ---------------------------------------------------------------------------

class TestContinuousGeometryPasses:

    def test_2d_walls_on_both_vertical_edges(self):
        """Symmetric walls at x=0 and x=Nx-1 are continuous under
        x-periodic -- wrapping a left-edge wall onto a right-edge wall
        is the same NC."""
        code = _make_2d_program(
            geometry=("nodes[0:0, :] = WALL; "
                      "nodes[9:9, :] = WALL;"),
            periodicity="{true, false}",
        )
        ast = get_typed_ast(code)
        resolve_geometry(ast)  # must not raise

    def test_2d_left_wall_with_x_non_periodic(self):
        """Wall at x=0 only is fine when x is NOT declared periodic."""
        code = _make_2d_program(
            geometry="nodes[0:0, :] = WALL;",
            periodicity="{false, true}",
        )
        ast = get_typed_ast(code)
        resolve_geometry(ast)  # must not raise

    def test_2d_fully_periodic_uniform_bulk(self):
        """Trivial doubly-periodic BULK-only geometry."""
        code = _make_2d_program(
            geometry="",
            periodicity="{true, true}",
        )
        ast = get_typed_ast(code)
        resolve_geometry(ast)  # must not raise

    def test_2d_fully_periodic_central_obstacle(self):
        """An obstacle in the interior is continuous at all wrap
        edges (the edges themselves are BULK on both sides)."""
        code = _make_2d_program(
            geometry="nodes[4:5, 4:5] = WALL;",
            periodicity="{true, true}",
        )
        ast = get_typed_ast(code)
        resolve_geometry(ast)  # must not raise

    def test_3d_fully_periodic_uniform_bulk(self):
        code = _make_3d_program(
            geometry="",
            periodicity="{true, true, true}",
        )
        ast = get_typed_ast(code)
        resolve_geometry(ast)  # must not raise

    def test_1d_periodic_single_interior_wall(self):
        """Single wall in the middle of a 1D x-periodic domain is
        continuous at the wrap edges (both edges are BULK)."""
        code = _make_1d_program(
            geometry="nodes[5:5] = WALL;",
            periodicity="true",
        )
        ast = get_typed_ast(code)
        resolve_geometry(ast)  # must not raise

    def test_2d_border_inferred_wall_around_interior_solid(self):
        """``border(SOLID) = WALL`` produces a continuous WALL layer
        around an interior SOLID region; nothing touches the wrap
        edge, so the geometry stays continuous under x/y periodicity."""
        code = _make_2d_program(
            geometry=("nodes[4:5, 4:5] = SOLID; "
                      "border(SOLID) = WALL;"),
            periodicity="{true, true}",
        )
        ast = get_typed_ast(code)
        resolve_geometry(ast)  # must not raise


# ---------------------------------------------------------------------------
# Opt-out kwarg
# ---------------------------------------------------------------------------

class TestValidateContinuityKwarg:

    def test_kwarg_disables_check(self):
        """``validate_continuity=False`` lets a deliberately
        discontinuous geometry resolve without raising -- needed for
        unit tests that want to inspect such an ``nc_map`` directly."""
        code = _make_2d_program(
            geometry="nodes[0:0, :] = WALL;",
            periodicity="{true, false}",
        )
        ast = get_typed_ast(code)
        geo = resolve_geometry(ast, validate_continuity=False)
        # Sanity: confirm the discontinuity is in fact present in nc_map.
        assert geo.nc_map[0, 0] != geo.nc_map[-1, 0]
