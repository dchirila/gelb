#!/usr/bin/env python3
"""
Tests for compile-time evaluation of intrinsic functions during constant folding.

Verifies that the ConstantFoldingVisitor evaluates intrinsics when all
arguments are compile-time constants, replacing IntrinsicFunctionCall_N
nodes with literal values.
"""

import math
import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.tests.test_utils import minimal_gelb_program_1d
from gelb.tests.unit.midware.midware_test_utils import get_midware_processed_ast


def _program_with_const_expr(const_decl):
    """Build a 1D program with constant declarations in the initializer block.

    Constants that use intrinsic calls (e.g. ``const real R = sin(0.0);``)
    must live inside a block, not in ``global_constants``, because the
    symbol table builder only allows literal expressions there.
    """
    return minimal_gelb_program_1d(
        initializer_content=f'{const_decl}\nf.out[x | 0] = 0;',
    )


def _get_folded_value(ast, const_name):
    """Extract the folded value of a constant from the AST.

    Searches global_constants and all initializer block statements for a
    ConstantDefinitionStmt_N with the given name and returns its
    (potentially folded) value node.
    """
    # Search global constants first
    if ast.global_constants is not None:
        for stmt in ast.global_constants.stmts:
            if isinstance(stmt, ConstantDefinitionStmt_N):
                if stmt.name.name == const_name:
                    return stmt.value
    # Then search initializer blocks
    for init in ast.initializers:
        for stmt in init.stmts:
            if isinstance(stmt, ConstantDefinitionStmt_N):
                if stmt.name.name == const_name:
                    return stmt.value
    raise ValueError(f"Constant '{const_name}' not found")


# ===================================================================
# Scalar math intrinsics -- single argument
# ===================================================================

class TestScalarMathFolding:
    """Test compile-time evaluation of single-arg scalar math intrinsics."""

    @pytest.mark.parametrize("func,arg,expected", [
        ("sin", "0.0", 0.0),
        ("cos", "0.0", 1.0),
        ("sqrt", "4.0", 2.0),
        ("exp", "0.0", 1.0),
        ("log", "1.0", 0.0),
        ("abs", "-3.0", 3.0),
        ("tan", "0.0", 0.0),
        ("tanh", "0.0", 0.0),
    ])
    def test_scalar_math_1arg(self, func, arg, expected):
        """Scalar math intrinsic with constant arg is folded to literal."""
        code = _program_with_const_expr(
            f"const real R = {func}({arg});")
        ast = get_midware_processed_ast(code)
        val = _get_folded_value(ast, 'R')
        assert isinstance(val, RealLiteral_N), \
            f"Expected RealLiteral_N, got {type(val).__name__}"
        assert abs(val.value - expected) < 1e-12

    def test_abs_integer(self):
        """abs(-5) folds to the integer 5: abs keeps its argument's type
        (user manual, Numerical semantics: Types and promotion); the real
        constant converts it."""
        code = _program_with_const_expr("const real R = abs(-5);")
        ast = get_midware_processed_ast(code)
        val = _get_folded_value(ast, 'R')
        assert isinstance(val, IntLiteral_N)
        assert val.value == 5
        assert val.inferred_type.element_dtype == "int"

    def test_abs_real(self):
        """abs(-5.0) folds to the real 5.0."""
        code = _program_with_const_expr("const real R = abs(-5.0);")
        ast = get_midware_processed_ast(code)
        val = _get_folded_value(ast, 'R')
        assert isinstance(val, RealLiteral_N)
        assert val.value == 5.0

    def test_sqrt_of_constant_expression(self):
        """sqrt(2.0) should fold to the correct value."""
        code = _program_with_const_expr("const real R = sqrt(2.0);")
        ast = get_midware_processed_ast(code)
        val = _get_folded_value(ast, 'R')
        assert isinstance(val, RealLiteral_N)
        assert abs(val.value - math.sqrt(2.0)) < 1e-12


# ===================================================================
# Scalar math intrinsics -- two arguments
# ===================================================================

class TestTwoArgMathFolding:
    """Test compile-time evaluation of two-arg scalar math intrinsics."""

    @pytest.mark.parametrize("func,a,b,expected", [
        ("min", "3.0", "5.0", 3.0),
        ("max", "3.0", "5.0", 5.0),
        ("mod", "7.0", "3.0", 1.0),
        ("atan2", "1.0", "1.0", math.atan2(1.0, 1.0)),
    ])
    def test_scalar_math_2arg(self, func, a, b, expected):
        """Two-arg scalar math intrinsic with constant args is folded."""
        code = _program_with_const_expr(
            f"const real R = {func}({a}, {b});")
        ast = get_midware_processed_ast(code)
        val = _get_folded_value(ast, 'R')
        assert isinstance(val, RealLiteral_N)
        assert abs(val.value - expected) < 1e-12


# ===================================================================
# Reduction intrinsics
# ===================================================================

class TestReductionFolding:
    """Test compile-time evaluation of sum() and dot_prod()."""

    def test_sum_constant_array(self):
        """sum({1.0, 2.0, 3.0}) should fold to 6.0 in global constants."""
        code = minimal_gelb_program_1d(
            global_constants_content=(
                "const array[real, 3] V = {1.0, 2.0, 3.0};\n"
                "const real S = sum(V);"
            ),
        )
        ast = get_midware_processed_ast(code)
        val = _get_folded_value(ast, 'S')
        assert isinstance(val, RealLiteral_N)
        assert abs(val.value - 6.0) < 1e-12

    def test_sum_of_a_named_constant_array_in_block_folds(self):
        """sum(V) in a runtime block folds to its value in V's width
        (user manual, Numerical semantics: Types and promotion): the
        array constant itself stays a named reference wherever it is
        read as an array, but a reduction of constants is a constant
        expression and every backend shares the folded value."""
        code = minimal_gelb_program_1d(
            global_constants_content="const array[real, 3] V = {1.0, 2.0, 3.0};",
            initializer_content="const real S = sum(V);\nf.out[x | 0] = 0;",
        )
        ast = get_midware_processed_ast(code)
        val = _get_folded_value(ast, 'S')
        assert isinstance(val, RealLiteral_N)
        assert val.value == 6.0

    def test_dot_prod_constant_arrays(self):
        """dot_prod({1.0, 2.0}, {3.0, 4.0}) should fold to 11.0 in global constants."""
        code = minimal_gelb_program_1d(
            global_constants_content=(
                "const array[real, 2] A = {1.0, 2.0};\n"
                "const array[real, 2] B = {3.0, 4.0};\n"
                "const real D = dot_prod(A, B);"
            ),
        )
        ast = get_midware_processed_ast(code)
        val = _get_folded_value(ast, 'D')
        assert isinstance(val, RealLiteral_N)
        assert abs(val.value - 11.0) < 1e-12


# ===================================================================
# Matrix intrinsics
# ===================================================================

def _program_with_matrix(gc_content, result_const):
    """Build a program with matrix constants and compile-time intrinsic
    calls (inverse, determinant, transpose, matmul) in global_constants,
    where array constant inlining allows folding."""
    return minimal_gelb_program_1d(
        global_constants_content=f'{gc_content}\n{result_const}',
    )


class TestMatrixInverseFolding:
    """Test compile-time evaluation of inverse()."""

    def test_inverse_2x2(self):
        """inverse of {{2,1},{1,1}} should be {{1,-1},{-1,2}}."""
        code = _program_with_matrix(
            "const array[real, {2, 2}] M = {{2.0, 1.0}, {1.0, 1.0}};",
            "const array[real, {2, 2}] MI = inverse(M);")
        ast = get_midware_processed_ast(code)
        val = _get_folded_value(ast, 'MI')
        assert isinstance(val, Array2DLiteral_N)
        rows = val.value.elements
        assert abs(rows[0].value.elements[0].value - 1.0) < 1e-12
        assert abs(rows[0].value.elements[1].value - (-1.0)) < 1e-12
        assert abs(rows[1].value.elements[0].value - (-1.0)) < 1e-12
        assert abs(rows[1].value.elements[1].value - 2.0) < 1e-12

    def test_inverse_identity(self):
        """inverse of identity matrix should be identity."""
        code = _program_with_matrix(
            "const array[real, {3, 3}] I = "
            "{{1.0, 0.0, 0.0}, {0.0, 1.0, 0.0}, {0.0, 0.0, 1.0}};",
            "const array[real, {3, 3}] II = inverse(I);")
        ast = get_midware_processed_ast(code)
        val = _get_folded_value(ast, 'II')
        assert isinstance(val, Array2DLiteral_N)
        for i, row in enumerate(val.value.elements):
            for j, elem in enumerate(row.value.elements):
                expected = 1.0 if i == j else 0.0
                assert abs(elem.value - expected) < 1e-12


class TestDeterminantFolding:
    """Test compile-time evaluation of determinant()."""

    def test_determinant_2x2(self):
        """determinant({{2,1},{1,1}}) should be 1.0."""
        code = _program_with_matrix(
            "const array[real, {2, 2}] M = {{2.0, 1.0}, {1.0, 1.0}};",
            "const real D = determinant(M);")
        ast = get_midware_processed_ast(code)
        val = _get_folded_value(ast, 'D')
        assert isinstance(val, RealLiteral_N)
        assert abs(val.value - 1.0) < 1e-12

    def test_determinant_3x3(self):
        """determinant of 3x3 identity should be 1.0."""
        code = _program_with_matrix(
            "const array[real, {3, 3}] I = "
            "{{1.0, 0.0, 0.0}, {0.0, 1.0, 0.0}, {0.0, 0.0, 1.0}};",
            "const real D = determinant(I);")
        ast = get_midware_processed_ast(code)
        val = _get_folded_value(ast, 'D')
        assert isinstance(val, RealLiteral_N)
        assert abs(val.value - 1.0) < 1e-12


class TestTransposeFolding:
    """Test compile-time evaluation of transpose()."""

    def test_transpose_2x2(self):
        """transpose({{1,2},{3,4}}) should be {{1,3},{2,4}}."""
        code = _program_with_matrix(
            "const array[real, {2, 2}] M = {{1.0, 2.0}, {3.0, 4.0}};",
            "const array[real, {2, 2}] MT = transpose(M);")
        ast = get_midware_processed_ast(code)
        val = _get_folded_value(ast, 'MT')
        assert isinstance(val, Array2DLiteral_N)
        rows = val.value.elements
        assert abs(rows[0].value.elements[0].value - 1.0) < 1e-12
        assert abs(rows[0].value.elements[1].value - 3.0) < 1e-12
        assert abs(rows[1].value.elements[0].value - 2.0) < 1e-12
        assert abs(rows[1].value.elements[1].value - 4.0) < 1e-12


class TestMatmulFolding:
    """Test compile-time evaluation of matmul()."""

    def test_matmul_identity(self):
        """matmul(I, M) should equal M."""
        code = _program_with_matrix(
            "const array[real, {2, 2}] I = {{1.0, 0.0}, {0.0, 1.0}};\n"
            "const array[real, {2, 2}] M = {{3.0, 4.0}, {5.0, 6.0}};",
            "const array[real, {2, 2}] R = matmul(I, M);")
        ast = get_midware_processed_ast(code)
        val = _get_folded_value(ast, 'R')
        assert isinstance(val, Array2DLiteral_N)
        rows = val.value.elements
        assert abs(rows[0].value.elements[0].value - 3.0) < 1e-12
        assert abs(rows[0].value.elements[1].value - 4.0) < 1e-12
        assert abs(rows[1].value.elements[0].value - 5.0) < 1e-12
        assert abs(rows[1].value.elements[1].value - 6.0) < 1e-12


class TestChainedFolding:
    """Test compile-time evaluation of chained intrinsic calls."""

    def test_matmul_inverse_gives_identity(self):
        """matmul(inverse(M), M) should approximate identity."""
        code = _program_with_matrix(
            "const array[real, {2, 2}] M = {{2.0, 1.0}, {1.0, 1.0}};",
            "const array[real, {2, 2}] R = matmul(inverse(M), M);")
        ast = get_midware_processed_ast(code)
        val = _get_folded_value(ast, 'R')
        assert isinstance(val, Array2DLiteral_N)
        rows = val.value.elements
        for i, row in enumerate(rows):
            for j, elem in enumerate(row.value.elements):
                expected = 1.0 if i == j else 0.0
                assert abs(elem.value - expected) < 1e-10


# ===================================================================
# MRT 9x9 matrix inverse (the motivating use case)
# ===================================================================

class TestMRTMatrixInverse:
    """Test that the 9x9 MRT transformation matrix inverse is computed correctly."""

    _MRT_M = (
        'const array[real, {9, 9}] M = {\n'
        '    { 1.0,  1.0,  1.0,  1.0,  1.0,  1.0,  1.0,  1.0,  1.0},\n'
        '    {-4.0, -1.0, -1.0, -1.0, -1.0,  2.0,  2.0,  2.0,  2.0},\n'
        '    { 4.0, -2.0, -2.0, -2.0, -2.0,  1.0,  1.0,  1.0,  1.0},\n'
        '    { 0.0,  1.0,  0.0, -1.0,  0.0,  1.0, -1.0, -1.0,  1.0},\n'
        '    { 0.0, -2.0,  0.0,  2.0,  0.0,  1.0, -1.0, -1.0,  1.0},\n'
        '    { 0.0,  0.0,  1.0,  0.0, -1.0,  1.0,  1.0, -1.0, -1.0},\n'
        '    { 0.0,  0.0, -2.0,  0.0,  2.0,  1.0,  1.0, -1.0, -1.0},\n'
        '    { 0.0,  1.0, -1.0,  1.0, -1.0,  0.0,  0.0,  0.0,  0.0},\n'
        '    { 0.0,  0.0,  0.0,  0.0,  0.0,  1.0, -1.0,  1.0, -1.0}};'
    )

    def test_mrt_inverse_compiles(self):
        """The MRT example with inverse(M) should compile through full pipeline."""
        code = _program_with_matrix(
            self._MRT_M,
            "const array[real, {9, 9}] MI = inverse(M);")
        ast = get_midware_processed_ast(code)
        val = _get_folded_value(ast, 'MI')
        assert isinstance(val, Array2DLiteral_N)
        # Check a few known values: MI[0][0] = 1/9
        assert abs(val.value.elements[0].value.elements[0].value - 1.0/9.0) < 1e-12
        # MI[0][1] = -1/9
        assert abs(val.value.elements[0].value.elements[1].value - (-1.0/9.0)) < 1e-12
        # MI[1][3] = 1/6
        assert abs(val.value.elements[1].value.elements[3].value - 1.0/6.0) < 1e-12
