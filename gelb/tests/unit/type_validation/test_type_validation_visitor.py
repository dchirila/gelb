#!/usr/bin/env python3
"""
Unit tests for TypeValidationVisitor.

Tests type validation after promotion has been applied.
"""

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.tests.test_utils import get_typed_ast, minimal_gelb_program_1d
from gelb.frontend.stage1_frontend import promote_types, validate_types
from gelb.utils.exceptions import GeLBExTypeError


class TestTypeValidationSuccess:
    """Test cases where type validation should succeed."""
    
    def test_arithmetic_after_promotion(self):
        """Test arithmetic operations validate after promotion."""
        test_code = minimal_gelb_program_1d(
            initializer_content="real x; x = 1 + 2.5;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        # Should not raise
        ast = validate_types(ast)
    
    def test_comparison_after_promotion(self):
        """Test comparison operations validate after promotion."""
        test_code = minimal_gelb_program_1d(
            initializer_content="bool b; b = 1 < 2.5;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        # Should not raise
        ast = validate_types(ast)
    
    def test_assignment_after_promotion(self):
        """Test assignments validate after promotion."""
        test_code = minimal_gelb_program_1d(
            initializer_content="real x; x = 42;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        # Should not raise
        ast = validate_types(ast)
    
    def test_constant_definition_after_promotion(self):
        """Test constant definitions validate after promotion."""
        test_code = minimal_gelb_program_1d(
            global_constants_content="const real PI = 3;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        # Should not raise
        ast = validate_types(ast)
    
    def test_logical_operations_bool_only(self):
        """Test logical operations with bool operands validate."""
        test_code = minimal_gelb_program_1d(
            initializer_content="bool a; bool b; bool c; c = a && b;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        # Should not raise
        ast = validate_types(ast)
    
    def test_unary_minus_numeric(self):
        """Test unary minus with numeric operands validates."""
        test_code = minimal_gelb_program_1d(
            initializer_content="int x; x = -5; real y; y = -3.14;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        # Should not raise
        ast = validate_types(ast)
    
    def test_logical_not_bool(self):
        """Test logical NOT with bool operand validates."""
        test_code = minimal_gelb_program_1d(
            initializer_content="bool a; bool b; b = !a;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        # Should not raise
        ast = validate_types(ast)


class TestTypeValidationErrors:
    """Test cases where type validation should fail."""
    
    def test_logical_and_non_bool(self):
        """Test logical AND with non-bool operands fails."""
        test_code = minimal_gelb_program_1d(
            initializer_content="bool b; b = 1 && 2;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            validate_types(ast)
        
        assert "logical AND" in str(exc_info.value)
        assert "expected 'bool'" in str(exc_info.value)
    
    def test_logical_or_non_bool(self):
        """Test logical OR with non-bool operands fails."""
        test_code = minimal_gelb_program_1d(
            initializer_content="bool b; b = 3.14 || 2.71;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            validate_types(ast)
        
        assert "logical OR" in str(exc_info.value)
        assert "expected 'bool'" in str(exc_info.value)
    
    def test_logical_not_non_bool(self):
        """Test logical NOT with non-bool operand fails."""
        test_code = minimal_gelb_program_1d(
            initializer_content="bool b; b = !42;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            validate_types(ast)
        
        assert "logical NOT" in str(exc_info.value)
        assert "expected 'bool'" in str(exc_info.value)
    
    def test_assignment_incompatible_types(self):
        """Test assignment with incompatible types fails."""
        # Since string literals have syntax restrictions, test a simpler case
        # Array type to scalar - this should fail validation
        test_code = minimal_gelb_program_1d(
            global_constants_content="const int SIZE = 3;",
            initializer_content='array[int, SIZE] arr; int x; arr[0] = 5; x = arr;'
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            validate_types(ast)
        
        assert "Cannot assign" in str(exc_info.value)
    

    def test_unary_minus_non_numeric(self):
        """Test unary minus with non-numeric operand fails."""
        test_code = minimal_gelb_program_1d(
            initializer_content="int x; x = -true;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            validate_types(ast)
        
        assert "unary minus" in str(exc_info.value)
        assert "numeric operand" in str(exc_info.value)


class TestTypeValidationComplex:
    """Test type validation in complex scenarios."""
    
    def test_nested_expressions(self):
        """Test validation in nested expressions."""
        test_code = minimal_gelb_program_1d(
            initializer_content="real x; x = (1 + 2) * 3.14 / (4 - 2.5);"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        # Should not raise - all promotions applied correctly
        ast = validate_types(ast)
    
    def test_mixed_operations(self):
        """Test validation with mixed arithmetic and comparison."""
        test_code = minimal_gelb_program_1d(
            initializer_content="bool b; b = (1 + 2.5) > (3 * 2);"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        # Should not raise
        ast = validate_types(ast)
    
    def test_array_element_validation(self):
        """Test validation of array element assignments."""
        test_code = minimal_gelb_program_1d(
            initializer_content="array[real, 3] data; data[0] = 1; data[1] = 2.5;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        # Should not raise - int promoted to real
        ast = validate_types(ast)
    
    def test_constant_in_expression(self):
        """Test validation with constants in expressions."""
        test_code = minimal_gelb_program_1d(
            global_constants_content="const int SIZE = 10; const real FACTOR = 2.5;",
            initializer_content="real x; x = SIZE * FACTOR;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        # Should not raise - SIZE promoted to real
        ast = validate_types(ast)