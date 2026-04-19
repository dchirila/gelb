#!/usr/bin/env python3

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.tests.test_utils import get_typed_ast, minimal_gelb_program_1d
from gelb.utils.exceptions import GeLBExTypeError


class TestIntrinsicFunctionValidation:
    """Test validation errors for intrinsic functions."""
    
    def test_sum_wrong_argument_count_too_few(self):
        """Test that sum() with no arguments raises an error."""
        test_string = minimal_gelb_program_1d(
            dynamic_content='int result = sum();'
        )
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_typed_ast(test_string)
        
        assert "expects exactly 1 argument, got 0" in str(exc_info.value)
    
    def test_sum_wrong_argument_count_too_many(self):
        """Test that sum() with too many arguments raises an error."""
        test_string = minimal_gelb_program_1d(
            global_constants_content='''
                const array[int, 3] a = {1, 2, 3};
                const array[int, 3] b = {4, 5, 6};
            ''',
            dynamic_content='int result = sum(a, b);'
        )
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_typed_ast(test_string)
        
        assert "expects exactly 1 argument, got 2" in str(exc_info.value)
    
    def test_sum_scalar_argument_error(self):
        """Test that sum() with scalar argument raises an error."""
        test_string = minimal_gelb_program_1d(
            global_constants_content='const int x = 42;',
            dynamic_content='int result = sum(x);'
        )
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_typed_ast(test_string)
        
        assert "expects an array argument, got scalar" in str(exc_info.value)
    
    def test_sum_non_numeric_array_error(self):
        """Test that sum() with non-numeric array raises an error."""
        test_string = minimal_gelb_program_1d(
            global_constants_content='const array[bool, 3] flags = {true, false, true};',
            dynamic_content='int result = sum(flags);'
        )
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_typed_ast(test_string)
        
        assert "expects numeric array, got array[bool" in str(exc_info.value)
    
    def test_dot_prod_wrong_argument_count_too_few(self):
        """Test that dot_prod() with one argument raises an error."""
        test_string = minimal_gelb_program_1d(
            global_constants_content='const array[int, 3] a = {1, 2, 3};',
            dynamic_content='int result = dot_prod(a);'
        )
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_typed_ast(test_string)
        
        assert "expects exactly 2 arguments, got 1" in str(exc_info.value)
    
    def test_dot_prod_wrong_argument_count_too_many(self):
        """Test that dot_prod() with too many arguments raises an error."""
        test_string = minimal_gelb_program_1d(
            global_constants_content='''
                const array[int, 3] a = {1, 2, 3};
                const array[int, 3] b = {4, 5, 6};
                const array[int, 3] c = {7, 8, 9};
            ''',
            dynamic_content='int result = dot_prod(a, b, c);'
        )
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_typed_ast(test_string)
        
        assert "expects exactly 2 arguments, got 3" in str(exc_info.value)
    
    def test_dot_prod_scalar_arguments_error(self):
        """Test that dot_prod() with scalar arguments raises an error."""
        test_string = minimal_gelb_program_1d(
            global_constants_content='''
                const int x = 1;
                const int y = 2;
            ''',
            dynamic_content='int result = dot_prod(x, y);'
        )
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_typed_ast(test_string)
        
        assert "expects array arguments, got scalar" in str(exc_info.value)
    
    def test_dot_prod_mixed_scalar_array_error(self):
        """Test that dot_prod() with mixed scalar and array raises an error."""
        test_string = minimal_gelb_program_1d(
            global_constants_content='''
                const array[int, 3] a = {1, 2, 3};
                const int x = 42;
            ''',
            dynamic_content='int result = dot_prod(a, x);'
        )
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_typed_ast(test_string)
        
        assert "expects array arguments, got scalar" in str(exc_info.value)
    
    def test_dot_prod_non_numeric_arrays_error(self):
        """Test that dot_prod() with non-numeric arrays raises an error."""
        test_string = minimal_gelb_program_1d(
            global_constants_content='''
                const array[bool, 3] a = {true, false, true};
                const array[bool, 3] b = {false, true, false};
            ''',
            dynamic_content='int result = dot_prod(a, b);'
        )
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_typed_ast(test_string)
        
        assert "expects numeric arrays, got array[bool" in str(exc_info.value)
    
    def test_dot_prod_dimension_mismatch_error(self):
        """Test that dot_prod() with a matrix operand raises an error.

        dot_prod takes vectors: the matrix is reported as such, whatever
        the other operand.
        """
        test_string = minimal_gelb_program_1d(
            global_constants_content='''
                const array[int, 3] a = {1, 2, 3};
                const array[int, {2, 2}] b = {{1, 2}, {3, 4}};
            ''',
            dynamic_content='int result = dot_prod(a, b);'
        )
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_typed_ast(test_string)
        
        assert "takes vectors; argument 2 is a 2-dimensional array" in str(exc_info.value)
    
    def test_unknown_intrinsic_function_error(self):
        """Test that unknown intrinsic function raises an error."""
        # Note: This would require modifying the grammar to allow unknown function names
        # For now, this test documents the expected behavior
        pass
    
    def test_sum_with_lattice_selection_valid(self):
        """Test that sum() works with lattice selections (should be valid)."""
        test_string = minimal_gelb_program_1d(
            dynamic_content='real result = sum(f.in[x|:]);'
        )
        
        # This should not raise an error since lattice selections are arrays
        ast_root = get_typed_ast(test_string)
        
        # Find the sum() call
        dynamic_block = ast_root.dynamics.elements[0]
        var_decl = dynamic_block.stmts.elements[0]
        sum_call = var_decl.initial_value
        
        # Check that it's properly typed
        assert isinstance(sum_call, IntrinsicFunctionCall_N)
        assert sum_call.function_name == "sum"
        assert hasattr(sum_call, 'inferred_type')
        assert sum_call.inferred_type.element_dtype == "int"  # lattice df_type is int in minimal_gelb_program_1d

    def test_random_wrong_argument_count(self):
        """Test that random() with arguments raises an error."""
        test_string = minimal_gelb_program_1d(
            dynamic_content='real r = random(42);'
        )

        with pytest.raises(GeLBExTypeError) as exc_info:
            get_typed_ast(test_string)

        assert "expects exactly 0 arguments, got 1" in str(exc_info.value)