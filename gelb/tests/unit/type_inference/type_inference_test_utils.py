#!/usr/bin/env python3
"""
Type inference test utilities.

This module provides utilities specific to type inference validation and testing.
"""

def get_typed_ast(gelb_code):
    """
    Helper to get a fully typed AST from GeLB code.
    
    Args:
        gelb_code (str): Complete GeLB program code
        
    Returns:
        AST with type inference applied
    """
    from gelb.tests.test_utils import get_typed_ast as main_get_typed_ast
    return main_get_typed_ast(gelb_code)


def minimal_gelb_program_1d(global_constants_content=""):
    """
    Generate a minimal valid 1D GeLB program with custom global constants.
    
    Args:
        global_constants_content (str): Content for the global_constants block
        
    Returns:
        str: Complete GeLB program
    """
    # Use the same template as the original test_utils.py
    from gelb.tests.test_utils import minimal_gelb_program_1d as main_minimal_1d
    return main_minimal_1d(global_constants_content)


def minimal_gelb_program_2d(global_constants_content=""):
    """
    Generate a minimal valid 2D GeLB program with custom global constants.
    
    Args:
        global_constants_content (str): Content for the global_constants block
        
    Returns:
        str: Complete GeLB program
    """
    # Use the same template as the original test_utils.py  
    from gelb.tests.test_utils import minimal_gelb_program_2d as main_minimal_2d
    return main_minimal_2d(global_constants_content)


def get_literal_type_inference_test_data():
    """Return test data for literal type inference tests."""
    return [
        # Scalar literals
        ("int_literal", "const int x = 42;", "int", 42),
        ("real_literal", "const real pi = 3.14159;", "real", 3.14159),
        ("bool_literal_true", "const bool flag = true;", "bool", True),
        ("bool_literal_false", "const bool flag = false;", "bool", False),
        
        # Array literals
        ("array_1d_int", "const array[int, 3] vec = {1, 2, 3};", "int", [1, 2, 3]),
        ("array_1d_real", "const array[real, 3] vec = {1.0, 2.5, 3.14};", "real", [1.0, 2.5, 3.14]),
        ("array_1d_bool", "const array[bool, 3] flags = {true, false, true};", "bool", [True, False, True]),
        
        ("array_2d_int", "const array[int, {2, 3}] mat = {{1, 2, 3}, {4, 5, 6}};", "int", [[1, 2, 3], [4, 5, 6]]),
        ("array_2d_real", "const array[real, {2, 2}] mat = {{1.0, 2.0}, {3.0, 4.0}};", "real", [[1.0, 2.0], [3.0, 4.0]]),
    ]


def get_expression_type_inference_test_data():
    """Return test data for expression type inference tests."""
    return [
        # Arithmetic expressions
        ("int_addition", "const int result = 5 + 3;", "int", 8),
        ("int_multiplication", "const int result = 6 * 7;", "int", 42),
        ("real_addition", "const real result = 2.5 + 3.7;", "real", 6.2),
        ("real_multiplication", "const real result = 3.14 * 2.0;", "real", 6.28),
        
        # Boolean expressions
        ("bool_and", "const bool result = true && false;", "bool", False),
        ("bool_or", "const bool result = true || false;", "bool", True),
        ("bool_not", "const bool result = !true;", "bool", False),
        
        # Comparison expressions
        ("int_comparison_lt", "const bool result = 5 < 10;", "bool", True),
        ("int_comparison_eq", "const bool result = 7 == 7;", "bool", True),
        ("real_comparison_gt", "const bool result = 3.14 > 2.71;", "bool", True),
        
        # Mixed type expressions (should use type promotion rules)
        ("int_real_addition", "const real result = 5 + 3.0;", "real", 8.0),
        ("real_int_multiplication", "const real result = 2.5 * 4;", "real", 10.0),
    ]


def get_identifier_type_inference_test_data():
    """Return test data for identifier type inference tests."""
    return [
        # Simple identifier references
        ("int_reference", 
         """
         const int N = 32;
         const int doubled = N * 2;
         """, "doubled", "int", 64),
        
        ("real_reference",
         """
         const real PI = 3.14159;
         const real TAU = PI * 2;
         """, "TAU", "real", 6.28318),
        
        ("bool_reference",
         """
         const bool flag1 = true;
         const bool flag2 = !flag1;
         """, "flag2", "bool", False),
        
        # Array type references
        ("array_reference",
         """
         const array[int, 3] vec1 = {1, 2, 3};
         const array[int, 3] vec2 = vec1;
         """, "vec2", "array[int, 3]", [1, 2, 3]),
    ]


def get_array_access_type_inference_test_data():
    """Return test data for array access type inference tests."""
    return [
        # 1D array access
        ("array_1d_element", 
         """
         const array[int, 5] arr = {10, 20, 30, 40, 50};
         const int element = arr[2];
         """, "element", "int", 30),
        
        ("array_1d_slice",
         """
         const array[real, 5] arr = {1.0, 2.0, 3.0, 4.0, 5.0};
         const array[real, 3] slice = arr[1:4];
         """, "slice", "array[real, 3]", [2.0, 3.0, 4.0]),
        
        # 2D array access
        ("array_2d_element",
         """
         const array[int, {3, 3}] matrix = {{1, 2, 3}, {4, 5, 6}, {7, 8, 9}};
         const int element = matrix[1, 2];
         """, "element", "int", 6),
        
        ("array_2d_row",
         """
         const array[real, {2, 3}] matrix = {{1.0, 2.0, 3.0}, {4.0, 5.0, 6.0}};
         const array[real, 3] row = matrix[0, :];
         """, "row", "array[real, 3]", [1.0, 2.0, 3.0]),
    ]


def get_lattice_access_type_inference_test_data():
    """Return test data for lattice access type inference tests."""
    return [
        # Simple lattice access  
        ("lattice_in_single_df",
         """
         lattice f(2, 9, real);
         const real value = f.in[x, y | 0];
         """, "value", "real"),
        
        ("lattice_out_single_df",
         """
         lattice f(2, 9, int);
         const int value = f.out[x, y | 5];
         """, "value", "int"),
        
        # Lattice range access
        ("lattice_in_df_range",
         """
         lattice f(1, 3, real);
         const array[real, 3] df_vector = f.in[x | :];
         """, "df_vector", "array[real, 3]"),
        
        ("lattice_out_df_range",
         """
         lattice f(2, 9, int);
         const array[int, 5] df_slice = f.out[x, y | 2:7];
         """, "df_slice", "array[int, 5]"),
    ]