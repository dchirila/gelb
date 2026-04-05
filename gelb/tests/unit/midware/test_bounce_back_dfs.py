"""Guarded stencil extraction and coverage, including the fallback path."""

import pytest

from gelb.midware.geometry import resolve_geometry
from gelb.midware.stage2_midware import (
    extract_stencils, validate_boundary_access, validate_cross_nc_df_coverage,
)
from gelb.tests.unit.midware.test_stencil_arg_validation import _validate
from gelb.utils.exceptions import GeLBExStencilError

PROGRAM = """
simulation_description("bounce-back coverage");
global_constants { const array[real, 3] EX = {0.0, 1.0, -1.0}; }
lattices { lattice f(1, 3, real, 7, false); }
initializer I { f.out[x | :] = {1.0, 2.0, 3.0}; }
dynamic D { f.out[x | :] = bounce_back_dfs(f, x, EX); }
gauge G -> (real value) { value = f.in[x | 0]; }
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
"""


def checked(source):
    ast = _validate(source)
    stencils = extract_stencils(ast)
    geometry = resolve_geometry(ast)
    validate_boundary_access(stencils, geometry)
    validate_cross_nc_df_coverage(stencils, geometry)
    return stencils


def test_neighbour_reads_are_guarded():
    stencils = checked(PROGRAM)
    assert {(r.spatial_offsets, r.df_index, r.guarded)
            for r in stencils.blocks["D"].reads} == {
                ((0,), 0, True), ((1,), 2, True), ((-1,), 1, True)}


def test_upstream_is_still_rejected_at_grid_edge():
    with pytest.raises(GeLBExStencilError, match="Out-of-bounds"):
        checked(PROGRAM.replace("bounce_back_dfs", "upstream_dfs"))


@pytest.mark.parametrize("replacement,match", [
    ("bounce_back_dfs(f, x + 1, EX)", "must be x itself"),
    ("bounce_back_dfs(f, x, x, EX)", "expects lattice"),
    ("bounce_back_dfs(f, x, {EX, EX})", "expects 1 velocity"),
])
def test_invalid_arguments(replacement, match):
    with pytest.raises(GeLBExStencilError, match=match):
        checked(PROGRAM.replace("bounce_back_dfs(f, x, EX)", replacement))


@pytest.mark.parametrize("velocities,match", [
    ("0.0, 1.5, -1.0", "not integer-valued"),
    ("0.0, 1.0, -2.0", "no opposite"),
])
def test_invalid_velocities(velocities, match):
    with pytest.raises(GeLBExStencilError, match=match):
        checked(PROGRAM.replace("0.0, 1.0, -1.0", velocities))


@pytest.mark.parametrize("missing", ["initial", "recurring"])
def test_fallback_requires_defined_local_df(missing):
    # At x=0, the -1 link falls back to local DF 1. No in-grid
    # neighbour read from B reaches B's DF 1, so only the guard's
    # fallback can expose this hole.
    source = PROGRAM.replace("nodes[:] = B;", "nodes[:] = S; nodes[0] = B;")
    source = source.replace("node_class B(I, D, G);",
                            "node_class B(I, D, G); node_class S(Full, G);")
    source = source.replace("initializer I", "initializer Full")
    source = source.replace("dynamic D", "initializer I { f.out[x | 0] = 1.0; f.out[x | 2] = 3.0; }\ndynamic D")
    if missing == "recurring":
        source = source.replace("node_class B(I, D, G)", "node_class B(Full, D, G)")
        # Keep a guarded read in the gauge while the dynamic omits DF 1.
        source = source.replace("f.out[x | :] = bounce_back_dfs(f, x, EX);",
                                "f.out[x | 0] = 1.0; f.out[x | 2] = 3.0;")
        source = source.replace("value = f.in[x | 0];",
                                "array[real, 3] bb = bounce_back_dfs(f, x, EX); value = sum(bb);")
    with pytest.raises(GeLBExStencilError, match=r"DF\(s\) \[1\]"):
        checked(source)


def test_guarded_neighbour_reads_still_require_coverage():
    source = PROGRAM.replace("nodes[:] = B;", "nodes[:] = S; nodes[0] = B;")
    source = source.replace("node_class B(I, D, G);",
                            "node_class B(I, D, G); node_class S(Partial, G);")
    source = source.replace("dynamic D", "initializer Partial { f.out[x | 0] = 1.0; f.out[x | 1] = 2.0; }\ndynamic D")
    with pytest.raises(GeLBExStencilError, match="never writes DF"):
        checked(source)


def test_guarded_read_does_not_require_unused_local_slots():
    source = PROGRAM.replace("nodes[:] = B;", "nodes[:] = S; nodes[3] = B;")
    source = source.replace("node_class B(I, D, G);",
                            "node_class B(Partial, D, G); node_class S(I, G);")
    source = source.replace("dynamic D", "initializer Partial { f.out[x | 0] = 1.0; }\ndynamic D")
    checked(source)  # Only the rest slot is read locally; moving slots read S.


def test_links_beyond_nonperiodic_domain_read_only_locally():
    checked(PROGRAM.replace("0.0, 1.0, -1.0", "0.0, 30.0, -30.0"))
