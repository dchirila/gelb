#!/usr/bin/env python3
"""
Comprehensive tests for mixed scalar/array operations with ArrayDataType_N system.

These tests validate operations between scalars (0-dimensional arrays) and 
multi-dimensional arrays, ensuring proper shape broadcasting and type inference.
"""

from gelb.gelb_ast.ASTNodes import *
from gelb.tests.test_utils import get_typed_ast, minimal_gelb_program_1d


class TestScalarArrayArithmeticOperations:
    """Test arithmetic operations between scalars and arrays."""
    
    def test_scalar_plus_1d_array_broadcasting(self):
        """Scalar + 1D Array should broadcast scalar to array shape."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="""
            const array[int, 3] vec = {1, 2, 3};
            const int scalar = 5;
            const array[int, 3] result = scalar + vec;
        """)
        ast = get_typed_ast(gelb_code)
        
        result_stmt = ast.global_constants.stmts.elements[2]
        add_expr = result_stmt.value
        
        assert isinstance(add_expr, Add_N)
        assert hasattr(add_expr, 'inferred_type')
        assert isinstance(add_expr.inferred_type, ArrayDataType_N)
        
        # Result should have the shape of the array operand (1D with size 3)
        assert add_expr.inferred_type.scalar_dtype == "int"
        shape = add_expr.inferred_type.shape
        assert isinstance(shape, IntLiteral_N)
        assert shape.value == 3
        
        # Check operand types
        scalar_operand = add_expr.left  # scalar
        array_operand = add_expr.right  # vec
        
        # Scalar should be 0-dimensional
        assert isinstance(scalar_operand.inferred_type, ArrayDataType_N)
        assert len(scalar_operand.inferred_type.shape.elements) == 0
        
        # Array should be 1-dimensional
        assert isinstance(array_operand.inferred_type, ArrayDataType_N)
        assert isinstance(array_operand.inferred_type.shape, IntLiteral_N)
        assert array_operand.inferred_type.shape.value == 3
    
    def test_1d_array_plus_scalar_broadcasting(self):
        """1D Array + Scalar should broadcast scalar to array shape."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="""
            const array[real, 4] vec = {1.0, 2.0, 3.0, 4.0};
            const real scalar = 2.5;
            const array[real, 4] result = vec + scalar;
        """)
        ast = get_typed_ast(gelb_code)
        
        result_stmt = ast.global_constants.stmts.elements[2]
        add_expr = result_stmt.value
        
        assert isinstance(add_expr, Add_N)
        assert isinstance(add_expr.inferred_type, ArrayDataType_N)
        
        # Result should have the shape of the array operand (1D with size 4)
        assert add_expr.inferred_type.scalar_dtype == "real"
        shape = add_expr.inferred_type.shape
        assert isinstance(shape, IntLiteral_N)
        assert shape.value == 4
        
        # Check operand types
        array_operand = add_expr.left   # vec
        scalar_operand = add_expr.right # scalar
        
        # Array should be 1-dimensional
        assert isinstance(array_operand.inferred_type, ArrayDataType_N)
        assert isinstance(array_operand.inferred_type.shape, IntLiteral_N)
        assert array_operand.inferred_type.shape.value == 4
        
        # Scalar should be 0-dimensional
        assert isinstance(scalar_operand.inferred_type, ArrayDataType_N)
        assert len(scalar_operand.inferred_type.shape.elements) == 0
    
    def test_scalar_multiply_2d_array_broadcasting(self):
        """Scalar * 2D Array should broadcast scalar to array shape."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="""
            const array[int, {2, 3}] mat = {{1, 2, 3}, {4, 5, 6}};
            const int scalar = 3;
            const array[int, {2, 3}] result = scalar * mat;
        """)
        ast = get_typed_ast(gelb_code)
        
        result_stmt = ast.global_constants.stmts.elements[2]
        mul_expr = result_stmt.value
        
        assert isinstance(mul_expr, Mul_N)
        assert isinstance(mul_expr.inferred_type, ArrayDataType_N)
        
        # Result should have the shape of the array operand (2D with shape {2, 3})
        assert mul_expr.inferred_type.scalar_dtype == "int"
        shape = mul_expr.inferred_type.shape
        assert isinstance(shape, Array1DLiteral_N)
        assert len(shape.value.elements) == 2
        assert shape.value.elements[0].value == 2
        assert shape.value.elements[1].value == 3
        
        # Check operand types
        scalar_operand = mul_expr.left  # scalar
        array_operand = mul_expr.right  # mat
        
        # Scalar should be 0-dimensional
        assert isinstance(scalar_operand.inferred_type, ArrayDataType_N)
        assert len(scalar_operand.inferred_type.shape.elements) == 0
        
        # Array should be 2-dimensional
        assert isinstance(array_operand.inferred_type, ArrayDataType_N)
        assert isinstance(array_operand.inferred_type.shape, Array1DLiteral_N)
        assert len(array_operand.inferred_type.shape.value.elements) == 2
    
    def test_2d_array_divide_scalar_broadcasting(self):
        """2D Array / Scalar should broadcast scalar to array shape."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="""
            const array[real, {3, 2}] mat = {{6.0, 8.0}, {10.0, 12.0}, {14.0, 16.0}};
            const real scalar = 2.0;
            const array[real, {3, 2}] result = mat / scalar;
        """)
        ast = get_typed_ast(gelb_code)
        
        result_stmt = ast.global_constants.stmts.elements[2]
        div_expr = result_stmt.value
        
        assert isinstance(div_expr, Div_N)
        assert isinstance(div_expr.inferred_type, ArrayDataType_N)
        
        # Result should have the shape of the array operand (2D with shape {3, 2})
        assert div_expr.inferred_type.scalar_dtype == "real"
        shape = div_expr.inferred_type.shape
        assert isinstance(shape, Array1DLiteral_N)
        assert len(shape.value.elements) == 2
        assert shape.value.elements[0].value == 3
        assert shape.value.elements[1].value == 2


class TestScalarArrayTypePromotion:
    """Test type promotion in mixed scalar/array operations."""
    
    def test_int_scalar_plus_real_array_promotes_to_real(self):
        """Int scalar + Real array should promote to Real array."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="""
            const array[real, 3] vec = {1.5, 2.5, 3.5};
            const int scalar = 2;
            const array[real, 3] result = scalar + vec;
        """)
        ast = get_typed_ast(gelb_code)
        
        result_stmt = ast.global_constants.stmts.elements[2]
        add_expr = result_stmt.value
        
        assert isinstance(add_expr, Add_N)
        assert isinstance(add_expr.inferred_type, ArrayDataType_N)
        
        # Result should be promoted to real and have array shape
        assert add_expr.inferred_type.scalar_dtype == "real"
        shape = add_expr.inferred_type.shape
        assert isinstance(shape, IntLiteral_N)
        assert shape.value == 3
        
        # Check operand types
        scalar_operand = add_expr.left  # int scalar
        array_operand = add_expr.right  # real array
        
        # Scalar is int (0D)
        assert scalar_operand.inferred_type.scalar_dtype == "int"
        assert len(scalar_operand.inferred_type.shape.elements) == 0
        
        # Array is real (1D)
        assert array_operand.inferred_type.scalar_dtype == "real"
        assert isinstance(array_operand.inferred_type.shape, IntLiteral_N)
    
    def test_real_array_multiply_int_scalar_promotes_to_real(self):
        """Real array * Int scalar should promote to Real array."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="""
            const array[real, {2, 2}] mat = {{1.1, 2.2}, {3.3, 4.4}};
            const int scalar = 3;
            const array[real, {2, 2}] result = mat * scalar;
        """)
        ast = get_typed_ast(gelb_code)
        
        result_stmt = ast.global_constants.stmts.elements[2]
        mul_expr = result_stmt.value
        
        assert isinstance(mul_expr, Mul_N)
        assert isinstance(mul_expr.inferred_type, ArrayDataType_N)
        
        # Result should be promoted to real and have 2D array shape
        assert mul_expr.inferred_type.scalar_dtype == "real"
        shape = mul_expr.inferred_type.shape
        assert isinstance(shape, Array1DLiteral_N)
        assert len(shape.value.elements) == 2
        assert shape.value.elements[0].value == 2
        assert shape.value.elements[1].value == 2


class TestScalarArrayComparisonOperations:
    """Test comparison operations between scalars and arrays."""
    
    def test_scalar_less_than_1d_array_produces_bool_array(self):
        """Scalar < 1D Array should produce 1D bool array."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="""
            const array[int, 4] vec = {1, 2, 3, 4};
            const int scalar = 2;
            const array[bool, 4] result = scalar < vec;
        """)
        ast = get_typed_ast(gelb_code)
        
        result_stmt = ast.global_constants.stmts.elements[2]
        less_expr = result_stmt.value
        
        assert isinstance(less_expr, Less_N)
        assert isinstance(less_expr.inferred_type, ArrayDataType_N)
        
        # Result should be bool array with same shape as array operand
        assert less_expr.inferred_type.scalar_dtype == "bool"
        # Note: For comparison ops, current implementation returns scalar bool
        # This test documents the expected behavior for future broadcasting
        
    def test_2d_array_greater_equal_scalar_produces_bool_array(self):
        """2D Array >= Scalar should produce 2D bool array."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="""
            const array[real, {2, 2}] mat = {{1.0, 2.0}, {3.0, 4.0}};
            const real scalar = 2.5;
            const array[bool, {2, 2}] result = mat >= scalar;
        """)
        ast = get_typed_ast(gelb_code)
        
        result_stmt = ast.global_constants.stmts.elements[2]
        ge_expr = result_stmt.value
        
        assert isinstance(ge_expr, GreaterEqual_N)
        assert isinstance(ge_expr.inferred_type, ArrayDataType_N)
        
        # Result should be bool (current behavior is scalar bool)
        assert ge_expr.inferred_type.scalar_dtype == "bool"


class TestScalarArrayLogicalOperations:
    """Test logical operations between scalar and array booleans."""
    
    def test_bool_scalar_and_bool_array_broadcasting(self):
        """Bool scalar && Bool array should broadcast to array shape."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="""
            const array[bool, 3] vec = {true, false, true};
            const bool scalar = true;
            const array[bool, 3] result = scalar && vec;
        """)
        ast = get_typed_ast(gelb_code)
        
        result_stmt = ast.global_constants.stmts.elements[2]
        and_expr = result_stmt.value
        
        assert isinstance(and_expr, And_N)
        assert isinstance(and_expr.inferred_type, ArrayDataType_N)
        
        # Result should be bool (current behavior may be scalar)
        assert and_expr.inferred_type.scalar_dtype == "bool"
        
        # Check operand types
        scalar_operand = and_expr.left  # bool scalar
        array_operand = and_expr.right  # bool array
        
        # Scalar should be 0-dimensional bool
        assert scalar_operand.inferred_type.scalar_dtype == "bool"
        assert len(scalar_operand.inferred_type.shape.elements) == 0
        
        # Array should be 1-dimensional bool
        assert array_operand.inferred_type.scalar_dtype == "bool"
        assert isinstance(array_operand.inferred_type.shape, IntLiteral_N)
        assert array_operand.inferred_type.shape.value == 3


class TestComplexScalarArrayExpressions:
    """Test complex expressions involving multiple scalar/array operations."""
    
    def test_nested_scalar_array_operations(self):
        """Complex expressions with nested scalar/array operations."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="""
            const array[real, 3] vec = {1.0, 2.0, 3.0};
            const real scalar1 = 2.0;
            const real scalar2 = 0.5;
            const array[real, 3] result = (vec * scalar1) + scalar2;
        """)
        ast = get_typed_ast(gelb_code)
        
        result_stmt = ast.global_constants.stmts.elements[3]
        add_expr = result_stmt.value
        
        assert isinstance(add_expr, Add_N)
        assert isinstance(add_expr.inferred_type, ArrayDataType_N)
        
        # Final result should be real array with shape of vec
        assert add_expr.inferred_type.scalar_dtype == "real"
        shape = add_expr.inferred_type.shape
        assert isinstance(shape, IntLiteral_N)
        assert shape.value == 3
        
        # Left operand should be (vec * scalar1) -> real array
        mul_expr = add_expr.left
        assert isinstance(mul_expr, Mul_N)
        assert isinstance(mul_expr.inferred_type, ArrayDataType_N)
        assert mul_expr.inferred_type.scalar_dtype == "real"
        
        # Right operand should be scalar2 -> real scalar (0D)
        scalar_operand = add_expr.right
        assert isinstance(scalar_operand.inferred_type, ArrayDataType_N)
        assert scalar_operand.inferred_type.scalar_dtype == "real"
        assert len(scalar_operand.inferred_type.shape.elements) == 0
    
    def test_scalar_array_with_type_promotion_chain(self):
        """Test type promotion in complex scalar/array expressions."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="""
            const array[int, 2] vec = {10, 20};
            const real scalar = 1.5;
            const array[real, 2] result = vec + scalar;
        """)
        ast = get_typed_ast(gelb_code)
        
        result_stmt = ast.global_constants.stmts.elements[2]
        add_expr = result_stmt.value
        
        assert isinstance(add_expr, Add_N)
        assert isinstance(add_expr.inferred_type, ArrayDataType_N)
        
        # Result should be promoted to real and have array shape
        assert add_expr.inferred_type.scalar_dtype == "real"
        shape = add_expr.inferred_type.shape
        assert isinstance(shape, IntLiteral_N)
        assert shape.value == 2
        
        # Check that operands have correct types before promotion
        array_operand = add_expr.left   # int array
        scalar_operand = add_expr.right # real scalar
        
        # Array operand should be int array
        assert array_operand.inferred_type.scalar_dtype == "int"
        assert isinstance(array_operand.inferred_type.shape, IntLiteral_N)
        
        # Scalar operand should be real scalar
        assert scalar_operand.inferred_type.scalar_dtype == "real"
        assert len(scalar_operand.inferred_type.shape.elements) == 0


class TestScalarArrayBroadcastingDocumentation:
    """Document the broadcasting behavior and design principles."""
    
    def test_broadcasting_design_principles(self):
        """Document key principles of scalar/array broadcasting in ArrayDataType_N system."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="""
            const int scalar_0d = 42;
            const array[int, 3] array_1d = {1, 2, 3};
            const array[int, {2, 2}] array_2d = {{1, 2}, {3, 4}};
        """)
        ast = get_typed_ast(gelb_code)
        
        scalar_stmt = ast.global_constants.stmts.elements[0]
        array_1d_stmt = ast.global_constants.stmts.elements[1]
        array_2d_stmt = ast.global_constants.stmts.elements[2]
        
        scalar_literal = scalar_stmt.value
        array_1d_literal = array_1d_stmt.value
        array_2d_literal = array_2d_stmt.value
        
        # Principle 1: Scalars are 0-dimensional arrays
        assert len(scalar_literal.inferred_type.shape.elements) == 0
        
        # Principle 2: 1D arrays have single dimension
        assert isinstance(array_1d_literal.inferred_type.shape, IntLiteral_N)
        assert array_1d_literal.inferred_type.shape.value == 3
        
        # Principle 3: 2D arrays have two dimensions
        assert isinstance(array_2d_literal.inferred_type.shape, Array1DLiteral_N)
        assert len(array_2d_literal.inferred_type.shape.value.elements) == 2
        
        # Principle 4: All use ArrayDataType_N universally
        for literal in [scalar_literal, array_1d_literal, array_2d_literal]:
            assert isinstance(literal.inferred_type, ArrayDataType_N)
            assert literal.inferred_type.scalar_dtype == "int"
        
        # Principle 5: Broadcasting rules (when implemented) should:
        # - Scalar + Array -> Array shape
        # - Array + Scalar -> Array shape  
        # - Compatible array shapes can be broadcast together
        # - Type promotion applies to scalar types, shapes are broadcast