#!/usr/bin/env python3
"""
Unit tests for compile-time range validation in array selections.

Tests that array range expressions must be compile-time evaluable.
"""

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.utils.exceptions import GeLBException, GeLBExTypeError
from gelb.tests.test_utils import (
    get_typed_ast,
    minimal_gelb_program_1d
)


class TestCompileTimeRangeValidation:
    """Test compile-time validation for range expressions."""
    
    def test_literal_ranges_allowed(self):
        """Test that literal ranges are allowed."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[int, {5, 7}] matrix;
                array[int, 3] slice;
                slice = matrix[2, 1:3];
            """
        )
        
        # Should not raise any exception
        ast = get_typed_ast(test_code)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[2]  # slice = matrix[2, 1:3]
        
        # Should have correct reduced type
        matrix_selection = assignment.rhs
        assert isinstance(matrix_selection.inferred_type, ArrayDataType_N)
        assert matrix_selection.inferred_type.element_dtype == "int"
        assert isinstance(matrix_selection.inferred_type.shape, IntLiteral_N)
        assert matrix_selection.inferred_type.shape.value == 3
    
    def test_constant_ranges_allowed(self):
        """Test that constant expressions in ranges are allowed."""
        test_code = minimal_gelb_program_1d(
            global_constants_content="""
                const int N = 10;
                const int START = 2;
            """,
            initializer_content="""
                array[real, {10, 12}] matrix;
                array[real, 8] slice;
                slice = matrix[START, N-2:N];
            """
        )
        
        # Should not raise any exception
        ast = get_typed_ast(test_code)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[2]  # slice = matrix[START, N-2:N]
        
        # Should have correct reduced type
        matrix_selection = assignment.rhs
        assert isinstance(matrix_selection.inferred_type, ArrayDataType_N)
        assert matrix_selection.inferred_type.element_dtype == "real"
        assert isinstance(matrix_selection.inferred_type.shape, IntLiteral_N)
        assert matrix_selection.inferred_type.shape.value == 3  # N-2:N = 8:10 = 3 elements
    
    def test_grid_dimension_ranges_allowed(self):
        """Test that grid dimensions (Nx, Ny, Nz) in ranges are allowed."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[real, {32, 32}] matrix;
                array[real, 32] boundary;
                boundary = matrix[0:Nx-1, 5];
            """
        )
        
        # Should not raise any exception  
        ast = get_typed_ast(test_code)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[2]  # boundary = matrix[0:Nx-1, 5]
        
        # Should have correct reduced type
        matrix_selection = assignment.rhs
        assert isinstance(matrix_selection.inferred_type, ArrayDataType_N)
        assert matrix_selection.inferred_type.element_dtype == "real"
        assert isinstance(matrix_selection.inferred_type.shape, IntLiteral_N)
        assert matrix_selection.inferred_type.shape.value == 32  # Full first dimension
    
    def test_arithmetic_with_constants_allowed(self):
        """Test that arithmetic expressions with constants are allowed."""
        test_code = minimal_gelb_program_1d(
            global_constants_content="""
                const int N = 8;
                const int HALF = 4;
            """,
            initializer_content="""
                array[int, {10, 10}] matrix;
                array[int, 4] slice;
                slice = matrix[N/2:N/2+3, HALF*2-1];
            """
        )
        
        # Should not raise any exception
        ast = get_typed_ast(test_code)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[2]  # slice = matrix[N/2:N/2+3, HALF*2-1]
        
        # Should have correct reduced type (1D array)
        matrix_selection = assignment.rhs
        assert isinstance(matrix_selection.inferred_type, ArrayDataType_N)
        assert matrix_selection.inferred_type.element_dtype == "int"
        assert isinstance(matrix_selection.inferred_type.shape, IntLiteral_N)
        assert matrix_selection.inferred_type.shape.value == 4  # N/2:N/2+3 = 4:7 = 4 elements

    def test_local_constant_ranges_allowed(self):
        """Test that local constant expressions in ranges are allowed."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                const int BASE = 2;
                const int WIDTH = BASE + 3;
                array[int, 8] vec;
                array[int, 4] slice;
                slice = vec[BASE:WIDTH];
            """
        )

        ast = get_typed_ast(test_code)

        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[4]  # slice = vec[BASE:WIDTH]

        vec_selection = assignment.rhs
        assert isinstance(vec_selection.inferred_type, ArrayDataType_N)
        assert vec_selection.inferred_type.element_dtype == "int"
        assert isinstance(vec_selection.inferred_type.shape, IntLiteral_N)
        assert vec_selection.inferred_type.shape.value == 4  # 2:5


class TestCompileTimeShapeEvaluation:
    """Test compile-time evaluation of array shape expressions."""

    def test_arithmetic_shape_expression_allowed(self):
        """Array shapes may use compile-time arithmetic expressions."""
        test_code = minimal_gelb_program_1d(
            global_constants_content="const int N = 4;",
            initializer_content="""
                array[int, N*2+1] vec;
                array[int, 9] copy;
                copy = vec[:];
            """
        )

        ast = get_typed_ast(test_code)

        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[2]  # copy = vec[:]

        vec_selection = assignment.rhs
        assert isinstance(vec_selection.inferred_type, ArrayDataType_N)
        assert vec_selection.inferred_type.element_dtype == "int"
        assert isinstance(vec_selection.inferred_type.shape, IntLiteral_N)
        assert vec_selection.inferred_type.shape.value == 9

    def test_local_constant_shape_expression_allowed(self):
        """Local constants may define array shapes."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                const int BASE = 5;
                const int WIDTH = BASE + 2;
                array[int, WIDTH] vec;
                array[int, 7] copy;
                copy = vec[:];
            """
        )

        ast = get_typed_ast(test_code)

        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[4]  # copy = vec[:]

        vec_selection = assignment.rhs
        assert isinstance(vec_selection.inferred_type, ArrayDataType_N)
        assert vec_selection.inferred_type.element_dtype == "int"
        assert isinstance(vec_selection.inferred_type.shape, IntLiteral_N)
        assert vec_selection.inferred_type.shape.value == 7

    def test_grid_dimension_shape_expression_allowed(self):
        """Implicit grid dimensions may define array shapes."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[int, Nx/2] vec;
                array[int, 16] copy;
                copy = vec[:];
            """
        )

        ast = get_typed_ast(test_code)

        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[2]  # copy = vec[:]

        vec_selection = assignment.rhs
        assert isinstance(vec_selection.inferred_type, ArrayDataType_N)
        assert vec_selection.inferred_type.element_dtype == "int"
        assert isinstance(vec_selection.inferred_type.shape, IntLiteral_N)
        assert vec_selection.inferred_type.shape.value == 16

    def test_grid_dimension_from_expression_lattice_size_allowed(self):
        """Implicit grid dimensions may come from expression lattice sizes."""
        test_code = """
            simulation_description("Test expression lattice size");
            global_constants {
                const int N = 16;
            }
            lattices {
                lattice f(1, 1, int, N*2, false);
            }
            initializer Init {
                array[int, Nx/2] vec;
                array[int, 16] copy;
                copy = vec[:];
            }
            dynamic Dyn {
                f.out[x | 0] = f.in[x | 0];
            }
            gauge Out -> (int val) {
                val = f.in[x | 0];
            }
            node_classes {
                node_class BULK(Init, Dyn, Out);
            }
            geometry {
                nodes[:] = BULK;
            }
        """

        ast = get_typed_ast(test_code)

        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[2]  # copy = vec[:]

        vec_selection = assignment.rhs
        assert isinstance(vec_selection.inferred_type, ArrayDataType_N)
        assert vec_selection.inferred_type.element_dtype == "int"
        assert isinstance(vec_selection.inferred_type.shape, IntLiteral_N)
        assert vec_selection.inferred_type.shape.value == 16

    def test_unused_compile_time_shape_expression_allowed(self):
        """Declaration-time shape validation allows constant expressions."""
        test_code = minimal_gelb_program_1d(
            global_constants_content="const int N = 4;",
            initializer_content="""
                array[int, N*2+1] vec;
            """
        )

        get_typed_ast(test_code)

    def test_unused_grid_dimension_shape_expression_allowed(self):
        """Declaration-time shape validation allows grid dimensions."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[int, Nx/2] vec;
            """
        )

        get_typed_ast(test_code)

    def test_runtime_variable_shape_expression_rejected(self):
        """Array shapes must not silently fall back for runtime values."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                int n;
                array[int, n] vec;
                array[int, 1] copy;
                copy = vec[:];
            """
        )

        with pytest.raises(GeLBExTypeError) as exc_info:
            get_typed_ast(test_code)

        assert "must be compile-time evaluable" in str(exc_info.value.error)

    def test_unused_runtime_variable_shape_expression_rejected(self):
        """Array shape errors are reported at declaration, not first use."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                int n;
                array[int, n] vec;
            """
        )

        with pytest.raises(GeLBExTypeError) as exc_info:
            get_typed_ast(test_code)

        assert "must be compile-time evaluable" in str(exc_info.value.error)

    def test_unused_runtime_variable_2d_shape_expression_rejected(self):
        """Multi-dimensional declarations validate every shape component."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                int n;
                array[int, {4, n}] matrix;
            """
        )

        with pytest.raises(GeLBExTypeError) as exc_info:
            get_typed_ast(test_code)

        assert "must be compile-time evaluable" in str(exc_info.value.error)

    def test_unused_runtime_constant_shape_expression_rejected(self):
        """Constant array declarations validate shapes before value use."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                int n;
                const array[int, n] vec = {1, 2};
            """
        )

        with pytest.raises(GeLBExTypeError) as exc_info:
            get_typed_ast(test_code)

        assert "must be compile-time evaluable" in str(exc_info.value.error)

    def test_gauge_output_shape_expression_rejected(self):
        """Gauge output declarations validate array shapes."""
        test_code = """
            simulation_description("Test gauge output shape");
            lattices {
                lattice f(1, 1, int, 32, false);
            }
            initializer Init {
                f.out[x | 0] = 0;
            }
            dynamic Dyn {
                f.out[x | 0] = f.in[x | 0];
            }
            gauge Out -> (array[int, 1/0] values) {
                values = f.in[x | :];
            }
            node_classes {
                node_class BULK(Init, Dyn, Out);
            }
            geometry {
                nodes[:] = BULK;
            }
        """

        with pytest.raises(GeLBExTypeError) as exc_info:
            get_typed_ast(test_code)

        assert "must be compile-time evaluable" in str(exc_info.value.error)

    def test_function_input_shape_expression_rejected(self):
        """Function input declarations validate array shapes."""
        test_code = """
            simulation_description("Test function input shape");
            lattices {
                lattice f(1, 1, int, 32, false);
            }
            function BadIn(array[int, 1/0] values) -> (int result) {
                result = 0;
            }
            initializer Init {
                f.out[x | 0] = 0;
            }
            dynamic Dyn {
                f.out[x | 0] = f.in[x | 0];
            }
            gauge Out -> (int val) {
                val = f.in[x | 0];
            }
            node_classes {
                node_class BULK(Init, Dyn, Out);
            }
            geometry {
                nodes[:] = BULK;
            }
        """

        with pytest.raises(GeLBExTypeError) as exc_info:
            get_typed_ast(test_code)

        assert "must be compile-time evaluable" in str(exc_info.value.error)

    def test_function_output_shape_expression_rejected(self):
        """Function output declarations validate array shapes."""
        test_code = """
            simulation_description("Test function output shape");
            lattices {
                lattice f(1, 1, int, 32, false);
            }
            function BadOut(int value) -> (array[int, 1/0] result) {
                result = {1, 2};
            }
            initializer Init {
                f.out[x | 0] = 0;
            }
            dynamic Dyn {
                f.out[x | 0] = f.in[x | 0];
            }
            gauge Out -> (int val) {
                val = f.in[x | 0];
            }
            node_classes {
                node_class BULK(Init, Dyn, Out);
            }
            geometry {
                nodes[:] = BULK;
            }
        """

        with pytest.raises(GeLBExTypeError) as exc_info:
            get_typed_ast(test_code)

        assert "must be compile-time evaluable" in str(exc_info.value.error)


class TestCompileTimeRangeRestrictions:
    """Test that runtime expressions in ranges are properly rejected."""
    
    def test_variable_in_range_rejected(self):
        """Test that variables in ranges are rejected."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[int, {5, 7}] matrix;
                int start_idx;
                int elem;
                start_idx = 2;
                elem = matrix[start_idx, 3];
            """
        )
        
        # Should raise an exception during type inference
        with pytest.raises(GeLBException) as exc_info:
            get_typed_ast(test_code)
        
        assert "must be compile-time evaluable" in str(exc_info.value.error)
    
    def test_variable_in_range_bound_rejected(self):
        """Test that variables in range bounds are rejected."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[real, {10, 10}] matrix;
                int end_idx;
                array[real, 5] slice;
                end_idx = 8;
                slice = matrix[2, 3:end_idx];
            """
        )
        
        # Should raise an exception during type inference
        with pytest.raises(GeLBException) as exc_info:
            get_typed_ast(test_code)
        
        assert "must be compile-time evaluable" in str(exc_info.value.error)
    
    def test_complex_expression_with_variables_rejected(self):
        """Test that complex expressions with variables are rejected."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[int, {10, 10}] matrix;
                int x;
                int y;
                int elem;
                x = 3;
                y = 5;
                elem = matrix[x+1, y*2];
            """
        )
        
        # Should raise an exception during type inference
        with pytest.raises(GeLBException) as exc_info:
            get_typed_ast(test_code)
        
        assert "must be compile-time evaluable" in str(exc_info.value.error)


class TestLatticeRangeValidation:
    """Test compile-time validation for lattice selection ranges."""
    
    def test_lattice_literal_ranges_allowed(self):
        """Test that literal ranges in lattice selections are allowed."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                f.out[x|0:2] = 1.0;
            """
        )
        
        # Should not raise any exception
        ast = get_typed_ast(test_code)
        
        # Find the lattice assignment
        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[0]  # f.out[x|0:2] = 1.0
        
        # Should have correct type
        lattice_selection = assignment.lhs
        assert isinstance(lattice_selection.inferred_type, ArrayDataType_N)
    
    def test_lattice_full_df_range_allowed(self):
        """Test that full DF ranges in lattice selections are allowed."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                f.out[x|:] = 0.0;
            """
        )
        
        # Should not raise any exception
        ast = get_typed_ast(test_code)
        
        # Find the lattice assignment  
        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[0]  # f.out[x|:] = 0.0
        
        # Should have correct type
        lattice_selection = assignment.lhs
        assert isinstance(lattice_selection.inferred_type, ArrayDataType_N)


class TestEdgeCases:
    """Test edge cases for compile-time range validation."""
    
    def test_open_ended_ranges_allowed(self):
        """Test that open-ended ranges are allowed."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[real, {10, 12}] matrix;
                array[real, 5] tail;
                tail = matrix[3, 7:];
            """
        )
        
        # Should not raise any exception
        ast = get_typed_ast(test_code)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[2]  # tail = matrix[3, 7:]
        
        # Should have correct reduced type
        matrix_selection = assignment.rhs
        assert isinstance(matrix_selection.inferred_type, ArrayDataType_N)
        assert matrix_selection.inferred_type.element_dtype == "real"
        assert isinstance(matrix_selection.inferred_type.shape, IntLiteral_N)
        assert matrix_selection.inferred_type.shape.value == 5  # 7: from 12-element dimension = 5 elements
    
    def test_full_ranges_allowed(self):
        """Test that full ranges (:) are allowed."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[int, {8, 6}] matrix;
                array[int, 8] column;
                column = matrix[:, 3];
            """
        )
        
        # Should not raise any exception
        ast = get_typed_ast(test_code)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[2]  # column = matrix[:, 3]
        
        # Should have correct reduced type
        matrix_selection = assignment.rhs
        assert isinstance(matrix_selection.inferred_type, ArrayDataType_N)
        assert matrix_selection.inferred_type.element_dtype == "int"
        assert isinstance(matrix_selection.inferred_type.shape, IntLiteral_N)
        assert matrix_selection.inferred_type.shape.value == 8  # Full first dimension
    
    def test_nested_constant_expressions_allowed(self):
        """Test that nested arithmetic with constants is allowed."""
        test_code = minimal_gelb_program_1d(
            global_constants_content="""
                const int BASE = 4;
                const int MULT = 2;
            """,
            initializer_content="""
                array[real, {20, 15}] matrix;
                array[real, 6] slice;
                slice = matrix[BASE*MULT+1, (BASE+1)*MULT-1:(BASE+1)*MULT+4];
            """
        )
        
        # Should not raise any exception
        ast = get_typed_ast(test_code)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[2]
        
        # Should have correct reduced type
        matrix_selection = assignment.rhs
        assert isinstance(matrix_selection.inferred_type, ArrayDataType_N)
        assert matrix_selection.inferred_type.element_dtype == "real"
        assert isinstance(matrix_selection.inferred_type.shape, IntLiteral_N)
        assert matrix_selection.inferred_type.shape.value == 6  # Range size
