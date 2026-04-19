#!/usr/bin/env python3
"""Array literals must be rectangular and match the declared shape.

Frontend-level checks only.  Which backends accept a *local*
two-dimensional array is validated separately, so
the positive cases here stay within one-dimensional locals and
two-dimensional global constants.
"""

import pytest
from gelb.utils.exceptions import GeLBExTypeError
from gelb.tests.test_utils import get_fully_validated_ast


def program(constants="", dynamic_body=""):
    return f"""
    simulation_description("array literal shapes");
    global_constants {{
        const int N = 8;
        {constants}
    }}
    lattices {{ lattice f(2, 9, real, {{N, N}}, {{true, true}}); }}
    initializer Init {{ f.out[x, y | :] = 1.0; }}
    dynamic Dyn {{
        real a = f.in[x, y | 0];
        real b = f.in[x, y | 1];
        {dynamic_body}
        f.out[x, y | :] = f.in[x, y | :];
    }}
    gauge Out -> (real rho) {{ rho = sum(f.in[x, y | :]); }}
    node_classes {{ node_class BULK(Init, Dyn, Out); }}
    geometry {{ nodes[:, :] = BULK; }}
    """


class TestRectangularity:
    @pytest.mark.parametrize("constants", [
        "const array[real, {2, 2}] M = {{1.0, 2.0}, {3.0, 4.0, 5.0}};",
        "const array[real, {2, 3}] M = {{1.0, 2.0}, {3.0, 4.0, 5.0}};",
        # ragged across blocks of a 3D literal, every block consistent
        "const array[real, {2, 2, 2}] M = {{{1.0, 2.0}, {3.0, 4.0}},"
        " {{5.0, 6.0, 7.0}, {8.0, 9.0, 1.0}}};",
    ])
    def test_ragged_constant_literal_is_rejected(self, constants):
        with pytest.raises(GeLBExTypeError, match=r"not rectangular"):
            get_fully_validated_ast(program(constants=constants))

    def test_ragged_runtime_literal_is_rejected(self):
        body = "array[real, {2, 2}] m = {{a, b}, {b, a, a}};"
        with pytest.raises(GeLBExTypeError, match=r"not rectangular"):
            get_fully_validated_ast(program(dynamic_body=body))

    @pytest.mark.parametrize("constants", [
        "const array[real, {2, 2}] M = {{1.0, 2.0}, {3.0, 4.0}};",
        "const array[real, {2, 3}] M = {{1.0, 2.0, 3.0}, {4.0, 5.0, 6.0}};",
    ])
    def test_rectangular_literals_are_accepted(self, constants):
        assert get_fully_validated_ast(program(constants=constants)) is not None


class TestDeclaredShape:
    @pytest.mark.parametrize("constants,expected", [
        ("const array[real, 3] V = {1.0, 2.0};",
         r"Constant 'V' is declared with shape \[3\] but initialized with shape \[2\]"),
        ("const array[real, 2] V = {1.0, 2.0, 3.0};",
         r"declared with shape \[2\] but initialized with shape \[3\]"),
        ("const array[real, {2, 3}] M = {{1.0, 2.0}, {3.0, 4.0}};",
         r"declared with shape \[2, 3\] but initialized with shape \[2, 2\]"),
        ("const array[real, {2, 2}] M = {1.0, 2.0, 3.0, 4.0};",
         r"declared with shape \[2, 2\] but initialized with shape \[4\]"),
    ])
    def test_constant_initializer_shape_mismatch(self, constants, expected):
        with pytest.raises(GeLBExTypeError, match=expected):
            get_fully_validated_ast(program(constants=constants))

    @pytest.mark.parametrize("body,expected", [
        ("array[real, 3] v = {a, b};",
         r"Variable 'v' is declared with shape \[3\] but initialized with shape \[2\]"),
        ("array[real, {2, 2}] m = {{a, b}, {b, a}, {a, a}};",
         r"declared with shape \[2, 2\] but initialized with shape \[3, 2\]"),
    ])
    def test_runtime_initializer_shape_mismatch(self, body, expected):
        with pytest.raises(GeLBExTypeError, match=expected):
            get_fully_validated_ast(program(dynamic_body=body))

    def test_assignment_of_wrong_size_literal(self):
        body = "array[real, 3] v; v = {a, b};"
        with pytest.raises(GeLBExTypeError, match=r"Cannot assign"):
            get_fully_validated_ast(program(dynamic_body=body))

    @pytest.mark.parametrize("body", [
        "array[real, 2] v = {a, b};",
        "array[real, 3] v; v = {a, b, a};",
    ])
    def test_matching_shapes_are_accepted(self, body):
        assert get_fully_validated_ast(program(dynamic_body=body)) is not None
