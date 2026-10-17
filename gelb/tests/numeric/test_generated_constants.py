"""Generated C++ -> GeLB tests of folding and compile-time predicates."""

import math

import pytest

from gelb.compiler_pipeline import PipelineOptions, PipelineProfile, compile_source
from gelb.gelb_ast.ASTNodes import (
    BoolLiteral_N,
    IntLiteral_N,
    RealLiteral_N,
    TypePromotionNode_N,
)
from gelb.midware.ast_eval import eval_const_expr

from .cases import CASES, Case, corpus, translate
from .checks import check_values


def program(constants, predicate):
    return f"""simulation_description("generated constant precision");
global_constants {{ {constants} }}
lattices {{ lattice f(1,1,real,4,false); }}
initializer I {{ f.out[x | 0] = 0.0; }}
dynamic D {{ f.out[x | 0] = f.in[x | 0]; }}
gauge G -> (real v) {{ v = f.in[x | 0]; }}
node_classes {{ node_class BULK(I,D,G); node_class HIT(I,D,G); node_class MISS(I,D,G); }}
geometry {{
    nodes[:] = BULK;
    nodes[where {predicate}] = HIT;
    nodes[where !({predicate})] = MISS;
}}
"""


def folded_values(source, names):
    values = {}

    def capture(ast, stage):
        if stage != "constant_folding":
            return
        for stmt in ast.global_constants.stmts:
            if stmt.name.name not in names:
                continue
            leaf = stmt.value
            while isinstance(leaf, TypePromotionNode_N):
                leaf = leaf.expr
            assert isinstance(leaf, (RealLiteral_N, IntLiteral_N, BoolLiteral_N)), (
                f"did not fold {stmt.name.name}: {stmt.value}\n{source}")
            values[stmt.name.name] = float(eval_const_expr(stmt.value, ast=ast))

    result = compile_source(source, PipelineProfile.DIAGNOSTICS, PipelineOptions(
        capture_ast=capture, require_geometry=True, require_stencils=True))
    assert set(values) == set(names)
    return values, result.geometry


CONSTANT_CASES = tuple(case for case in CASES if case.constant)


@pytest.mark.parametrize("case", CONSTANT_CASES, ids=lambda c: c.name)
def test_generated_constants_and_predicate_match_native_cpp(case, numeric_oracle, tmp_path):
    cells = min(case.cells, 4)   # the predicate program has four cells
    expected = [numeric_oracle[case.name][x]["raw"] for x in range(cells)]
    constants = [f"const {case.gelb_type} INPUT = {translate(case.initial, {})};"]
    for x in range(cells):
        expr = translate(case.expression, {"u": "INPUT", "x": str(x)})
        constants.append(f"const real VALUE{x} = {expr};")
    padded = expected + [expected[-1]] * (4 - cells)
    constants.append("const array[real,4] EXPECTED = {" + ",".join(map(repr, padded)) + "};")
    expression = translate(case.expression, {"u": "INPUT", "x": "x"})
    predicate = " || ".join(
        f"((x == {x}) && (real({expression}) == EXPECTED[{x}]))" for x in range(4))
    source = program("\n".join(constants), predicate)
    (tmp_path / "case.gelb").write_text(source)
    values, geometry = folded_values(source, [f"VALUE{x}" for x in range(cells)])
    check_values([values[f"VALUE{x}"] for x in range(cells)], expected,
                 case=case, context="constant folding", source=source)
    hit = geometry.nc_info["HIT"].nc_id
    check_values(geometry.nc_map.tolist()[:cells], [hit] * cells,
                 case=case, context="geometry predicate", source=source)


ARRAY_CASES = tuple(case for case in CASES if case.name.startswith("store_boundary_")
                    or case.name in ("double_literal", "negative_zero", "small_float"))


@pytest.mark.parametrize("case", ARRAY_CASES, ids=lambda c: c.name)
@pytest.mark.parametrize("form", ["literal", "expression", "alias"])
def test_array_declaration_conversion_survives_substitution(case, form, numeric_oracle, tmp_path):
    # Native C++ rounds the input to float, then widens and adds zero.
    # This exercises the same storage boundary through GeLB array references.
    expected = numeric_oracle[case.name][0]["array_sum"]
    initial = translate(case.initial, {})
    initializer = f"{{{initial}, 0.0}}"
    prelude = ""
    if form == "expression":
        initializer += " + {0.0, 0.0}"
    elif form == "alias":
        prelude = f"const array[real,2] WIDE = {initializer};"
        initializer = "WIDE"
    # The zero second entry allows a reduction without additional rounding.
    source = program(f"""{prelude}
const array[real32,2] ARR = {initializer};
const array[real,2] COPY = ARR + {{0.0, 0.0}};
const real VALUE = sum(COPY);
""", f"VALUE == {expected!r}")
    (tmp_path / "case.gelb").write_text(source)
    values, geometry = folded_values(source, ["VALUE"])
    check_values([values["VALUE"]], [expected], case=case, context=f"array/{form}", source=source)
    assert geometry.nc_map.tolist() == [geometry.nc_info["HIT"].nc_id] * 4


def test_translation_is_parenthesized_and_rejects_unimplemented_cpp():
    assert translate("0.1f") == "real32(0.1)"
    assert translate("static_cast<double>(u)") == "real((u))"
    assert translate("u + x * 2LL") == "((u) + ((x) * 2))"
    for invalid in ("u; x", "std::sin(u)", "u && x", "u[0]", "foo", "u +", "u ? 1 : 0"):
        with pytest.raises(ValueError):
            translate(invalid)


def test_generator_is_reproducible_and_seed_changes_compositions():
    assert corpus(123, 32) == corpus(123, 32)
    assert corpus(123, 32) != corpus(124, 32)
    assert len({case.name for case in CASES}) == len(CASES)
    assert all(isinstance(case, Case) and translate(case.expression) for case in CASES)


def test_native_reference_distinguishes_the_historical_failure_values(numeric_oracle):
    # Protect the discriminating inputs, independently of the GeLB compiler.
    assert numeric_oracle["double_literal"][0]["stored"] == 0.10999999940395355
    assert numeric_oracle["narrow_composite"][0]["stored"] == 15.869999885559082
    assert numeric_oracle["integer_conversion"][1]["stored"] == 8388609.0
    assert numeric_oracle["integer_quotient"][0]["stored"] == -1.5
    assert numeric_oracle["literal_conversion_before_algebra"][0]["stored"] == 0.0
    assert numeric_oracle["minimum_int64"][0]["stored"] == -4611686018427387904.0
    assert numeric_oracle["coordinate_sum"][1]["stored"] == 2147483648.0
    assert numeric_oracle["coordinate_product"][2]["stored"] == 2147483648.0
    assert numeric_oracle["literal_double_round"][0]["stored"] == 9007200328482816.0
    assert numeric_oracle["cast_double_round"][0]["raw"] == 18014400656965632.0
    assert numeric_oracle["cancellation_nonzero"][0]["stored"] == 0.0
    assert numeric_oracle["coordinate_sum_singleton"][0]["stored"] == 2147483648.0
    assert numeric_oracle["coordinate_division_simd"][0]["stored"] == -3.0
    assert numeric_oracle["coordinate_division_simd"][66]["stored"] == 29.0
    # real32 temporaries and signed zeros.
    assert numeric_oracle["repeated_narrow_square"][0]["stored"] == 4.392300605773926
    assert numeric_oracle["repeated_narrow_sum"][0]["stored"] == 1.7457001209259033
    for name, negative in (("zero_product_sign", True), ("zero_product_sign_float", True),
                           ("zero_sum_sign", False), ("zero_difference_sign", False),
                           ("negated_cancellation", False)):
        stored = numeric_oracle[name][0]["stored"]
        assert stored == 0.0 and (math.copysign(1.0, stored) < 0) == negative, name
