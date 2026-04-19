#!/usr/bin/env python3

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.tests.test_utils import get_typed_ast, minimal_gelb_program_1d


class TestIntrinsicFunctionTypeInference:
    """Test type inference for intrinsic functions."""
    
    def test_sum_function_type_inference_1d_array(self):
        """Test that sum() with 1D array infers correct return type."""
        test_string = minimal_gelb_program_1d(
            global_constants_content='const array[int, 5] data = {1, 2, 3, 4, 5};',
            dynamic_content='int result = sum(data);'
        )
        
        ast_root = get_typed_ast(test_string)
        
        # Find the sum() call in the dynamic block
        dynamic_block = ast_root.dynamics.elements[0]
        var_decl = dynamic_block.stmts.elements[0]  # int result = sum(data);
        sum_call = var_decl.initial_value  # sum(data)
        
        # Check that it's an intrinsic function call
        assert isinstance(sum_call, IntrinsicFunctionCall_N)
        assert sum_call.function_name == "sum"
        
        # Check that return type is scalar int (0-dimensional array)
        assert hasattr(sum_call, 'inferred_type')
        return_type = sum_call.inferred_type
        assert isinstance(return_type, ArrayDataType_N)
        assert return_type.element_dtype == "int"
        assert len(return_type.shape.elements) == 0  # Scalar
    
    def test_sum_function_type_inference_real_array(self):
        """Test that sum() with real array returns real scalar."""
        test_string = minimal_gelb_program_1d(
            global_constants_content='const array[real, 3] data = {1.0, 2.0, 3.0};',
            dynamic_content='real result = sum(data);'
        )
        
        ast_root = get_typed_ast(test_string)
        
        # Find the sum() call
        dynamic_block = ast_root.dynamics.elements[0]
        var_decl = dynamic_block.stmts.elements[0]
        sum_call = var_decl.initial_value
        
        # Check return type is scalar real
        return_type = sum_call.inferred_type
        assert isinstance(return_type, ArrayDataType_N)
        assert return_type.element_dtype == "real"
        assert len(return_type.shape.elements) == 0  # Scalar
    
    def test_dot_prod_function_type_inference_same_types(self):
        """Test that dot_prod() with same types returns correct type."""
        test_string = minimal_gelb_program_1d(
            global_constants_content='''
                const array[int, 3] a = {1, 2, 3};
                const array[int, 3] b = {4, 5, 6};
            ''',
            dynamic_content='int result = dot_prod(a, b);'
        )
        
        ast_root = get_typed_ast(test_string)
        
        # Find the dot_prod() call
        dynamic_block = ast_root.dynamics.elements[0]
        var_decl = dynamic_block.stmts.elements[0]
        dot_prod_call = var_decl.initial_value
        
        # Check that it's an intrinsic function call
        assert isinstance(dot_prod_call, IntrinsicFunctionCall_N)
        assert dot_prod_call.function_name == "dot_prod"
        
        # Check return type is scalar int
        return_type = dot_prod_call.inferred_type
        assert isinstance(return_type, ArrayDataType_N)
        assert return_type.element_dtype == "int"
        assert len(return_type.shape.elements) == 0  # Scalar
    
    def test_dot_prod_function_type_promotion(self):
        """Test that dot_prod() promotes int and real to real."""
        test_string = minimal_gelb_program_1d(
            global_constants_content='''
                const array[int, 3] a = {1, 2, 3};
                const array[real, 3] b = {4.0, 5.0, 6.0};
            ''',
            dynamic_content='real result = dot_prod(a, b);'
        )
        
        ast_root = get_typed_ast(test_string)
        
        # Find the dot_prod() call
        dynamic_block = ast_root.dynamics.elements[0]
        var_decl = dynamic_block.stmts.elements[0]
        dot_prod_call = var_decl.initial_value
        
        # Check return type is promoted to real
        return_type = dot_prod_call.inferred_type
        assert isinstance(return_type, ArrayDataType_N)
        assert return_type.element_dtype == "real"
        assert len(return_type.shape.elements) == 0  # Scalar
    
    def test_nested_intrinsic_function_calls(self):
        """Test that intrinsic functions can be nested."""
        test_string = minimal_gelb_program_1d(
            global_constants_content='''
                const array[real, 3] a = {1.0, 2.0, 3.0};
                const array[real, 3] b = {4.0, 5.0, 6.0};
                const array[real, 2] nested = {dot_prod(a, b), sum(a)};
            ''',
            dynamic_content='real total = sum(nested);'
        )
        
        ast_root = get_typed_ast(test_string)
        
        # Find the nested array with intrinsic function calls
        global_constants = ast_root.global_constants
        nested_const = global_constants.stmts.elements[2]  # const array[real, 2] nested = ...
        nested_array = nested_const.value  # {dot_prod(a, b), sum(a)}
        
        # Check first element - dot_prod(a, b)
        dot_prod_call = nested_array.value.elements[0]
        assert isinstance(dot_prod_call, IntrinsicFunctionCall_N)
        assert dot_prod_call.function_name == "dot_prod"
        assert dot_prod_call.inferred_type.element_dtype == "real"
        
        # Check second element - sum(a)
        sum_call = nested_array.value.elements[1]
        assert isinstance(sum_call, IntrinsicFunctionCall_N)
        assert sum_call.function_name == "sum"
        assert sum_call.inferred_type.element_dtype == "real"
        
        # Check final sum call
        dynamic_block = ast_root.dynamics.elements[0]
        var_decl = dynamic_block.stmts.elements[0]
        final_sum = var_decl.initial_value
        assert isinstance(final_sum, IntrinsicFunctionCall_N)
        assert final_sum.function_name == "sum"
        assert final_sum.inferred_type.element_dtype == "real"

    def test_random_function_type_inference(self):
        """Test that random() infers scalar real return type."""
        test_string = minimal_gelb_program_1d(
            dynamic_content='real r = random();'
        )

        ast_root = get_typed_ast(test_string)

        dynamic_block = ast_root.dynamics.elements[0]
        var_decl = dynamic_block.stmts.elements[0]
        random_call = var_decl.initial_value

        assert isinstance(random_call, IntrinsicFunctionCall_N)
        assert random_call.function_name == "random"

        return_type = random_call.inferred_type
        assert isinstance(return_type, ArrayDataType_N)
        assert return_type.element_dtype == "real"
        assert len(return_type.shape.elements) == 0  # Scalar