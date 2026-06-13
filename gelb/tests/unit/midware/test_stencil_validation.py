#!/usr/bin/env python3
"""
Unit tests for stencil-based compile-time validations.
"""

import pytest

from gelb.tests.test_utils import (
    get_typed_ast,
    minimal_gelb_program_1d,
    minimal_gelb_program_2d,
)
from gelb.midware.geometry import resolve_geometry
from gelb.midware.stage2_midware import fold_constants, extract_stencils
from gelb.midware.stage2_midware import (
    validate_cross_nc_df_coverage,
    validate_initializer_coverage,
    validate_boundary_access,
    warn_writeonly_dynamics,
    warn_unused_lattices,
)
from gelb.utils.exceptions import GeLBExStencilError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _line_of(gelb_code, text):
    """1-based number of the first source line that contains ``text``."""
    return next(i for i, line in enumerate(gelb_code.splitlines(), 1)
                if text in line)


def _extract(gelb_code):
    """Run the full pipeline up to stencil extraction."""
    ast = get_typed_ast(gelb_code)
    ast = fold_constants(ast)
    return extract_stencils(ast)


def _check_walls(gelb_code):
    """The wall check on the resolved class map (the only map it takes)."""
    ast = get_typed_ast(gelb_code)
    ast = fold_constants(ast)
    validate_boundary_access(extract_stencils(ast), resolve_geometry(ast))


def _custom_2d_program(
    periodic_x=False,
    periodic_y=False,
    initializer_content="",
    dynamic_content="",
    gauge_content="",
    geometry_content="",
    grid_size=8,
):
    """Build a 2D GeLB program with configurable periodicity.

    Uses literal grid size (not a constant) so that grid_size resolves
    correctly through get_typed_ast + fold_constants.
    """
    px = "true" if periodic_x else "false"
    py = "true" if periodic_y else "false"
    gs = grid_size
    init = initializer_content or "f.out[x, y | 0] = 0;"
    dyn = dynamic_content or "f.out[x, y | 0] = f.in[x, y | 0];"
    gauge = gauge_content or "val = f.in[x, y | 0];"
    geom = geometry_content or "nodes[:, :] = BULK;"
    return f"""
    simulation_description("Test 2D custom");
    lattices {{
        lattice f(2, 9, int, {{{gs}, {gs}}}, {{{px}, {py}}});
    }}
    initializer Init {{
        {init}
    }}
    dynamic Dyn {{
        {dyn}
    }}
    gauge Out -> (int val) {{
        {gauge}
    }}
    node_classes {{
        node_class BULK(Init, Dyn, Out);
        node_class WALL(Init, Dyn, Out);
    }}
    geometry {{
        {geom}
    }}
    """


# ===========================================================================
# Validation 1: Initializer DF coverage
# ===========================================================================

class TestInitializerCoveragePass:
    """Programs with complete initializer DF coverage should pass."""

    def test_full_range_write_passes(self):
        """f.out[x, y | :] = W covers all DFs."""
        prog = minimal_gelb_program_2d(
            global_constants_content="""
                const int N = 32;
                const array[int, 9] W = {1, 1, 1, 1, 1, 1, 1, 1, 1};
            """,
            initializer_content="f.out[x, y | :] = W;",
        )
        stencils = _extract(prog)
        validate_initializer_coverage(stencils)  # should not raise

    def test_all_dfs_written_individually_passes(self):
        """Writing each DF 0-8 individually covers all DFs."""
        writes = "\n".join(
            f"f.out[x, y | {i}] = 0;" for i in range(9)
        )
        prog = minimal_gelb_program_2d(initializer_content=writes)
        stencils = _extract(prog)
        validate_initializer_coverage(stencils)

    def test_multiple_writes_union_passes(self):
        """Writing DFs 0-4 and 5-8 in two groups covers all."""
        writes = "\n".join(
            f"f.out[x, y | {i}] = 0;" for i in range(9)
        )
        prog = minimal_gelb_program_2d(initializer_content=writes)
        stencils = _extract(prog)
        validate_initializer_coverage(stencils)

    def test_1d_single_df_passes(self):
        """1D lattice with q=1: writing DF 0 covers everything."""
        prog = minimal_gelb_program_1d(
            initializer_content="f.out[x | 0] = 0;",
        )
        stencils = _extract(prog)
        validate_initializer_coverage(stencils)


class TestInitializerCoverageFail:
    """Programs with incomplete initializer DF coverage should raise."""

    def test_partial_write_raises(self):
        """Writing only DF 0 of a D2Q9 lattice should raise."""
        prog = minimal_gelb_program_2d(
            initializer_content="f.out[x, y | 0] = 0;",
        )
        stencils = _extract(prog)
        with pytest.raises(GeLBExStencilError, match="missing"):
            validate_initializer_coverage(stencils)

    def test_some_dfs_written_raises(self):
        """Writing DFs 0 and 1 of 9 should raise for missing 2-8."""
        writes = "f.out[x, y | 0] = 0;\nf.out[x, y | 1] = 0;"
        prog = minimal_gelb_program_2d(initializer_content=writes)
        stencils = _extract(prog)
        with pytest.raises(GeLBExStencilError, match="missing"):
            validate_initializer_coverage(stencils)

    def test_error_names_node_class(self):
        """Error message should mention the node class name."""
        prog = minimal_gelb_program_2d(
            initializer_content="f.out[x, y | 0] = 0;",
        )
        stencils = _extract(prog)
        with pytest.raises(GeLBExStencilError, match="BULK"):
            validate_initializer_coverage(stencils)


# ===========================================================================
# Validation 2: Boundary access
# ===========================================================================

class TestBoundaryAccessPass:
    """Programs with safe boundary access should pass."""

    def test_local_access_passes(self):
        """Dynamic with only (0,0) offsets is always safe."""
        prog = _custom_2d_program(
            dynamic_content="f.out[x, y | 0] = f.in[x, y | 0];",
        )
        _check_walls(prog)

    def test_periodic_with_offset_passes(self):
        """Periodic dimension with offset is safe (wraps)."""
        prog = _custom_2d_program(
            periodic_x=True,
            periodic_y=True,
            dynamic_content="""
                real fl = f.in[x-1, y | 0];
                f.out[x, y | 0] = fl;
            """,
            geometry_content="nodes[:, :] = BULK;",
        )
        _check_walls(prog)

    def test_boundary_overridden_passes(self):
        """BULK has offset but WALL overrides at boundary -- safe.

        WALL uses a different dynamic (local access only), so even though
        BULK's dynamic reads x-1, WALL at x=0 is safe.
        """
        prog = """
        simulation_description("Test boundary override");
        lattices {
            lattice f(2, 9, int, {8, 8}, {false, false});
        }
        initializer Init {
            f.out[x, y | 0] = 0;
        }
        dynamic BulkDyn {
            real fl = f.in[x-1, y | 0];
            f.out[x, y | 0] = fl;
        }
        dynamic WallDyn {
            f.out[x, y | 0] = f.in[x, y | 0];
        }
        gauge Out -> (int val) {
            val = f.in[x, y | 0];
        }
        node_classes {
            node_class BULK(Init, BulkDyn, Out);
            node_class WALL(Init, WallDyn, Out);
        }
        geometry {
            nodes[:, :] = BULK;
            nodes[0, :] = WALL;
        }
        """
        _check_walls(prog)


class TestBoundaryAccessFail:
    """Programs with out-of-bounds boundary access should raise."""

    def test_nonperiodic_negative_offset_raises(self):
        """Non-periodic x, dynamic reads x-1, BULK at x=0."""
        prog = _custom_2d_program(
            periodic_x=False,
            dynamic_content="""
                real fl = f.in[x-1, y | 0];
                f.out[x, y | 0] = fl;
            """,
            geometry_content="nodes[:, :] = BULK;",
        )
        with pytest.raises(GeLBExStencilError, match="(?i)out-of-bounds"):
            _check_walls(prog)

    def test_nonperiodic_positive_offset_raises(self):
        """Non-periodic x, dynamic reads x+1, BULK at x=N-1."""
        prog = _custom_2d_program(
            periodic_x=False,
            dynamic_content="""
                real fr = f.in[x+1, y | 0];
                f.out[x, y | 0] = fr;
            """,
            geometry_content="nodes[:, :] = BULK;",
        )
        with pytest.raises(GeLBExStencilError, match="(?i)out-of-bounds"):
            _check_walls(prog)

    def test_nested_offset_expression_raises(self):
        """(x + 1) + 1 is an offset of +2 and is checked like x + 2."""
        prog = _custom_2d_program(
            periodic_x=False,
            dynamic_content="""
                real fr = f.in[(x + 1) + 1, y | 0];
                f.out[x, y | 0] = fr;
            """,
            geometry_content="nodes[:, :] = BULK;",
        )
        with pytest.raises(GeLBExStencilError, match="(?i)out-of-bounds"):
            _check_walls(prog)

    def test_1d_wall_with_scalar_periodicity_raises(self):
        """A 1-D lattice declares its periodicity as a scalar; a wall
        read past the end must still be caught."""
        prog = minimal_gelb_program_1d(
            dynamic_content="f.out[x | 0] = f.in[x + 2 | 0];")
        with pytest.raises(GeLBExStencilError, match=r"offset \+2 in x"):
            _check_walls(prog)

    def test_1d_periodic_scalar_passes(self):
        prog = minimal_gelb_program_1d(
            dynamic_content="f.out[x | 0] = f.in[x + 2 | 0];",
        ).replace("32, false", "32, true")
        _check_walls(prog)

    def test_nonperiodic_offset_in_y_raises(self):
        """Non-periodic y, dynamic reads y-1, painted at y=0."""
        prog = _custom_2d_program(
            periodic_y=False,
            dynamic_content="""
                real fd = f.in[x, y-1 | 0];
                f.out[x, y | 0] = fd;
            """,
            geometry_content="nodes[:, :] = BULK;",
        )
        with pytest.raises(GeLBExStencilError, match="(?i)out-of-bounds"):
            _check_walls(prog)


# ===========================================================================
# Warning 1: Write-only dynamic blocks
# ===========================================================================

class TestWriteonlyDynamicsWarning:
    """Write-only dynamic blocks should trigger a warning."""

    def test_normal_dynamic_no_warning(self):
        """Dynamic that reads and writes produces no warning."""
        prog = minimal_gelb_program_1d(
            dynamic_content="f.out[x | 0] = f.in[x | 0];",
        )
        stencils = _extract(prog)
        assert warn_writeonly_dynamics(stencils) == []

    def test_noop_dynamic_no_warning(self):
        """Empty dynamic (no reads, no writes) produces no warning."""
        prog = _custom_2d_program(
            dynamic_content="int dummy = 0;",
        )
        stencils = _extract(prog)
        assert warn_writeonly_dynamics(stencils) == []

    def test_writeonly_dynamic_warns(self):
        """Dynamic that writes but never reads produces a warning."""
        prog = minimal_gelb_program_1d(
            dynamic_content="f.out[x | 0] = 42;",
        )
        stencils = _extract(prog)
        warnings = warn_writeonly_dynamics(stencils)
        assert len(warnings) == 1
        msg, hint, line = warnings[0]
        assert "writes to f.out" in msg
        assert "never reads f.in" in msg
        # The dynamic block's first line, where the Problems panel jumps.
        assert line == _line_of(prog, "dynamic ")

    def test_dirichlet_style_warns(self):
        """Dirichlet-style BC (write-only) still triggers warning."""
        prog = _custom_2d_program(
            initializer_content="f.out[x, y | :] = 0;",
            dynamic_content="""
                f.out[x, y | 0] = 1;
                f.out[x, y | 1] = 1;
                f.out[x, y | 2] = 1;
                f.out[x, y | 3] = 1;
                f.out[x, y | 4] = 1;
                f.out[x, y | 5] = 1;
                f.out[x, y | 6] = 1;
                f.out[x, y | 7] = 1;
                f.out[x, y | 8] = 1;
            """,
        )
        stencils = _extract(prog)
        warnings = warn_writeonly_dynamics(stencils)
        assert len(warnings) >= 1


# ===========================================================================
# Warning 2: Unused lattices
# ===========================================================================

class TestUnusedLatticesWarning:
    """Unused lattice declarations should trigger a warning."""

    def test_used_lattice_no_warning(self):
        """Single lattice used in all blocks produces no warning."""
        prog = minimal_gelb_program_1d()
        stencils = _extract(prog)
        assert warn_unused_lattices(stencils) == []

    def test_unused_lattice_warns(self):
        """Declared but unreferenced lattice produces a warning."""
        prog = """
        simulation_description("Unused lattice test");
        lattices {
            lattice f(1, 1, int, 4, true);
            lattice g(1, 3, int, 4, true);
        }
        initializer Init {
            f.out[x | 0] = 0;
        }
        dynamic Dyn {
            f.out[x | 0] = f.in[x | 0];
        }
        gauge Out -> (int val) {
            val = f.in[x | 0];
        }
        node_classes {
            node_class BULK(Init, Dyn, Out);
        }
        geometry {
            nodes[:] = BULK;
        }
        """
        stencils = _extract(prog)
        warnings = warn_unused_lattices(stencils)
        assert len(warnings) == 1
        msg, hint, line = warnings[0]
        assert "'g'" in msg
        assert "never read" in msg
        assert line == _line_of(prog, "lattice g(")


# ---------------------------------------------------------------------------
# validate_cross_nc_df_coverage
# ---------------------------------------------------------------------------

def _two_lattice_two_nc_program(nc_b="node_class B(InitG, GaugeB);",
                                gauge_a_reads="f"):
    """2D program: NC A (writes f) bordered by an interior column of
    NC B; A's dynamic reads f at x+1, crossing into B's cells."""
    return f"""
    simulation_description("cross-NC coverage test");
    lattices {{
        lattice f(2, 9, real, {{16, 16}}, {{true, true}});
        lattice g(2, 5, real, {{16, 16}}, {{true, true}});
    }}
    initializer InitF {{
        f.out[x, y | :] = 1.0;
    }}
    initializer InitG {{
        g.out[x, y | :] = 2.0;
    }}
    dynamic DynA {{
        f.out[x, y | :] = f.in[x + 1, y | :];
    }}
    gauge GaugeA -> (real rho) {{
        rho = sum({gauge_a_reads}.in[x, y | :]);
    }}
    gauge GaugeB -> (real rho) {{
        rho = sum(g.in[x, y | :]);
    }}
    node_classes {{
        node_class A(InitF, DynA, GaugeA);
        {nc_b}
    }}
    geometry {{
        nodes[:, :] = A;
        nodes[8, :] = B;
    }}
    """


def _extract_with_geometry(gelb_code):
    from gelb.midware.geometry import resolve_geometry
    ast = get_typed_ast(gelb_code)
    ast = fold_constants(ast)
    return extract_stencils(ast), resolve_geometry(ast)


class TestCrossNCDFCoverage:

    def test_neighbour_never_writes_lattice_raises(self):
        stencils, geometry = _extract_with_geometry(
            _two_lattice_two_nc_program())
        with pytest.raises(GeLBExStencilError) as exc:
            validate_cross_nc_df_coverage(stencils, geometry)
        msg = str(exc.value)
        assert "DynA" in msg and "'A'" in msg and "'B'" in msg
        assert "'f'" in msg and "(+1, 0)" in msg

    def test_neighbour_writing_lattice_passes(self):
        code = _two_lattice_two_nc_program(
            nc_b="node_class B(InitF, GaugeA);")
        stencils, geometry = _extract_with_geometry(code)
        validate_cross_nc_df_coverage(stencils, geometry)  # no raise

    def test_masked_neighbour_is_exempt(self):
        code = _two_lattice_two_nc_program(nc_b="node_class B() masked;")
        stencils, geometry = _extract_with_geometry(code)
        validate_cross_nc_df_coverage(stencils, geometry)  # no raise

    def test_gauge_reading_unwritten_lattice_raises(self):
        # GaugeA reads g, which NC A never writes (offset-0 gauge gap).
        code = _two_lattice_two_nc_program(
            nc_b="node_class B(InitF, GaugeA);", gauge_a_reads="g")
        stencils, geometry = _extract_with_geometry(code)
        with pytest.raises(GeLBExStencilError) as exc:
            validate_cross_nc_df_coverage(stencils, geometry)
        msg = str(exc.value)
        assert "GaugeA" in msg and "'g'" in msg and "ever writes" in msg

    def test_single_nc_program_passes(self):
        stencils, geometry = _extract_with_geometry(
            minimal_gelb_program_2d())
        validate_cross_nc_df_coverage(stencils, geometry)  # no raise
