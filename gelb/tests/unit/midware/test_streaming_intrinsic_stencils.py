#!/usr/bin/env python3
"""
Unit tests for stencil extraction from upstream_dfs and bounce_back_dfs intrinsics.

Verifies that the extracted read stencils have accurate spatial offsets
and DF indices for D1Q3, D2Q9, and D3Q19 lattice models.
"""

import pytest

from gelb.tests.test_utils import get_typed_ast
from gelb.utils.exceptions import GeLBExStencilError
from gelb.midware.stage2_midware import fold_constants, extract_stencils, \
    warn_writeonly_dynamics


def _extract(gelb_code):
    """Run the full pipeline up to stencil extraction."""
    ast = get_typed_ast(gelb_code)
    ast = fold_constants(ast)
    return extract_stencils(ast)


# ---------------------------------------------------------------------------
# D1Q3 upstream_dfs
# ---------------------------------------------------------------------------

_D1Q3_PROGRAM = '''\
simulation_description("D1Q3 upstream_dfs test");
global_constants {
    const int N = 10;
    const array[real, 3] EX = {0.0, 1.0, -1.0};
}
lattices { lattice f(1, 3, real, N, true); }
initializer Init { f.out[x | :] = {0.0, 0.0, 0.0}; }
dynamic Dyn {
    array[real, 3] fIn = upstream_dfs(f, x, EX);
    f.out[x | :] = fIn;
}
gauge G -> (real rho) { rho = f.in[x | 0]; }
node_classes { node_class BULK(Init, Dyn, G); }
geometry { nodes[:] = BULK; }
'''


class TestStreamingIntrinsicCoordinates:
    """The coordinate arguments must be the current cell's coordinates;
    the stencil would otherwise not describe what the code reads."""

    @pytest.mark.parametrize("coord", ["x + 1", "0"])
    def test_other_coordinate_is_an_error(self, coord):
        prog = _D1Q3_PROGRAM.replace("upstream_dfs(f, x, EX)",
                                     f"upstream_dfs(f, {coord}, EX)")
        with pytest.raises(GeLBExStencilError, match="must be x itself"):
            _extract(prog)


class TestUpstreamDfsD1Q3:
    """Stencil accuracy for upstream_dfs on a D1Q3 lattice."""

    def test_read_count(self):
        stencils = _extract(_D1Q3_PROGRAM)
        dyn = stencils.blocks['Dyn']
        assert len(dyn.reads) == 3

    def test_df0_local(self):
        """DF 0 (rest): offset (0,)"""
        stencils = _extract(_D1Q3_PROGRAM)
        reads = stencils.blocks['Dyn'].reads
        r0 = [r for r in reads if r.df_index == 0]
        assert len(r0) == 1
        assert r0[0].spatial_offsets == (0,)

    def test_df1_pull_from_left(self):
        """DF 1 (c=+1): pull from left, offset (-1,)"""
        stencils = _extract(_D1Q3_PROGRAM)
        reads = stencils.blocks['Dyn'].reads
        r1 = [r for r in reads if r.df_index == 1]
        assert len(r1) == 1
        assert r1[0].spatial_offsets == (-1,)

    def test_df2_pull_from_right(self):
        """DF 2 (c=-1): pull from right, offset (+1,)"""
        stencils = _extract(_D1Q3_PROGRAM)
        reads = stencils.blocks['Dyn'].reads
        r2 = [r for r in reads if r.df_index == 2]
        assert len(r2) == 1
        assert r2[0].spatial_offsets == (1,)

    def test_all_offsets(self):
        """Verify the complete set of read offsets."""
        stencils = _extract(_D1Q3_PROGRAM)
        offsets = stencils.blocks['Dyn'].read_offsets
        assert offsets == {(0,), (-1,), (1,)}


# ---------------------------------------------------------------------------
# D2Q9 upstream_dfs
# ---------------------------------------------------------------------------

_D2Q9_PROGRAM = '''\
simulation_description("D2Q9 upstream_dfs test");
global_constants {
    const int N = 10;
    const array[real, 9] EX = {0.0, 1.0, 0.0, -1.0,  0.0, 1.0, -1.0, -1.0,  1.0};
    const array[real, 9] EY = {0.0, 0.0, 1.0,  0.0, -1.0, 1.0,  1.0, -1.0, -1.0};
    const array[real, 9] W = {4.0/9.0,
        1.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0,
        1.0/36.0, 1.0/36.0, 1.0/36.0, 1.0/36.0};
}
lattices { lattice f(2, 9, real, {N, N}, {true, true}); }
initializer Init { f.out[x, y | :] = W; }
dynamic Dyn {
    array[real, 9] fIn = upstream_dfs(f, x, y, {EX, EY});
    f.out[x, y | :] = fIn;
}
gauge G -> (real rho) { rho = sum(f.in[x, y | :]); }
node_classes { node_class BULK(Init, Dyn, G); }
geometry { nodes[:,:] = BULK; }
'''

# D2Q9 velocity vectors: (EX[i], EY[i])
# i=0: (0,0)   i=1: (1,0)   i=2: (0,1)   i=3: (-1,0)  i=4: (0,-1)
# i=5: (1,1)   i=6: (-1,1)  i=7: (-1,-1) i=8: (1,-1)
_D2Q9_EXPECTED_OFFSETS = {
    0: (0, 0),
    1: (-1, 0),
    2: (0, -1),
    3: (1, 0),
    4: (0, 1),
    5: (-1, -1),
    6: (1, -1),
    7: (1, 1),
    8: (-1, 1),
}


class TestUpstreamDfsD2Q9:
    """Stencil accuracy for upstream_dfs on a D2Q9 lattice."""

    def test_read_count(self):
        stencils = _extract(_D2Q9_PROGRAM)
        dyn = stencils.blocks['Dyn']
        assert len(dyn.reads) == 9

    @pytest.mark.parametrize("df_idx,expected_offset",
                             list(_D2Q9_EXPECTED_OFFSETS.items()))
    def test_df_offset(self, df_idx, expected_offset):
        stencils = _extract(_D2Q9_PROGRAM)
        reads = stencils.blocks['Dyn'].reads
        matches = [r for r in reads if r.df_index == df_idx]
        assert len(matches) == 1
        assert matches[0].spatial_offsets == expected_offset

    def test_all_unique_offsets(self):
        """D2Q9 pull streaming has 9 unique offset vectors."""
        stencils = _extract(_D2Q9_PROGRAM)
        offsets = stencils.blocks['Dyn'].read_offsets
        # (0,0), (+/-1,0), (0,+/-1), (+/-1,+/-1) = 9 distinct vectors
        assert len(offsets) == 9


# ---------------------------------------------------------------------------
# D2Q9 bounce_back_dfs
# ---------------------------------------------------------------------------

_D2Q9_BOUNCE_BACK_PROGRAM = '''\
simulation_description("D2Q9 bounce_back_dfs test");
global_constants {
    const int N = 10;
    const array[real, 9] EX = {0.0, 1.0, 0.0, -1.0,  0.0, 1.0, -1.0, -1.0,  1.0};
    const array[real, 9] EY = {0.0, 0.0, 1.0,  0.0, -1.0, 1.0,  1.0, -1.0, -1.0};
    const array[real, 9] W = {4.0/9.0,
        1.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0,
        1.0/36.0, 1.0/36.0, 1.0/36.0, 1.0/36.0};
}
lattices { lattice f(2, 9, real, {N, N}, {false, false}); }
initializer Init { f.out[x, y | :] = W; }
dynamic BB {
    f.out[x, y | :] = bounce_back_dfs(f, x, y, {EX, EY});
}
gauge G -> (real rho) { rho = sum(f.in[x, y | :]); }
node_classes { node_class BULK(Init, BB, G); }
geometry { nodes[:,:] = BULK; }
'''

# D2Q9 opposite mapping: 0<->0, 1<->3, 2<->4, 5<->7, 6<->8
_D2Q9_OPPOSITE_MAP = {0: 0, 1: 3, 2: 4, 3: 1, 4: 2, 5: 7, 6: 8, 7: 5, 8: 6}


_D2Q9_EX = (0, 1, 0, -1, 0, 1, -1, -1, 1)
_D2Q9_EY = (0, 0, 1, 0, -1, 1, 1, -1, -1)


class TestBounceBackDfsD2Q9:
    """Stencil accuracy for bounce_back_dfs on a D2Q9 lattice."""

    def test_read_count(self):
        stencils = _extract(_D2Q9_BOUNCE_BACK_PROGRAM)
        bb = stencils.blocks['BB']
        assert len(bb.reads) == 9

    def test_reads_are_the_guarded_neighbours(self):
        """Entry i reads the neighbour at (+EX[i], +EY[i]), guarded at
        the edge of the non-periodic grid."""
        stencils = _extract(_D2Q9_BOUNCE_BACK_PROGRAM)
        bb = stencils.blocks['BB']
        for i, r in enumerate(bb.reads):
            assert r.spatial_offsets == (_D2Q9_EX[i], _D2Q9_EY[i])
            assert r.guarded

    @pytest.mark.parametrize("df_idx,expected_opp",
                             list(_D2Q9_OPPOSITE_MAP.items()))
    def test_opposite_df_index(self, df_idx, expected_opp):
        """Verify DF index mapping: for output DF i, input reads opp(i)."""
        stencils = _extract(_D2Q9_BOUNCE_BACK_PROGRAM)
        reads = stencils.blocks['BB'].reads
        # The i-th StencilAccess corresponds to output DF i
        # and reads from input DF opp(i)
        assert reads[df_idx].df_index == expected_opp


# ---------------------------------------------------------------------------
# D3Q19 upstream_dfs
# ---------------------------------------------------------------------------

_D3Q19_PROGRAM = '''\
simulation_description("D3Q19 upstream_dfs test");
global_constants {
    const int N = 8;
    const array[real, 19] EX = {0.0,  1.0, -1.0, 0.0, 0.0, 0.0, 0.0,
        1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 0.0, 0.0, 0.0, 0.0};
    const array[real, 19] EY = {0.0,  0.0, 0.0, 1.0, -1.0, 0.0, 0.0,
        1.0, -1.0, -1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, -1.0, 1.0, -1.0};
    const array[real, 19] EZ = {0.0,  0.0, 0.0, 0.0, 0.0, 1.0, -1.0,
        0.0, 0.0, 0.0, 0.0, 1.0, -1.0, -1.0, 1.0, 1.0, -1.0, -1.0, 1.0};
    const array[real, 19] W = {1.0/3.0,
        1.0/18.0, 1.0/18.0, 1.0/18.0, 1.0/18.0, 1.0/18.0, 1.0/18.0,
        1.0/36.0, 1.0/36.0, 1.0/36.0, 1.0/36.0, 1.0/36.0, 1.0/36.0,
        1.0/36.0, 1.0/36.0, 1.0/36.0, 1.0/36.0, 1.0/36.0, 1.0/36.0};
}
lattices { lattice f(3, 19, real, {N, N, N}, {true, true, true}); }
initializer Init { f.out[x, y, z | :] = W; }
dynamic Dyn {
    array[real, 19] fIn = upstream_dfs(f, x, y, z, {EX, EY, EZ});
    f.out[x, y, z | :] = fIn;
}
gauge G -> (real rho) { rho = sum(f.in[x, y, z | :]); }
node_classes { node_class BULK(Init, Dyn, G); }
geometry { nodes[:,:,:] = BULK; }
'''


class TestUpstreamDfsD3Q19:
    """Stencil accuracy for upstream_dfs on a D3Q19 lattice."""

    def test_read_count(self):
        stencils = _extract(_D3Q19_PROGRAM)
        dyn = stencils.blocks['Dyn']
        assert len(dyn.reads) == 19

    def test_df0_local(self):
        """DF 0 (rest): offset (0, 0, 0)"""
        stencils = _extract(_D3Q19_PROGRAM)
        reads = stencils.blocks['Dyn'].reads
        r0 = [r for r in reads if r.df_index == 0]
        assert len(r0) == 1
        assert r0[0].spatial_offsets == (0, 0, 0)

    def test_df1_pull(self):
        """DF 1 (c=(1,0,0)): pull from (-1,0,0)"""
        stencils = _extract(_D3Q19_PROGRAM)
        reads = stencils.blocks['Dyn'].reads
        r1 = [r for r in reads if r.df_index == 1]
        assert len(r1) == 1
        assert r1[0].spatial_offsets == (-1, 0, 0)

    def test_df7_pull_diagonal(self):
        """DF 7 (c=(1,1,0)): pull from (-1,-1,0)"""
        stencils = _extract(_D3Q19_PROGRAM)
        reads = stencils.blocks['Dyn'].reads
        r7 = [r for r in reads if r.df_index == 7]
        assert len(r7) == 1
        assert r7[0].spatial_offsets == (-1, -1, 0)

    def test_df11_pull_3d(self):
        """DF 11 (c=(1,0,1)): pull from (-1,0,-1)"""
        stencils = _extract(_D3Q19_PROGRAM)
        reads = stencils.blocks['Dyn'].reads
        r11 = [r for r in reads if r.df_index == 11]
        assert len(r11) == 1
        assert r11[0].spatial_offsets == (-1, 0, -1)

    def test_all_offsets_3d(self):
        """All 19 DFs should have distinct offset vectors."""
        stencils = _extract(_D3Q19_PROGRAM)
        offsets = stencils.blocks['Dyn'].read_offsets
        assert len(offsets) == 19


# ---------------------------------------------------------------------------
# False warning elimination
# ---------------------------------------------------------------------------

class TestNoFalseWriteOnlyWarning:
    """upstream_dfs/bounce_back_dfs should prevent the 'never reads f.in' warning."""

    def test_upstream_dfs_no_warning(self):
        stencils = _extract(_D2Q9_PROGRAM)
        warnings = warn_writeonly_dynamics(stencils)
        assert warnings == []

    def test_bounce_back_dfs_no_warning(self):
        stencils = _extract(_D2Q9_BOUNCE_BACK_PROGRAM)
        warnings = warn_writeonly_dynamics(stencils)
        assert warnings == []
