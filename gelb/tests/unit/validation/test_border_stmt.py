#!/usr/bin/env python3
"""
Tests for the border() geometry statement.

``border(SOURCE) = TARGET;`` repaints the boundary cells of SOURCE
(those with at least one neighbor at Chebyshev distance 1 of a different class)
as TARGET, leaving interior cells as SOURCE.
Periodic axes wrap; off-grid neighbors on non-periodic axes are ignored.
"""

import itertools
from pathlib import Path

import numpy as np
import pytest
from gelb.tests.test_utils import get_typed_ast
from gelb.gelb_ast.ASTNodes import BorderStmt_N, PaintNodesStmt_N
from gelb.midware.geometry import resolve_geometry


ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / 'gelb/tests/fixtures/regressions'


def _resolve(code, *, validate_continuity=True):
    return resolve_geometry(get_typed_ast(code), validate_continuity=validate_continuity)


def _cells(geo, name):
    return {tuple(c) for c in np.argwhere(geo.nc_map == geo.nc_info[name].nc_id)}


def _geometry_program(ndim, geometry, *, periodic=None, size=9):
    coords = ', '.join(('x', 'y', 'z')[:ndim])
    slices = ', '.join(':' for _ in range(ndim))
    periodic = periodic or (False,) * ndim
    sizes = ', '.join(str(size) for _ in range(ndim))
    flags = ', '.join(str(flag).lower() for flag in periodic)
    if ndim > 1:
        sizes, flags = '{' + sizes + '}', '{' + flags + '}'
    return f'''
    simulation_description("border geometry");
    lattices {{ lattice f({ndim}, 1, int, {sizes}, {flags}); }}
    initializer I {{ f.out[{coords} | 0] = 0; }}
    dynamic D {{ f.out[{coords} | 0] = f.in[{coords} | 0]; }}
    gauge G -> (int value) {{ value = f.in[{coords} | 0]; }}
    node_classes {{
        node_class FLUID(I, D, G);
        node_class WALL(I, D, G);
        node_class SOLID() masked;
    }}
    geometry {{ nodes[{slices}] = SOLID; {geometry} }}
    '''


def _assert_no_masked_fluid_neighbours(geo):
    fluid = geo.nc_map == geo.nc_info['FLUID'].nc_id
    masked = np.isin(geo.nc_map, [info.nc_id for info in geo.nc_info.values()
                                 if info.masked])
    assert fluid.any() and masked.any()  # Do not pass by repainting the whole solid.
    for delta in itertools.product((-1, 0, 1), repeat=geo.ndim):
        if not any(delta):
            continue
        neighbours = np.roll(masked, tuple(-d for d in delta), axis=tuple(range(geo.ndim)))
        valid = [slice(None)] * geo.ndim
        for axis, step in enumerate(delta):
            if not geo.periodic[axis]:
                valid[axis] = slice(max(0, -step), min(geo.grid_sizes[axis],
                                                     geo.grid_sizes[axis] - step))
        valid = tuple(valid)
        assert not np.any(fluid[valid] & neighbours[valid]), delta


class TestBorderStmtGeometry:
    def test_diagonal_fixture_repaints_entire_plus(self):
        geo = _resolve((FIXTURES / 'border_diagonal.gelb').read_text())
        assert _cells(geo, 'SOLID') == set()
        assert _cells(geo, 'WALL') == {(5, 5), (4, 5), (6, 5), (5, 4), (5, 6)}

    def test_seam_fixture_wraps_only_periodic_axis(self):
        # The separate continuity validator rejects unlike seam classes;
        # bypass it here to isolate the border pass on this deliberate probe.
        geo = _resolve((FIXTURES / 'border_seam.gelb').read_text(),
                       validate_continuity=False)
        assert _cells(geo, 'SOLID') == set()
        assert _cells(geo, 'WALL') == {(x, y) for x in (0, 1) for y in range(10)}

    @pytest.mark.parametrize('ndim', [1, 2, 3])
    @pytest.mark.parametrize('wrap', [False, True])
    def test_every_link_including_periodic_corners(self, ndim, wrap):
        # A single FLUID cell in SOLID must have a complete one-cell WALL
        # shell. At the periodic origin this also exercises multi-axis wraps.
        point = (0 if wrap else 4,) * ndim
        paint = ', '.join(map(str, point))
        geo = _resolve(_geometry_program(
            ndim, f'nodes[{paint}] = FLUID; border(SOLID) = WALL;',
            periodic=(wrap,) * ndim), validate_continuity=not wrap)
        expected = {tuple((c + d) % 9 for c, d in zip(point, delta))
                    for delta in itertools.product((-1, 0, 1), repeat=ndim)
                    if any(delta)}
        assert _cells(geo, 'WALL') == expected
        assert _cells(geo, 'FLUID') == {point}
        _assert_no_masked_fluid_neighbours(geo)

    @pytest.mark.parametrize('ndim', [1, 2, 3])
    def test_nonperiodic_exterior_is_not_another_class(self, ndim):
        geo = _resolve(_geometry_program(ndim, 'border(SOLID) = WALL;'))
        assert _cells(geo, 'WALL') == set()
        assert len(_cells(geo, 'SOLID')) == 9 ** ndim

    @pytest.mark.parametrize('axis', [0, 1, 2])
    def test_mixed_periodic_axes(self, axis):
        periodic = tuple(i == axis for i in range(3))
        geo = _resolve(_geometry_program(
            3, 'nodes[0, 0, 0] = FLUID; border(SOLID) = WALL;',
            periodic=periodic), validate_continuity=False)
        ranges = [(0, 1, 8) if flag else (0, 1) for flag in periodic]
        assert _cells(geo, 'WALL') == set(itertools.product(*ranges)) - {(0, 0, 0)}
        _assert_no_masked_fluid_neighbours(geo)

    def test_rules_use_a_snapshot_then_see_previous_rule(self):
        code = _make_2d_program('''
            nodes[:, :] = FLUID;
            nodes[2:6, 2:6] = SOLID;
            border(SOLID) = WALL;
        ''')
        first = _resolve(code)
        assert _cells(first, 'SOLID') == set(itertools.product(range(3, 6), repeat=2))
        second = _resolve(code.replace('border(SOLID) = WALL;',
                                       'border(SOLID) = WALL; border(SOLID) = WALL;'))
        assert _cells(second, 'SOLID') == {(4, 4)}

    def test_karman_one_pass_separates_fluid_from_masked_disk(self):
        source = (ROOT / 'examples/sukop/karman_vortex_street_2d_bgk.gelb').read_text()
        ast = get_typed_ast(source)
        # Keep only the first border() pass, so the test shows that one
        # pass suffices; the geometry and default dimensions are the
        # example's own, resolved without a run.
        seen = False
        stmts = []
        for stmt in ast.geometry.stmts.elements:
            if isinstance(stmt, BorderStmt_N):
                if seen:
                    continue
                seen = True
            stmts.append(stmt)
        assert seen
        ast.geometry.stmts.elements = stmts
        geo = resolve_geometry(ast)
        _assert_no_masked_fluid_neighbours(geo)

    def test_sphere_one_pass_separates_fluid_from_masked_interior(self):
        geo = _resolve(_geometry_program(3, '''
            nodes[:, :, :] = FLUID;
            nodes[where (x-8)*(x-8) + (y-8)*(y-8) + (z-8)*(z-8) < 36] = SOLID;
            border(SOLID) = WALL;
        ''', size=17))
        assert (8, 8, 8) in _cells(geo, 'SOLID')
        _assert_no_masked_fluid_neighbours(geo)


def _make_1d_program(geometry_content, extra_nc=''):
    return f"""
    simulation_description("test");
    lattices {{ lattice f(1, 1, int, 10, false); }}
    initializer InitA {{ f.out[x | 0] = 0; }}
    initializer InitB {{ f.out[x | 0] = 1; }}
    dynamic DynA {{ f.out[x | 0] = f.in[x | 0]; }}
    dynamic DynB {{ f.out[x | 0] = f.in[x | 0]; }}
    gauge OutA -> (int val) {{ val = f.in[x | 0]; }}
    gauge OutB -> (int val) {{ val = f.in[x | 0]; }}
    node_classes {{
        node_class FLUID(InitA, DynA, OutA);
        node_class WALL(InitB, DynB, OutB);
        node_class SOLID() masked;
        {extra_nc}
    }}
    geometry {{
        {geometry_content}
    }}
    """


def _make_2d_program(geometry_content, nx=10, ny=10, extra_nc=''):
    return f"""
    simulation_description("test");
    lattices {{ lattice f(2, 1, int, {{{nx}, {ny}}}, {{false, false}}); }}
    initializer InitA {{ f.out[x, y | 0] = 0; }}
    initializer InitB {{ f.out[x, y | 0] = 1; }}
    dynamic DynA {{ f.out[x, y | 0] = f.in[x, y | 0]; }}
    dynamic DynB {{ f.out[x, y | 0] = f.in[x, y | 0]; }}
    gauge OutA -> (int val) {{ val = f.in[x, y | 0]; }}
    gauge OutB -> (int val) {{ val = f.in[x, y | 0]; }}
    node_classes {{
        node_class FLUID(InitA, DynA, OutA);
        node_class WALL(InitB, DynB, OutB);
        node_class SOLID() masked;
        {extra_nc}
    }}
    geometry {{
        {geometry_content}
    }}
    """


class TestBorderStmtParsing:
    """border() statements parse into BorderStmt_N nodes."""

    def test_border_stmt_in_ast(self):
        code = _make_2d_program("""
            nodes[:, :] = FLUID;
            nodes[3:6, 3:6] = SOLID;
            border(SOLID) = WALL;
        """)
        ast = get_typed_ast(code)
        stmts = ast.geometry.stmts.elements
        border_stmts = [s for s in stmts if isinstance(s, BorderStmt_N)]
        assert len(border_stmts) == 1
        assert border_stmts[0].source.name == 'SOLID'
        assert border_stmts[0].target.name == 'WALL'

    def test_paint_stmts_still_work(self):
        code = _make_2d_program("""
            nodes[:, :] = FLUID;
            nodes[3:6, 3:6] = SOLID;
            border(SOLID) = WALL;
        """)
        ast = get_typed_ast(code)
        stmts = ast.geometry.stmts.elements
        paint_stmts = [s for s in stmts if isinstance(s, PaintNodesStmt_N)]
        assert len(paint_stmts) == 2


class TestBorderStmtValidation:
    """border() rejects unknown node class names."""

    def test_unknown_source_rejected(self):
        from gelb.utils.exceptions import GeLBExSymbolUnknown
        code = _make_2d_program("""
            nodes[:, :] = FLUID;
            border(UNKNOWN) = WALL;
        """)
        with pytest.raises(GeLBExSymbolUnknown):
            get_typed_ast(code)

    def test_unknown_target_rejected(self):
        from gelb.utils.exceptions import GeLBExSymbolUnknown
        code = _make_2d_program("""
            nodes[:, :] = FLUID;
            nodes[3:6, 3:6] = SOLID;
            border(SOLID) = UNKNOWN;
        """)
        with pytest.raises(GeLBExSymbolUnknown):
            get_typed_ast(code)


class TestBorderStmtCodeGen:
    """border() produces correct geometry in generated Fortran."""

    def _generate(self, code):
        from gelb.backends.stage3_backend_cpu_fortran_serial import generate_fortran
        from gelb.midware.inline_functions import inline_functions
        ast = get_typed_ast(code)
        ast = inline_functions(ast)
        return generate_fortran(ast, num_timesteps=1)

    def test_2d_square_obstacle_border(self):
        """A 4x4 SOLID block in a 10x10 grid: border cells become WALL."""
        code = _make_2d_program("""
            nodes[:, :] = FLUID;
            nodes[3:6, 3:6] = SOLID;
            border(SOLID) = WALL;
        """)
        fortran = self._generate(code)
        # The generated code should contain nc_map assignments for all 3 classes
        assert 'FLUID' in fortran
        assert 'WALL' in fortran
        assert 'SOLID' in fortran
        # border() corrections should appear
        assert 'border' in fortran.lower()

    def test_2d_border_interior_stays_solid(self):
        """Interior cells of a 5x5 SOLID block (5:9 in 15x15) should remain SOLID."""
        code = _make_2d_program("""
            nodes[:, :] = FLUID;
            nodes[5:9, 5:9] = SOLID;
            border(SOLID) = WALL;
        """, nx=15, ny=15)
        fortran = self._generate(code)
        # Interior cells (6:8, 6:8) should still be SOLID (masked)
        # WALL cells should be on the border only
        # We verify by checking that both SOLID and WALL appear in nc_map
        assert 'SOLID' in fortran
        assert 'WALL' in fortran

    def test_1d_border(self):
        """1D: SOLID at [3:7], border should repaint cells 3 and 7 as WALL."""
        code = _make_1d_program("""
            nodes[:] = FLUID;
            nodes[3:7] = SOLID;
            border(SOLID) = WALL;
        """)
        # Should not raise -- just verify it generates successfully
        from gelb.backends.stage3_backend_cpu_fortran_serial import generate_fortran
        from gelb.midware.inline_functions import inline_functions
        ast = get_typed_ast(code)
        ast = inline_functions(ast)
        fortran = generate_fortran(ast, num_timesteps=1)
        assert 'program gelb_simulation' in fortran
