#!/usr/bin/env python3

from gelb.gelb_ast.ASTNodes import *
from gelb.utils.exceptions import *


class IntrinsicFunction:
    """
    Definition of an intrinsic (built-in) function.
    
    Intrinsic functions are pure functions with no side effects that provide
    essential mathematical operations like sum, dot_prod, etc.
    """
    def __init__(self, name, min_args, max_args, type_checker, return_type_computer):
        self.name = name
        self.min_args = min_args  # Minimum number of arguments
        self.max_args = max_args  # Maximum number of arguments (None for unlimited)
        self.type_checker = type_checker  # Function to validate argument types
        self.return_type_computer = return_type_computer  # Function to compute return type


def _check_sum_arguments(function_name, arguments, node):
    """
    Check that sum() has exactly one array argument of numeric type.
    
    Args:
        function_name: Name of the function ('sum')
        arguments: List of argument expressions
        node: The IntrinsicFunctionCall_N node for error reporting
    
    Raises:
        GeLBExTypeError: If arguments are invalid
    """
    # Check argument count
    if len(arguments) != 1:
        raise GeLBExTypeError(
            node,
            f"Function '{function_name}' expects exactly 1 argument, got {len(arguments)}",
            f"Usage: {function_name}(array_expression)"
        )
    
    # Check that argument has been type-inferred
    arg = arguments[0]
    if not hasattr(arg, 'inferred_type') or arg.inferred_type is None:
        raise GeLBException(
            f"Argument to '{function_name}' has no inferred type",
            "This is likely an internal compiler error - type inference should run before validation"
        )
    
    # Check that argument is an array (not scalar)
    arg_type = arg.inferred_type
    if not isinstance(arg_type, ArrayDataType_N):
        raise GeLBExTypeError(
            node,
            f"Function '{function_name}' expects an array argument, got non-array type",
            f"The argument to {function_name}() must be an array, not a scalar or other type"
        )
    
    # Check that it's not a scalar (0-dimensional array)
    # Handle different shape representations
    is_scalar = False
    if isinstance(arg_type.shape, List_N):
        # Multi-dimensional arrays use List_N for shape
        is_scalar = len(arg_type.shape.elements) == 0
    elif isinstance(arg_type.shape, IntLiteral_N):
        # 1D arrays use IntLiteral_N for shape - these are not scalars
        is_scalar = False
    else:
        # Unknown shape type - assume not scalar
        is_scalar = False
    
    if is_scalar:
        raise GeLBExTypeError(
            node,
            f"Function '{function_name}' expects an array argument, got scalar '{arg_type.element_dtype}'",
            f"Use {function_name}() with arrays like 'array[int, 5]', not scalars like 'int'"
        )
    
    # Check that element type is numeric
    if arg_type.element_dtype not in ['int', 'int8', 'int16', 'int32', 'int64', 'real', 'real16', 'real32', 'real64']:
        raise GeLBExTypeError(
            node,
            f"Function '{function_name}' expects numeric array, got array[{arg_type.element_dtype}, ...]",
            f"The {function_name}() function can only be used with arrays of numeric types (int, real, etc.), not {arg_type.element_dtype}"
        )


def _compute_sum_return_type(function_name, arguments, node, code_range):
    """
    Compute return type for sum() function.
    
    Returns a scalar (0-dimensional array) of the same element type as the input array.
    
    Args:
        function_name: Name of the function ('sum')
        arguments: List of argument expressions  
        node: The IntrinsicFunctionCall_N node
        code_range: Code range for creating the return type
        
    Returns:
        ArrayDataType_N: Scalar type of the same element type as input array
    """
    arg = arguments[0]
    arg_type = arg.inferred_type
    
    # Return scalar type (0-dimensional array) with same element type
    empty_shape = List_N(code_range)
    return ArrayDataType_N(code_range, arg_type.element_dtype, empty_shape)


def _check_dot_prod_arguments(function_name, arguments, node):
    """
    Check that dot_prod() has exactly two array arguments of compatible types and shapes.
    
    Args:
        function_name: Name of the function ('dot_prod')
        arguments: List of argument expressions
        node: The IntrinsicFunctionCall_N node for error reporting
        
    Raises:
        GeLBExTypeError: If arguments are invalid
    """
    # Check argument count
    if len(arguments) != 2:
        raise GeLBExTypeError(
            node,
            f"Function '{function_name}' expects exactly 2 arguments, got {len(arguments)}",
            f"Usage: {function_name}(array1, array2)"
        )
    
    # Check that both arguments have been type-inferred
    for i, arg in enumerate(arguments):
        if not hasattr(arg, 'inferred_type') or arg.inferred_type is None:
            raise GeLBException(
                f"Argument {i+1} to '{function_name}' has no inferred type",
                "This is likely an internal compiler error - type inference should run before validation"
            )
    
    arg1, arg2 = arguments
    arg1_type, arg2_type = arg1.inferred_type, arg2.inferred_type
    
    # Check that both arguments are arrays
    for i, (arg, arg_type) in enumerate([(arg1, arg1_type), (arg2, arg2_type)]):
        if not isinstance(arg_type, ArrayDataType_N):
            raise GeLBExTypeError(
                node,
                f"Function '{function_name}' expects array arguments, got non-array type for argument {i+1}",
                f"Both arguments to {function_name}() must be arrays"
            )
        
        # Check that it's not a scalar (0-dimensional array)
        # Handle different shape representations
        is_scalar = False
        if isinstance(arg_type.shape, List_N):
            # Multi-dimensional arrays use List_N for shape
            is_scalar = len(arg_type.shape.elements) == 0
        elif isinstance(arg_type.shape, IntLiteral_N):
            # 1D arrays use IntLiteral_N for shape - these are not scalars
            is_scalar = False
        else:
            # Unknown shape type - assume not scalar
            is_scalar = False
        
        if is_scalar:
            raise GeLBExTypeError(
                node,
                f"Function '{function_name}' expects array arguments, got scalar '{arg_type.element_dtype}' for argument {i+1}",
                f"Use {function_name}() with arrays like 'array[int, 5]', not scalars"
            )
        
        # Check that element type is numeric
        if arg_type.element_dtype not in ['int', 'int8', 'int16', 'int32', 'int64', 'real', 'real16', 'real32', 'real64']:
            raise GeLBExTypeError(
                node,
                f"Function '{function_name}' expects numeric arrays, got array[{arg_type.element_dtype}, ...] for argument {i+1}",
                f"The {function_name}() function requires numeric array types, not {arg_type.element_dtype}"
            )
    
    # Check that arrays have the same shape
    # Handle different shape representations
    def get_shape_info(shape):
        """Helper to get dimensionality info from shape."""
        if isinstance(shape, List_N):
            return ("multi", len(shape.elements))
        elif isinstance(shape, IntLiteral_N):
            return ("1d", shape.value)
        elif isinstance(shape, Array1DLiteral_N):
            # Multi-dimensional array represented as Array1DLiteral_N
            return ("multi", len(shape.value.elements))
        else:
            return ("unknown", None)
    
    shape1_type, shape1_info = get_shape_info(arg1_type.shape)
    shape2_type, shape2_info = get_shape_info(arg2_type.shape)
    
    # Check dimensional compatibility
    if shape1_type != shape2_type:
        # Different shape representations indicate different dimensionalities
        dim1 = 1 if shape1_type == "1d" else (shape1_info if shape1_type == "multi" else "unknown")
        dim2 = 1 if shape2_type == "1d" else (shape2_info if shape2_type == "multi" else "unknown")
        raise GeLBExTypeError(
            node,
            f"Function '{function_name}' requires arrays of the same shape",
            f"Array 1 has {dim1} dimensions, array 2 has {dim2} dimensions"
        )
    
    # For 1D arrays, check that they have the same size
    if shape1_type == "1d" and shape2_type == "1d":
        if shape1_info != shape2_info:
            raise GeLBExTypeError(
                node,
                f"Function '{function_name}' requires arrays of the same size",
                f"Array 1 has size {shape1_info}, array 2 has size {shape2_info}"
            )
    
    # For multi-dimensional arrays, we could add more sophisticated shape checking here
    # For now, we trust that the shapes are compatible if they have the same dimensionality


def _compute_dot_prod_return_type(function_name, arguments, node, code_range):
    """
    Compute return type for dot_prod() function.
    
    Returns a scalar (0-dimensional array) of the promoted type of the two input arrays.
    
    Args:
        function_name: Name of the function ('dot_prod')
        arguments: List of argument expressions
        node: The IntrinsicFunctionCall_N node
        code_range: Code range for creating the return type
        
    Returns:
        ArrayDataType_N: Scalar type of the promoted element type
    """
    arg1, arg2 = arguments
    arg1_type, arg2_type = arg1.inferred_type, arg2.inferred_type
    
    # Promote the types according to GeLB's type promotion rules
    promoted_type = _promote_numeric_types(arg1_type.element_dtype, arg2_type.element_dtype)
    
    # Return scalar type (0-dimensional array) with promoted element type
    empty_shape = List_N(code_range)
    return ArrayDataType_N(code_range, promoted_type, empty_shape)


def _promote_numeric_types(type1, type2):
    """
    Promote two numeric types according to GeLB's type promotion rules.
    
    Rules: bool → int → real, with higher precision preserved
    
    Args:
        type1: First element type string
        type2: Second element type string
        
    Returns:
        str: Promoted type string
    """
    # Define type hierarchy: bool < int < real
    # Within each category, higher precision wins
    
    # Normalize types to base types for hierarchy comparison
    base_type1 = _get_base_type(type1)
    base_type2 = _get_base_type(type2)
    
    # If one is real and the other is not, real wins
    if base_type1 == 'real' and base_type2 != 'real':
        return _get_highest_precision_real_type(type1, 'real')
    elif base_type2 == 'real' and base_type1 != 'real':
        return _get_highest_precision_real_type(type2, 'real')
    elif base_type1 == 'real' and base_type2 == 'real':
        return _get_highest_precision_real_type(type1, type2)
    
    # If one is int and the other is bool, int wins
    if base_type1 == 'int' and base_type2 == 'bool':
        return type1
    elif base_type2 == 'int' and base_type1 == 'bool':
        return type2
    elif base_type1 == 'int' and base_type2 == 'int':
        return _get_highest_precision_int_type(type1, type2)
    
    # Both are bool
    if base_type1 == 'bool' and base_type2 == 'bool':
        return 'bool'
    
    # Fallback - return the "higher" type
    return type2 if base_type2 == 'real' else (type1 if base_type1 == 'int' else type1)


def _get_base_type(type_str):
    """Get the base type (bool/int/real) from a type string."""
    if 'real' in type_str:
        return 'real'
    elif 'int' in type_str:
        return 'int'
    elif 'bool' in type_str:
        return 'bool'
    else:
        return type_str


def _get_highest_precision_real_type(type1, type2):
    """Get the higher precision real type."""
    # Map types to their precision levels
    precision_order = {'real16': 1, 'real32': 2, 'real': 3, 'real64': 4}
    
    prec1 = precision_order.get(type1, 3)  # Default to 'real'
    prec2 = precision_order.get(type2, 3)
    
    return type1 if prec1 >= prec2 else type2


def _get_highest_precision_int_type(type1, type2):
    """Get the higher precision int type."""
    # Map types to their precision levels
    precision_order = {'int8': 1, 'int16': 2, 'int32': 3, 'int': 4, 'int64': 5}
    
    prec1 = precision_order.get(type1, 4)  # Default to 'int'
    prec2 = precision_order.get(type2, 4)
    
    return type1 if prec1 >= prec2 else type2


# Registry of intrinsic functions
INTRINSIC_FUNCTIONS = {
    'sum': IntrinsicFunction(
        name='sum',
        min_args=1,
        max_args=1,
        type_checker=_check_sum_arguments,
        return_type_computer=_compute_sum_return_type
    ),
    'dot_prod': IntrinsicFunction(
        name='dot_prod',
        min_args=2,
        max_args=2,
        type_checker=_check_dot_prod_arguments,
        return_type_computer=_compute_dot_prod_return_type
    )
}


def get_intrinsic_function(name):
    """
    Get intrinsic function definition by name.
    
    Args:
        name: Function name string
        
    Returns:
        IntrinsicFunction: Function definition, or None if not found
    """
    return INTRINSIC_FUNCTIONS.get(name)


def is_intrinsic_function(name):
    """
    Check if a name is an intrinsic function.
    
    Args:
        name: Function name string
        
    Returns:
        bool: True if name is an intrinsic function
    """
    return name in INTRINSIC_FUNCTIONS