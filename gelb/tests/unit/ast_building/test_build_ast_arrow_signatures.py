#!/usr/bin/env python3

import pytest

from gelb.frontend.stage1_frontend import get_ast


@pytest.mark.parametrize(
    ("rule", "canonical", "input_names", "result_names"),
    [
        (
            "function_block",
            "function Scale(real x, int n) "
            "-> (real result) { result = x * n; }",
            ["x", "n"],
            ["result"],
        ),
        (
            "gauge_block",
            "gauge Current -> (real rho, int step) "
            "{ rho = 1.0; step = 2; }",
            [],
            ["rho", "step"],
        ),
    ],
)
def test_canonical_signatures_build_ordered_declaration_lists(
        rule, canonical, input_names, result_names):
    ast = get_ast(rule, canonical)
    actual_inputs = (
        [parameter.name.name for parameter in ast.inputs]
        if rule == "function_block"
        else []
    )

    assert actual_inputs == input_names
    assert [result.name.name for result in ast.outputs] == result_names


def test_multiline_zero_input_function_builds_named_result():
    ast = get_ast(
        "function_block",
        """
        function Noise()
                -> (real value) {
            value = 1.0;
        }
        """,
    )

    assert len(ast.inputs.elements) == 0
    assert [result.name.name for result in ast.outputs] == ["value"]


def test_empty_function_results_are_preserved_for_semantic_validation():
    ast = get_ast(
        "function_block",
        "function Invalid() -> () { int value; }",
    )

    assert len(ast.outputs.elements) == 0


def test_bare_gauge_is_preserved_for_semantic_validation():
    ast = get_ast(
        "gauge_block",
        "gauge Invalid { int value; }",
    )

    assert len(ast.outputs.elements) == 0
