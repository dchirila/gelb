#!/usr/bin/env python3
"""
Unit tests for stencil extraction (gelb.midware.stencil + StencilExtractionVisitor).
"""

import pytest

from gelb.tests.test_utils import (
    get_typed_ast,
    minimal_gelb_program_1d,
    minimal_gelb_program_2d,
)
from gelb.midware.stage2_midware import fold_constants, extract_stencils
from gelb.utils.exceptions import GeLBExStencilError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract(gelb_code):
    """Run the full pipeline up to stencil extraction."""
    ast = get_typed_ast(gelb_code)
    ast = fold_constants(ast)
    return extract_stencils(ast)


# ---------------------------------------------------------------------------
# 2D pull-streaming dynamic
# ---------------------------------------------------------------------------

class TestPullStreamingDynamic2D:
    """Stencils for a D2Q9 pull-streaming dynamic block."""

    PROGRAM = minimal_gelb_program_2d(
        dynamic_content="""
            real f0 = f.in[x,   y   | 0];
            real f1 = f.in[x-1, y   | 1];
            real f2 = f.in[x,   y-1 | 2];
            real f3 = f.in[x+1, y   | 3];
            real f4 = f.in[x,   y+1 | 4];
            real f5 = f.in[x-1, y-1 | 5];
            real f6 = f.in[x+1, y-1 | 6];
            real f7 = f.in[x+1, y+1 | 7];
            real f8 = f.in[x-1, y+1 | 8];
            f.out[x, y | 0] = f0;
            f.out[x, y | 1] = f1;
            f.out[x, y | 2] = f2;
            f.out[x, y | 3] = f3;
            f.out[x, y | 4] = f4;
            f.out[x, y | 5] = f5;
            f.out[x, y | 6] = f6;
            f.out[x, y | 7] = f7;
            f.out[x, y | 8] = f8;
        """,
    )

    def test_read_offsets_cover_d2q9(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Dyn"]
        expected = {
            (0, 0), (-1, 0), (0, -1), (1, 0), (0, 1),
            (-1, -1), (1, -1), (1, 1), (-1, 1),
        }
        assert bs.read_offsets == expected

    def test_write_offsets_are_local(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Dyn"]
        assert bs.write_offsets == {(0, 0)}

    def test_nine_reads(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Dyn"]
        assert len(bs.reads) == 9

    def test_nine_writes(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Dyn"]
        assert len(bs.writes) == 9

    def test_read_df_indices(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Dyn"]
        df_indices = sorted(a.df_index for a in bs.reads)
        assert df_indices == list(range(9))

    def test_is_not_local(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Dyn"]
        assert not bs.is_local

    def test_specific_offset_for_df1(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Dyn"]
        df1_reads = [a for a in bs.reads if a.df_index == 1]
        assert len(df1_reads) == 1
        assert df1_reads[0].spatial_offsets == (-1, 0)


# ---------------------------------------------------------------------------
# Bounce-back (local) dynamic
# ---------------------------------------------------------------------------

class TestBounceBackDynamic:
    """Stencils for a local bounce-back dynamic (reads and writes at (0,0))."""

    PROGRAM = minimal_gelb_program_2d(
        dynamic_content="""
            f.out[x, y | 0] = f.in[x, y | 0];
            f.out[x, y | 1] = f.in[x, y | 3];
            f.out[x, y | 2] = f.in[x, y | 4];
            f.out[x, y | 3] = f.in[x, y | 1];
            f.out[x, y | 4] = f.in[x, y | 2];
            f.out[x, y | 5] = f.in[x, y | 7];
            f.out[x, y | 6] = f.in[x, y | 8];
            f.out[x, y | 7] = f.in[x, y | 5];
            f.out[x, y | 8] = f.in[x, y | 6];
        """,
    )

    def test_is_local(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Dyn"]
        assert bs.is_local

    def test_read_offsets(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Dyn"]
        assert bs.read_offsets == {(0, 0)}

    def test_write_offsets(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Dyn"]
        assert bs.write_offsets == {(0, 0)}


# ---------------------------------------------------------------------------
# Initializer (writes only)
# ---------------------------------------------------------------------------

class TestInitializer:
    """Stencils for an initializer block (writes f.out, no f.in)."""

    PROGRAM = minimal_gelb_program_2d(
        initializer_content="f.out[x, y | 0] = 42;",
    )

    def test_no_reads(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Init"]
        assert len(bs.reads) == 0

    def test_has_writes(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Init"]
        assert len(bs.writes) == 1

    def test_block_type(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Init"]
        assert bs.block_type == "initializer"


# ---------------------------------------------------------------------------
# Gauge (reads only)
# ---------------------------------------------------------------------------

class TestGauge:
    """Stencils for a gauge block (reads f.in, no f.out)."""

    PROGRAM = minimal_gelb_program_2d()  # default gauge: val = f.in[x, y | 0]

    def test_no_writes(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Out"]
        assert len(bs.writes) == 0

    def test_has_reads(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Out"]
        assert len(bs.reads) == 1

    def test_read_at_origin(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Out"]
        assert bs.reads[0].spatial_offsets == (0, 0)

    def test_block_type(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Out"]
        assert bs.block_type == "gauge"


# ---------------------------------------------------------------------------
# Full-range DF access (`:` syntax)
# ---------------------------------------------------------------------------

class TestFullRangeDF:
    """Full-range DF access should expand to individual DF indices 0..q-1."""

    PROGRAM = minimal_gelb_program_2d(
        dynamic_content="f.out[x, y | :] = f.in[x, y | :];",
    )

    def test_read_covers_all_dfs(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Dyn"]
        df_indices = sorted(
            a.df_index for a in bs.reads if a.df_index is not None
        )
        assert df_indices == list(range(9))

    def test_write_covers_all_dfs(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Dyn"]
        df_indices = sorted(
            a.df_index for a in bs.writes if a.df_index is not None
        )
        assert df_indices == list(range(9))


# ---------------------------------------------------------------------------
# Per-DF access (specific index)
# ---------------------------------------------------------------------------

class TestPerDFAccess:
    """Per-DF access like f.in[x, y | 3] should record the specific index."""

    PROGRAM = minimal_gelb_program_2d(
        dynamic_content="""
            f.out[x, y | 5] = f.in[x, y | 3];
        """,
    )

    def test_read_df_index(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Dyn"]
        assert len(bs.reads) == 1
        assert bs.reads[0].df_index == 3

    def test_write_df_index(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Dyn"]
        assert len(bs.writes) == 1
        assert bs.writes[0].df_index == 5


# ---------------------------------------------------------------------------
# 1D stencil
# ---------------------------------------------------------------------------

class TestStencil1D:
    """Stencil extraction for a 1D program."""

    PROGRAM = minimal_gelb_program_1d(
        dynamic_content="""
            real fl = f.in[x-1 | 0];
            real fc = f.in[x   | 0];
            real fr = f.in[x+1 | 0];
            f.out[x | 0] = fc;
        """,
    )

    def test_read_offsets(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Dyn"]
        offsets = bs.read_offsets
        assert offsets == {(-1,), (0,), (1,)}

    def test_write_offset(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Dyn"]
        assert bs.write_offsets == {(0,)}

    def test_one_dimensional_offsets(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Dyn"]
        for a in bs.reads:
            assert len(a.spatial_offsets) == 1


# ---------------------------------------------------------------------------
# Multi-block program
# ---------------------------------------------------------------------------

class TestMultiBlock:
    """All blocks in a program should be extracted."""

    PROGRAM = minimal_gelb_program_2d()  # has Init, Dyn, Out

    def test_all_blocks_present(self):
        stencils = _extract(self.PROGRAM)
        assert "Init" in stencils.blocks
        assert "Dyn" in stencils.blocks
        assert "Out" in stencils.blocks

    def test_block_types(self):
        stencils = _extract(self.PROGRAM)
        assert stencils.blocks["Init"].block_type == "initializer"
        assert stencils.blocks["Dyn"].block_type == "dynamic"
        assert stencils.blocks["Out"].block_type == "gauge"


# ---------------------------------------------------------------------------
# Node class -> block mapping
# ---------------------------------------------------------------------------

class TestNodeClassMapping:
    """Node classes should map to their initializer, dynamic, and gauge."""

    PROGRAM = minimal_gelb_program_2d()  # BULK and WALL, both -> (Init, Dyn, Out)

    def test_node_classes_populated(self):
        stencils = _extract(self.PROGRAM)
        assert "BULK" in stencils.node_classes
        assert "WALL" in stencils.node_classes

    def test_mapping_values(self):
        stencils = _extract(self.PROGRAM)
        nc = stencils.node_classes["BULK"]
        assert nc.initializer == "Init"
        assert nc.dynamic == "Dyn"
        assert nc.gauge == "Out"


# ---------------------------------------------------------------------------
# Geometry paints
# ---------------------------------------------------------------------------

class TestGeometryPaints:
    """Geometry paint statements should be captured in order."""

    PROGRAM = minimal_gelb_program_2d(
        geometry_content="""
            nodes[:, :] = BULK;
            nodes[:, 0] = WALL;
            nodes[:, 31] = WALL;
        """,
    )

    def test_paint_count(self):
        stencils = _extract(self.PROGRAM)
        assert len(stencils.geometry_paints) == 3

    def test_paint_order(self):
        stencils = _extract(self.PROGRAM)
        assert stencils.geometry_paints[0].node_class == "BULK"
        assert stencils.geometry_paints[1].node_class == "WALL"
        assert stencils.geometry_paints[2].node_class == "WALL"

    def test_full_range_paint(self):
        stencils = _extract(self.PROGRAM)
        p = stencils.geometry_paints[0]
        # Full range in both dimensions -> None entries
        assert p.ranges[0] is None
        assert p.ranges[1] is None

    def test_single_index_paint(self):
        stencils = _extract(self.PROGRAM)
        p = stencils.geometry_paints[1]
        # nodes[:, 0] -> first dim full, second dim (0, 0)
        assert p.ranges[0] is None
        assert p.ranges[1] == (0, 0)

    def test_get_node_class_at(self):
        stencils = _extract(self.PROGRAM)
        # Interior point -> BULK (first paint)
        assert stencils.get_node_class_at(5, 5) == "BULK"
        # Boundary -> WALL (second paint overwrites)
        assert stencils.get_node_class_at(5, 0) == "WALL"
        assert stencils.get_node_class_at(5, 31) == "WALL"


# ---------------------------------------------------------------------------
# Lattice metadata
# ---------------------------------------------------------------------------

class TestLatticeMetadata:
    """Lattice info (d, q) should be extracted."""

    PROGRAM = minimal_gelb_program_2d()

    def test_lattice_present(self):
        stencils = _extract(self.PROGRAM)
        assert "f" in stencils.lattices

    def test_dimensionality(self):
        stencils = _extract(self.PROGRAM)
        assert stencils.lattices["f"].d == 2

    def test_num_speeds(self):
        stencils = _extract(self.PROGRAM)
        assert stencils.lattices["f"].q == 9

    def test_list_periodicity(self):
        stencils = _extract(self.PROGRAM)
        assert stencils.lattices["f"].periodic == (False, False)

    @pytest.mark.parametrize("flag", ["true", "false"])
    def test_scalar_periodicity_1d(self, flag):
        """A 1-D lattice gives its periodicity as a scalar, not a list."""
        prog = minimal_gelb_program_1d().replace("32, false", f"32, {flag}")
        stencils = _extract(prog)
        assert stencils.lattices["f"].periodic == (flag == "true",)


# ---------------------------------------------------------------------------
# Index forms: every lattice index is its axis coordinate plus a constant
# ---------------------------------------------------------------------------

class TestIndexForms:
    """Offsets are read from any constant affine form of the axis's own
    coordinate; any other index is an error rather than offset 0."""

    @pytest.mark.parametrize("index, offset", [
        ("x", 0), ("x + 2", 2), ("x - 3", -3), ("2 + x", 2),
        ("(x + 1) + 1", 2), ("(x - 1) - 1", -2), ("x - (-1)", 1),
        ("x + 2 * 1", 2), ("(x + 3) - 1", 2),
    ])
    def test_affine_offsets(self, index, offset):
        prog = minimal_gelb_program_1d(
            dynamic_content=f"f.out[x | 0] = f.in[{index} | 0];")
        [read] = _extract(prog).blocks["Dyn"].reads
        assert read.spatial_offsets == (offset,)

    def test_2d_affine_offsets(self):
        prog = minimal_gelb_program_2d(
            dynamic_content="f.out[x, y | 0] = f.in[(x + 1) + 1, 1 + y | 0];")
        reads = _extract(prog).blocks["Dyn"].reads
        assert [r.spatial_offsets for r in reads] == [(2, 1)]

    @pytest.mark.parametrize("index", ["0", "2 * x", "x * x", "31 - x"])
    def test_non_offset_index_is_an_error(self, index):
        prog = minimal_gelb_program_1d(
            dynamic_content=f"f.out[x | 0] = f.in[{index} | 0];")
        with pytest.raises(GeLBExStencilError, match="along x"):
            _extract(prog)

    @pytest.mark.parametrize("read", ["f.in[y, x | 0]", "f.in[x + y, y | 0]"])
    def test_wrong_axis_is_an_error(self, read):
        prog = minimal_gelb_program_2d(
            dynamic_content=f"f.out[x, y | 0] = {read};")
        with pytest.raises(GeLBExStencilError, match="along x"):
            _extract(prog)

    def test_write_index_is_checked_too(self):
        prog = minimal_gelb_program_1d(
            dynamic_content="f.out[0 | 0] = f.in[x | 0];")
        with pytest.raises(GeLBExStencilError, match="along x"):
            _extract(prog)

    def test_error_points_at_the_line(self):
        prog = minimal_gelb_program_1d(
            dynamic_content="f.out[x | 0] = f.in[2 * x | 0];")
        with pytest.raises(GeLBExStencilError) as info:
            _extract(prog)
        line = next(i for i, text in enumerate(prog.splitlines(), 1)
                    if "2 * x" in text)
        assert info.value.source_line == line


# ---------------------------------------------------------------------------
# Text report formatting
# ---------------------------------------------------------------------------

class TestFormatReport:
    """BlockStencil.format_report() should produce readable output."""

    PROGRAM = minimal_gelb_program_2d()

    def test_report_contains_block_name(self):
        stencils = _extract(self.PROGRAM)
        report = stencils.blocks["Dyn"].format_report()
        assert "Dyn" in report

    def test_report_contains_block_type(self):
        stencils = _extract(self.PROGRAM)
        report = stencils.blocks["Dyn"].format_report()
        assert "dynamic" in report

    def test_full_report_contains_all_blocks(self):
        stencils = _extract(self.PROGRAM)
        report = stencils.format_report()
        assert "Init" in report
        assert "Dyn" in report
        assert "Out" in report


# ---------------------------------------------------------------------------
# Deduplication of stencil accesses
# ---------------------------------------------------------------------------

class TestDeduplication1D:
    """When a block reads the same DF multiple times, stencil should deduplicate."""

    PROGRAM = minimal_gelb_program_1d(
        dynamic_content="""
            real a = f.in[x | 0];
            real b = f.in[x | 0];
            f.out[x | 0] = a + b;
        """,
    )

    def test_read_deduplicated(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Dyn"]
        # f.in[x | 0] appears twice but should be deduplicated to one entry
        assert len(bs.reads) == 1
        assert bs.reads[0].df_index == 0
        assert bs.reads[0].spatial_offsets == (0,)

    def test_write_deduplicated(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Dyn"]
        assert len(bs.writes) == 1


class TestDeduplication2D:
    """Deduplication for 2D programs with repeated accesses."""

    PROGRAM = minimal_gelb_program_2d(
        dynamic_content="""
            real a = f.in[x, y | 0];
            real b = f.in[x, y | 0];
            real c = f.in[x-1, y | 1];
            real d = f.in[x-1, y | 1];
            f.out[x, y | 0] = a + b;
            f.out[x, y | 0] = c + d;
            f.out[x, y | 1] = a;
        """,
    )

    def test_reads_deduplicated(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Dyn"]
        # Two unique reads: (0,0)|0 and (-1,0)|1
        assert len(bs.reads) == 2

    def test_writes_deduplicated(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Dyn"]
        # Two unique writes: (0,0)|0 and (0,0)|1
        assert len(bs.writes) == 2

    def test_read_offsets(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Dyn"]
        assert bs.read_offsets == {(0, 0), (-1, 0)}

    def test_dedup_preserves_order(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Dyn"]
        # First unique read encountered should come first
        assert bs.reads[0].df_index == 0
        assert bs.reads[0].spatial_offsets == (0, 0)
        assert bs.reads[1].df_index == 1
        assert bs.reads[1].spatial_offsets == (-1, 0)


class TestDeduplicationGauge:
    """Gauge blocks that read the same DF for multiple computations."""

    PROGRAM = minimal_gelb_program_2d(
        gauge_content="""
            val = f.in[x, y | 0] + f.in[x, y | 0];
        """,
    )

    def test_gauge_reads_deduplicated(self):
        stencils = _extract(self.PROGRAM)
        bs = stencils.blocks["Out"]
        assert len(bs.reads) == 1
        assert bs.reads[0].df_index == 0
