#!/usr/bin/env python3
"""
Predicate paints: ``nodes[where <bool expression>] = CLASS;``

The expression sees the implicit coordinates (x; x, y; x, y, z, by rank),
constants, dimension constants and pure single-output user functions, and
is evaluated at compile time for every cell.  These tests cover parsing in
every rank, the resolved class map for overlapping paints and borders,
the evaluator's contract (composed calls, conversions, source-ordered
assignments) and every rejection path with its diagnostic, plus the
Fortran replay of the map in source order (Fortran once replayed the
predicate paints after every rectangular paint, so a later rectangular
override was lost).
"""

import json

import numpy as np
import pytest
from click.testing import CliRunner

from gelb.compiler_pipeline import (
    PipelineOptions, PipelineProfile, compile_source)
from gelb.gelb_ast.ASTNodes import ConditionalPaintStmt_N
from gelb.gelbc import cli as gelbc_cli
from gelb.midware.program_analysis import compile_to_program_analysis
from gelb.tests.test_utils import get_typed_ast
from gelb.utils.exceptions import (
    GeLBExFunctionRecursion, GeLBExStencilError, GeLBExSymbolNotAllowedHere,
    GeLBExSymbolUnknown, GeLBExSyntaxError, GeLBExTypeError)


def _program_2d(functions="", geometry="", nx=10, ny=10,
                periodic="false, false", extra_blocks="", extra_constants=""):
    return f"""
    simulation_description("test");
    global_constants {{ const int CX = 5; const int CY = 5; const int R = 3;
                        const array[real, 3] W3 = {{0.5, 0.25, 0.25}};
                        {extra_constants} }}
    lattices {{ lattice f(2, 1, int, {{{nx}, {ny}}}, {{{periodic}}}); }}
    {functions}
    initializer InitA {{ f.out[x, y | 0] = 0; }}
    initializer InitB {{ f.out[x, y | 0] = 1; }}
    dynamic DynA {{ f.out[x, y | 0] = f.in[x, y | 0]; }}
    dynamic DynB {{ f.out[x, y | 0] = f.in[x, y | 0]; }}
    gauge OutA -> (int val) {{ val = f.in[x, y | 0]; }}
    gauge OutB -> (int val) {{ val = f.in[x, y | 0]; }}
    {extra_blocks}
    node_classes {{
        node_class FLUID(InitA, DynA, OutA);
        node_class WALL(InitB, DynB, OutB);
        node_class SOLID() masked;
    }}
    geometry {{
        nodes[:, :] = FLUID;
        {geometry}
    }}
    """


def _program_1d(geometry, n=8):
    return f"""
    simulation_description("test");
    lattices {{ lattice f(1, 1, int, {n}, false); }}
    initializer Init {{ f.out[x | 0] = 0; }}
    dynamic Dyn {{ f.out[x | 0] = f.in[x | 0]; }}
    gauge Out -> (int val) {{ val = f.in[x | 0]; }}
    node_classes {{ node_class FLUID(Init, Dyn, Out); node_class SOLID() masked; }}
    geometry {{ nodes[:] = FLUID; {geometry} }}
    """


def _program_3d(geometry, n=4):
    return f"""
    simulation_description("test");
    lattices {{ lattice f(3, 1, int, {{{n}, {n}, {n}}}, {{false, false, false}}); }}
    initializer Init {{ f.out[x, y, z | 0] = 0; }}
    dynamic Dyn {{ f.out[x, y, z | 0] = f.in[x, y, z | 0]; }}
    gauge Out -> (int val) {{ val = f.in[x, y, z | 0]; }}
    node_classes {{ node_class FLUID(Init, Dyn, Out); node_class SOLID() masked; }}
    geometry {{ nodes[:, :, :] = FLUID; {geometry} }}
    """


CIRCLE = """
    function InCircle(int x, int y, int cx, int cy, int r) -> (bool hit) {
        hit = (x - cx)*(x - cx) + (y - cy)*(y - cy) < r*r;
    }
"""


def _resolve(code):
    """Resolved geometry of ``code`` (raises the GeLB diagnostic if any)."""
    result = compile_source(
        code, PipelineProfile.DIAGNOSTICS,
        PipelineOptions(require_stencils=True, require_geometry=True))
    return result.geometry


def _cells(geo, name):
    """Set of coordinate tuples painted ``name``; nc_map is indexed [x, y, z]."""
    if name not in geo.nc_info:
        return set()
    return {tuple(int(c) for c in idx)
            for idx in np.argwhere(geo.nc_map == geo.nc_info[name].nc_id)}


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

class TestParsing:

    def test_where_paint_becomes_a_predicate_statement(self):
        ast = get_typed_ast(_program_2d(geometry="nodes[where x < 5] = SOLID;"))
        cond = [s for s in ast.geometry.stmts.elements
                if isinstance(s, ConditionalPaintStmt_N)]
        assert len(cond) == 1
        assert cond[0].node_class.name == 'SOLID'
        assert cond[0].predicate is not None
        assert 'where' in str(cond[0])

    def test_where_paint_in_1d_and_3d(self):
        geo = _resolve(_program_1d("nodes[where x >= 6] = SOLID;"))
        assert _cells(geo, 'SOLID') == {(6,), (7,)}
        geo = _resolve(_program_3d("nodes[where x == 0 && y == 0 && z >= 2] = SOLID;"))
        assert _cells(geo, 'SOLID') == {(0, 0, 2), (0, 0, 3)}

    def test_point_paint_still_takes_constant_indices(self):
        geo = _resolve(_program_2d(geometry="nodes[3, 4] = SOLID; nodes[CX, CY] = WALL;"))
        assert _cells(geo, 'SOLID') == {(3, 4)}
        assert _cells(geo, 'WALL') == {(5, 5)}

    def test_legacy_placeholder_form_is_a_syntax_error_with_a_hint(self):
        with pytest.raises(GeLBExSyntaxError) as info:
            get_typed_ast(_program_2d(
                functions=CIRCLE,
                geometry="nodes[InCircle(:, :, CX, CY, R)] = SOLID;"))
        assert 'nodes[where' in str(info.value)

    def test_reserved_words_cannot_be_identifiers(self):
        for word in ('where', 'enter', 'leave', 'reduce', 'reduction',
                     'update', 'global_variables', 'transition', 'zone'):
            with pytest.raises(GeLBExSyntaxError) as info:
                get_typed_ast(_program_2d(
                    functions=f"function {word}(int x, int y) -> (bool b) {{ b = x < 1; }}",
                    geometry=f"nodes[where {word}(x, y)] = SOLID;"))
            assert 'reserved keyword' in str(info.value)


# --------------------------------------------------------------------------
# Resolved maps
# --------------------------------------------------------------------------

class TestResolvedMap:

    def test_circle_matches_an_independent_computation(self):
        geo = _resolve(_program_2d(
            functions=CIRCLE,
            geometry="nodes[where InCircle(x, y, CX, CY, R)] = SOLID;"))
        expected = {(x, y) for x in range(10) for y in range(10)
                    if (x - 5) ** 2 + (y - 5) ** 2 < 9}
        assert _cells(geo, 'SOLID') == expected
        assert len(expected) == 25

    def test_plain_expression_without_a_function(self):
        geo = _resolve(_program_2d(geometry="nodes[where x < 2 && !(y == 0)] = SOLID;"))
        assert _cells(geo, 'SOLID') == {(x, y) for x in range(2) for y in range(1, 10)}

    def test_later_point_paint_overrides_an_earlier_predicate(self):
        # The resolved map must honour source order: Fortran once replayed
        # the predicate paints after every rectangular paint, so a later
        # rectangular override was lost.
        geo = _resolve(_program_2d(
            geometry="nodes[where x < 2] = WALL; nodes[1, 1] = FLUID;",
            nx=4, ny=3))
        assert _cells(geo, 'WALL') == {(0, 0), (0, 1), (0, 2), (1, 0), (1, 2)}
        assert (1, 1) in _cells(geo, 'FLUID')

    def test_later_predicate_overrides_an_earlier_rectangle(self):
        geo = _resolve(_program_2d(
            geometry="nodes[0:3, :] = WALL; nodes[where x == 1] = SOLID;",
            nx=4, ny=3))
        assert _cells(geo, 'SOLID') == {(1, 0), (1, 1), (1, 2)}
        assert _cells(geo, 'WALL') == {(0, y) for y in range(3)} | {(2, y) for y in range(3)} | {(3, y) for y in range(3)}

    def test_border_repaints_the_inner_boundary_after_all_paints(self):
        # The border is written between the two paints but applies to the
        # final painted region: the 3x3 block plus the extra column.
        geo = _resolve(_program_2d(
            geometry="nodes[where x >= 4 && x <= 6 && y >= 4 && y <= 6] = SOLID;"
                     " border(SOLID) = WALL;"
                     " nodes[7, 4:6] = SOLID;"))
        # (6, 5) is interior after the later paint: all eight neighbours are SOLID.
        assert _cells(geo, 'SOLID') == {(5, 5), (6, 5)}
        block = {(x, y) for x in range(4, 8) for y in range(4, 7)}
        assert _cells(geo, 'WALL') == block - {(5, 5), (6, 5)}

    def test_borders_apply_in_source_order_and_see_each_other(self):
        code = _program_2d(
            geometry="nodes[where x >= 3 && x <= 7 && y >= 3 && y <= 7] = SOLID;"
                     " border(SOLID) = WALL; border(WALL) = FLUID;")
        geo = _resolve(code)
        # first border: the 5x5 block's ring becomes WALL, the 3x3 core stays SOLID
        # second border: every WALL cell touches FLUID or SOLID, so all become FLUID
        assert _cells(geo, 'WALL') == set()
        assert _cells(geo, 'SOLID') == {(x, y) for x in range(4, 7) for y in range(4, 7)}

    def test_border_ignores_off_grid_neighbours_on_nonperiodic_axis(self):
        # Two full SOLID rows at the bottom of a grid periodic in x: the
        # y=0 row has no in-domain neighbour of another class (y=-1 is
        # off-grid, x wraps to SOLID anyway), so only the y=1 row is a border.
        geo = _resolve(_program_2d(
            geometry="nodes[where y <= 1] = SOLID; border(SOLID) = WALL;",
            periodic="true, false"))
        assert _cells(geo, 'SOLID') == {(x, 0) for x in range(10)}
        assert _cells(geo, 'WALL') == {(x, 1) for x in range(10)}

    def test_border_repaints_a_thin_block_completely(self):
        # A 2x2 block: every cell has a neighbour outside it.
        geo = _resolve(_program_2d(
            geometry="nodes[where x >= 4 && x <= 5 && y >= 4 && y <= 5] = SOLID;"
                     " border(SOLID) = WALL;"))
        assert _cells(geo, 'SOLID') == set()
        assert _cells(geo, 'WALL') == {(4, 4), (4, 5), (5, 4), (5, 5)}


# --------------------------------------------------------------------------
# The compile-time evaluator's contract
# --------------------------------------------------------------------------

class TestEvaluator:

    def test_composed_functions_and_numeric_conversions(self):
        geo = _resolve(_program_2d(
            functions=CIRCLE + """
            function Big(int x, int y) -> (bool b) {
                real d = real(x) / 2.0;
                b = InCircle(x, y, 3, 3, 2) || d > 2.5;
            }""",
            geometry="nodes[where Big(x, y)] = SOLID;"))
        expected = {(x, y) for x in range(10) for y in range(10)
                    if (x - 3) ** 2 + (y - 3) ** 2 < 4 or x / 2.0 > 2.5}
        assert _cells(geo, 'SOLID') == expected

    def test_assignments_run_in_source_order_and_the_last_output_wins(self):
        geo = _resolve(_program_2d(
            functions="function Last(int x, int y) -> (bool b) { b = true; b = x > 100; }",
            geometry="nodes[where Last(x, y)] = SOLID;"))
        assert _cells(geo, 'SOLID') == set()
        geo = _resolve(_program_2d(
            functions="function Acc(int x, int y) -> (bool b) { int s = x; s = s + y; b = s == 3; }",
            geometry="nodes[where Acc(x, y)] = SOLID;"))
        assert _cells(geo, 'SOLID') == {(x, y) for x in range(10) for y in range(10) if x + y == 3}

    def test_integer_division_truncates_toward_zero(self):
        geo = _resolve(_program_2d(geometry="nodes[where (x - 5) / 2 == -1 && y == 0] = SOLID;"))
        # x - 5 in {-3, -2} gives -1 with truncation (floor would add -4 too)
        assert _cells(geo, 'SOLID') == {(2, 0), (3, 0)}

    def test_scalar_intrinsics_constant_arrays_and_dimension_constants(self):
        geo = _resolve(_program_2d(
            geometry="nodes[where abs(x - 4) + abs(y - 4) <= 1] = SOLID;"
                     " nodes[where W3[1] < 0.3 && mod(x, 3) == 0 && y == Ny - 1] = WALL;"))
        assert _cells(geo, 'SOLID') == {(4, 4), (3, 4), (5, 4), (4, 3), (4, 5)}
        assert _cells(geo, 'WALL') == {(0, 9), (3, 9), (6, 9), (9, 9)}

    def test_conversions_keep_their_declared_width(self):
        # A real32 has 24 significand bits: 16777217 rounds to 16777216
        # and 16777218 is exact, so the Fortran expression is true at
        # x = 0 and x = 1.
        geo = _resolve(_program_2d(
            geometry="nodes[where real32(x + 16777216) == real32(16777216) && y == 0] = SOLID;"))
        assert _cells(geo, 'SOLID') == {(0, 0), (1, 0)}
        # (real16, with 11 bits, is not in this version: the parser
        # rejects it.)
        # narrowing an integer wraps
        geo = _resolve(_program_2d(
            geometry="nodes[where int32(x + 2147483647) < 0 && y == 0] = SOLID;"))
        assert _cells(geo, 'SOLID') == {(x, 0) for x in range(1, 10)}
        # the default widths are unchanged: a real is double precision
        geo = _resolve(_program_2d(
            geometry="nodes[where real(x + 16777216) == real(16777216) && y == 0] = SOLID;"))
        assert _cells(geo, 'SOLID') == {(0, 0)}

    def test_typed_constants_and_folded_casts_keep_their_width(self):
        # The declared width survives constant folding, constant
        # propagation and array elements, in both declaration forms (it
        # was once lost between a declaration and its use).  Expected:
        # x = 0 and x = 1.
        for constants, predicate in (
            ("const array[real32, 2] A = {real32(16777217.0), real32(0.0)};",
             "real(A[0]) == real(real32(x + 16777216))"),
            ("const array[real32, 2] A = {16777217.0, 0.0};",
             "real(A[0]) == real(real32(x + 16777216))"),
            ("const real32 A = 16777217.0;",
             "real(A) == real(real32(x + 16777216))"),
            ("", "real(real32(16777217)) == real(real32(x + 16777216))"),
            ("const real32 A = 16777216.0; const real32 B = A + 1.0;",
             "real(B) == real(real32(x + 16777216))"),
        ):
            geo = _resolve(_program_2d(
                extra_constants=constants,
                geometry=f"nodes[where {predicate} && y == 0] = SOLID;"))
            assert _cells(geo, 'SOLID') == {(0, 0), (1, 0)}, (constants, predicate)
        # an int32 constant wraps where a 64-bit int would not
        geo = _resolve(_program_2d(
            extra_constants="const int32 TOP = 2147483647;",
            geometry="nodes[where int32(TOP + x) < 0 && y == 0] = SOLID;"))
        assert _cells(geo, 'SOLID') == {(x, 0) for x in range(1, 10)}

    def test_promotions_apply_before_a_predicate_is_folded(self):
        # A folder that reads a promoted operand's raw value, or
        # propagates a real constant written as an integer as an
        # integer, gets these wrong.  Every cell of row 0 is expected.
        row = {(x, 0) for x in range(10)}
        for constants, predicate in (
            ("", "16777217 == real32(16777216)"),
            ("", "16777217 - real32(16777216) == 0.0"),
            ("const array[real32, 2] ARR = {16777217, -16777216}; const real C = sum(ARR);",
             "C == 0.0"),
            ("const real P = 7; const real Q = 2; const real F = P / Q;", "F == 3.5"),
            # an array constant through arithmetic, and integer
            # division behind an integer-width promotion
            ("const array[real32, 2] ARR = {16777217.0, 0.0};"
             " const array[real, 2] WIDE = ARR + {0.0, 0.0}; const real C = sum(WIDE);",
             "C == 16777216.0"),
            ("const int VALUE = (int8(7) / int16(2)) * int16(2);", "VALUE == 6"),
            ("const int NEG = (int8(-7) / int16(2)) * int16(2);", "NEG == -6"),
            # an array initialized by an expression, and an alias
            ("const array[real32, 2] ARR = {16777216.0, 0.0} + {1.0, 0.0};"
             " const array[real, 2] WIDE = ARR + {0.0, 0.0}; const real C = sum(WIDE);",
             "C == 16777216.0"),
            ("const array[real, 2] BIG = {16777216.0, 0.0} + {1.0, 0.0};"
             " const array[real32, 2] ARR = BIG;"
             " const array[real, 2] WIDE = ARR + {0.0, 0.0}; const real C = sum(WIDE);",
             "C == 16777216.0"),
        ):
            geo = _resolve(_program_2d(
                extra_constants=constants,
                geometry=f"nodes[where {predicate} && y == 0] = SOLID;"))
            assert _cells(geo, 'SOLID') == row, (constants, predicate)

    def test_declared_widths_apply_inside_functions(self):
        # A parameter, a local and the arithmetic between them have the
        # width they are declared with.
        geo = _resolve(_program_2d(
            functions="""
            function Narrow(real32 v) -> (bool b) {
                real32 big = real32(16777216);
                b = v == big;
            }""",
            geometry="nodes[where Narrow(x + 16777216) && y == 0] = SOLID;"))
        assert _cells(geo, 'SOLID') == {(0, 0), (1, 0)}
        geo = _resolve(_program_2d(
            functions="""
            function Sum(int x, int y) -> (bool b) {
                real32 s = real32(x) + real32(16777216);
                b = s == real32(16777216) && y == 0;
            }""",
            geometry="nodes[where Sum(x, y)] = SOLID;"))
        assert _cells(geo, 'SOLID') == {(0, 0), (1, 0)}

    def test_function_local_t_and_class_name_shadowing_stay_legal(self):
        geo = _resolve(_program_2d(
            functions="function Ft(int t, int y) -> (bool b) { b = t == y; }",
            geometry="nodes[where Ft(x, y)] = SOLID;",
            extra_blocks="dynamic Shadow { int SOLID = 2; f.out[x, y | 0] = SOLID; }"))
        assert _cells(geo, 'SOLID') == {(i, i) for i in range(10)}


# --------------------------------------------------------------------------
# Rejections
# --------------------------------------------------------------------------

class TestRejections:

    def test_non_bool_predicate(self):
        with pytest.raises(GeLBExTypeError) as info:
            _resolve(_program_2d(geometry="nodes[where x + y] = SOLID;"))
        assert 'scalar bool' in str(info.value)

    def test_time_step_in_geometry(self):
        with pytest.raises(GeLBExSymbolNotAllowedHere) as info:
            _resolve(_program_2d(geometry="nodes[where x == t] = SOLID;"))
        assert 'time-dependent geometry is not supported' in str(info.value)

    def test_lattice_read_in_predicate(self):
        with pytest.raises(GeLBExTypeError) as info:
            _resolve(_program_2d(geometry="nodes[where f.in[x, y | 0] > 0] = SOLID;"))
        assert 'state-dependent geometry is not supported' in str(info.value)

    def test_coordinate_in_a_point_or_range_paint(self):
        with pytest.raises(GeLBExTypeError) as info:
            _resolve(_program_2d(geometry="nodes[x, 0] = SOLID;"))
        assert "only inside a 'where' predicate" in str(info.value)
        with pytest.raises(GeLBExTypeError):
            _resolve(_program_2d(geometry="nodes[0:x, 0] = SOLID;"))

    def test_random_in_a_called_function_even_behind_a_false_branch(self):
        for body in ("b = random() > 0.5;", "b = false && random() > 0.5;"):
            with pytest.raises(GeLBExTypeError) as info:
                _resolve(_program_2d(
                    functions=f"function Rnd(int x, int y) -> (bool b) {{ {body} }}",
                    geometry="nodes[where Rnd(x, y)] = SOLID;"))
            assert 'random()' in str(info.value)

    def test_array_intrinsic_in_predicate(self):
        with pytest.raises(GeLBExTypeError) as info:
            _resolve(_program_2d(geometry="nodes[where sum(W3) > 0.0] = SOLID;"))
        assert 'sum()' in str(info.value)

    def test_unknown_function_identifier_and_out_of_rank_coordinate(self):
        with pytest.raises(GeLBExTypeError):
            _resolve(_program_2d(geometry="nodes[where Nope(x, y)] = SOLID;"))
        with pytest.raises(GeLBExSymbolUnknown):
            _resolve(_program_2d(geometry="nodes[where x < NOPE] = SOLID;"))
        with pytest.raises(GeLBExSymbolUnknown):
            _resolve(_program_2d(geometry="nodes[where z == 0] = SOLID;"))
        with pytest.raises(GeLBExSymbolUnknown):
            _resolve(_program_1d("nodes[where y == 0] = SOLID;"))

    def test_wrong_arity_and_multi_output_functions(self):
        with pytest.raises(GeLBExTypeError):
            _resolve(_program_2d(functions=CIRCLE,
                                 geometry="nodes[where InCircle(x, y, 1)] = SOLID;"))
        with pytest.raises(GeLBExTypeError) as info:
            _resolve(_program_2d(
                functions="function Two(int x, int y) -> (bool a, bool b) { a = x < 1; b = y < 1; }",
                geometry="nodes[where Two(x, y)] = SOLID;"))
        assert 'exactly one' in str(info.value)

    def test_unknown_node_class(self):
        with pytest.raises(GeLBExSymbolUnknown):
            _resolve(_program_2d(geometry="nodes[where x < 1] = UNKNOWN;"))

    def test_recursive_predicate_function_is_rejected_in_every_profile(self, tmp_path):
        code = _program_2d(
            functions="function Loop(int n) -> (bool b) { b = Loop(n); }",
            geometry="nodes[where Loop(x)] = SOLID;")
        # codegen and diagnostics: the program-wide recursion check fires first
        with pytest.raises(GeLBExFunctionRecursion):
            _resolve(code)
        # the analysis profile (gelb-view) has no such pass; the evaluator
        # must report the cycle rather than recurse (Python RecursionError)
        path = tmp_path / "loop.gelb"
        path.write_text(code)
        with pytest.raises(GeLBExTypeError) as info:
            compile_to_program_analysis(path)
        assert "calls itself (Loop -> Loop)" in str(info.value)
        path.write_text(_program_2d(
            functions="function F(int n) -> (bool b) { b = G(n); }"
                      " function G(int n) -> (bool b) { b = F(n); }",
            geometry="nodes[where F(x)] = SOLID;"))
        with pytest.raises(GeLBExTypeError) as info:
            compile_to_program_analysis(path)
        assert "(F -> G -> F)" in str(info.value)

    def test_function_that_never_assigns_its_output(self):
        with pytest.raises(GeLBExStencilError) as info:
            _resolve(_program_2d(
                functions="function Never(int x, int y) -> (bool b) { int s = x; }",
                geometry="nodes[where Never(x, y)] = SOLID;"))
        assert 'does not assign its output' in str(info.value)


# --------------------------------------------------------------------------
# --diagnostics-json locations
# --------------------------------------------------------------------------

def _diagnostics(tmp_path, code):
    """Run gelbc --diagnostics-json; return (path, exit code, diagnostics)
    with each diagnostic's text (message plus hint) and its 1-based line."""
    path = tmp_path / "prog.gelb"
    path.write_text(code)
    result = CliRunner().invoke(gelbc_cli, [str(path), "--diagnostics-json"])
    payload = json.loads(result.output)
    diags = [{"severity": d.get("severity", "error"),
              "text": d.get("message", "") + " " + d.get("hint", ""),
              "line": d["range"]["startLine"] + 1}
             for d in payload["diagnostics"]]
    return path, result.exit_code, diags


def _line_of(path, text):
    return next(i for i, line in enumerate(path.read_text().splitlines(), 1)
                if text in line)


class TestDiagnosticsJson:

    @pytest.mark.parametrize("geometry, needle", [
        ("nodes[where x == t] = SOLID;", "time-dependent geometry"),
        ("nodes[x, 0] = SOLID;", "only inside a 'where' predicate"),
        ("nodes[where x + y] = SOLID;", "scalar bool"),
        ("nodes[where f.in[x, y | 0] > 0] = SOLID;", "state-dependent geometry"),
    ])
    def test_errors_point_at_the_offending_line(self, tmp_path, geometry, needle):
        path, code, diags = _diagnostics(tmp_path, _program_2d(geometry=geometry))
        assert code != 0
        errors = [d for d in diags if d["severity"] == "error"]
        assert errors, diags
        assert needle in errors[0]["text"]
        assert errors[0]["line"] == _line_of(path, geometry.split(';')[0])

    def test_legacy_syntax_points_at_its_line(self, tmp_path):
        stmt = "nodes[InCircle(:, :, CX, CY, R)] = SOLID;"
        path, code, diags = _diagnostics(tmp_path, _program_2d(functions=CIRCLE, geometry=stmt))
        assert code != 0
        assert 'nodes[where' in diags[0]["text"]
        assert diags[0]["line"] == _line_of(path, stmt)


# --------------------------------------------------------------------------
# Fortran replays the map in source order
# --------------------------------------------------------------------------

class TestFortranClassMap:

    def _generate(self, code):
        from gelb.backends.stage3_backend_cpu_fortran_serial import generate_fortran
        from gelb.midware.inline_functions import inline_functions
        ast = get_typed_ast(code)
        ast = inline_functions(ast)
        return generate_fortran(ast, num_timesteps=1)

    def test_point_paint_after_a_predicate_is_emitted_after_it(self):
        fortran = self._generate(_program_2d(
            geometry="nodes[where x < 2] = WALL; nodes[1, 1] = FLUID;",
            nx=4, ny=3))
        lines = [l.strip() for l in fortran.splitlines() if 'gelb_nc_map(' in l and '=' in l]
        assert lines[0].startswith('gelb_nc_map(:, :) = 1')
        wall_lines = [i for i, l in enumerate(lines) if l.endswith('! WALL')]
        fluid_point = [i for i, l in enumerate(lines) if l.startswith('gelb_nc_map(1, 1) = 1')]
        assert len(wall_lines) == 6 and len(fluid_point) == 1
        assert fluid_point[0] > max(wall_lines)

    def test_circle_and_border_are_present(self):
        fortran = self._generate(_program_2d(
            functions=CIRCLE,
            geometry="nodes[where InCircle(x, y, CX, CY, R)] = SOLID; border(SOLID) = WALL;"))
        assert 'program gelb_simulation' in fortran
        assert '! where-paint: SOLID' in fortran
        assert '! WALL (border)' in fortran
