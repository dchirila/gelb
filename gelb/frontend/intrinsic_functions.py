#!/usr/bin/env python3

from gelb.gelb_ast.ASTNodes import *
from gelb.utils.exceptions import *
from gelb.frontend.type_rules import (
    INTEGER_TYPES, NUMERIC_TYPES, REAL_TYPES, common_type, intrinsic_result_type)


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


# The type names are type_rules' (user manual, Numerical semantics:
# Types and promotion; real16 is not in this version), as is every
# promotion below.
_INT_TYPES = INTEGER_TYPES
_REAL_TYPES = REAL_TYPES
_NUMERIC_TYPES = NUMERIC_TYPES

_TYPE_INFERENCE_REQUIRED_DETAIL = (
    "This is likely an internal compiler error - type inference should run before validation"
)


def _require_inferred_type(
        function_name, arg, *, arg_number=None,
        detail=_TYPE_INFERENCE_REQUIRED_DETAIL):
    """Return ``arg.inferred_type`` or raise the existing internal error."""
    if not hasattr(arg, 'inferred_type') or arg.inferred_type is None:
        if arg_number is None:
            message = f"Argument to '{function_name}' has no inferred type"
        else:
            message = (
                f"Argument {arg_number} to '{function_name}' has no inferred type")
        raise GeLBException(message, detail)
    return arg.inferred_type


def _assert_array_type(node, arg_type, message, detail):
    if not isinstance(arg_type, ArrayDataType_N):
        raise GeLBExTypeError(
            node,
            message,
            detail
        )


def _is_scalar_array_type(array_type):
    return (
        isinstance(array_type.shape, List_N)
        and len(array_type.shape.elements) == 0
    )


def _assert_numeric_element_type(node, array_type, message, detail):
    if array_type.element_dtype not in _NUMERIC_TYPES:
        raise GeLBExTypeError(
            node,
            message,
            detail
        )


def _make_scalar_shape(code_range):
    return List_N(code_range)


def _make_unknown_shape(code_range):
    return List_N(code_range)


def _make_2d_shape(code_range, first_dim, second_dim):
    shape_elements = List_N(code_range)
    shape_elements.append(IntLiteral_N(code_range, first_dim))
    shape_elements.append(IntLiteral_N(code_range, second_dim))
    return Array1DLiteral_N(code_range, shape_elements)


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
    
    arg = arguments[0]
    arg_type = _require_inferred_type(function_name, arg)
    
    # Check that argument is an array (not scalar)
    _assert_array_type(
        node,
        arg_type,
        f"Function '{function_name}' expects an array argument, got non-array type",
        f"The argument to {function_name}() must be an array, not a scalar or other type"
    )
    
    if _is_scalar_array_type(arg_type):
        raise GeLBExTypeError(
            node,
            f"Function '{function_name}' expects an array argument, got scalar '{arg_type.element_dtype}'",
            f"Use {function_name}() with arrays like 'array[int, 5]', not scalars like 'int'"
        )
    
    # Check that element type is numeric
    _assert_numeric_element_type(
        node,
        arg_type,
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
    empty_shape = _make_scalar_shape(code_range)
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
    
    arg1, arg2 = arguments
    arg1_type = _require_inferred_type(function_name, arg1, arg_number=1)
    arg2_type = _require_inferred_type(function_name, arg2, arg_number=2)
    
    # Check that both arguments are arrays
    for i, arg_type in enumerate([arg1_type, arg2_type], start=1):
        _assert_array_type(
            node,
            arg_type,
            f"Function '{function_name}' expects array arguments, got non-array type for argument {i}",
            f"Both arguments to {function_name}() must be arrays"
        )

        if _is_scalar_array_type(arg_type):
            raise GeLBExTypeError(
                node,
                f"Function '{function_name}' expects array arguments, got scalar '{arg_type.element_dtype}' for argument {i}",
                f"Use {function_name}() with arrays like 'array[int, 5]', not scalars"
            )
        
        # Check that element type is numeric
        _assert_numeric_element_type(
            node,
            arg_type,
            f"Function '{function_name}' expects numeric arrays, got array[{arg_type.element_dtype}, ...] for argument {i}",
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

    # dot_prod is the inner product of two vectors.  A matrix operand
    # passed the shape checks below (both operands rank 2) and reached
    # the native compiler, whose dot_product takes vectors only; it is
    # an error here, at the call.
    for i, (shape_type, shape_info) in enumerate(
            [(shape1_type, shape1_info), (shape2_type, shape2_info)], start=1):
        if shape_type == "multi" and shape_info > 1:
            raise GeLBExTypeError(
                node,
                f"Function '{function_name}' takes vectors; argument {i} "
                f"is a {shape_info}-dimensional array",
                f"{function_name}(a, b) is the inner product of two "
                "one-dimensional arrays of the same length; for "
                "matrices use matmul().  An inner product of "
                "higher-rank arrays is not in this version."
            )

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
    
    # The element types' common type (type_rules)
    promoted_type = _common_element_type(arg1_type.element_dtype, arg2_type.element_dtype)
    
    # Return scalar type (0-dimensional array) with promoted element type
    empty_shape = _make_scalar_shape(code_range)
    return ArrayDataType_N(code_range, promoted_type, empty_shape)


def _common_element_type(type1, type2):
    """type_rules' common type of two element types; the first type
    when one takes no part in arithmetic (the checkers report those)."""
    common = common_type(type1, type2)
    return common if common is not None else type1


def _check_scalar_math_arguments(function_name, arguments, node):
    """
    Check that a scalar math function (sin, cos, sqrt) has exactly one
    scalar numeric argument.

    Args:
        function_name: Name of the function ('sin', 'cos', or 'sqrt')
        arguments: List of argument expressions
        node: The IntrinsicFunctionCall_N node for error reporting
    """
    if len(arguments) != 1:
        raise GeLBExTypeError(
            node,
            f"Function '{function_name}' expects exactly 1 argument, got {len(arguments)}",
            f"Usage: {function_name}(numeric_expression)"
        )

    arg = arguments[0]
    arg_type = _require_inferred_type(function_name, arg)

    _assert_array_type(
        node,
        arg_type,
        f"Function '{function_name}' expects a numeric argument, got non-array type",
        f"Internal error: all expressions should have ArrayDataType_N inferred_type"
    )

    # Must be scalar (0-dimensional)
    if not _is_scalar_array_type(arg_type):
        raise GeLBExTypeError(
            node,
            f"Function '{function_name}' expects a scalar argument, got an array",
            f"Use {function_name}() with scalar values, not arrays"
        )

    # Must be numeric
    _assert_numeric_element_type(
        node,
        arg_type,
        f"Function '{function_name}' expects a numeric argument, got '{arg_type.element_dtype}'",
        f"The {function_name}() function requires a numeric type (int or real)"
    )


def _compute_scalar_intrinsic_return_type(function_name, arguments, node, code_range):
    """The result type of a scalar intrinsic, from the one table
    (type_rules.intrinsic_result_type): ``sqrt`` of a ``real32`` is
    ``real32`` and of an integer ``real``; ``abs`` keeps its argument's
    type; ``min``, ``max`` and ``mod`` return the common type of their
    arguments; ``atan2`` the common real type.  Always a scalar."""
    result_type = intrinsic_result_type(
        function_name, [arg.inferred_type.element_dtype for arg in arguments])
    empty_shape = _make_scalar_shape(code_range)
    return ArrayDataType_N(code_range, result_type, empty_shape)


def _check_two_scalar_math_arguments(function_name, arguments, node):
    """
    Check that a 2-arg math function (min, max, mod, atan2) has exactly two
    scalar numeric arguments.
    """
    if len(arguments) != 2:
        raise GeLBExTypeError(
            node,
            f"Function '{function_name}' expects exactly 2 arguments, got {len(arguments)}",
            f"Usage: {function_name}(a, b)"
        )

    for i, arg in enumerate(arguments):
        arg_number = i + 1
        arg_type = _require_inferred_type(
            function_name, arg, arg_number=arg_number)

        _assert_array_type(
            node,
            arg_type,
            f"Function '{function_name}' expects numeric arguments, got non-array type for argument {arg_number}",
            f"Internal error: all expressions should have ArrayDataType_N inferred_type"
        )

        if not _is_scalar_array_type(arg_type):
            raise GeLBExTypeError(
                node,
                f"Function '{function_name}' expects scalar arguments, got an array for argument {arg_number}",
                f"Use {function_name}() with scalar values, not arrays"
            )

        _assert_numeric_element_type(
            node,
            arg_type,
            f"Function '{function_name}' expects numeric arguments, got '{arg_type.element_dtype}' for argument {arg_number}",
            f"The {function_name}() function requires numeric types (int or real)"
        )


def _check_random_arguments(function_name, arguments, node):
    """Check that random() takes no arguments."""
    if len(arguments) != 0:
        raise GeLBExTypeError(
            node,
            f"Function '{function_name}' expects no arguments, got {len(arguments)}",
            f"Usage: {function_name}()"
        )


def _compute_random_return_type(function_name, arguments, node, code_range):
    """Return type for random(): scalar real in [0, 1)."""
    empty_shape = _make_scalar_shape(code_range)
    return ArrayDataType_N(code_range, 'real', empty_shape)


def _extract_shape_dims(array_type):
    """Extract dimension sizes from an ArrayDataType_N's shape.

    Returns a list of int (e.g. [9] for 1D, [9, 9] for 2D), or None
    if the shape cannot be resolved to concrete dimensions.
    """
    shape = array_type.shape
    if isinstance(shape, List_N):
        if len(shape.elements) == 0:
            return []  # scalar
        return [e.value for e in shape.elements if hasattr(e, 'value')]
    if isinstance(shape, IntLiteral_N):
        return [shape.value]
    if isinstance(shape, Array1DLiteral_N):
        if hasattr(shape, 'value') and hasattr(shape.value, 'elements'):
            return [e.value for e in shape.value.elements if hasattr(e, 'value')]
    return None


def _check_matmul_arguments(function_name, arguments, node):
    """Check matmul(A, B) arguments.

    Supports matrix-vector and matrix-matrix multiplication:
      - array[T, {M,N}] x array[T, N]     -> array[T, M]
      - array[T, {M,K}] x array[T, {K,N}] -> array[T, {M,N}]
    """
    if len(arguments) != 2:
        raise GeLBExTypeError(
            node,
            f"Function '{function_name}' expects exactly 2 arguments, got {len(arguments)}",
            f"Usage: {function_name}(matrix, vector_or_matrix)"
        )

    arg_types = []
    for i, arg in enumerate(arguments, start=1):
        arg_type = _require_inferred_type(
            function_name, arg, arg_number=i, detail="Internal compiler error")
        _assert_array_type(
            node,
            arg_type,
            f"Function '{function_name}' expects array arguments, got non-array for argument {i}",
            f"Both arguments must be arrays"
        )
        arg_types.append(arg_type)

    dims_a = _extract_shape_dims(arg_types[0])
    dims_b = _extract_shape_dims(arg_types[1])

    if dims_a is None or dims_b is None:
        return  # cannot validate statically

    if len(dims_a) < 2:
        raise GeLBExTypeError(
            node,
            f"First argument to '{function_name}' must be a 2D array (matrix), got {len(dims_a)}D",
            f"Usage: {function_name}(matrix, vector_or_matrix)"
        )

    # Inner dimension check
    inner_a = dims_a[-1]  # last dim of A
    if len(dims_b) == 1:
        inner_b = dims_b[0]  # vector size
    elif len(dims_b) >= 2:
        inner_b = dims_b[0]  # first dim of B
    else:
        return

    if inner_a != inner_b:
        raise GeLBExTypeError(
            node,
            f"Dimension mismatch in '{function_name}': "
            f"inner dimensions {inner_a} and {inner_b} do not match",
            f"For matmul(A, B), A's last dimension must equal B's first dimension"
        )


def _compute_matmul_return_type(function_name, arguments, node, code_range):
    """Return type for matmul: depends on argument shapes."""
    type_a = arguments[0].inferred_type
    type_b = arguments[1].inferred_type
    promoted = _common_element_type(type_a.element_dtype, type_b.element_dtype)

    dims_a = _extract_shape_dims(type_a)
    dims_b = _extract_shape_dims(type_b)

    if dims_a is not None and dims_b is not None:
        if len(dims_b) == 1:
            # Matrix-vector: result is 1D array of size dims_a[0]
            result_shape = IntLiteral_N(code_range, dims_a[0])
        else:
            # Matrix-matrix: result is 2D {dims_a[0], dims_b[1]}
            result_shape = _make_2d_shape(code_range, dims_a[0], dims_b[1])
    else:
        result_shape = _make_unknown_shape(code_range)

    return ArrayDataType_N(code_range, promoted, result_shape)


def _check_transpose_arguments(function_name, arguments, node):
    """Check transpose(A) argument: must be a 2D array."""
    if len(arguments) != 1:
        raise GeLBExTypeError(
            node,
            f"Function '{function_name}' expects exactly 1 argument, got {len(arguments)}",
            f"Usage: {function_name}(matrix)"
        )

    arg = arguments[0]
    arg_type = _require_inferred_type(
        function_name, arg, detail="Internal compiler error")
    _assert_array_type(
        node,
        arg_type,
        f"Function '{function_name}' expects a 2D array, got non-array",
        f"Usage: {function_name}(matrix)"
    )

    dims = _extract_shape_dims(arg_type)
    if dims is not None and len(dims) != 2:
        raise GeLBExTypeError(
            node,
            f"Function '{function_name}' expects a 2D array, got {len(dims)}D",
            f"transpose() only works on 2D arrays (matrices)"
        )


def _compute_transpose_return_type(function_name, arguments, node, code_range):
    """Return type for transpose: swap dimensions."""
    arg_type = arguments[0].inferred_type
    dims = _extract_shape_dims(arg_type)

    if dims is not None and len(dims) == 2:
        result_shape = _make_2d_shape(code_range, dims[1], dims[0])
    else:
        result_shape = _make_unknown_shape(code_range)

    return ArrayDataType_N(code_range, arg_type.element_dtype, result_shape)


def _check_square_matrix_argument(function_name, arguments, node):
    """Check that a single argument is a 2D square array (for inverse/determinant)."""
    if len(arguments) != 1:
        raise GeLBExTypeError(
            node,
            f"Function '{function_name}' expects exactly 1 argument, got {len(arguments)}",
            f"Usage: {function_name}(matrix)"
        )

    arg = arguments[0]
    arg_type = _require_inferred_type(
        function_name, arg, detail="Internal compiler error")
    _assert_array_type(
        node,
        arg_type,
        f"Function '{function_name}' expects a 2D array, got non-array",
        f"Usage: {function_name}(square_matrix)"
    )

    dims = _extract_shape_dims(arg_type)
    if dims is not None:
        if len(dims) != 2:
            raise GeLBExTypeError(
                node,
                f"Function '{function_name}' expects a 2D array, got {len(dims)}D",
                f"{function_name}() only works on 2D arrays (matrices)"
            )
        if dims[0] != dims[1]:
            raise GeLBExTypeError(
                node,
                f"Function '{function_name}' expects a square matrix, "
                f"got {dims[0]}x{dims[1]}",
                f"{function_name}() requires equal row and column dimensions"
            )


def _compute_inverse_return_type(function_name, arguments, node, code_range):
    """Return type for inverse: same shape, promoted to real."""
    arg_type = arguments[0].inferred_type
    dims = _extract_shape_dims(arg_type)
    promoted = _common_element_type(arg_type.element_dtype, 'real')

    if dims is not None and len(dims) == 2:
        result_shape = _make_2d_shape(code_range, dims[0], dims[1])
    else:
        result_shape = _make_unknown_shape(code_range)

    return ArrayDataType_N(code_range, promoted, result_shape)


def _compute_determinant_return_type(function_name, arguments, node, code_range):
    """Return type for determinant: scalar real."""
    return ArrayDataType_N(code_range, 'real', _make_scalar_shape(code_range))


def _check_streaming_dfs_arguments(function_name, arguments, node):
    """Check streaming intrinsic arguments.

    Expected: (lattice_name, coord_1, ..., coord_d, {vel_1, ..., vel_d})
    Minimum 3 args (1D: lattice, x, {EX}).  Deep lattice/type validation
    is deferred to the backend which has full AST access.
    """
    if len(arguments) < 3:
        raise GeLBExTypeError(
            node,
            f"Function '{function_name}' expects at least 3 arguments "
            f"(lattice, coordinates, velocity_vectors), got {len(arguments)}",
            f"Usage: {function_name}(f, x, y, {{EX, EY}})"
        )


def _compute_streaming_dfs_return_type(function_name, arguments, node, code_range):
    """Return type for streaming intrinsics: array[real, q].

    The last argument is the velocity set {EX, EY, ...}.  Each velocity
    array has q elements, so the return type is array[real, q].  We infer
    q from the first velocity array in the set.
    """
    vel_set = arguments[-1]  # The {EX, EY, ...} array literal
    # vel_set is an Array1DLiteral_N containing the velocity arrays
    if hasattr(vel_set, 'value') and hasattr(vel_set.value, 'elements'):
        first_vel = vel_set.value.elements[0]
        if hasattr(first_vel, 'inferred_type') and first_vel.inferred_type is not None:
            # Get q from the velocity array's shape
            vel_type = first_vel.inferred_type
            if isinstance(vel_type, ArrayDataType_N):
                return ArrayDataType_N(code_range, 'real', vel_type.shape)
    # Fallback: can't determine q, return generic array
    # The backend will handle this correctly
    empty_shape = _make_unknown_shape(code_range)
    return ArrayDataType_N(code_range, 'real', empty_shape)


# ----------------------------------------------------------------------
# Type-cast intrinsics: int(x), real(x), int8(x), ..., real64(x)
# ----------------------------------------------------------------------
#
# These let users explicitly convert between numeric types (and bool),
# bypassing the implicit-promotion rules that reject lossy downcasts.
# All cast intrinsics share a common type checker that accepts any
# numeric or bool argument; each has its own return-type computer that
# preserves the argument's shape (so casts work element-wise on arrays).

# Public source of truth: the names of all type-cast intrinsics.
# Imported by ConstantFoldingVisitor and the Fortran backend so the
# set lives in exactly one place.
CAST_INTRINSIC_NAMES = _INT_TYPES + _REAL_TYPES
INT_CAST_NAMES = frozenset(_INT_TYPES)
REAL_CAST_NAMES = frozenset(_REAL_TYPES)

_NUMERIC_OR_BOOL_TYPES = frozenset({'bool'} | _NUMERIC_TYPES)


def _check_cast_arguments(function_name, arguments, node):
    """Type checker for cast intrinsics: 1 numeric or bool argument."""
    if len(arguments) != 1:
        raise GeLBExTypeError(
            node,
            f"Function '{function_name}' expects exactly 1 argument, got {len(arguments)}",
            f"Usage: {function_name}(numeric_or_bool_expression)"
        )

    arg = arguments[0]
    arg_type = _require_inferred_type(
        function_name,
        arg,
        detail=(
            "This is likely an internal compiler error — type inference "
            "should run before validation"
        ),
    )

    _assert_array_type(
        node,
        arg_type,
        f"Function '{function_name}' expects a numeric or bool argument, "
        f"got non-array type",
        f"Internal error: all expressions should have ArrayDataType_N inferred_type"
    )

    if arg_type.element_dtype not in _NUMERIC_OR_BOOL_TYPES:
        raise GeLBExTypeError(
            node,
            f"Function '{function_name}' expects a numeric or bool argument, "
            f"got '{arg_type.element_dtype}'",
            f"Cast intrinsics work on int, real, and bool types"
        )


def _make_cast_return_type_computer(target_type):
    """Build a return-type computer that preserves the argument's shape.

    Casts apply element-wise on arrays: ``int({1.5, 2.5, 3.5})`` returns
    an ``array[int, 3]`` of ``{1, 2, 3}``.
    """
    def _compute(function_name, arguments, node, code_range):
        arg_type = arguments[0].inferred_type
        # Preserve the argument's shape (scalar or array)
        return ArrayDataType_N(code_range, target_type, arg_type.shape)
    return _compute


# Intrinsics whose calls do more than return a value: each call draws
# the next number of a stream, so two calls are two values.  An optimizer
# must keep their count and order: it may not share, drop, duplicate or
# move an expression containing one (user manual, Numerical semantics:
# Random numbers).
STATEFUL_INTRINSIC_NAMES = frozenset({'random'})


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
    ),
    'sin': IntrinsicFunction(
        name='sin',
        min_args=1,
        max_args=1,
        type_checker=_check_scalar_math_arguments,
        return_type_computer=_compute_scalar_intrinsic_return_type
    ),
    'cos': IntrinsicFunction(
        name='cos',
        min_args=1,
        max_args=1,
        type_checker=_check_scalar_math_arguments,
        return_type_computer=_compute_scalar_intrinsic_return_type
    ),
    'sqrt': IntrinsicFunction(
        name='sqrt',
        min_args=1,
        max_args=1,
        type_checker=_check_scalar_math_arguments,
        return_type_computer=_compute_scalar_intrinsic_return_type
    ),
    'random': IntrinsicFunction(
        name='random',
        min_args=0,
        max_args=0,
        type_checker=_check_random_arguments,
        return_type_computer=_compute_random_return_type
    ),
    'exp': IntrinsicFunction(
        name='exp',
        min_args=1,
        max_args=1,
        type_checker=_check_scalar_math_arguments,
        return_type_computer=_compute_scalar_intrinsic_return_type
    ),
    'abs': IntrinsicFunction(
        name='abs',
        min_args=1,
        max_args=1,
        type_checker=_check_scalar_math_arguments,
        return_type_computer=_compute_scalar_intrinsic_return_type
    ),
    'log': IntrinsicFunction(
        name='log',
        min_args=1,
        max_args=1,
        type_checker=_check_scalar_math_arguments,
        return_type_computer=_compute_scalar_intrinsic_return_type
    ),
    'tan': IntrinsicFunction(
        name='tan',
        min_args=1,
        max_args=1,
        type_checker=_check_scalar_math_arguments,
        return_type_computer=_compute_scalar_intrinsic_return_type
    ),
    'tanh': IntrinsicFunction(
        name='tanh',
        min_args=1,
        max_args=1,
        type_checker=_check_scalar_math_arguments,
        return_type_computer=_compute_scalar_intrinsic_return_type
    ),
    'min': IntrinsicFunction(
        name='min',
        min_args=2,
        max_args=2,
        type_checker=_check_two_scalar_math_arguments,
        return_type_computer=_compute_scalar_intrinsic_return_type
    ),
    'max': IntrinsicFunction(
        name='max',
        min_args=2,
        max_args=2,
        type_checker=_check_two_scalar_math_arguments,
        return_type_computer=_compute_scalar_intrinsic_return_type
    ),
    'mod': IntrinsicFunction(
        name='mod',
        min_args=2,
        max_args=2,
        type_checker=_check_two_scalar_math_arguments,
        return_type_computer=_compute_scalar_intrinsic_return_type
    ),
    'atan2': IntrinsicFunction(
        name='atan2',
        min_args=2,
        max_args=2,
        type_checker=_check_two_scalar_math_arguments,
        return_type_computer=_compute_scalar_intrinsic_return_type
    ),
    'matmul': IntrinsicFunction(
        name='matmul',
        min_args=2,
        max_args=2,
        type_checker=_check_matmul_arguments,
        return_type_computer=_compute_matmul_return_type
    ),
    'transpose': IntrinsicFunction(
        name='transpose',
        min_args=1,
        max_args=1,
        type_checker=_check_transpose_arguments,
        return_type_computer=_compute_transpose_return_type
    ),
    'inverse': IntrinsicFunction(
        name='inverse',
        min_args=1,
        max_args=1,
        type_checker=_check_square_matrix_argument,
        return_type_computer=_compute_inverse_return_type
    ),
    'determinant': IntrinsicFunction(
        name='determinant',
        min_args=1,
        max_args=1,
        type_checker=_check_square_matrix_argument,
        return_type_computer=_compute_determinant_return_type
    ),
    'upstream_dfs': IntrinsicFunction(
        name='upstream_dfs',
        min_args=3,
        max_args=None,  # variable: lattice + d coords + velocity set
        type_checker=_check_streaming_dfs_arguments,
        return_type_computer=_compute_streaming_dfs_return_type
    ),
    'bounce_back_dfs': IntrinsicFunction(
        name='bounce_back_dfs',
        min_args=3,
        max_args=None,
        type_checker=_check_streaming_dfs_arguments,
        return_type_computer=_compute_streaming_dfs_return_type
    ),
    # Type-cast intrinsics (one entry per target type, all generated
    # from CAST_INTRINSIC_NAMES via the loop below).
}

# Register cast intrinsics in a loop to keep the table compact.
for _t in CAST_INTRINSIC_NAMES:
    INTRINSIC_FUNCTIONS[_t] = IntrinsicFunction(
        name=_t,
        min_args=1,
        max_args=1,
        type_checker=_check_cast_arguments,
        return_type_computer=_make_cast_return_type_computer(_t),
    )
del _t


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
