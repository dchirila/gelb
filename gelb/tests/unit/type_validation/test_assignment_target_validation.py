#!/usr/bin/env python3
"""
Unit tests for assignment target validation - improved error messages.

Tests that assignment validation provides clear, user-friendly error messages
when trying to assign incompatible types (especially array to scalar).
"""

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.tests.test_utils import get_fully_validated_ast, minimal_gelb_program_1d
from gelb.utils.exceptions import GeLBExTypeError


class TestAssignmentTargetValidation:
    """Test validation of assignment targets with improved error messages."""
    
    def test_valid_scalar_to_scalar_assignment(self):
        """Test that valid scalar assignments work."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                real a = 3.14;
                real b;
                b = a;  // Valid: scalar to scalar
                f.out[x | 0] = 0;
            """
        )
        
        # Should succeed without exception
        ast = get_fully_validated_ast(test_code)
        assert ast is not None
    
    def test_array_to_scalar_assignment_rejected(self):
        """Test that array to scalar assignment is rejected with clear error."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[real, {2, 2}] matrix;
                real scalar;
                scalar = matrix;  // Invalid: array to scalar
                f.out[x | 0] = 0;
            """
        )
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_fully_validated_ast(test_code)
        
        error = exc_info.value
        assert "Cannot assign array[real, {2, 2}] to scalar 'real'" in str(error.error)
        assert "Scalars cannot hold array values" in str(error.hint)
        assert "array indexing" in str(error.hint)
    
    def test_scalar_to_array_assignment_accepted(self):
        """Test that scalar to array assignment is handled by broadcasting system."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                real scalar = 3.14;
                array[real, 3] vector;
                vector = scalar;  // Valid: scalar to array broadcasting
                f.out[x | 0] = 0;
            """
        )
        
        # Should succeed - broadcasting system handles scalar to array assignment
        ast = get_fully_validated_ast(test_code)
        assert ast is not None
    
    def test_1d_array_assignment_error_message(self):
        """Test 1D array assignment error messages."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[int, 5] vector;
                int scalar;
                scalar = vector;  // Invalid: 1D array to scalar
                f.out[x | 0] = 0;
            """
        )
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_fully_validated_ast(test_code)
        
        error = exc_info.value
        assert "Cannot assign array[int, 5] to scalar 'int'" in str(error.error)
        assert "Scalars cannot hold array values" in str(error.hint)
    
    def test_3d_array_assignment_error_message(self):
        """Test 3D array assignment error messages."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[bool, {3, 4, 5}] tensor;
                bool flag;
                flag = tensor;  // Invalid: 3D array to scalar
                f.out[x | 0] = 0;
            """
        )
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_fully_validated_ast(test_code)
        
        error = exc_info.value
        # Check error structure
        assert hasattr(error, 'error')
        assert hasattr(error, 'hint')
        assert hasattr(error, 'node')
        
        # Check content
        assert "Cannot assign array[bool, {3, 4, 5}] to scalar 'bool'" in str(error.error)
        assert "array indexing" in str(error.hint)
        assert "[0, 1]" in str(error.hint)  # Example indexing
    
    def test_valid_array_element_assignment(self):
        """Test that valid array element access works."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[real, {2, 2}] matrix;
                real scalar;
                scalar = matrix[0, 1];  // Valid: array element to scalar
                f.out[x | 0] = 0;
            """
        )
        
        # Should succeed without exception
        ast = get_fully_validated_ast(test_code)
        assert ast is not None
    
    def test_type_promotion_still_works(self):
        """Test that type promotion still works with improved error messages."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                int int_val = 42;
                real real_var;
                real_var = int_val;  // Valid: int → real promotion
                f.out[x | 0] = 0;
            """
        )
        
        # Should succeed - promotion should handle this
        ast = get_fully_validated_ast(test_code)
        assert ast is not None