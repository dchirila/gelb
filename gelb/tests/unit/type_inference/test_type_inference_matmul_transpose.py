#!/usr/bin/env python3
"""
Tests for matmul and transpose intrinsic type inference.
"""

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.tests.test_utils import get_typed_ast
from gelb.utils.exceptions import GeLBExTypeError


def _program_with_matmul(expr):
    """Build a minimal program that uses matmul in an initializer."""
    return f'''\
simulation_description("matmul test");
global_constants {{
    const int N = 4;
    const array[real, {{3, 3}}] M = {{{{1.0, 0.0, 0.0}}, {{0.0, 1.0, 0.0}}, {{0.0, 0.0, 1.0}}}};
    const array[real, {{3, 4}}] A = {{{{1.0, 2.0, 3.0, 4.0}}, {{5.0, 6.0, 7.0, 8.0}}, {{9.0, 10.0, 11.0, 12.0}}}};
    const array[real, {{4, 2}}] B = {{{{1.0, 2.0}}, {{3.0, 4.0}}, {{5.0, 6.0}}, {{7.0, 8.0}}}};
    const array[real, 3] V = {{1.0, 2.0, 3.0}};
}}
lattices {{ lattice f(1, 3, real, N, true); }}
initializer Init {{
    {expr}
    f.out[x | :] = {{0.0, 0.0, 0.0}};
}}
dynamic Noop {{ f.out[x | :] = f.in[x | :]; }}
gauge G -> (real val) {{ val = f.in[x | 0]; }}
node_classes {{ node_class BULK(Init, Noop, G); }}
geometry {{ nodes[:] = BULK; }}
'''


class TestMatmulTypeInference:
    """Type inference tests for matmul()."""

    def test_matrix_vector(self):
        """matmul(array[real, {3,3}], array[real, 3]) -> array[real, 3]"""
        code = _program_with_matmul("array[real, 3] result = matmul(M, V);")
        ast = get_typed_ast(code)
        # Should compile without errors
        assert ast is not None

    def test_matrix_matrix(self):
        """matmul(array[real, {3,4}], array[real, {4,2}]) -> array[real, {3,2}]"""
        code = _program_with_matmul(
            "array[real, {3, 2}] result = matmul(A, B);")
        ast = get_typed_ast(code)
        assert ast is not None

    def test_wrong_arg_count_one(self):
        """matmul(M) with one argument -> error"""
        code = _program_with_matmul("array[real, 3] r = matmul(M);")
        with pytest.raises(GeLBExTypeError):
            get_typed_ast(code)

    def test_wrong_arg_count_three(self):
        """matmul(M, V, V) with three arguments -> error"""
        code = _program_with_matmul("array[real, 3] r = matmul(M, V, V);")
        with pytest.raises(GeLBExTypeError):
            get_typed_ast(code)

    def test_first_arg_must_be_2d(self):
        """matmul(1D, 1D) -> error (first arg must be 2D)"""
        code = _program_with_matmul("array[real, 3] r = matmul(V, V);")
        with pytest.raises(GeLBExTypeError):
            get_typed_ast(code)


class TestTransposeTypeInference:
    """Type inference tests for transpose()."""

    def test_transpose_2d(self):
        """transpose(array[real, {3,3}]) -> array[real, {3,3}]"""
        code = _program_with_matmul(
            "array[real, {3, 3}] result = transpose(M);")
        ast = get_typed_ast(code)
        assert ast is not None

    def test_transpose_non_square(self):
        """transpose(array[real, {3,4}]) -> array[real, {4,3}]"""
        code = _program_with_matmul(
            "array[real, {4, 3}] result = transpose(A);")
        ast = get_typed_ast(code)
        assert ast is not None

    def test_wrong_arg_count(self):
        """transpose(M, M) -> error"""
        code = _program_with_matmul(
            "array[real, {3, 3}] r = transpose(M, M);")
        with pytest.raises(GeLBExTypeError):
            get_typed_ast(code)

    def test_transpose_1d_error(self):
        """transpose(1D array) -> error"""
        code = _program_with_matmul("array[real, 3] r = transpose(V);")
        with pytest.raises(GeLBExTypeError):
            get_typed_ast(code)


class TestInverseTypeInference:
    """Type inference tests for inverse()."""

    def test_inverse_square_matrix(self):
        """inverse(array[real, {3,3}]) -> array[real, {3,3}]"""
        code = _program_with_matmul(
            "array[real, {3, 3}] result = inverse(M);")
        ast = get_typed_ast(code)
        assert ast is not None

    def test_inverse_non_square_error(self):
        """inverse(array[real, {3,4}]) -> error (not square)"""
        code = _program_with_matmul(
            "array[real, {3, 4}] r = inverse(A);")
        with pytest.raises(GeLBExTypeError):
            get_typed_ast(code)

    def test_inverse_1d_error(self):
        """inverse(1D array) -> error (not 2D)"""
        code = _program_with_matmul("array[real, 3] r = inverse(V);")
        with pytest.raises(GeLBExTypeError):
            get_typed_ast(code)

    def test_inverse_wrong_arg_count(self):
        """inverse(M, M) -> error"""
        code = _program_with_matmul(
            "array[real, {3, 3}] r = inverse(M, M);")
        with pytest.raises(GeLBExTypeError):
            get_typed_ast(code)


class TestDeterminantTypeInference:
    """Type inference tests for determinant()."""

    def test_determinant_square_matrix(self):
        """determinant(array[real, {3,3}]) -> real (scalar)"""
        code = _program_with_matmul("real det = determinant(M);")
        ast = get_typed_ast(code)
        assert ast is not None

    def test_determinant_non_square_error(self):
        """determinant(array[real, {3,4}]) -> error (not square)"""
        code = _program_with_matmul("real det = determinant(A);")
        with pytest.raises(GeLBExTypeError):
            get_typed_ast(code)

    def test_determinant_1d_error(self):
        """determinant(1D array) -> error (not 2D)"""
        code = _program_with_matmul("real det = determinant(V);")
        with pytest.raises(GeLBExTypeError):
            get_typed_ast(code)


class TestMatmulWithTranspose:
    """Combined matmul + transpose usage."""

    def test_matmul_transpose(self):
        """matmul(transpose(A), ...) should work."""
        # transpose({3,4}) -> {4,3}, then matmul({4,3}, {3}) -> {4}
        code = _program_with_matmul(
            "array[real, 4] r = matmul(transpose(A), V);")
        ast = get_typed_ast(code)
        assert ast is not None

    def test_matmul_inverse(self):
        """matmul(inverse(M), V) should work."""
        code = _program_with_matmul(
            "array[real, 3] r = matmul(inverse(M), V);")
        ast = get_typed_ast(code)
        assert ast is not None
