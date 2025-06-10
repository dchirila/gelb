#!/usr/bin/env python3
"""
Unit tests for array range selection shape reduction functionality.

Tests that array range selections properly reduce their shape based on the ranges provided.
"""

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.utils.exceptions import GeLBException
from gelb.tests.test_utils import (
    get_typed_ast,
    minimal_gelb_program_1d,
    minimal_gelb_program_2d
)


class TestArrayRangeShapeReduction:
    """Test array range selection shape reduction."""
    
    def test_single_element_selection_2d_to_scalar(self):
        """Test that single element selection from 2D array results in scalar."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[real, {3, 4}] matrix;
                real scalar;
                scalar = matrix[1, 2];
            """
        )
        
        ast = get_typed_ast(test_code)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[2]  # scalar = matrix[1, 2]
        
        # Check that RHS is scalar (0D array)
        matrix_selection = assignment.rhs
        assert isinstance(matrix_selection, RectSelOfArrayElems_N)
        assert isinstance(matrix_selection.inferred_type, ArrayDataType_N)
        assert matrix_selection.inferred_type.element_dtype == "real"
        assert isinstance(matrix_selection.inferred_type.shape, List_N)
        assert len(matrix_selection.inferred_type.shape.elements) == 0  # Scalar
    
    def test_mixed_selection_2d_to_1d(self):
        """Test that mixed selection (single element + range) reduces dimension."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[real, {3, 4}] matrix;
                array[real, 4] row;
                row = matrix[1, :];
            """
        )
        
        ast = get_typed_ast(test_code)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[2]  # row = matrix[1, :]
        
        # Check that RHS is 1D array of size 4
        matrix_selection = assignment.rhs
        assert isinstance(matrix_selection, RectSelOfArrayElems_N)
        assert isinstance(matrix_selection.inferred_type, ArrayDataType_N)
        assert matrix_selection.inferred_type.element_dtype == "real"
        assert isinstance(matrix_selection.inferred_type.shape, IntLiteral_N)
        assert matrix_selection.inferred_type.shape.value == 4
    
    def test_partial_range_selection(self):
        """Test that partial range selection calculates correct size."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[int, {5, 7}] matrix;
                array[int, 3] slice;
                slice = matrix[2, 1:3];
            """
        )
        
        ast = get_typed_ast(test_code)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[2]  # slice = matrix[2, 1:3]
        
        # Check that RHS is 1D array of size 3 (elements 1, 2, 3)
        matrix_selection = assignment.rhs
        assert isinstance(matrix_selection, RectSelOfArrayElems_N)
        assert isinstance(matrix_selection.inferred_type, ArrayDataType_N)
        assert matrix_selection.inferred_type.element_dtype == "int"
        assert isinstance(matrix_selection.inferred_type.shape, IntLiteral_N)
        assert matrix_selection.inferred_type.shape.value == 3
    
    def test_open_ended_range_selection(self):
        """Test that open-ended range selection works correctly."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[real, {5, 7}] matrix;
                array[real, 2] tail;
                tail = matrix[3, 5:];
            """
        )
        
        ast = get_typed_ast(test_code)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[2]  # tail = matrix[3, 5:]
        
        # Check that RHS is 1D array of size 2 (elements 5, 6 from 0-6 range)
        matrix_selection = assignment.rhs
        assert isinstance(matrix_selection, RectSelOfArrayElems_N)
        assert isinstance(matrix_selection.inferred_type, ArrayDataType_N)
        assert matrix_selection.inferred_type.element_dtype == "real"
        assert isinstance(matrix_selection.inferred_type.shape, IntLiteral_N)
        assert matrix_selection.inferred_type.shape.value == 2
    
    def test_multiple_range_selection_2d_to_2d(self):
        """Test that multiple range selections preserve appropriate dimensions."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[int, {5, 7}] matrix;
                array[int, {2, 3}] submatrix;
                submatrix = matrix[1:2, 2:4];
            """
        )
        
        ast = get_typed_ast(test_code)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[2]  # submatrix = matrix[1:2, 2:4]
        
        # Check that RHS is 2D array of size {2, 3}
        matrix_selection = assignment.rhs
        assert isinstance(matrix_selection, RectSelOfArrayElems_N)
        assert isinstance(matrix_selection.inferred_type, ArrayDataType_N)
        assert matrix_selection.inferred_type.element_dtype == "int"
        assert isinstance(matrix_selection.inferred_type.shape, Array1DLiteral_N)
        
        shape_elements = matrix_selection.inferred_type.shape.value.elements
        assert len(shape_elements) == 2
        assert shape_elements[0].value == 2  # 1:2 gives elements 1,2
        assert shape_elements[1].value == 3  # 2:4 gives elements 2,3,4
    
    def test_full_dimension_range_selection(self):
        """Test that full dimension range (:) preserves dimension size."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[real, {3, 4}] matrix;
                array[real, 3] column;
                column = matrix[:, 2];
            """
        )
        
        ast = get_typed_ast(test_code)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[2]  # column = matrix[:, 2]
        
        # Check that RHS is 1D array of size 3 (full first dimension)
        matrix_selection = assignment.rhs
        assert isinstance(matrix_selection, RectSelOfArrayElems_N)
        assert isinstance(matrix_selection.inferred_type, ArrayDataType_N)
        assert matrix_selection.inferred_type.element_dtype == "real"
        assert isinstance(matrix_selection.inferred_type.shape, IntLiteral_N)
        assert matrix_selection.inferred_type.shape.value == 3
    
    def test_assignment_compatibility_after_reduction(self):
        """Test that reduced shapes work correctly in assignments."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[real, {2, 3}] a;
                array[real, {5, 7}] b;
                a[1, 0:2] = b[3, 5:];
            """
        )
        
        # This should not raise any exceptions during type inference
        ast = get_typed_ast(test_code)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[2]  # a[1, 0:2] = b[3, 5:]
        
        # Both sides should be 1D arrays
        lhs = assignment.lhs
        rhs = assignment.rhs
        
        # LHS: a[1, 0:2] should be array[real, {3}]
        assert isinstance(lhs.inferred_type, ArrayDataType_N)
        assert lhs.inferred_type.element_dtype == "real"
        assert isinstance(lhs.inferred_type.shape, IntLiteral_N)
        assert lhs.inferred_type.shape.value == 3
        
        # RHS: b[3, 5:] should be array[real, {2}]
        assert isinstance(rhs.inferred_type, ArrayDataType_N)
        assert rhs.inferred_type.element_dtype == "real"
        assert isinstance(rhs.inferred_type.shape, IntLiteral_N)
        assert rhs.inferred_type.shape.value == 2


class TestArrayRangeEdgeCases:
    """Test edge cases for array range selection."""
    
    def test_1d_array_single_element(self):
        """Test single element selection from 1D array."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[int, 5] vec;
                int elem;
                elem = vec[3];
            """
        )
        
        ast = get_typed_ast(test_code)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[2]  # elem = vec[3]
        
        # Should be scalar
        vec_selection = assignment.rhs
        assert isinstance(vec_selection.inferred_type, ArrayDataType_N)
        assert vec_selection.inferred_type.element_dtype == "int"
        assert len(vec_selection.inferred_type.shape.elements) == 0  # Scalar
    
    def test_1d_array_range_selection(self):
        """Test range selection from 1D array."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[real, 10] vec;
                array[real, 3] slice;
                slice = vec[2:4];
            """
        )
        
        ast = get_typed_ast(test_code)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[2]  # slice = vec[2:4]
        
        # Should be 1D array of size 3
        vec_selection = assignment.rhs
        assert isinstance(vec_selection.inferred_type, ArrayDataType_N)
        assert vec_selection.inferred_type.element_dtype == "real"
        assert isinstance(vec_selection.inferred_type.shape, IntLiteral_N)
        assert vec_selection.inferred_type.shape.value == 3
    
    def test_same_element_range(self):
        """Test range where low == high (single element)."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[int, {3, 4}] matrix;
                array[int, 4] row;
                row = matrix[2:2, :];
            """
        )
        
        ast = get_typed_ast(test_code)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[2]  # row = matrix[2:2, :]
        
        # Should be 1D array of size 4 (second dimension preserved)
        matrix_selection = assignment.rhs
        assert isinstance(matrix_selection.inferred_type, ArrayDataType_N)
        assert matrix_selection.inferred_type.element_dtype == "int"
        assert isinstance(matrix_selection.inferred_type.shape, IntLiteral_N)
        assert matrix_selection.inferred_type.shape.value == 4


class TestArrayRangeErrorCases:
    """Test error conditions for array range selection."""
    
    def test_too_many_indices_error(self):
        """Test error when providing too many indices."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[int, {2, 3}] matrix;
                int elem;
                elem = matrix[0, 1, 2];
            """
        )
        
        # This should raise an exception during type inference
        with pytest.raises(GeLBException) as exc_info:
            get_typed_ast(test_code)
        
        # Updated to match the new improved error message format
        assert "Cannot index" in str(exc_info.value.error) and "with 3 indices" in str(exc_info.value.error)
    
    def test_negative_range_size_fallback(self):
        """Test fallback behavior for invalid ranges."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[int, 5] vec;
                array[int, 1] invalid;
                invalid = vec[4:2];
            """
        )
        
        # Should not crash, should provide fallback behavior
        ast = get_typed_ast(test_code)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assignment = init_block.stmts.elements[2]  # invalid = vec[4:2]
        
        # Should have some reasonable fallback type
        vec_selection = assignment.rhs
        assert isinstance(vec_selection.inferred_type, ArrayDataType_N)
        assert vec_selection.inferred_type.element_dtype == "int"