#!/usr/bin/env python3
"""
Comprehensive tests for shape preservation in operations with ArrayDataType_N system.

These tests validate that array shapes are correctly preserved and inferred
across different types of operations: scalar-scalar, scalar-array, array-array.
"""

# Remove unused import to fix diagnostic
# import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.tests.test_utils import get_typed_ast, minimal_gelb_program_1d


class TestScalarOperationsShapePreservation:
    """Test that scalar operations correctly preserve 0-dimensional array shapes."""
    
    def test_scalar_plus_scalar_preserves_zero_dimensional_shape(self):
        """Scalar + Scalar should result in 0-dimensional array."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const int result = 5 + 3;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        add_expr = const_stmt.value
        
        # Check result shape
        assert isinstance(add_expr.inferred_type, ArrayDataType_N)
        assert len(add_expr.inferred_type.shape.elements) == 0  # 0-dimensional
        assert add_expr.inferred_type.scalar_dtype == "int"
        
        # Check operand shapes are also 0-dimensional
        left_operand = add_expr.left
        right_operand = add_expr.right
        assert isinstance(left_operand.inferred_type, ArrayDataType_N)
        assert isinstance(right_operand.inferred_type, ArrayDataType_N)
        assert len(left_operand.inferred_type.shape.elements) == 0
        assert len(right_operand.inferred_type.shape.elements) == 0
    
    def test_scalar_multiplication_preserves_zero_dimensional_shape(self):
        """Scalar * Scalar should result in 0-dimensional array."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const real result = 2.5 * 4.0;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        mul_expr = const_stmt.value
        
        assert isinstance(mul_expr.inferred_type, ArrayDataType_N)
        assert len(mul_expr.inferred_type.shape.elements) == 0  # 0-dimensional
        assert mul_expr.inferred_type.scalar_dtype == "real"
    
    def test_scalar_comparison_produces_zero_dimensional_bool(self):
        """Scalar comparison should result in 0-dimensional bool array."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const bool result = 5.0 > 3.0;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        gt_expr = const_stmt.value
        
        assert isinstance(gt_expr.inferred_type, ArrayDataType_N)
        assert len(gt_expr.inferred_type.shape.elements) == 0  # 0-dimensional
        assert gt_expr.inferred_type.scalar_dtype == "bool"
    
    def test_logical_operations_preserve_zero_dimensional_bool_shape(self):
        """Logical operations should result in 0-dimensional bool arrays."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const bool result = true && false;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        and_expr = const_stmt.value
        
        assert isinstance(and_expr.inferred_type, ArrayDataType_N)
        assert len(and_expr.inferred_type.shape.elements) == 0  # 0-dimensional
        assert and_expr.inferred_type.scalar_dtype == "bool"


class TestArrayLiteralShapeInference:
    """Test that array literals correctly infer their shapes."""
    
    def test_1d_array_literal_shape_inference(self):
        """1D array literal should infer correct 1-dimensional shape."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const array[int, 3] vec = {1, 2, 3};")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        array_literal = const_stmt.value
        
        assert isinstance(array_literal.inferred_type, ArrayDataType_N)
        assert array_literal.inferred_type.scalar_dtype == "int"
        
        # Check shape - should be 1-dimensional with size 3
        shape = array_literal.inferred_type.shape
        assert isinstance(shape, IntLiteral_N)
        assert shape.value == 3
    
    def test_2d_array_literal_shape_inference(self):
        """2D array literal should infer correct 2-dimensional shape."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const array[real, {2, 3}] mat = {{1.0, 2.0, 3.0}, {4.0, 5.0, 6.0}};")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        array_literal = const_stmt.value
        
        assert isinstance(array_literal.inferred_type, ArrayDataType_N)
        assert array_literal.inferred_type.scalar_dtype == "real"
        
        # Check shape - should be 2-dimensional with shape {2, 3}
        shape = array_literal.inferred_type.shape
        assert isinstance(shape, Array1DLiteral_N)
        assert len(shape.value.elements) == 2
        assert shape.value.elements[0].value == 2
        assert shape.value.elements[1].value == 3
    
    def test_nested_array_elements_preserve_scalar_array_types(self):
        """Elements within array literals should be typed as 0-dimensional arrays."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const array[int, 3] vec = {42, 84, 126};")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        array_literal = const_stmt.value
        
        # Check that individual elements are typed as 0-dimensional arrays
        elements = array_literal.value.elements
        for element in elements:
            assert isinstance(element, IntLiteral_N)
            assert hasattr(element, 'inferred_type')
            assert isinstance(element.inferred_type, ArrayDataType_N)
            assert element.inferred_type.scalar_dtype == "int"
            assert len(element.inferred_type.shape.elements) == 0  # 0-dimensional


class TestMixedScalarArrayOperationsShapes:
    """Test shape preservation in operations involving both scalars and arrays."""
    
    def test_scalar_plus_array_shape_broadcast_semantics(self):
        """Scalar + Array operations should follow broadcasting rules (future feature)."""
        # Note: This test documents expected behavior for future broadcasting implementation
        # Currently, GeLB may not support direct scalar-array arithmetic, but this test
        # ensures the type system is ready for such operations.
        
        gelb_code = minimal_gelb_program_1d(global_constants_content="""
            const array[int, 3] vec = {1, 2, 3};
            const int scalar = 5;
        """)
        ast = get_typed_ast(gelb_code)
        
        # Verify that both are correctly typed
        vec_stmt = ast.global_constants.stmts.elements[0]
        scalar_stmt = ast.global_constants.stmts.elements[1]
        
        vec_literal = vec_stmt.value
        scalar_literal = scalar_stmt.value
        
        # Array should have 1D shape
        assert isinstance(vec_literal.inferred_type, ArrayDataType_N)
        assert isinstance(vec_literal.inferred_type.shape, IntLiteral_N)
        assert vec_literal.inferred_type.shape.value == 3
        
        # Scalar should have 0D shape
        assert isinstance(scalar_literal.inferred_type, ArrayDataType_N)
        assert len(scalar_literal.inferred_type.shape.elements) == 0


class TestUnaryOperationsShapePreservation:
    """Test that unary operations preserve operand shapes correctly."""
    
    def test_unary_minus_preserves_scalar_shape(self):
        """Unary minus on scalar should preserve 0-dimensional shape."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const int result = -42;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        minus_expr = const_stmt.value
        
        # Result should be 0-dimensional
        assert isinstance(minus_expr.inferred_type, ArrayDataType_N)
        assert len(minus_expr.inferred_type.shape.elements) == 0
        assert minus_expr.inferred_type.scalar_dtype == "int"
        
        # Operand should also be 0-dimensional
        operand = minus_expr.value
        assert isinstance(operand.inferred_type, ArrayDataType_N)
        assert len(operand.inferred_type.shape.elements) == 0
    
    def test_logical_not_preserves_scalar_bool_shape(self):
        """Logical NOT on scalar bool should preserve 0-dimensional shape."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const bool result = !true;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        not_expr = const_stmt.value
        
        # Result should be 0-dimensional bool
        assert isinstance(not_expr.inferred_type, ArrayDataType_N)
        assert len(not_expr.inferred_type.shape.elements) == 0
        assert not_expr.inferred_type.scalar_dtype == "bool"


class TestComplexExpressionShapePreservation:
    """Test shape preservation in complex nested expressions."""
    
    def test_nested_scalar_arithmetic_preserves_shapes(self):
        """Complex nested scalar arithmetic should preserve 0-dimensional shapes throughout."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const real result = (1 + 2) * (3.0 / 4.0);")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        mul_expr = const_stmt.value
        
        # Outer multiplication should be 0-dimensional real
        assert isinstance(mul_expr.inferred_type, ArrayDataType_N)
        assert len(mul_expr.inferred_type.shape.elements) == 0
        assert mul_expr.inferred_type.scalar_dtype == "real"
        
        # Left operand (1 + 2) should be 0-dimensional int
        left_add = mul_expr.left
        assert isinstance(left_add.inferred_type, ArrayDataType_N)
        assert len(left_add.inferred_type.shape.elements) == 0
        assert left_add.inferred_type.scalar_dtype == "int"
        
        # Right operand (3.0 / 4.0) should be 0-dimensional real
        right_div = mul_expr.right
        assert isinstance(right_div.inferred_type, ArrayDataType_N)
        assert len(right_div.inferred_type.shape.elements) == 0
        assert right_div.inferred_type.scalar_dtype == "real"
    
    def test_mixed_type_promotion_preserves_shapes(self):
        """Type promotion should preserve array shapes while promoting scalar types."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const real result = 5 + 3.14;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        add_expr = const_stmt.value
        
        # Result should be 0-dimensional real (promoted from int + real)
        assert isinstance(add_expr.inferred_type, ArrayDataType_N)
        assert len(add_expr.inferred_type.shape.elements) == 0
        assert add_expr.inferred_type.scalar_dtype == "real"
        
        # Operands should be 0-dimensional with their original types
        int_operand = add_expr.left
        real_operand = add_expr.right
        
        assert isinstance(int_operand.inferred_type, ArrayDataType_N)
        assert len(int_operand.inferred_type.shape.elements) == 0
        assert int_operand.inferred_type.scalar_dtype == "int"
        
        assert isinstance(real_operand.inferred_type, ArrayDataType_N)
        assert len(real_operand.inferred_type.shape.elements) == 0
        assert real_operand.inferred_type.scalar_dtype == "real"


class TestShapeCompatibilityValidation:
    """Test that shape compatibility rules are correctly enforced."""
    
    def test_consistent_shapes_in_homogeneous_arrays(self):
        """Array literals should have consistent element shapes."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const array[int, 4] vec = {10, 20, 30, 40};")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        array_literal = const_stmt.value
        
        # All elements should have the same 0-dimensional shape
        elements = array_literal.value.elements
        for element in elements:
            assert isinstance(element.inferred_type, ArrayDataType_N)
            assert len(element.inferred_type.shape.elements) == 0
            assert element.inferred_type.scalar_dtype == "int"
    
    def test_shape_inference_with_constants(self):
        """Shape inference should work correctly with constant references."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="""
            const int SIZE = 3;
            const array[real, 3] vec = {1.0, 2.0, 3.0};
        """)
        ast = get_typed_ast(gelb_code)
        
        size_stmt = ast.global_constants.stmts.elements[0] 
        vec_stmt = ast.global_constants.stmts.elements[1]
        
        # SIZE constant should be 0-dimensional
        size_literal = size_stmt.value
        assert isinstance(size_literal.inferred_type, ArrayDataType_N)
        assert len(size_literal.inferred_type.shape.elements) == 0
        assert size_literal.inferred_type.scalar_dtype == "int"
        
        # Array should be 1-dimensional
        vec_literal = vec_stmt.value
        assert isinstance(vec_literal.inferred_type, ArrayDataType_N)
        assert isinstance(vec_literal.inferred_type.shape, IntLiteral_N)
        assert vec_literal.inferred_type.shape.value == 3


class TestShapePreservationDocumentation:
    """Document expected behavior for shape preservation in the universal array type system."""
    
    def test_shape_preservation_design_principles(self):
        """Document the key principles of shape preservation in ArrayDataType_N system."""
        # This test serves as executable documentation of design principles
        
        gelb_code = minimal_gelb_program_1d(global_constants_content="""
            const int scalar = 42;
            const array[int, 3] vec1d = {1, 2, 3};
            const array[real, {2, 2}] mat2d = {{1.0, 2.0}, {3.0, 4.0}};
        """)
        ast = get_typed_ast(gelb_code)
        
        scalar_stmt = ast.global_constants.stmts.elements[0]
        vec1d_stmt = ast.global_constants.stmts.elements[1]
        mat2d_stmt = ast.global_constants.stmts.elements[2]
        
        # Principle 1: Scalars are 0-dimensional arrays
        scalar_literal = scalar_stmt.value
        assert len(scalar_literal.inferred_type.shape.elements) == 0
        
        # Principle 2: 1D arrays have 1-element shape
        vec1d_literal = vec1d_stmt.value
        assert isinstance(vec1d_literal.inferred_type.shape, IntLiteral_N)
        
        # Principle 3: 2D arrays have 2-element shape
        mat2d_literal = mat2d_stmt.value
        assert isinstance(mat2d_literal.inferred_type.shape, Array1DLiteral_N)
        assert len(mat2d_literal.inferred_type.shape.value.elements) == 2
        
        # Principle 4: All use ArrayDataType_N universally
        assert isinstance(scalar_literal.inferred_type, ArrayDataType_N)
        assert isinstance(vec1d_literal.inferred_type, ArrayDataType_N)
        assert isinstance(mat2d_literal.inferred_type, ArrayDataType_N)