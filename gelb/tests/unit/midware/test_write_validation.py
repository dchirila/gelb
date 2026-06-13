#!/usr/bin/env python3
"""
Validation of lattice writes and of DF coverage across the run
(user manual chapter 3, writes at an offset).

A write at a non-zero offset (a "push") lands on the cell the offset
reaches, wrapped on periodic axes; it may not land in a static or an
empty masked cell, and at most one source cell may write each (cell,
lattice, DF) per phase.  The wall check covers initializers.  DF coverage
is proved per cell and separately for t = 0 (initializer writes) and for
every later step (dynamic writes, or the initializer's for a static
class), pushes included.  A write whose DF index is not a compile-time
integer is an error.  Every check is exercised through the diagnostics
pipeline, on the resolved geometry, and the wall check also through the
normal compilation path, which validates on the same map.
"""

import json

import pytest
from click.testing import CliRunner

from gelb.compiler_pipeline import (
    PipelineOptions, PipelineProfile, compile_source)
from gelb.gelbc import cli as gelbc_cli
from gelb.utils.exceptions import GeLBExStencilError


def _compile(code):
    return compile_source(
        code, PipelineProfile.DIAGNOSTICS,
        PipelineOptions(require_stencils=True, require_geometry=True))


def _program_1d(*, q=1, init="u.out[x | 0] = x;", dyn="u.out[x | 0] = u.in[x | 0];",
                gauge="v = u.in[x | 0];", periodic="true", n=8, lattices="",
                node_classes=None, geometry=None):
    node_classes = node_classes or "node_class B(I, D, G);"
    geometry = geometry or "nodes[:] = B;"
    return f"""
    simulation_description("write validation");
    lattices {{ lattice u(1, {q}, real, {n}, {periodic}); {lattices} }}
    initializer I {{ {init} }}
    dynamic D {{ {dyn} }}
    gauge G -> (real v) {{ {gauge} }}
    node_classes {{ {node_classes} }}
    geometry {{ {geometry} }}
    """


def _program_2d(*, blocks, node_classes, geometry, nx=8, ny=6, periodic="{true, true}",
                lattices="lattice u(2, 2, real, {NX, NY}, PER);"):
    lattices = lattices.replace("{NX, NY}", f"{{{nx}, {ny}}}").replace("PER", periodic)
    return f"""
    simulation_description("write validation");
    lattices {{ {lattices} }}
    {blocks}
    node_classes {{ {node_classes} }}
    geometry {{ {geometry} }}
    """


# --------------------------------------------------------------------------
# destinations of writes at an offset
# --------------------------------------------------------------------------

class TestOffsetWriteDestinations:

    @pytest.mark.parametrize("dyn", [
        "u.out[x + 1 | 0] = u.in[x | 0];",
        "u.out[x - 1 | 0] = u.in[x | 0];",
        "u.out[x + 2 | 0] = u.in[x | 0];",
        "u.out[x + 9 | 0] = u.in[x | 0];",          # beyond the domain: wraps
    ])
    def test_pushes_into_active_cells_are_accepted(self, dyn):
        assert _compile(_program_1d(dyn=dyn)).geometry is not None

    def test_initializer_push_is_accepted(self):
        result = _compile(_program_1d(init="u.out[x + 1 | 0] = x;"))
        assert result.geometry is not None

    def test_local_writes_are_fine(self):
        result = _compile(_program_1d(dyn="u.out[x | 0] = u.in[x + 1 | 0] + u.in[x - 2 | 0];"))
        assert result.stencils is not None

    def test_ordered_overwrites_from_one_source_cell_are_accepted(self):
        # DF 0 twice locally; DF 1 pushed twice from the same source cell
        # (offsets 1 and 9 coincide on 8 periodic cells): no conflict.
        result = _compile(_program_1d(
            q=2, init="u.out[x | :] = 0.0;",
            dyn="u.out[x | 0] = 2.0; u.out[x | 0] = 3.0;"
                " u.out[x + 1 | 1] = 1.0; u.out[x + 9 | 1] = 2.0;",
            gauge="v = u.in[x | 0];"))
        assert result.geometry is not None

    def test_push_into_a_static_cell_is_rejected(self):
        code = _program_2d(
            blocks="""
            initializer I { u.out[x, y | :] = 1.0; }
            initializer IW { u.out[x, y | :] = 2.0; }
            dynamic D { u.out[x, y | :] = u.in[x, y | :]; u.out[x, y - 1 | 0] = 5.0; }
            gauge G -> (real v) { v = u.in[x, y | 0]; }""",
            node_classes="node_class B(I, D, G); node_class W(IW, G);",
            geometry="nodes[:, :] = B; nodes[:, 0] = W;",
            periodic="{true, false}")
        with pytest.raises(GeLBExStencilError) as info:
            _compile(code)
        assert "static node class" in str(info.value) and "'W'" in str(info.value)

    def test_initializer_push_into_a_static_cell_is_rejected_too(self):
        code = _program_2d(
            blocks="""
            initializer I { u.out[x, y | :] = 1.0; u.out[x, y - 1 | 0] = 5.0; }
            initializer IW { u.out[x, y | :] = 2.0; }
            dynamic D { u.out[x, y | :] = u.in[x, y | :]; }
            gauge G -> (real v) { v = u.in[x, y | 0]; }""",
            node_classes="node_class B(I, D, G); node_class W(IW, G);",
            geometry="nodes[:, :] = B; nodes[:, 0] = W;",
            periodic="{true, false}")
        with pytest.raises(GeLBExStencilError) as info:
            _compile(code)
        assert "static node class" in str(info.value)

    def test_push_into_an_empty_masked_cell_is_rejected(self):
        code = _program_2d(
            blocks="""
            initializer I { u.out[x, y | :] = 1.0; }
            dynamic D { u.out[x, y | :] = u.in[x, y | :]; u.out[x, y - 1 | 0] = 5.0; }
            gauge G -> (real v) { v = u.in[x, y | 0]; }""",
            node_classes="node_class B(I, D, G); node_class S() masked;",
            geometry="nodes[:, :] = B; nodes[:, 0] = S;",
            periodic="{true, false}")
        with pytest.raises(GeLBExStencilError) as info:
            _compile(code)
        assert "empty masked" in str(info.value)

    def test_push_into_an_active_masked_cell_is_accepted(self):
        # A push lands in same-class cells too, so a class that pushes DF 0
        # downward must not write DF 0 locally; the top row T supplies the
        # row below it and never reads its own DF 0.
        code = _program_2d(
            blocks="""
            initializer I { u.out[x, y | :] = 1.0; }
            dynamic D { u.out[x, y | 1] = u.in[x, y | 1]; u.out[x, y - 1 | 0] = 5.0; }
            dynamic DT { u.out[x, y | 1] = u.in[x, y | 1]; u.out[x, y - 1 | 0] = 7.0; }
            dynamic DM { u.out[x, y | 1] = u.in[x, y | 1] + u.in[x, y | 0]; }
            gauge G -> (real v) { v = u.in[x, y | 0]; }
            gauge GT -> (real v) { v = u.in[x, y | 1]; }""",
            node_classes="node_class B(I, D, G); node_class T(I, DT, GT);"
                         " node_class M(I, DM) masked;",
            geometry="nodes[:, :] = B; nodes[:, 0] = M; nodes[:, Ny - 1] = T;",
            periodic="{true, false}")
        assert _compile(code).geometry is not None

    def test_two_node_classes_writing_the_same_cell_and_df_conflict(self):
        code = _program_2d(
            blocks="""
            initializer I { u.out[x, y | :] = 1.0; }
            dynamic D { u.out[x, y | :] = u.in[x, y | :]; u.out[x, y - 1 | 0] = 5.0; }
            dynamic DE { u.out[x, y | :] = u.in[x, y | :]; }
            gauge G -> (real v) { v = u.in[x, y | 0]; }""",
            node_classes="node_class B(I, D, G); node_class E(I, DE, G);",
            geometry="nodes[:, :] = B; nodes[:, 0] = E;",
            periodic="{true, false}")
        with pytest.raises(GeLBExStencilError) as info:
            _compile(code)
        assert "Two source cells write DF 0" in str(info.value)

    def test_two_offsets_from_distinct_source_cells_conflict(self):
        with pytest.raises(GeLBExStencilError) as info:
            _compile(_program_1d(dyn="u.out[x + 1 | 0] = 1.0; u.out[x + 2 | 0] = 2.0;"))
        assert "Two source cells write DF 0" in str(info.value)

    def test_push_onto_a_locally_written_df_conflicts(self):
        with pytest.raises(GeLBExStencilError) as info:
            _compile(_program_1d(dyn="u.out[x | 0] = u.in[x | 0]; u.out[x + 1 | 0] = 2.0;"))
        assert "Two source cells write DF 0" in str(info.value)

    def test_conflict_names_the_cell(self):
        with pytest.raises(GeLBExStencilError) as info:
            _compile(_program_1d(dyn="u.out[x + 1 | 0] = 1.0; u.out[x + 2 | 0] = 2.0;"))
        assert "at cell (" in str(info.value)

    def test_push_off_a_wall_is_rejected(self):
        with pytest.raises(GeLBExStencilError) as info:
            _compile(_program_1d(dyn="u.out[x + 1 | 0] = u.in[x | 0];", periodic="false"))
        assert "+1 in x" in str(info.value)

    def test_complete_push_coverage_is_accepted(self):
        # Every cell receives DF 0 from its left neighbour (periodic), and
        # writes DF 1 itself: complete.
        result = _compile(_program_1d(
            q=2, init="u.out[x | :] = 0.0;",
            dyn="u.out[x | 1] = u.in[x | 1]; u.out[x + 1 | 0] = u.in[x | 0];",
            gauge="v = u.in[x | 0] + u.in[x | 1];"))
        assert result.geometry is not None

    def test_push_covering_only_part_of_a_class_is_reported_per_cell(self):
        # B pushes DF 1 into the row below it and never writes DF 1 locally;
        # E's cells at y = 0 receive it from B, but E also occupies the
        # x = 0 column, whose cells have E (not B) above them and so keep
        # DF 1 from the initializer only.  Nothing at B reads DF 1.
        code = _program_2d(
            blocks="""
            initializer I { u.out[x, y | :] = 1.0; }
            dynamic D { u.out[x, y | 0] = u.in[x, y | 0]; u.out[x, y - 1 | 1] = 5.0; }
            dynamic DE { u.out[x, y | 0] = u.in[x, y | 0] + u.in[x, y | 1]; }
            gauge G -> (real v) { v = u.in[x, y | 0]; }""",
            node_classes="node_class B(I, D, G); node_class E(I, DE, G);",
            geometry="nodes[:, :] = B; nodes[:, 0] = E; nodes[0, :] = E;",
            periodic="{false, false}")
        with pytest.raises(GeLBExStencilError) as info:
            _compile(code)
        msg = str(info.value)
        assert "only in its initializer" in msg and "[1]" in msg
        assert "'E'" in msg and "(0, " in msg

    def test_write_wrapping_back_to_its_own_cell_is_a_local_write(self):
        # On 8 periodic cells the offset +8 reaches the writing cell itself:
        # a static class may initialize its own cells that way.
        code = _static_self_write(offset=8)
        assert _compile(code).geometry is not None

    def test_write_wrapping_onto_another_cell_of_a_static_class_is_rejected(self):
        code = _static_self_write(offset=9)
        with pytest.raises(GeLBExStencilError) as info:
            _compile(code)
        assert "static node class" in str(info.value)


def _static_self_write(offset):
    return f"""
    simulation_description("wrapped self write");
    lattices {{ lattice u(1, 1, real, 8, true); }}
    initializer I {{ u.out[x | 0] = x; }}
    initializer IS {{ u.out[x + {offset} | 0] = 2.0; }}
    dynamic D {{ u.out[x | 0] = u.in[x | 0]; }}
    gauge G -> (real v) {{ v = u.in[x | 0]; }}
    node_classes {{ node_class B(I, D, G); node_class S(IS, G); }}
    geometry {{ nodes[:] = B; nodes[2:5] = S; }}
    """


# --------------------------------------------------------------------------
# the wall check covers initializers, on the resolved geometry
# --------------------------------------------------------------------------

class TestWallCheck:

    def test_initializer_write_off_a_wall_is_caught_by_the_wall_check(self):
        code = _program_1d(init="u.out[x + 2 | 0] = x;", periodic="false")
        with pytest.raises(GeLBExStencilError) as info:
            _compile(code)
        assert "'I'" in str(info.value) and "+2 in x" in str(info.value)

    def test_where_painted_class_at_the_wall_is_seen(self):
        # The class is painted by a predicate, which the paint-replay of the
        # stencil analysis cannot see; the resolved map can.
        code = _program_2d(
            blocks="""
            initializer I { u.out[x, y | :] = 1.0; }
            dynamic Bulk { u.out[x, y | :] = u.in[x, y | :]; }
            dynamic Edge { u.out[x, y | :] = u.in[x + 1, y | :]; }
            gauge G -> (real v) { v = u.in[x, y | 0]; }""",
            node_classes="node_class B(I, Bulk, G); node_class E(I, Edge, G);",
            geometry="nodes[:, :] = B; nodes[where x == Nx - 1] = E;",
            periodic="{false, true}")
        with pytest.raises(GeLBExStencilError) as info:
            _compile(code)
        assert "'Edge'" in str(info.value) and "+1 in x" in str(info.value)

    def test_wall_check_still_passes_for_interior_classes(self):
        code = _program_2d(
            blocks="""
            initializer I { u.out[x, y | :] = 1.0; }
            dynamic Bulk { u.out[x, y | :] = u.in[x, y | :]; }
            dynamic Mid { u.out[x, y | :] = u.in[x + 1, y | :]; }
            gauge G -> (real v) { v = u.in[x, y | 0]; }""",
            node_classes="node_class B(I, Bulk, G); node_class M(I, Mid, G);",
            geometry="nodes[:, :] = B; nodes[where x == 3] = M;",
            periodic="{false, true}")
        assert _compile(code).geometry is not None


# --------------------------------------------------------------------------
# initial and recurring coverage, checked separately per destination cell
# --------------------------------------------------------------------------

class TestCoverage:

    def test_df_written_only_by_the_initializer_of_an_active_class(self):
        with pytest.raises(GeLBExStencilError) as info:
            _compile(_program_1d(
                q=2, init="u.out[x | 0] = 1.0; u.out[x | 1] = 42.0;",
                dyn="u.out[x | 0] = u.in[x | 1];",
                gauge="v = u.in[x | 0];"))
        msg = str(info.value)
        assert "only in its initializer" in msg and "[1]" in msg

    def test_gauge_reading_a_lattice_only_the_dynamic_writes(self):
        with pytest.raises(GeLBExStencilError) as info:
            _compile(_program_1d(
                lattices="lattice r(1, 1, real, 8, true);",
                dyn="u.out[x | 0] = u.in[x | 0]; r.out[x | 0] = 42.0;",
                gauge="v = r.in[x | 0];"))
        msg = str(info.value)
        assert "only in its dynamic" in msg and "t = 0" in msg

    def test_unread_initializer_only_storage_is_not_an_error(self):
        result = _compile(_program_1d(
            q=2, init="u.out[x | 0] = 1.0; u.out[x | 1] = 42.0;",
            dyn="u.out[x | 0] = u.in[x | 0];",
            gauge="v = u.in[x | 0];"))
        assert result.geometry is not None

    def test_static_class_values_persist_for_neighbours(self):
        code = _program_2d(
            blocks="""
            initializer I { u.out[x, y | :] = 1.0; }
            initializer IW { u.out[x, y | :] = 2.0; }
            dynamic D { u.out[x, y | :] = u.in[x, y - 1 | :]; }
            gauge G -> (real v) { v = u.in[x, y | 0]; }""",
            node_classes="node_class B(I, D, G); node_class W(IW, G);",
            geometry="nodes[:, :] = B; nodes[:, 0] = W;",
            periodic="{true, false}")
        assert _compile(code).geometry is not None

    def test_neighbour_df_written_only_by_the_initializer_of_an_active_class(self):
        # H sits on the y = 0 row (a wall axis, so no seam question); B's
        # cells at y = 1 read DF 1 from H, whose dynamic writes DF 0 only.
        code = _program_2d(
            blocks="""
            initializer I { u.out[x, y | :] = 1.0; }
            dynamic D { u.out[x, y | :] = u.in[x, y - 1 | :]; }
            dynamic Half { u.out[x, y | 0] = u.in[x, y | 0]; }
            gauge G -> (real v) { v = u.in[x, y | 0]; }""",
            node_classes="node_class B(I, D, G); node_class H(I, Half, G);",
            geometry="nodes[:, :] = B; nodes[:, 0] = H;",
            periodic="{true, false}")
        with pytest.raises(GeLBExStencilError) as info:
            _compile(code)
        assert "only in its initializer" in str(info.value)
        assert "'H'" in str(info.value) and "[1]" in str(info.value)

    def test_empty_masked_neighbour_holds_defined_zeros(self):
        code = _program_2d(
            blocks="""
            initializer I { u.out[x, y | :] = 1.0; }
            dynamic D { u.out[x, y | :] = u.in[x, y - 1 | :]; }
            gauge G -> (real v) { v = u.in[x, y | 0]; }""",
            node_classes="node_class B(I, D, G); node_class S() masked;",
            geometry="nodes[:, :] = B; nodes[:, 0] = S;",
            periodic="{true, false}")
        assert _compile(code).geometry is not None

    def test_active_masked_class_follows_the_recurring_rule(self):
        code = _program_2d(
            blocks="""
            initializer I { u.out[x, y | :] = 1.0; }
            dynamic D { u.out[x, y | :] = u.in[x, y - 1 | :]; }
            dynamic Half { u.out[x, y | 0] = u.in[x, y | 0]; }
            gauge G -> (real v) { v = u.in[x, y | 0]; }""",
            node_classes="node_class B(I, D, G); node_class M(I, Half) masked;",
            geometry="nodes[:, :] = B; nodes[:, 0] = M;",
            periodic="{true, false}")
        with pytest.raises(GeLBExStencilError) as info:
            _compile(code)
        assert "only in its initializer" in str(info.value)

    def test_neighbour_df_never_written_keeps_the_original_message(self):
        # Z touches lattice w only; B reads DF 1 of u from Z's row.
        code = _program_2d(
            lattices="lattice u(2, 2, real, {NX, NY}, PER); lattice w(2, 1, real, {NX, NY}, PER);",
            blocks="""
            initializer I { u.out[x, y | :] = 1.0; w.out[x, y | 0] = 0.0; }
            initializer IZ { w.out[x, y | 0] = 2.0; }
            dynamic D { u.out[x, y | :] = u.in[x, y | :]; u.out[x, y | 1] = u.in[x, y - 1 | 1];
                        w.out[x, y | 0] = w.in[x, y | 0]; }
            dynamic DZ { w.out[x, y | 0] = w.in[x, y | 0]; }
            gauge G -> (real v) { v = u.in[x, y | 0]; }
            gauge GZ -> (real v) { v = w.in[x, y | 0]; }""",
            node_classes="node_class B(I, D, G); node_class Z(IZ, DZ, GZ);",
            geometry="nodes[:, :] = B; nodes[:, 0] = Z;",
            periodic="{true, false}")
        with pytest.raises(GeLBExStencilError) as info:
            _compile(code)
        assert "never writes DF(s) [1] of 'u'" in str(info.value)


    def test_masked_storage_starts_at_zero_even_if_a_dynamic_writes_it_later(self):
        # Masked storage is zeroed in both buffers before initializers run,
        # so a zero is a defined initial value wherever no initializer
        # writes: M's initializer leaves v alone and its dynamic writes v
        # every step; B reads v from M's row at t = 0 (zero by the masked
        # guarantee) and after every swap (DM's value).
        code = _program_2d(
            lattices="lattice u(2, 1, real, {NX, NY}, PER); lattice v(2, 1, real, {NX, NY}, PER);",
            blocks="""
            initializer I { u.out[x, y | 0] = 1.0; v.out[x, y | 0] = 0.0; }
            initializer IM { u.out[x, y | 0] = 2.0; }
            dynamic D { u.out[x, y | 0] = u.in[x, y | 0]; v.out[x, y | 0] = v.in[x, y - 1 | 0]; }
            dynamic DM { u.out[x, y | 0] = u.in[x, y | 0]; v.out[x, y | 0] = u.in[x, y | 0]; }
            gauge G -> (real w) { w = v.in[x, y - 1 | 0]; }""",
            node_classes="node_class B(I, D, G); node_class M(IM, DM) masked;",
            geometry="nodes[:, :] = B; nodes[:, 0] = M;",
            periodic="{true, false}")
        assert _compile(code).geometry is not None

    def test_a_dynamic_may_read_a_lattice_its_own_initializer_never_writes(self):
        # B reads v only from M's cell, where it is defined (zero, then
        # DM's value); the lattice-level rule that B's initializer must
        # write v would have been a false rejection.
        code = """
        simulation_description("read from a masked neighbour only");
        lattices { lattice u(1, 1, real, 8, false); lattice v(1, 1, real, 8, false); }
        initializer I { u.out[x | 0] = 1.0; v.out[x | 0] = 0.0; }
        initializer IB { u.out[x | 0] = 1.0; }
        initializer IM { u.out[x | 0] = 2.0; }
        dynamic D { u.out[x | 0] = u.in[x | 0]; v.out[x | 0] = v.in[x | 0]; }
        dynamic DB { u.out[x | 0] = u.in[x | 0] + v.in[x - 1 | 0]; }
        dynamic DM { u.out[x | 0] = u.in[x | 0]; v.out[x | 0] = u.in[x | 0]; }
        gauge G -> (real w) { w = u.in[x | 0]; }
        node_classes { node_class C(I, D, G); node_class B(IB, DB, G); node_class M(IM, DM) masked; }
        geometry { nodes[:] = C; nodes[1] = B; nodes[0] = M; }
        """
        assert _compile(code).geometry is not None

    def test_a_masked_initializer_may_write_some_dfs_only(self):
        # DF 1 of u at M's cell is never written: zero in both phases.
        code = """
        simulation_description("partial masked initializer");
        lattices { lattice u(1, 2, real, 8, false); }
        initializer I { u.out[x | :] = 1.0; }
        initializer IM { u.out[x | 0] = 5.0; }
        dynamic D { u.out[x | :] = u.in[x - 1 | :]; }
        dynamic DM { u.out[x | 0] = u.in[x | 0]; }
        gauge G -> (real w) { w = u.in[x | 1]; }
        node_classes { node_class B(I, D, G); node_class M(IM, DM) masked; }
        geometry { nodes[:] = B; nodes[0] = M; }
        """
        assert _compile(code).geometry is not None


# --------------------------------------------------------------------------
# a write must name its DFs at compile time
# --------------------------------------------------------------------------

class TestDFSelection:

    def test_runtime_df_index_in_a_write_is_rejected(self):
        with pytest.raises(GeLBExStencilError) as info:
            _compile(_program_1d(q=8, init="u.out[x | x] = 1.0;",
                                 dyn="u.out[x | :] = u.in[x | :];"))
        assert "compile-time integer" in str(info.value)

    def test_constant_slices_and_full_range_are_fine(self):
        result = _compile(_program_1d(
            q=3, init="u.out[x | 0:1] = 5.0; u.out[x | 2] = 7.0;",
            dyn="u.out[x | :] = u.in[x | :];"))
        writes = result.stencils.blocks['I'].writes
        assert sorted(w.df_index for w in writes) == [0, 1, 2]

    def test_runtime_df_index_in_a_read_needs_every_df_written(self):
        # A read whose DF is not known may touch any DF: the writer must
        # cover them all.  Here it does, so the program is accepted.
        result = _compile(_program_1d(
            q=3, init="u.out[x | :] = 1.0;",
            dyn="u.out[x | :] = u.in[x | :];",
            gauge="v = u.in[x | mod(x, 3)];"))
        assert result.geometry is not None


# --------------------------------------------------------------------------
# --diagnostics-json puts the errors on the block
# --------------------------------------------------------------------------

def _diagnostics(tmp_path, code):
    path = tmp_path / "prog.gelb"
    path.write_text(code)
    result = CliRunner().invoke(gelbc_cli, [str(path), "--diagnostics-json"])
    payload = json.loads(result.output)
    return path, [(d["message"] + " " + d.get("hint", ""), d["range"]["startLine"] + 1)
                  for d in payload["diagnostics"]]


def _line_of(path, text):
    return next(i for i, line in enumerate(path.read_text().splitlines(), 1)
                if text in line)


class TestDiagnosticsJson:

    def test_conflict_error_lands_on_the_dynamic(self, tmp_path):
        code = _program_1d(dyn="u.out[x + 1 | 0] = 1.0; u.out[x + 2 | 0] = 2.0;")
        path, diags = _diagnostics(tmp_path, code)
        text, line = diags[0]
        assert "Two source cells" in text
        assert line == _line_of(path, "dynamic D")

    def test_static_destination_error_lands_on_the_dynamic(self, tmp_path):
        code = _program_2d(
            blocks="""
            initializer I { u.out[x, y | :] = 1.0; }
            initializer IW { u.out[x, y | :] = 2.0; }
            dynamic D { u.out[x, y | :] = u.in[x, y | :]; u.out[x, y - 1 | 0] = 5.0; }
            gauge G -> (real v) { v = u.in[x, y | 0]; }""",
            node_classes="node_class B(I, D, G); node_class W(IW, G);",
            geometry="nodes[:, :] = B; nodes[:, 0] = W;",
            periodic="{true, false}")
        path, diags = _diagnostics(tmp_path, code)
        text, line = diags[0]
        assert "static node class" in text
        assert line == _line_of(path, "dynamic D")

    def test_recurring_coverage_error_lands_on_the_dynamic(self, tmp_path):
        code = _program_1d(q=2, init="u.out[x | 0] = 1.0; u.out[x | 1] = 42.0;",
                           dyn="u.out[x | 0] = u.in[x | 1];", gauge="v = u.in[x | 0];")
        path, diags = _diagnostics(tmp_path, code)
        text, line = diags[0]
        assert "only in its initializer" in text
        assert line == _line_of(path, "dynamic D")

    def test_runtime_df_index_error_lands_on_its_line(self, tmp_path):
        code = _program_1d(q=8, init="u.out[x | x] = 1.0;", dyn="u.out[x | :] = u.in[x | :];")
        path, diags = _diagnostics(tmp_path, code)
        text, line = diags[0]
        assert "compile-time integer" in text
        assert line == _line_of(path, "u.out[x | x]")


# --------------------------------------------------------------------------
# every compilation validates walls on the resolved map
# --------------------------------------------------------------------------

_EDGE_PROGRAM = """
simulation_description("wall check on the resolved map");
lattices {{ lattice u(1, 1, real, 8, false); }}
initializer I {{ u.out[x | 0] = x; }}
initializer IE {{ u.out[x | 0] = x; {edge_init} }}
dynamic D {{ u.out[x | 0] = {bulk_read}; }}
dynamic DE {{ u.out[x | 0] = u.in[x | 0]; }}
gauge G -> (real v) {{ v = u.in[x | 0]; }}
node_classes {{ node_class B(I, D, G); node_class E(IE, DE, G); }}
geometry {{ nodes[:] = B; nodes[where x == 7] = E; }}
"""

# E, painted by a predicate at the wall, pushes off the grid.
_UNSAFE_EDGE = _EDGE_PROGRAM.format(edge_init="u.out[x + 2 | 0] = 123.0;",
                                    bulk_read="u.in[x | 0]")
# B reads x + 1 but the predicate repaints x = 7 with E: safe.
_SAFE_EDGE = _EDGE_PROGRAM.format(edge_init="", bulk_read="u.in[x + 1 | 0]")


def _gelbc(tmp_path, code, *extra):
    path = tmp_path / "edge.gelb"
    path.write_text(code)
    out = tmp_path / "edge.f90"
    result = CliRunner().invoke(
        gelbc_cli,
        [str(path), "--backend", "cpu_fortran_serial", "--output", str(out), *extra])
    return result, out


class TestNormalCompilation:

    @pytest.mark.parametrize("extra", [(), ("--no-geometry-lint",)])
    def test_unsafe_push_from_a_predicate_painted_class_is_rejected(self, tmp_path, extra):
        result, out = _gelbc(tmp_path, _UNSAFE_EDGE, *extra)
        assert result.exit_code != 0
        assert isinstance(result.exception, GeLBExStencilError), result.output
        assert "'IE'" in str(result.exception) and "+2 in x" in str(result.exception)
        assert not out.exists()

    @pytest.mark.parametrize("extra", [(), ("--no-geometry-lint",)])
    def test_safe_boundary_repaint_by_a_predicate_compiles(self, tmp_path, extra):
        result, out = _gelbc(tmp_path, _SAFE_EDGE, *extra)
        assert result.exit_code == 0, result.output + str(result.exception)
        assert out.exists()

    def test_stencil_report_validates_on_the_map_too(self, tmp_path):
        result, _ = _gelbc(tmp_path, _UNSAFE_EDGE, "--stencils", "--no-geometry-lint")
        assert result.exit_code != 0
        assert isinstance(result.exception, GeLBExStencilError)

    def test_diagnostics_agree_with_compilation(self, tmp_path):
        _, diags = _diagnostics(tmp_path, _UNSAFE_EDGE)
        assert any("+2 in x" in text for text, _ in diags)
        _, diags = _diagnostics(tmp_path, _SAFE_EDGE)
        assert not any("Out-of-bounds" in text for text, _ in diags)
