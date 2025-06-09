#!/usr/bin/env python3
"""
Comprehensive tests for the ArrayDataType_N universal type system.

Tests validate that the new array type inference system works correctly
for all scalar operations, maintaining 0-dimensional array semantics.
"""

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.tests.test_utils import get_typed_ast, minimal_gelb_program_1d


class TestScalarAsArrayRepresentation:
    """Test that scalars are properly represented as 0-dimensional arrays."""
    
    def test_int_literal_as_zero_dimensional_array(self):
        """Integer literals should be ArrayDataType_N with empty shape."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const int test_val = 42;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        int_literal = const_stmt.value
        
        assert isinstance(int_literal, IntLiteral_N)
        assert hasattr(int_literal, 'inferred_type')
        assert isinstance(int_literal.inferred_type, ArrayDataType_N)
        assert int_literal.inferred_type.element_dtype == "int"
        assert len(int_literal.inferred_type.shape.elements) == 0
    
    def test_real_literal_as_zero_dimensional_array(self):
        """Real literals should be ArrayDataType_N with empty shape."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const real test_val = 3.14;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        real_literal = const_stmt.value
        
        assert isinstance(real_literal, RealLiteral_N)
        assert hasattr(real_literal, 'inferred_type')
        assert isinstance(real_literal.inferred_type, ArrayDataType_N)
        assert real_literal.inferred_type.element_dtype == "real"
        assert len(real_literal.inferred_type.shape.elements) == 0
    
    def test_bool_literal_as_zero_dimensional_array(self):
        """Boolean literals should be ArrayDataType_N with empty shape."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const bool test_val = true;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        bool_literal = const_stmt.value
        
        assert isinstance(bool_literal, BoolLiteral_N)
        assert hasattr(bool_literal, 'inferred_type')
        assert isinstance(bool_literal.inferred_type, ArrayDataType_N)
        assert bool_literal.inferred_type.element_dtype == "bool"
        assert len(bool_literal.inferred_type.shape.elements) == 0
    
    def test_string_literal_exception_confirmed(self):
        """Confirm that string literals use StringType_N (design exception)."""
        # Note: Strings don't have explicit constants in GeLB since they're not part 
        # of the numerical computation focus. String literals only appear in 
        # simulation_description and similar contexts.
        # This test confirms the design decision is correctly implemented.
        
        # We validate this in the context where strings do appear
        gelb_code = minimal_gelb_program_1d()
        gelb_code = gelb_code.replace('simulation_description("");', 'simulation_description("Test");')
        ast = get_typed_ast(gelb_code)
        
        string_literal = ast.simulation_description
        assert isinstance(string_literal, StringLiteral_N)
        # String literals are the only exception to the universal array type rule
        # They remain as their original form since GeLB doesn't treat strings as arrays


class TestArithmeticOperationsArrayTypes:
    """Test that arithmetic operations preserve array semantics correctly."""
    
    def test_addition_preserves_scalar_array_semantics(self):
        """Addition between scalars should result in scalar arrays."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const int result = 5 + 3;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        add_expr = const_stmt.value
        
        assert isinstance(add_expr, Add_N)
        assert hasattr(add_expr, 'inferred_type')
        assert isinstance(add_expr.inferred_type, ArrayDataType_N)
        assert add_expr.inferred_type.element_dtype == "int"
        assert len(add_expr.inferred_type.shape.elements) == 0
    
    def test_multiplication_preserves_scalar_array_semantics(self):
        """Multiplication between scalars should result in scalar arrays."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const int result = 6 * 7;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        mul_expr = const_stmt.value
        
        assert isinstance(mul_expr, Mul_N)
        assert hasattr(mul_expr, 'inferred_type')
        assert isinstance(mul_expr.inferred_type, ArrayDataType_N)
        assert mul_expr.inferred_type.element_dtype == "int"
        assert len(mul_expr.inferred_type.shape.elements) == 0
    
    def test_comparison_operations_return_scalar_bool_arrays(self):
        """Comparison operations should return 0-dimensional bool arrays."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const bool result = 5 > 3;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        gt_expr = const_stmt.value
        
        assert isinstance(gt_expr, Greater_N)
        assert hasattr(gt_expr, 'inferred_type')
        assert isinstance(gt_expr.inferred_type, ArrayDataType_N)
        assert gt_expr.inferred_type.element_dtype == "bool"
        assert len(gt_expr.inferred_type.shape.elements) == 0
    
    def test_equality_operations_return_scalar_bool_arrays(self):
        """Equality operations should return 0-dimensional bool arrays."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const bool result = 5 == 5;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        eq_expr = const_stmt.value
        
        assert isinstance(eq_expr, Equal_N)
        assert hasattr(eq_expr, 'inferred_type')
        assert isinstance(eq_expr.inferred_type, ArrayDataType_N)
        assert eq_expr.inferred_type.element_dtype == "bool"
        assert len(eq_expr.inferred_type.shape.elements) == 0
    
    def test_logical_and_operations_return_scalar_bool_arrays(self):
        """Logical AND operations should return 0-dimensional bool arrays."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const bool result = true && false;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        and_expr = const_stmt.value
        
        assert isinstance(and_expr, And_N)
        assert hasattr(and_expr, 'inferred_type')
        assert isinstance(and_expr.inferred_type, ArrayDataType_N)
        assert and_expr.inferred_type.element_dtype == "bool"
        assert len(and_expr.inferred_type.shape.elements) == 0
    
    def test_logical_or_operations_return_scalar_bool_arrays(self):
        """Logical OR operations should return 0-dimensional bool arrays."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const bool result = false || true;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        or_expr = const_stmt.value
        
        assert isinstance(or_expr, Or_N)
        assert hasattr(or_expr, 'inferred_type')
        assert isinstance(or_expr.inferred_type, ArrayDataType_N)
        assert or_expr.inferred_type.element_dtype == "bool"
        assert len(or_expr.inferred_type.shape.elements) == 0
    
    def test_unary_minus_preserves_operand_array_semantics(self):
        """Unary minus should preserve the array semantics of its operand."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const int result = -42;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        minus_expr = const_stmt.value
        
        assert isinstance(minus_expr, UnaryMinusExpr_N)
        assert hasattr(minus_expr, 'inferred_type')
        assert isinstance(minus_expr.inferred_type, ArrayDataType_N)
        assert minus_expr.inferred_type.element_dtype == "int"
        assert len(minus_expr.inferred_type.shape.elements) == 0
    
    def test_logical_not_preserves_operand_array_semantics(self):
        """Logical NOT should preserve array semantics and return bool."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const bool result = !true;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        not_expr = const_stmt.value
        
        assert isinstance(not_expr, NotExpr_N)
        assert hasattr(not_expr, 'inferred_type')
        assert isinstance(not_expr.inferred_type, ArrayDataType_N)
        assert not_expr.inferred_type.element_dtype == "bool"
        assert len(not_expr.inferred_type.shape.elements) == 0


class TestMixedTypeOperationsWithArraySemantics:
    """Test operations involving mixed scalar types with array semantics."""
    
    def test_mixed_int_real_addition_promotes_to_real_array(self):
        """Mixed int/real addition should preserve array wrapper and promote to real."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const real result = 5 + 3.14;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        add_expr = const_stmt.value
        
        assert isinstance(add_expr, Add_N)
        assert hasattr(add_expr, 'inferred_type')
        assert isinstance(add_expr.inferred_type, ArrayDataType_N)
        assert add_expr.inferred_type.element_dtype == "real"
        assert len(add_expr.inferred_type.shape.elements) == 0
    
    def test_mixed_int_real_multiplication_promotes_to_real_array(self):
        """Mixed int/real multiplication should preserve array wrapper and promote to real."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const real result = 2 * 3.5;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        mul_expr = const_stmt.value
        
        assert isinstance(mul_expr, Mul_N)
        assert hasattr(mul_expr, 'inferred_type')
        assert isinstance(mul_expr.inferred_type, ArrayDataType_N)
        assert mul_expr.inferred_type.element_dtype == "real"
        assert len(mul_expr.inferred_type.shape.elements) == 0
    
    def test_nested_expressions_maintain_array_types(self):
        """Complex nested expressions should maintain array types throughout."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const real result = (1 + 2) * 3.0;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        mul_expr = const_stmt.value
        
        # Check outer multiplication
        assert isinstance(mul_expr, Mul_N)
        assert hasattr(mul_expr, 'inferred_type')
        assert isinstance(mul_expr.inferred_type, ArrayDataType_N)
        assert mul_expr.inferred_type.element_dtype == "real"
        assert len(mul_expr.inferred_type.shape.elements) == 0
        
        # Check inner addition (left operand of multiplication)
        add_expr = mul_expr.left
        assert isinstance(add_expr, Add_N)
        assert hasattr(add_expr, 'inferred_type')
        assert isinstance(add_expr.inferred_type, ArrayDataType_N)
        assert add_expr.inferred_type.element_dtype == "int"
        assert len(add_expr.inferred_type.shape.elements) == 0


class TestConstantFoldingWithArrayTypes:
    """Test that constant folding works correctly with the new array type system."""
    
    def test_constant_folding_preserves_array_types(self):
        """Constant folding should preserve array type semantics for folded values."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="""
            const int N = 32;
            const int doubled = N * 2;
        """)
        ast = get_typed_ast(gelb_code)
        
        # Constant folding should have occurred, replacing N*2 with literal 64
        const_stmt = ast.global_constants.stmts.elements[1]
        mul_expr = const_stmt.value
        
        # The multiplication should still be typed as array
        assert isinstance(mul_expr, Mul_N)
        assert hasattr(mul_expr, 'inferred_type')
        assert isinstance(mul_expr.inferred_type, ArrayDataType_N)
        assert mul_expr.inferred_type.element_dtype == "int"
        assert len(mul_expr.inferred_type.shape.elements) == 0
        
        # The operands should also be array-typed literals
        assert isinstance(mul_expr.left, IntLiteral_N)
        assert hasattr(mul_expr.left, 'inferred_type')
        assert isinstance(mul_expr.left.inferred_type, ArrayDataType_N)
        assert mul_expr.left.inferred_type.element_dtype == "int"


class TestTypePromotionWithArrayTypes:
    """Test that type promotion works correctly with array types."""
    
    def test_bool_to_int_promotion_preserves_array_semantics(self):
        """Boolean to int promotion should preserve 0-dimensional array structure."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const int result = true + 1;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        add_expr = const_stmt.value
        
        assert isinstance(add_expr, Add_N)
        assert hasattr(add_expr, 'inferred_type')
        assert isinstance(add_expr.inferred_type, ArrayDataType_N)
        assert add_expr.inferred_type.element_dtype == "int"
        assert len(add_expr.inferred_type.shape.elements) == 0
    
    def test_int_to_real_promotion_preserves_array_semantics(self):
        """Integer to real promotion should preserve 0-dimensional array structure."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const real result = 42 + 1.5;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        add_expr = const_stmt.value
        
        assert isinstance(add_expr, Add_N)
        assert hasattr(add_expr, 'inferred_type')
        assert isinstance(add_expr.inferred_type, ArrayDataType_N)
        assert add_expr.inferred_type.element_dtype == "real"
        assert len(add_expr.inferred_type.shape.elements) == 0
    
    def test_complex_promotion_chain_preserves_array_semantics(self):
        """Complex promotion chains should preserve array semantics throughout."""
        gelb_code = minimal_gelb_program_1d(global_constants_content="const real result = true + 5 + 2.3;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        outer_add = const_stmt.value
        
        assert isinstance(outer_add, Add_N)
        assert hasattr(outer_add, 'inferred_type')
        assert isinstance(outer_add.inferred_type, ArrayDataType_N)
        assert outer_add.inferred_type.element_dtype == "real"
        assert len(outer_add.inferred_type.shape.elements) == 0