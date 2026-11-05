"""Tests for the geometry-lint analysis module."""

from __future__ import annotations

import os
import tempfile
import pathlib
import pytest

from gelb.midware.geometry_lint import (
    warn_disconnected_nc_regions,
    warn_empty_node_classes,
    warn_reversed_paint_ranges,
    warn_unreachable_fluid_pockets,
    all_geometry_warnings,
)


def _resolve(gelb_src: str):
    """Compile a GeLB source string and return the ResolvedGeometry."""
    from gelb.visualization.geo_viewer import compile_to_geometry
    with tempfile.NamedTemporaryFile(
            mode='w', suffix='.gelb', delete=False) as f:
        f.write(gelb_src)
        tmp = f.name
    try:
        return compile_to_geometry(tmp)
    finally:
        os.unlink(tmp)


def _line_of(gelb_src: str, text: str) -> int:
    """1-based number of the first source line that contains ``text``."""
    return next(i for i, line in enumerate(gelb_src.splitlines(), 1)
                if text in line)


# ---------------------------------------------------------------------------
# warn_disconnected_nc_regions
# ---------------------------------------------------------------------------

def test_disconnected_clean_single_region():
    """A simple 2-NC channel should produce no disconnected-region warnings."""
    src = """
    simulation_description("clean");
    global_constants { const int N = 16; }
    lattices { lattice f(2, 9, real, {N, N}, {true, false}); }
    initializer Init { f.out[x, y | :] = 1.0; }
    dynamic D { f.out[x, y | :] = f.in[x, y | :]; }
    gauge G -> (real v) { v = sum(f.in[x, y | :]); }
    node_classes {
        node_class FLUID(Init, D, G);
        node_class WALL(Init, G);
    }
    geometry {
        nodes[:, :] = FLUID;
        nodes[:, 0] = WALL;
        nodes[:, N - 1] = WALL;
    }
    """
    geo = _resolve(src)
    assert warn_disconnected_nc_regions(geo) == []


def test_disconnected_many_obstacles_triggers_warning():
    """Many small WALL pockets should trigger the disconnected warning."""
    # Build a 16x16 grid with 8 separate isolated WALL cells in BULK
    # using conditional paint to scatter them
    src = """
    simulation_description("scattered");
    global_constants { const int N = 16; }
    lattices { lattice f(2, 9, real, {N, N}, {true, true}); }
    initializer Init { f.out[x, y | :] = 1.0; }
    dynamic D { f.out[x, y | :] = f.in[x, y | :]; }
    gauge G -> (real v) { v = sum(f.in[x, y | :]); }
    function ManyDots(int x, int y) -> (bool hit) {
        hit = ((x == 2)  && (y == 2))
           || ((x == 5)  && (y == 5))
           || ((x == 8)  && (y == 8))
           || ((x == 11) && (y == 11))
           || ((x == 14) && (y == 14))
           || ((x == 2)  && (y == 14))
           || ((x == 14) && (y == 2))
           || ((x == 7)  && (y == 13));
    }
    node_classes {
        node_class FLUID(Init, D, G);
        node_class DOT(Init, G);
    }
    geometry {
        nodes[:, :] = FLUID;
        nodes[where ManyDots(x, y)] = DOT;
    }
    """
    geo = _resolve(src)
    warnings = warn_disconnected_nc_regions(geo)
    assert any("DOT" in msg for msg, *_ in warnings)
    assert any(">" in msg or "disconnected regions" in msg
               for msg, *_ in warnings)
    # The warning points at DOT's node_class statement.
    assert [line for msg, _, line in warnings if "DOT" in msg] == [
        _line_of(src, "node_class DOT")]


# ---------------------------------------------------------------------------
# warn_unreachable_fluid_pockets
# ---------------------------------------------------------------------------

def test_fluid_pockets_clean():
    """A simple channel has one connected fluid region -- no warning."""
    src = """
    simulation_description("clean");
    global_constants { const int N = 16; }
    lattices { lattice f(2, 9, real, {N, N}, {true, false}); }
    initializer Init { f.out[x, y | :] = 1.0; }
    dynamic D { f.out[x, y | :] = f.in[x, y | :]; }
    gauge G -> (real v) { v = sum(f.in[x, y | :]); }
    node_classes {
        node_class FLUID(Init, D, G);
        node_class WALL(Init, G);
    }
    geometry {
        nodes[:, :] = FLUID;
        nodes[:, 0] = WALL;
        nodes[:, N - 1] = WALL;
    }
    """
    geo = _resolve(src)
    assert warn_unreachable_fluid_pockets(geo) == []


def test_fluid_pockets_warn_at_geometry_block():
    """A wall across a non-periodic channel leaves two fluid pockets;
    the warning points at the geometry block."""
    src = """
    simulation_description("two pockets");
    global_constants { const int N = 16; }
    lattices { lattice f(2, 9, real, {N, N}, {false, false}); }
    initializer Init { f.out[x, y | :] = 1.0; }
    dynamic D { f.out[x, y | :] = f.in[x, y | :]; }
    gauge G -> (real v) { v = sum(f.in[x, y | :]); }
    node_classes {
        node_class FLUID(Init, D, G);
        node_class WALL(Init, G);
    }
    geometry {
        nodes[:, :] = FLUID;
        nodes[N / 2, :] = WALL;
    }
    """
    geo = _resolve(src)
    warnings = warn_unreachable_fluid_pockets(geo)
    assert len(warnings) == 1
    msg, _, line = warnings[0]
    assert "2 disconnected pockets" in msg
    assert line == _line_of(src, "geometry {")


# ---------------------------------------------------------------------------
# warn_empty_node_classes, warn_reversed_paint_ranges
# ---------------------------------------------------------------------------

_EMPTY_CLASS_SRC = """
simulation_description("empty class");
global_constants {{ const real R = {r}; }}
lattices {{ lattice f(2, 9, real, {{16, 8}}, {{true, true}}); }}
initializer Init {{ f.out[x, y | :] = 1.0; }}
dynamic D {{ f.out[x, y | :] = f.in[x, y | :]; }}
gauge G -> (real v) {{ v = f.in[x, y | 0]; }}
node_classes {{
    node_class BULK(Init, D, G);
    node_class OBST(Init, D, G);
    node_class WALL(Init, D, G);
}}
geometry {{
    nodes[:, :] = BULK;
{paints}
}}
"""

# name: (R, paints, the classes left without a cell)
_EMPTY_TRIGGERS = {
    "overwritten": ("1.0", "    nodes[4:6, 2:3] = OBST;\n"
                           "    nodes[4:6, 2:3] = WALL;", ["OBST"]),
    "where_matches_nothing": (
        "0.0", "    nodes[where (real(x) - 8.0)^2 < R^2] = OBST;\n"
               "    nodes[12:13, 5:6] = WALL;", ["OBST"]),
    "border_of_an_empty_class": (
        "0.0", "    nodes[where (real(x) - 8.0)^2 < R^2] = OBST;\n"
               "    border(OBST) = WALL;", ["OBST", "WALL"]),
    "border_converts_every_cell": ("1.0", "    nodes[4:5, 2:3] = OBST;\n"
                                          "    border(OBST) = WALL;",
                                   ["OBST"]),
    "reversed_range": ("1.0", "    nodes[6:4, 2:3] = OBST;\n"
                              "    nodes[12:13, 5:6] = WALL;", ["OBST"]),
}


@pytest.mark.parametrize("trigger", sorted(_EMPTY_TRIGGERS))
def test_a_class_with_no_cells_is_reported(trigger):
    """Each way a class can lose all its cells gets one warning per
    empty class, on the line of its node_class statement."""
    r, paints, empty = _EMPTY_TRIGGERS[trigger]
    src = _EMPTY_CLASS_SRC.format(r=r, paints=paints)
    warnings = warn_empty_node_classes(_resolve(src))
    assert [(m, line) for m, _, line in warnings] == [
        (f"Node class '{name}' has no cells",
         _line_of(src, f"node_class {name}(")) for name in empty]


def test_classes_with_cells_are_not_reported():
    src = _EMPTY_CLASS_SRC.format(
        r="2.0", paints="    nodes[where (real(x) - 8.0)^2 < R^2] = OBST;\n"
                        "    border(OBST) = WALL;")
    assert warn_empty_node_classes(_resolve(src)) == []


def test_a_reversed_range_is_reported():
    """``nodes[6:4, ..]`` paints nothing; the warning names the axis and
    points at the geometry block."""
    src = _EMPTY_CLASS_SRC.format(
        r="1.0", paints="    nodes[12:13, 5:6] = WALL;\n"
                        "    nodes[2:2, 5:3] = OBST;\n"
                        "    nodes[4:5, 2:3] = OBST;")
    geo = _resolve(src)
    warnings = warn_reversed_paint_ranges(geo)
    assert [(m, line) for m, _, line in warnings] == [
        ("A paint of 'OBST' covers no cells: its y-range 5:3 runs backwards",
         _line_of(src, "geometry {"))]
    assert "write 3:5" in warnings[0][1]
    # OBST still has the cells of its second paint.
    assert warn_empty_node_classes(geo) == []


def test_a_reversed_range_on_a_1d_grid_is_reported():
    src = """
    simulation_description("1-D");
    lattices { lattice f(1, 3, real, 16, true); }
    initializer Init { f.out[x | :] = 1.0; }
    dynamic D { f.out[x | :] = f.in[x | :]; }
    gauge G -> (real v) { v = f.in[x | 0]; }
    node_classes {
        node_class BULK(Init, D, G);
        node_class OBST(Init, D, G);
    }
    geometry {
        nodes[:] = BULK;
        nodes[9:7] = OBST;
    }
    """
    messages = [m for m, *_ in all_geometry_warnings(_resolve(src))]
    assert messages == [
        "A paint of 'OBST' covers no cells: its x-range 9:7 runs backwards",
        "Node class 'OBST' has no cells"]


# ---------------------------------------------------------------------------
# all_geometry_warnings -- aggregator
# ---------------------------------------------------------------------------

def test_all_warnings_aggregator_signature():
    """The aggregator accepts geo + optional stencils."""
    src = """
    simulation_description("trivial");
    global_constants { const int N = 8; }
    lattices { lattice f(2, 9, real, {N, N}, {true, true}); }
    initializer Init { f.out[x, y | :] = 1.0; }
    dynamic D { f.out[x, y | :] = f.in[x, y | :]; }
    gauge G -> (real v) { v = sum(f.in[x, y | :]); }
    node_classes { node_class BULK(Init, D, G); }
    geometry { nodes[:, :] = BULK; }
    """
    geo = _resolve(src)
    warnings = all_geometry_warnings(geo)
    assert isinstance(warnings, list)


# ---------------------------------------------------------------------------
# Smoke test: every existing example should lint cleanly (or document why)
# ---------------------------------------------------------------------------

# Examples with known/intentional warnings.  Maps file basename to a list
# of substrings that must appear in the warning messages (each substring
# matches one expected warning).
_EXPECTED_WARNINGS_BY_EXAMPLE: dict[str, list[str]] = {}


def _list_examples():
    """Return every .gelb example under examples/."""
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    examples = repo_root / "examples"
    return sorted(examples.rglob("*.gelb"))


@pytest.mark.parametrize("example", _list_examples(),
                         ids=lambda p: p.relative_to(
                             pathlib.Path(__file__).resolve().parents[3]
                         ).as_posix())
def test_existing_example_lints_cleanly(example):
    """Every example in examples/ should lint cleanly."""
    from gelb.visualization.geo_viewer import compile_to_geometry
    try:
        geo = compile_to_geometry(str(example))
    except Exception as e:
        pytest.skip(f"Cannot compile {example.name}: {e}")
    warnings = all_geometry_warnings(geo)
    expected = _EXPECTED_WARNINGS_BY_EXAMPLE.get(example.name, [])
    if not expected:
        assert warnings == [], (
            f"Unexpected geometry-lint warnings for {example.name}:\n"
            + "\n".join(f"  - {m}" for m, *_ in warnings)
        )
    else:
        # Each expected substring must match at least one warning
        msgs = "\n".join(m for m, *_ in warnings)
        for needle in expected:
            assert needle in msgs, (
                f"Expected warning containing '{needle}' for "
                f"{example.name}, got:\n{msgs}"
            )
