#!/usr/bin/env python3
"""
Unit tests for TypePromotionVisitor.

Tests implicit type promotions in various contexts.
"""

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.tests.test_utils import get_typed_ast, minimal_gelb_program_1d
from gelb.frontend.stage1_frontend import promote_types


class TestTypePromotionVisitor:
    """Test type promotion functionality."""
    
    def test_arithmetic_int_real_promotion(self):
        """Test int + real promotes int to real."""
        test_code = minimal_gelb_program_1d(
            initializer_content="real x; x = 1 + 2.5;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[1]  # x = 1 + 2.5
        add_expr = assign_stmt.rhs
        
        # Check that left operand (1) is wrapped in TypePromotionNode_N
        assert isinstance(add_expr.left, TypePromotionNode_N)
        assert isinstance(add_expr.left.expr, IntLiteral_N)
        assert add_expr.left.expr.value == 1
        assert add_expr.left.target_type.element_dtype == "real"
        
        # Right operand (2.5) should not be promoted
        assert isinstance(add_expr.right, RealLiteral_N)
        assert add_expr.right.value == 2.5
    
    def test_arithmetic_bool_int_promotion(self):
        """Test bool + int promotes bool to int."""
        test_code = minimal_gelb_program_1d(
            initializer_content="int x; x = true + 5;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[1]  # x = true + 5
        add_expr = assign_stmt.rhs
        
        # Check that left operand (true) is wrapped in TypePromotionNode_N
        assert isinstance(add_expr.left, TypePromotionNode_N)
        assert isinstance(add_expr.left.expr, BoolLiteral_N)
        assert add_expr.left.expr.value == "true"
        assert add_expr.left.target_type.element_dtype == "int"
    
    def test_arithmetic_bool_real_promotion(self):
        """Test bool * real promotes bool to real."""
        test_code = minimal_gelb_program_1d(
            initializer_content="real x; x = false * 3.14;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[1]  # x = false * 3.14
        mul_expr = assign_stmt.rhs
        
        # Check that left operand (false) is wrapped in TypePromotionNode_N
        assert isinstance(mul_expr.left, TypePromotionNode_N)
        assert isinstance(mul_expr.left.expr, BoolLiteral_N)
        assert mul_expr.left.expr.value == "false"
        assert mul_expr.left.target_type.element_dtype == "real"
    
    def test_comparison_promotion(self):
        """Test comparison with different types promotes to common type."""
        test_code = minimal_gelb_program_1d(
            initializer_content="bool b; b = 1 < 2.5;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[1]  # b = 1 < 2.5
        less_expr = assign_stmt.rhs
        
        # Check that left operand (1) is wrapped in TypePromotionNode_N
        assert isinstance(less_expr.left, TypePromotionNode_N)
        assert isinstance(less_expr.left.expr, IntLiteral_N)
        assert less_expr.left.expr.value == 1
        assert less_expr.left.target_type.element_dtype == "real"
    
    def test_assignment_promotion(self):
        """Test assignment promotes RHS to LHS type."""
        test_code = minimal_gelb_program_1d(
            initializer_content="real x; x = 42;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[1]  # x = 42
        
        # Check that RHS (42) is wrapped in TypePromotionNode_N
        assert isinstance(assign_stmt.rhs, TypePromotionNode_N)
        assert isinstance(assign_stmt.rhs.expr, IntLiteral_N)
        assert assign_stmt.rhs.expr.value == 42
        assert assign_stmt.rhs.target_type.element_dtype == "real"
    
    def test_constant_definition_promotion(self):
        """Test constant definition promotes value to declared type."""
        test_code = minimal_gelb_program_1d(
            global_constants_content="const real radius = 10;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the constant definition
        const_def = ast.global_constants.stmts.elements[0]
        
        # Check that value (10) is wrapped in TypePromotionNode_N
        assert isinstance(const_def.value, TypePromotionNode_N)
        assert isinstance(const_def.value.expr, IntLiteral_N)
        assert const_def.value.expr.value == 10
        assert const_def.value.target_type.element_dtype == "real"
    
    def test_no_promotion_same_types(self):
        """Test no promotion when types already match."""
        test_code = minimal_gelb_program_1d(
            initializer_content="int x; x = 1 + 2;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[1]  # x = 1 + 2
        add_expr = assign_stmt.rhs
        
        # Neither operand should be promoted
        assert isinstance(add_expr.left, IntLiteral_N)
        assert isinstance(add_expr.right, IntLiteral_N)
    
    def test_logical_operations_no_promotion(self):
        """Test logical operations don't promote operands."""
        test_code = minimal_gelb_program_1d(
            initializer_content="bool b1; bool b2; bool b3; b3 = b1 && b2;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[3]  # b3 = b1 && b2
        and_expr = assign_stmt.rhs
        
        # Neither operand should be promoted
        assert isinstance(and_expr.left, Identifier_N)
        assert isinstance(and_expr.right, Identifier_N)
    
    def test_nested_promotion(self):
        """Test promotion in nested expressions."""
        test_code = minimal_gelb_program_1d(
            initializer_content="real x; x = (1 + 2) * 3.14;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[1]
        mul_expr = assign_stmt.rhs
        
        # The (1 + 2) result should be promoted to real
        assert isinstance(mul_expr.left, TypePromotionNode_N)
        assert isinstance(mul_expr.left.expr, Add_N)
        assert mul_expr.left.target_type.element_dtype == "real"
    
    def test_array_element_assignment_promotion(self):
        """Test promotion in array element assignments."""
        test_code = minimal_gelb_program_1d(
            initializer_content="array[real, 3] data; data[0] = 1;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[1]  # data[0] = 1
        
        # RHS should be promoted to real
        assert isinstance(assign_stmt.rhs, TypePromotionNode_N)
        assert isinstance(assign_stmt.rhs.expr, IntLiteral_N)
        assert assign_stmt.rhs.expr.value == 1
        assert assign_stmt.rhs.target_type.element_dtype == "real"


class TestTypePromotionInExpressions:
    """Test type promotion in various expression contexts."""
    
    def test_complex_arithmetic_chain(self):
        """Test promotion in complex arithmetic expressions."""
        test_code = minimal_gelb_program_1d(
            initializer_content="real x; x = 1 + 2 * 3.0 - 4;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[1]
        
        # The entire expression should have promotions applied
        # Structure: (1 + (2 * 3.0)) - 4
        sub_expr = assign_stmt.rhs
        assert isinstance(sub_expr, Sub_N)
        
        # Left side of subtraction: 1 + (2 * 3.0)
        add_expr = sub_expr.left
        assert isinstance(add_expr, Add_N)
        
        # 1 should be promoted to real
        assert isinstance(add_expr.left, TypePromotionNode_N)
        assert add_expr.left.target_type.element_dtype == "real"
        
        # 2 * 3.0: 2 should be promoted to real
        mul_expr = add_expr.right
        assert isinstance(mul_expr.left, TypePromotionNode_N)
        assert mul_expr.left.target_type.element_dtype == "real"
        
        # 4 should be promoted to real
        assert isinstance(sub_expr.right, TypePromotionNode_N)
        assert sub_expr.right.target_type.element_dtype == "real"
    
    def test_mixed_bool_int_real(self):
        """Test promotion with mixed bool, int, and real."""
        test_code = minimal_gelb_program_1d(
            initializer_content="real x; x = true + 1 + 2.5;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[1]
        
        # Structure: (true + 1) + 2.5
        outer_add = assign_stmt.rhs
        assert isinstance(outer_add, Add_N)
        
        # (true + 1) should result in int, then promoted to real
        inner_add = outer_add.left
        assert isinstance(inner_add, TypePromotionNode_N)
        assert inner_add.target_type.element_dtype == "real"